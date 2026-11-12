"""Experiments 1-3 (PRD 5.2) + evaluation framework (PRD 5.3-5.5).

E1  RFM rule-based     quintile R/M scores, absolute F tiers, documented rule map
E2  RFM + K-Means      transform {original, log} x scaler {standard, robust} x K 2..10, multi-seed + bootstrap
E3  Behavioural        3 screened feature configurations x {K-Means, GMM, Ward hierarchical} x K 2..10, + DBSCAN

Every fitted configuration is one row in the experiment log (06_experimental_design/experiment_tracking.xlsx).
"""
from __future__ import annotations

import json
import time
import warnings
from dataclasses import dataclass, field

import joblib
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from sklearn.cluster import DBSCAN, KMeans
from sklearn.metrics import adjusted_rand_score, calinski_harabasz_score, davies_bouldin_score, silhouette_score
from sklearn.mixture import GaussianMixture
from sklearn.neighbors import NearestCentroid, NearestNeighbors
from sklearn.preprocessing import RobustScaler, StandardScaler

from custseg import config
from custseg import features as F

warnings.filterwarnings("ignore", category=FutureWarning)

RFM = ["recency_days", "frequency", "monetary"]
# common business space used to compare *different* approaches on equal terms (stage-2 comparison + profiling)
PROFILE_FEATURES = ["recency_days", "frequency", "monetary", "avg_items_per_order", "avg_installments",
                    "avg_review_score", "late_delivery_share", "freight_ratio"]
PROFILE_LOG = ["frequency", "monetary", "avg_items_per_order"]
SELECT_K = range(3, 9)    # K = 2 is not a segmentation a campaign team can act on; > 8 is not manageable
STAB_ROUNDS = 5

# composite weights (documented in 06_experimental_design/evaluation_framework.md)
WEIGHTS = {"silhouette": 0.15, "davies_bouldin": 0.10, "calinski_harabasz": 0.05, "stability": 0.25,
           "balance": 0.15, "interpretability": 0.30}


# ============================================================================================ data
@dataclass
class Space:
    """A preprocessed feature space: name, columns, transform, scaler, matrix."""
    name: str
    columns: list[str]
    log_cols: list[str]
    scaler_name: str
    X: np.ndarray = field(repr=False)
    scaler: object = field(repr=False)

    def describe(self) -> dict:
        return {"features": self.columns, "log1p": self.log_cols, "scaler": self.scaler_name}


def make_space(df: pd.DataFrame, name: str, cols: list[str], log_cols: list[str], scaler: str = "standard") -> Space:
    d = F.log_transform(df[cols], log_cols).astype(float)
    d = d.fillna(d.median())
    sc = StandardScaler() if scaler == "standard" else RobustScaler()
    return Space(name, cols, log_cols, scaler, sc.fit_transform(d.values), sc)


def transform(space: Space, df: pd.DataFrame) -> np.ndarray:
    d = F.log_transform(df[space.columns], space.log_cols).astype(float)
    d = d.fillna(d.median())
    return space.scaler.transform(d.values)


def profile_space(df: pd.DataFrame) -> Space:
    return make_space(df, "profile", PROFILE_FEATURES, PROFILE_LOG, "standard")


# ============================================================================================ metrics
def sample_idx(n: int, size: int, seed: int) -> np.ndarray:
    return np.sort(np.random.default_rng(seed).choice(n, min(size, n), replace=False))


def internal_metrics(X: np.ndarray, labels: np.ndarray, sil_idx: np.ndarray) -> dict:
    mask = labels != -1
    k = len(np.unique(labels[mask]))
    out = {"n_clusters": k, "noise_share": float(1 - mask.mean())}
    if k < 2:
        return {**out, "silhouette": np.nan, "davies_bouldin": np.nan, "calinski_harabasz": np.nan,
                "min_cluster_share": np.nan, "max_cluster_share": np.nan, "size_entropy": np.nan}
    si = sil_idx[mask[sil_idx]]
    sizes = pd.Series(labels[mask]).value_counts(normalize=True)
    return {**out,
            "silhouette": float(silhouette_score(X[si], labels[si])) if len(np.unique(labels[si])) > 1 else np.nan,
            "davies_bouldin": float(davies_bouldin_score(X[mask], labels[mask])),
            "calinski_harabasz": float(calinski_harabasz_score(X[mask], labels[mask])),
            "min_cluster_share": float(sizes.min()), "max_cluster_share": float(sizes.max()),
            "size_entropy": float(-(sizes * np.log(sizes)).sum() / np.log(k))}


def interpretability(P: np.ndarray, labels: np.ndarray, d_large: float = 0.8, d_sig: float = 0.5) -> dict:
    """Business-interpretability proxy in the common profile space (standardised, so differences = Cohen-d-like).

    distinct_share : clusters with >= 1 feature whose mean differs from the population by >= 0.8 SD
    unique_share   : clusters whose signature (sign of every >= 0.5 SD difference) is not shared with another cluster
    score          : mean of both - penalises clusters that cannot be told apart (over-segmentation)
    """
    ks = [k for k in np.unique(labels) if k != -1]
    sigs, distinct = [], 0
    for k in ks:
        d = P[labels == k].mean(axis=0)            # population mean is 0, SD 1
        distinct += bool((np.abs(d) >= d_large).any())
        sigs.append(tuple(np.sign(d) * (np.abs(d) >= d_sig)))
    uniq = sum(1 for s in sigs if sigs.count(s) == 1 and any(s))
    return {"distinct_share": distinct / len(ks), "unique_share": uniq / len(ks),
            "interpretability": (distinct / len(ks) + uniq / len(ks)) / 2}


# ============================================================================================ algorithms
def fit_kmeans(X, k, seed):
    m = KMeans(n_clusters=k, init="k-means++", n_init=10, random_state=seed).fit(X)
    return m, m.labels_


def fit_gmm(X, k, seed):
    m = GaussianMixture(n_components=k, covariance_type="full", n_init=1, max_iter=300, reg_covar=1e-4,
                        random_state=seed).fit(X)
    return m, m.predict(X)


def ward_tree(X, idx):
    return linkage(X[idx], method="ward")


def ward_labels(X, idx, tree, k):
    """Cut the Ward tree fitted on a sample, then assign every customer to the nearest sample-cluster centroid."""
    lab_s = fcluster(tree, k, criterion="maxclust") - 1
    nc = NearestCentroid().fit(X[idx], lab_s)
    return nc, nc.predict(X)


def relabel_by_size(labels: np.ndarray) -> np.ndarray:
    """Deterministic ids: 0 = largest cluster (noise stays -1)."""
    s = pd.Series(labels[labels != -1]).value_counts()
    mapping = {old: new for new, old in enumerate(s.index)}
    return np.array([mapping.get(x, -1) for x in labels])


# ============================================================================================ experiment log
class Tracker:
    def __init__(self, dataset_version: str):
        self.rows: list[dict] = []
        self.dataset_version = dataset_version

    def log(self, experiment: str, run_id: str, space: Space | None, algorithm: str, params: dict, metrics: dict,
            labels: np.ndarray | None = None, note: str = ""):
        dist = {}
        if labels is not None:
            dist = {int(k): int(v) for k, v in pd.Series(labels).value_counts().sort_index().items()}
        self.rows.append({"experiment_id": run_id, "experiment": experiment, "dataset_version": self.dataset_version,
                          "feature_configuration": space.name if space else "rfm_scores",
                          "features": ", ".join(space.columns) if space else "R, F, M scores",
                          "preprocessing": json.dumps({"log1p": space.log_cols, "scaler": space.scaler_name})
                          if space else "quintile scoring", "algorithm": algorithm,
                          "hyperparameters": json.dumps(params), **{k: (round(v, 5) if isinstance(v, float) else v)
                                                                    for k, v in metrics.items()},
                          "cluster_distribution": json.dumps(dist), "note": note,
                          "logged_at": time.strftime("%Y-%m-%d %H:%M:%S")})

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


# ============================================================================================ E1 - RFM rule based
RFM_RULES = [  # (segment, rule description, predicate on R, F, M scores) - first match wins
    ("Champions", "repeat buyer (F>=2), recent (R>=4), high spend (M>=4)", lambda r, f, m: (f >= 2) & (r >= 4) & (m >= 4)),
    ("Potential Loyalists", "repeat buyer (F>=2), recent (R>=4), lower spend", lambda r, f, m: (f >= 2) & (r >= 4)),
    ("Loyal Customers", "repeat buyer (F>=2), mid recency (R=3)", lambda r, f, m: (f >= 2) & (r == 3)),
    ("At Risk", "lapsing (R<=2) but previously valuable: repeat buyer or high spend (M>=4)",
     lambda r, f, m: (r <= 2) & ((f >= 2) | (m >= 4))),
    ("Big Spenders", "one purchase, not lapsed (R>=3), top-quintile spend (M=5)", lambda r, f, m: (f == 1) & (r >= 3) & (m == 5)),
    ("New Customers", "one purchase in the most recent quintile (R=5)", lambda r, f, m: (f == 1) & (r == 5)),
    ("Promising", "one purchase, recent (R=4)", lambda r, f, m: (f == 1) & (r == 4)),
    ("Need Attention", "one purchase, mid recency (R=3)", lambda r, f, m: (f == 1) & (r == 3)),
    ("Hibernating", "one purchase, low recency (R=2), low/mid spend", lambda r, f, m: (f == 1) & (r == 2)),
    ("Lost", "one purchase, oldest quintile (R=1), low/mid spend", lambda r, f, m: (f == 1) & (r == 1)),
]


def rfm_edges(df: pd.DataFrame) -> dict:
    q = [0.2, 0.4, 0.6, 0.8]
    return {"recency": df.recency_days.quantile(q).tolist(), "monetary": df.monetary.quantile(q).tolist()}


def rfm_scores(df: pd.DataFrame, edges: dict) -> pd.DataFrame:
    """R: quintiles (recent = 5). M: quintiles (high = 5). F: absolute tiers 1,2,3,4,5+ orders.

    F cannot be quantile-scored: 97% of customers have exactly one order, so every quintile edge equals 1.
    """
    r = 5 - np.searchsorted(edges["recency"], df.recency_days.values, side="left")
    m = 1 + np.searchsorted(edges["monetary"], df.monetary.values, side="left")
    f = np.clip(df.frequency.values, 1, 5)
    out = pd.DataFrame({"r_score": r, "f_score": f, "m_score": m}, index=df.index)
    out["rfm_cell"] = out.r_score.astype(str) + out.f_score.astype(str) + out.m_score.astype(str)
    out["rfm_score"] = out[["r_score", "f_score", "m_score"]].sum(axis=1)
    return out


def rfm_segment(scores: pd.DataFrame) -> pd.Series:
    r, f, m = scores.r_score.values, scores.f_score.values, scores.m_score.values
    seg = np.full(len(scores), None, dtype=object)
    for name, _, pred in RFM_RULES:
        hit = pred(r, f, m) & (seg == None)  # noqa: E711
        seg[hit] = name
    assert (seg != None).all(), "RFM rule map is not exhaustive"  # noqa: E711
    return pd.Series(seg, index=scores.index, name="rfm_segment")


def experiment_1(df: pd.DataFrame, tracker: Tracker, ref: Space, prof: Space, sil_idx) -> dict:
    edges = rfm_edges(df)
    scores = rfm_scores(df, edges)
    seg = rfm_segment(scores)
    codes = pd.Categorical(seg, categories=[r[0] for r in RFM_RULES]).codes
    # stability: re-derive quintile edges on bootstrap samples, re-score everyone
    aris = []
    for b in range(config.BOOTSTRAP_ROUNDS):
        idx = sample_idx(len(df), int(config.BOOTSTRAP_FRACTION * len(df)), 1000 + b)
        sb = rfm_segment(rfm_scores(df, rfm_edges(df.iloc[idx])))
        aris.append(adjusted_rand_score(seg.values, sb.values))
    met = internal_metrics(ref.X, codes, sil_idx)
    met.update(interpretability(prof.X, codes))
    met.update({"stability_bootstrap_ari": float(np.mean(aris)), "stability_seed_ari": 1.0})
    tracker.log("E1 RFM rule-based", "E1-rfm-rules", None, "rule-based (quintile scoring)",
                {"r_bins": "quintiles", "m_bins": "quintiles", "f_tiers": "1,2,3,4,5+", "n_rules": len(RFM_RULES),
                 "recency_edges_days": [round(x, 1) for x in edges["recency"]],
                 "monetary_edges_brl": [round(x, 2) for x in edges["monetary"]]}, met, codes,
                note="metrics evaluated in the E2 reference space (log RFM, standard scaled)")
    return {"scores": scores, "segment": seg, "codes": codes, "edges": edges, "metrics": met}


# ============================================================================================ E2 / E3 grids
def run_grid(df: pd.DataFrame, tracker: Tracker, experiment: str, space: Space, algorithm: str,
             prof: Space, sil_idx: np.ndarray, store: dict) -> pd.DataFrame:
    """Fit K = 2..10 for one (space, algorithm); stability (seed + bootstrap) only for K in SELECT_K."""
    X = space.X
    rows = []
    tree_ref = idx_ref = None
    if algorithm == "ward":
        idx_ref = sample_idx(len(X), config.HIER_SAMPLE, config.SEED)
        tree_ref = ward_tree(X, idx_ref)
        boot = []
        for b in range(STAB_ROUNDS):
            ib = sample_idx(len(X), config.HIER_SAMPLE, 2000 + b)
            boot.append((ib, ward_tree(X, ib)))
    for k in config.K_RANGE:
        t0 = time.time()
        if algorithm == "kmeans":
            model, lab = fit_kmeans(X, k, config.SEED)
            extra = {"inertia": float(model.inertia_)}
        elif algorithm == "gmm":
            model, lab = fit_gmm(X, k, config.SEED)
            extra = {"bic": float(model.bic(X)), "converged": bool(model.converged_)}
        else:
            model, lab = ward_labels(X, idx_ref, tree_ref, k)
            extra = {}
        lab = relabel_by_size(lab)
        met = internal_metrics(X, lab, sil_idx)
        met.update(extra)
        met.update(interpretability(prof.X, lab))
        if k in SELECT_K:
            seed_aris, boot_aris = [], []
            if algorithm in ("kmeans", "gmm"):
                fit = fit_kmeans if algorithm == "kmeans" else fit_gmm
                for s in config.SEEDS[:STAB_ROUNDS]:
                    if s == config.SEED:
                        continue
                    seed_aris.append(adjusted_rand_score(lab, fit(X, k, s)[1]))
                for b in range(STAB_ROUNDS):
                    ib = sample_idx(len(X), int(config.BOOTSTRAP_FRACTION * len(X)), 1000 + b)
                    mb = fit(X[ib], k, config.SEED)[0]
                    boot_aris.append(adjusted_rand_score(lab, mb.predict(X)))
            else:
                seed_aris = [1.0]  # Ward is deterministic given the sample; sample variation = bootstrap below
                for ib, tb in boot:
                    boot_aris.append(adjusted_rand_score(lab, ward_labels(X, ib, tb, k)[1]))
            met.update({"stability_seed_ari": float(np.mean(seed_aris)),
                        "stability_bootstrap_ari": float(np.mean(boot_aris))})
        met["fit_seconds"] = round(time.time() - t0, 2)
        run_id = f"{experiment.split()[0]}-{space.name}-{algorithm}-k{k}"
        params = {"k": k, "random_state": config.SEED}
        if algorithm == "kmeans":
            params.update({"init": "k-means++", "n_init": 10})
        elif algorithm == "gmm":
            params.update({"covariance_type": "full", "reg_covar": 1e-4})
        else:
            params.update({"linkage": "ward", "fit_sample": config.HIER_SAMPLE, "assignment": "nearest centroid"})
        tracker.log(experiment, run_id, space, algorithm, params, met, lab)
        store[run_id] = {"labels": lab, "model": model, "space": space, "algorithm": algorithm, "k": k,
                         "experiment": experiment}
        rows.append({"run_id": run_id, "experiment": experiment, "space": space.name, "algorithm": algorithm,
                     "k": k, **met})
        print(f"  [{run_id}] sil={met['silhouette']:.3f} db={met['davies_bouldin']:.2f} "
              f"interp={met['interpretability']:.2f} stab={met.get('stability_bootstrap_ari', np.nan):.3f} "
              f"min={met['min_cluster_share']:.3f} ({met['fit_seconds']}s)")
    return pd.DataFrame(rows)


def run_dbscan(df, tracker, space: Space, prof: Space, sil_idx) -> pd.DataFrame:
    """Exploratory: DBSCAN on 10k-customer samples, eps = 90th pct of the k-distance curve (k = 2 x dims)."""
    rows = []
    min_samples = 2 * space.X.shape[1]
    for s in range(3):
        idx = sample_idx(len(space.X), 10_000, 3000 + s)
        Xs = space.X[idx]
        dist = NearestNeighbors(n_neighbors=min_samples).fit(Xs).kneighbors(Xs)[0][:, -1]
        eps = float(np.quantile(dist, 0.90))
        lab = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(Xs)
        lab = relabel_by_size(lab)
        met = internal_metrics(Xs, lab, np.arange(len(Xs)))
        if met["n_clusters"] >= 1:
            met.update(interpretability(prof.X[idx], lab) if met["n_clusters"] >= 1 else {})
        run_id = f"E3-{space.name}-dbscan-sample{s}"
        tracker.log("E3 Behavioural clustering", run_id, space, "dbscan",
                    {"eps": round(eps, 4), "min_samples": min_samples, "sample": 10_000, "sample_seed": 3000 + s},
                    met, lab, note="exploratory; fitted on a sample")
        rows.append({"run_id": run_id, "space": space.name, "algorithm": "dbscan", "eps": eps, **met})
        print(f"  [{run_id}] clusters={met['n_clusters']} noise={met['noise_share']:.1%}")
    return pd.DataFrame(rows)


# ============================================================================================ selection
def minmax(s: pd.Series, higher_better=True) -> pd.Series:
    s = s.astype(float)
    if s.max() == s.min():
        return pd.Series(1.0, index=s.index)
    z = (s - s.min()) / (s.max() - s.min())
    return z if higher_better else 1 - z


def composite(df: pd.DataFrame) -> pd.Series:
    parts = {
        "silhouette": minmax(df.silhouette),
        "davies_bouldin": minmax(df.davies_bouldin, higher_better=False),
        "calinski_harabasz": minmax(np.log(df.calinski_harabasz)),
        "stability": minmax(df.stability_bootstrap_ari),
        "balance": minmax(df.size_entropy),
        "interpretability": minmax(df.interpretability),
    }
    return sum(WEIGHTS[k] * v for k, v in parts.items())


def small_cluster_review(df: pd.DataFrame, labels: np.ndarray) -> dict:
    """PRD 5.4: a cluster < 1% of customers is a niche high-value group, an anomaly, or over-segmentation."""
    out = {}
    shares = pd.Series(labels).value_counts(normalize=True)
    overall = df.monetary.median()
    for k, sh in shares.items():
        if k == -1 or sh >= config.MIN_CLUSTER_SHARE:
            continue
        mm = df.monetary.values[labels == k]
        med = float(np.median(mm))
        verdict = ("niche high-value" if med >= 3 * overall else "over-segmentation / anomaly")
        out[int(k)] = {"share": float(sh), "median_monetary": med, "verdict": verdict}
    return out


def select_within_family(grid: pd.DataFrame, df: pd.DataFrame, store: dict) -> pd.DataFrame:
    """Stage 1: best K per (space, algorithm) among K in SELECT_K, composite normalised within the family."""
    picks = []
    for (space, algo), g in grid[grid.k.isin(SELECT_K)].groupby(["space", "algorithm"]):
        g = g.copy()
        g["composite"] = composite(g)
        g["small_cluster_issue"] = [
            any(v["verdict"] != "niche high-value" for v in small_cluster_review(df, store[r]["labels"]).values())
            for r in g.run_id]
        ok = g[~g.small_cluster_issue]
        best = (ok if len(ok) else g).sort_values("composite", ascending=False).iloc[0]
        picks.append(best)
    return pd.DataFrame(picks).reset_index(drop=True)


def cross_space_metrics(labels: np.ndarray, spaces: dict, sil_idx: np.ndarray) -> dict:
    """Separation of one labelling measured in *every* candidate feature space, then averaged.

    Internal metrics are only comparable inside one feature space. Scoring all finalists in one model's space hands
    that model a home advantage (first design of this stage used the E2 log-RFM space -> E2 won; scoring in the
    8-feature profile space instead -> the E3 model with exactly those features won). Averaging over all 7 candidate
    spaces gives each finalist its own space once and dilutes the bias equally.
    """
    ms = {name: internal_metrics(sp.X, labels, sil_idx) for name, sp in spaces.items()}
    out = {f"silhouette@{n}": m["silhouette"] for n, m in ms.items()}
    for key in ("silhouette", "davies_bouldin", "calinski_harabasz"):
        out[key] = float(np.mean([m[key] for m in ms.values()]))
    return out


def compare_finalists(stage1: pd.DataFrame, e1: dict, store: dict, spaces: dict, sil_idx) -> pd.DataFrame:
    """Stage 2: the best model of every family + E1, re-scored on equal terms; composite normalised across them."""
    rows = []
    for r in stage1.itertuples():
        rows.append({"run_id": r.run_id, "experiment": r.experiment, "space": r.space, "algorithm": r.algorithm,
                     "k": r.k, "own_silhouette": r.silhouette,
                     **cross_space_metrics(np.asarray(store[r.run_id]["labels"], int), spaces, sil_idx),
                     "stability_bootstrap_ari": r.stability_bootstrap_ari, "stability_seed_ari": r.stability_seed_ari,
                     "size_entropy": r.size_entropy, "min_cluster_share": r.min_cluster_share,
                     "interpretability": r.interpretability})
    e1m = e1["metrics"]
    rows.append({"run_id": "E1-rfm-rules", "experiment": "E1 RFM rule-based", "space": "rfm_scores",
                 "algorithm": "rule-based", "k": len(RFM_RULES), "own_silhouette": np.nan,
                 **cross_space_metrics(np.asarray(e1["codes"], int), spaces, sil_idx),
                 "stability_bootstrap_ari": e1m["stability_bootstrap_ari"], "stability_seed_ari": 1.0,
                 "size_entropy": e1m["size_entropy"], "min_cluster_share": e1m["min_cluster_share"],
                 "interpretability": e1m["interpretability"]})
    f = pd.DataFrame(rows)
    f["composite"] = composite(f)
    f["rank"] = f.composite.rank(ascending=False, method="first").astype(int)
    return f.sort_values("composite", ascending=False).reset_index(drop=True)


def select(res: dict, df: pd.DataFrame) -> dict:
    res["stage1"] = select_within_family(res["grid"], df, res["store"])
    res["stage2"] = compare_finalists(res["stage1"], res["e1"], res["store"], res["spaces"], res["sil_idx"])
    res["winner"] = res["stage2"].iloc[0].run_id
    print(f"[select] winner = {res['winner']}")
    return res


# ============================================================================================ driver
def run_all(dataset_version: str) -> dict:
    df = F.customer_mart()
    tracker = Tracker(dataset_version)
    sil_idx = sample_idx(len(df), config.SILHOUETTE_SAMPLE, config.SEED)
    prof = profile_space(df)
    store: dict = {}

    # ---- E2 spaces (also give the reference space for E1 / stage 2)
    e2_spaces = [make_space(df, f"rfm-{t}-{s}", RFM, RFM if t == "log" else [], s)
                 for t in ("original", "log") for s in ("standard", "robust")]
    ref = next(s for s in e2_spaces if s.name == "rfm-log-standard")

    print("[E1] RFM rule-based")
    e1 = experiment_1(df, tracker, ref, prof, sil_idx)

    print("[E2] RFM + K-Means")
    e2 = pd.concat([run_grid(df, tracker, "E2 RFM + K-Means", s, "kmeans", prof, sil_idx, store) for s in e2_spaces])

    # ---- E3 feature configurations from the screened pool
    pool, screen_log = F.screen_features(df)
    b1 = ["recency_days", "frequency", "monetary", "avg_items_per_order", "avg_installments"]
    b2 = b1 + ["avg_review_score", "late_delivery_share", "freight_ratio"]
    b3 = pool
    for cfg in (b1, b2):
        assert set(cfg) <= set(pool), f"configuration uses a screened-out feature: {set(cfg) - set(pool)}"
    e3_spaces = [make_space(df, name, cols, F.skewed(df, cols), "standard")
                 for name, cols in (("beh-value-lifecycle", b1), ("beh-value-experience", b2), ("beh-full-pool", b3))]
    print("[E3] Behavioural clustering")
    e3 = pd.concat([run_grid(df, tracker, "E3 Behavioural clustering", s, a, prof, sil_idx, store)
                    for s in e3_spaces for a in ("kmeans", "gmm", "ward")])
    dbs = pd.concat([run_dbscan(df, tracker, s, prof, sil_idx) for s in e3_spaces])

    # ---- selection
    grid = pd.concat([e2, e3], ignore_index=True)
    res = {"df": df, "tracker": tracker, "e1": e1, "e2": e2, "e3": e3, "dbscan": dbs, "grid": grid,
           "screen_log": screen_log, "store": store, "spaces": {s.name: s for s in e2_spaces + e3_spaces},
           "ref": ref, "prof": prof, "sil_idx": sil_idx}
    return select(res, df)


def save_artifacts(res: dict) -> None:
    config.ensure_dirs()
    out = config.SEG_RESULTS
    res["tracker"].frame().to_csv(out / "experiment_log.csv", index=False)
    res["grid"].to_csv(out / "grid_results.csv", index=False)
    res["dbscan"].to_csv(out / "dbscan_results.csv", index=False)
    res["screen_log"].to_csv(out / "feature_screening.csv", index=False)
    res["stage1"].to_csv(out / "stage1_best_k_per_family.csv", index=False)
    res["stage2"].to_csv(out / "stage2_model_comparison.csv", index=False)
    with pd.ExcelWriter(config.EXP_DIR / "experiment_tracking.xlsx") as xw:
        res["tracker"].frame().to_excel(xw, sheet_name="runs", index=False)
        res["stage1"].to_excel(xw, sheet_name="stage1_best_k", index=False)
        res["stage2"].to_excel(xw, sheet_name="stage2_comparison", index=False)
        res["screen_log"].to_excel(xw, sheet_name="feature_screening", index=False)
        pd.DataFrame([{"criterion": k, "weight": v} for k, v in WEIGHTS.items()]).to_excel(
            xw, sheet_name="composite_weights", index=False)
    for rid in res["stage2"].run_id:
        if rid in res["store"]:
            s = res["store"][rid]
            joblib.dump({"model": s["model"], "scaler": s["space"].scaler, "space": s["space"].describe(),
                         "algorithm": s["algorithm"], "k": s["k"]}, config.MODELS_DIR / f"{rid}.joblib")


RESULTS_PKL = config.ARTIFACTS / "segmentation_results.joblib"


def load_results() -> dict:
    import __main__
    for cls in ("Tracker", "Space"):          # results pickled by an older `python -m` entry point
        if not hasattr(__main__, cls):
            setattr(__main__, cls, globals()[cls])
    return joblib.load(RESULTS_PKL)


def _persist(res: dict) -> None:
    save_artifacts(res)
    for s in res["store"].values():
        s["labels"] = np.asarray(s["labels"]).astype(np.int8)
    joblib.dump({k: v for k, v in res.items() if k != "df"}, RESULTS_PKL, compress=3)


def main(argv=None) -> None:
    import sys
    argv = sys.argv[1:] if argv is None else argv
    t0 = time.time()
    if "--reselect" in argv:          # recompute stage 1/2 selection from the saved grid (no refitting)
        res = select(load_results(), F.customer_mart())
    else:
        manifest = json.loads((config.ROOT / "02_data" / "dataset_manifest.json").read_text())
        res = run_all(manifest["dataset_version"])
    _persist(res)
    print(f"[segmentation] done in {time.time() - t0:.0f}s -> {RESULTS_PKL}")


if __name__ == "__main__":
    # import through the package so pickled classes resolve to custseg.segmentation (not __main__)
    from custseg.segmentation import main as _main
    _main()
