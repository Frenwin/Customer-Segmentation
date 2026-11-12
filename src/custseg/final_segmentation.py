"""Final segmentation (PRD 5.4, 7): take the selected model, give every cluster a business identity, profile it,
measure segment growth / migration, and publish mart.customer_segmentation + mart.segment_profile.

Naming is rule-based on the cluster profile (not hand-labelled), so a re-run on new data re-derives the names.
"""
from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd

from custseg import config, db, viz
from custseg import features as F
from custseg import segmentation as S

OUT = config.SEG_RESULTS
SNAPSHOT_PREV = "2018-03-01"   # earlier snapshot for segment growth & migration (6 months before analysis date)

# Business strategy library (PRD 7 table, refined with what the Olist data shows). Keys = segment names.
STRATEGY = {
    "Champions": ("Repeat buyers who bought recently and spend the most.",
                  "VIP programme: early access, free-shipping threshold waiver, personal recommendations; protect with "
                  "delivery SLA priority (late delivery is the strongest dissatisfaction driver)."),
    "Loyal Customers": ("Customers with two or more delivered orders - the only group with proven repeat behaviour.",
                        "Membership / loyalty points on the 2nd-to-3rd order, category cross-sell based on their "
                        "history, review-request after on-time delivery."),
    "Potential Loyalists": ("Recent repeat buyers with moderate spend.",
                            "Nurture to Champions: bundle offers in their top category, installment-friendly upsell."),
    "At Risk Repeaters": ("Customers who bought more than once but have been inactive for a long time.",
                          "Win-back campaign with personalised incentive; measure reactivation against a hold-out "
                          "control group before scaling."),
    "Big Spenders": ("One high-value purchase, usually paid in many installments.",
                     "Premium / high-ticket upsell with interest-free installments, white-glove delivery, "
                     "post-purchase satisfaction check."),
    "High-Value Lapsing": ("One high-value purchase a long time ago; previously valuable, now inactive.",
                           "Targeted reactivation offers in the original category; cap incentive cost against the "
                           "expected 12-month value (BG/NBD x Gamma-Gamma)."),
    "New Customers": ("Recently acquired (last ~3 months), one purchase, typical basket.",
                      "Onboarding journey and second-purchase incentive inside the 0-90 day window where most "
                      "second purchases happen; ensure the first delivery is on time."),
    "Promising": ("Recent one-time buyers with moderate spend.",
                  "Cross-sell complementary categories and nurture e-mails; second-purchase coupon."),
    "Need Attention": ("One purchase, mid recency - drifting towards inactivity.",
                       "Re-engagement reminder with relevant recommendations before the inactivity threshold."),
    "Big-Ticket Installment Buyers": ("One high-value purchase financed in many installments (credit card).",
                                      "Upsell premium items with interest-free installment offers; partner with card "
                                      "issuers; white-glove delivery and proactive tracking for high-ticket orders."),
    "Multi-Item Basket Buyers": ("Bought several items in one order - more split shipments and a lower review score.",
                                 "Consolidate shipments / single-delivery promise, bundle pricing, and a post-delivery "
                                 "check because partial deliveries drive their lower satisfaction."),
    "Low-Ticket Freight-Sensitive": ("Small orders where freight is a large share of the price paid.",
                                     "Free-shipping threshold just above their typical basket to lift AOV; "
                                     "add-on recommendations; regional fulfilment to cut freight."),
    "Core One-Time Buyers": ("Mid-value single purchase, delivered on time, satisfied - the bulk of the base.",
                             "Second-purchase programme: personalised recommendations from the first category, "
                             "time-boxed coupon inside the 0-90 day window where most repeat purchases happen."),
    "Unhappy Customers": ("Customers whose order experience was poor (late delivery / low review).",
                          "Service recovery first (apology + voucher, carrier escalation), then re-engagement; "
                          "do not include in promotional blasts until resolved."),
    "At Risk": ("High-spend one-time buyers whose typical last purchase is at or past the inactivity threshold - "
                "previously valuable, now slipping away.",
                "Targeted win-back in the original category with a personalised incentive capped by expected value; "
                "prioritise the high-value-at-risk list (top-20 % spenders still inside the threshold); "
                "measure reactivation against a hold-out group."),
    "Hibernating": ("One low-value purchase; the typical member is at or past the inactivity threshold.",
                    "Low-cost reactivation (newsletter, seasonal campaigns such as Black Friday)."),
    "Lost Customers": ("One purchase, past the inactivity threshold, low engagement.",
                       "Low-cost win-back only (automated e-mail); exclude from paid retargeting."),
}


# ============================================================================================ labels
def load_results() -> dict:
    return S.load_results()


def final_labels(res: dict, df: pd.DataFrame) -> np.ndarray:
    if res["winner"] == "E1-rfm-rules":
        seg = S.rfm_segment(S.rfm_scores(df, res["e1"]["edges"]))
        return pd.Categorical(seg, categories=[r[0] for r in S.RFM_RULES]).codes.astype(int)
    return res["store"][res["winner"]]["labels"].astype(int)


def predict(res: dict, run_id: str, feats: pd.DataFrame) -> np.ndarray:
    """Apply a fitted model to customer features computed at another snapshot."""
    if run_id == "E1-rfm-rules":
        seg = S.rfm_segment(S.rfm_scores(feats, res["e1"]["edges"]))
        return pd.Categorical(seg, categories=[r[0] for r in S.RFM_RULES]).codes.astype(int)
    s = res["store"][run_id]
    X = S.transform(s["space"], feats)
    lab = s["model"].predict(X)
    if s["algorithm"] in ("kmeans", "gmm", "ward"):
        # map raw model ids to the size-ordered ids used in the analysis
        raw_full = s["model"].predict(s["space"].X)
        mapping = pd.crosstab(raw_full, s["labels"]).idxmax(axis=1).to_dict()
        lab = np.array([mapping[x] for x in lab])
    return lab


# ============================================================================================ profile & naming
def profile(df: pd.DataFrame, labels: np.ndarray, threshold: int, clv: pd.DataFrame | None) -> pd.DataFrame:
    d = df.copy()
    d["cluster"] = labels
    d["is_churned"] = d.recency_days > threshold
    if clv is not None:
        d = d.join(clv.set_index("customer_key")[["predicted_clv_12m", "p_alive", "expected_purchases_12m"]])
    total_rev = d.monetary.sum()
    g = d.groupby("cluster")
    p = pd.DataFrame({
        "customers": g.size(), "avg_recency_days": g.recency_days.mean(), "median_recency_days": g.recency_days.median(),
        "avg_frequency": g.frequency.mean(), "avg_monetary": g.monetary.mean(), "median_monetary": g.monetary.median(),
        "revenue": g.monetary.sum(), "orders": g.frequency.sum(),
        "repeat_rate": g.is_repeat_customer.mean(), "churn_rate": g.is_churned.mean(),
        "avg_items_per_order": g.avg_items_per_order.mean(), "avg_installments": g.avg_installments.mean(),
        "avg_review_score": g.avg_review_score.mean(), "late_delivery_share": g.late_delivery_share.mean(),
        "avg_delivery_days": g.avg_delivery_days.mean(), "freight_ratio": g.freight_ratio.mean(),
        "credit_card_share": g.credit_card_order_share.mean(), "voucher_share": g.voucher_order_share.mean(),
        "cross_category_share": g.is_cross_category.mean(),
        "top_category_group": g.top_category_group.agg(lambda s: s.value_counts().index[0]),
        "top_category_group_share": g.top_category_group.agg(lambda s: s.value_counts(normalize=True).iloc[0]),
        "top_state": g.state.agg(lambda s: s.value_counts().index[0]),
        "sudeste_share": g.region.agg(lambda s: (s == "Sudeste").mean()),
    })
    p["customer_share"] = p.customers / p.customers.sum()
    p["revenue_contribution"] = p.revenue / total_rev
    p["avg_order_value"] = p.revenue / p.orders
    p["avg_historical_clv"] = p.avg_monetary
    if clv is not None:
        p["avg_predicted_clv_12m"] = g.predicted_clv_12m.mean()
        p["avg_p_alive"] = g.p_alive.mean()
        p["expected_purchases_12m"] = g.expected_purchases_12m.sum()
    p["retention_rate"] = p.repeat_rate      # segment retention = share of customers who came back (2+ orders)
    return p


def name_clusters(p: pd.DataFrame, df: pd.DataFrame, threshold: int, z: pd.DataFrame) -> dict[int, str]:
    """Rule-based naming from each cluster's signature.

    p : business profile per cluster (repeat rate, recency, median spend, ...)
    z : mean standardised value per cluster in the common profile space (0 = customer average, units = SD)
    Rules are applied in priority order: loyalty -> experience -> distinctive behaviour (>= 0.8 SD) ->
    lifecycle (average recency vs the inactivity threshold T) -> value.
    """
    med_m = df.monetary.median()
    med_r = df.recency_days.median()
    names = {}
    for k, r in p.iterrows():
        zz = z.loc[k]
        rel_m = r.median_monetary / med_m
        if r.repeat_rate >= 0.5:
            if r.avg_recency_days > threshold * 0.95:
                n = "At Risk Repeaters"
            elif rel_m >= 1.5 and r.avg_recency_days <= med_r * 0.75:
                n = "Champions"
            else:
                n = "Loyal Customers"
        elif r.late_delivery_share >= 0.4 or r.avg_review_score <= 3.0:
            n = "Unhappy Customers"
        elif zz.avg_installments >= 0.8 and rel_m >= 1.4:
            n = "Big-Ticket Installment Buyers"
        elif zz.avg_items_per_order >= 0.8:
            n = "Multi-Item Basket Buyers"
        elif zz.freight_ratio >= 0.8 and rel_m < 0.7:
            n = "Low-Ticket Freight-Sensitive"
        elif r.avg_recency_days > threshold * 1.3:
            n = "Lost Customers"
        elif r.avg_recency_days > threshold * 0.9:      # typical member is at / past the inactivity threshold
            n = "At Risk" if rel_m >= 1.5 else ("Hibernating" if rel_m < 1.0 else "Need Attention")
        elif zz.recency_days <= -0.8:
            n = "New Customers" if rel_m < 1.2 else "Promising"
        elif rel_m >= 2.0:
            n = "Big Spenders"
        else:
            n = "Core One-Time Buyers"
        names[k] = n
    seen: dict[str, list[int]] = {}
    for k, n in names.items():
        seen.setdefault(n, []).append(k)
    for n, ks in seen.items():
        if len(ks) > 1:   # duplicates get a qualifier from the dimension that separates them most
            for k in ks:
                r = p.loc[k]
                q = "higher spend" if r.median_monetary >= p.loc[ks].median_monetary.max() else                     ("more recent" if r.avg_recency_days <= p.loc[ks].avg_recency_days.min() else "lower spend")
                names[k] = f"{n} ({q})"
    return names


def segment_colors(order: list[str]) -> dict[str, str]:
    """Colour follows the segment name (viz.SEGMENT_PALETTE); unknown names take unused validated slots, then the
    general categorical order."""
    used = {viz.SEGMENT_PALETTE[n] for n in order if n in viz.SEGMENT_PALETTE}
    spare = [c for c in viz.SEGMENT_FALLBACK if c not in used] + viz.CATEGORICAL
    out = {}
    for n in order:
        out[n] = viz.SEGMENT_PALETTE.get(n) or spare.pop(0)
    return out


# ============================================================================================ growth / migration
def migration(res: dict, df: pd.DataFrame, labels_now: np.ndarray, names: dict[int, str]) -> dict:
    prev_feats = F.build_features(SNAPSHOT_PREV)
    prev_lab = predict(res, res["winner"], prev_feats)
    prev = pd.Series(prev_lab, index=prev_feats.index).map(names)
    now = pd.Series(labels_now, index=df.index).map(names)
    counts = pd.DataFrame({"customers_prev": prev.value_counts(), "customers_now": now.value_counts()}).fillna(0)
    counts["growth_rate"] = counts.customers_now / counts.customers_prev.replace(0, np.nan) - 1
    both = prev.index.intersection(now.index)
    trans = pd.crosstab(prev.loc[both], now.loc[both], normalize="index")
    trans_n = pd.crosstab(prev.loc[both], now.loc[both])
    return {"counts": counts, "transition_share": trans, "transition_n": trans_n, "snapshot_prev": SNAPSHOT_PREV}


# ============================================================================================ run
def run(threshold: int, clv: pd.DataFrame) -> dict:
    res = load_results()
    df = F.customer_mart()
    labels = final_labels(res, df)
    prof = profile(df, labels, threshold, clv)
    P = S.profile_space(df).X
    z = pd.DataFrame(P, columns=S.PROFILE_FEATURES, index=df.index).groupby(labels).mean()
    names = name_clusters(prof, df, threshold, z)
    prof.insert(0, "segment_name", prof.index.map(names))
    prof = prof.sort_values("revenue", ascending=False)
    order = list(prof.segment_name)
    prof.insert(0, "segment_id", [f"S{i + 1}" for i in range(len(prof))])
    prof["segment_description"] = prof.segment_name.map(lambda n: STRATEGY[n.split(" (")[0]][0])
    prof["recommended_strategy"] = prof.segment_name.map(lambda n: STRATEGY[n.split(" (")[0]][1])
    colors = segment_colors(order)
    prof["color"] = prof.segment_name.map(colors)
    mig = migration(res, df, labels, names)
    prof["customers_prev_snapshot"] = prof.segment_name.map(mig["counts"].customers_prev).fillna(0).astype(int)
    prof["segment_growth_rate"] = prof.segment_name.map(mig["counts"].growth_rate)

    # ---- customer-level table: final segment + the alternative labellings (for comparison in BI)
    e1 = res["e1"]
    e2_best = res["stage2"][res["stage2"].experiment.str.startswith("E2")]
    e3_best = res["stage2"][res["stage2"].experiment.str.startswith("E3")]
    cust = pd.DataFrame(index=df.index)
    cust["segment_name"] = pd.Series(labels, index=df.index).map(names)
    cust["segment_id"] = cust.segment_name.map(dict(zip(prof.segment_name, prof.segment_id)))
    cust = cust.join(e1["scores"]).join(e1["segment"])
    if len(e2_best):
        cust["e2_cluster"] = res["store"][e2_best.iloc[0].run_id]["labels"].astype(int)
    if len(e3_best):
        cust["e3_cluster"] = res["store"][e3_best.iloc[0].run_id]["labels"].astype(int)
    cust["churn_status"] = np.where(df.recency_days > threshold, "Churned (inactive)", "Active")
    cust = cust.join(clv.set_index("customer_key")[["historical_clv", "predicted_clv_12m", "p_alive", "clv_tier"]])
    cust = cust.reset_index()

    # ---- publish
    OUT.mkdir(parents=True, exist_ok=True)
    cust.to_csv(config.PROCESSED_DIR / "customer_segmentation.csv", index=False)
    prof.reset_index(names="cluster").to_csv(OUT / "segment_profile.csv", index=False)
    mig["transition_share"].to_csv(OUT / "segment_migration_share.csv")
    mig["transition_n"].to_csv(OUT / "segment_migration_counts.csv")
    db.load_df(cust.assign(clv_tier=cust.clv_tier.astype(str)), "customer_segmentation", "mart", primary_key="customer_key")
    db.load_df(prof.reset_index(names="cluster"), "segment_profile", "mart")
    tm = mig["transition_n"].stack().rename("customers").reset_index()
    tm.columns = ["segment_prev", "segment_now", "customers"]
    db.load_df(tm, "segment_migration", "mart")
    (OUT / "final_model.json").write_text(json.dumps({
        "winner": res["winner"], "segments": dict(zip(prof.segment_id, prof.segment_name)),
        "colors": colors, "churn_threshold_days": threshold, "snapshot_prev": SNAPSHOT_PREV,
        "analysis_date": config.ANALYSIS_DATE}, indent=2), encoding="utf-8")
    if res["winner"] in res["store"]:
        s = res["store"][res["winner"]]
        joblib.dump({"model": s["model"], "scaler": s["space"].scaler, "space": s["space"].describe(),
                     "algorithm": s["algorithm"], "k": s["k"], "segment_names": names},
                    config.MODELS_DIR / "final_segmentation_model.joblib")
    _figures(df, labels, names, prof, colors, res)
    print(f"[final] {res['winner']} -> " + ", ".join(f"{n} ({c:,})" for n, c in zip(prof.segment_name, prof.customers)))
    return {"profile": prof, "customers": cust, "names": names, "colors": colors, "migration": mig, "res": res,
            "labels": labels, "df": df}


# ============================================================================================ figures
def _figures(df, labels, names, prof, colors, res):
    import matplotlib.pyplot as plt
    seg = pd.Series(labels, index=df.index).map(names)
    order = list(prof.segment_name)
    # 1. share of customers vs share of revenue
    fig, ax = plt.subplots(figsize=(8.5, 0.5 * len(order) + 1.2))
    y = np.arange(len(order))[::-1]
    ax.barh(y + 0.18, prof.customer_share * 100, height=0.34, color=viz.NEUTRAL, label="% of customers")
    ax.barh(y - 0.18, prof.revenue_contribution * 100, height=0.34, color=viz.BLUE, label="% of revenue")
    for yi, a, b in zip(y, prof.customer_share * 100, prof.revenue_contribution * 100):
        ax.text(a + 0.4, yi + 0.18, f"{a:.1f}%", va="center", fontsize=7, color=viz.INK2)
        ax.text(b + 0.4, yi - 0.18, f"{b:.1f}%", va="center", fontsize=7, color=viz.INK2)
    ax.set_yticks(y, order)
    ax.tick_params(axis="y", length=0, colors=viz.INK2)
    ax.xaxis.set_visible(False)
    ax.grid(False)
    ax.legend(loc="lower right")
    ax.set_title("Final segments: share of customers vs share of revenue")
    viz.save(fig, config.SEG_FIG / "segment_customers_vs_revenue.png")
    # 2. profile heatmap (z-scores in the profile space)
    P = S.profile_space(df).X
    z = pd.DataFrame(P, columns=S.PROFILE_FEATURES, index=df.index).groupby(seg.values).mean().loc[order]
    fig, ax = plt.subplots(figsize=(9, 0.45 * len(order) + 1.6))
    from custseg.eda import matplotlib_diverging
    im = ax.imshow(z.values, cmap=matplotlib_diverging(), vmin=-2, vmax=2, aspect="auto")
    ax.set_xticks(range(z.shape[1]), z.columns, rotation=30, ha="right", fontsize=8)
    ax.set_yticks(range(len(order)), order, fontsize=8)
    for (i, j), v in np.ndenumerate(z.values):
        ax.text(j, i, f"{v:+.1f}", ha="center", va="center", fontsize=7, color="#ffffff" if abs(v) > 1.2 else viz.INK)
    ax.grid(False)
    ax.set_title("Segment profiles - mean standardised value vs all customers (0 = average)")
    fig.colorbar(im, ax=ax, shrink=0.8)
    viz.save(fig, config.SEG_FIG / "segment_profile_heatmap.png")
    # 3. recency vs monetary scatter (sample), colour = segment
    idx = S.sample_idx(len(df), 8000, config.SEED)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    for n in order:
        m = (seg.values[idx] == n)
        axes[0].scatter(df.recency_days.values[idx][m], df.monetary.values[idx][m], s=6, alpha=0.6, color=colors[n],
                        label=n, edgecolors="none")
        jitter = np.random.default_rng(0).uniform(-0.25, 0.25, m.sum())
        axes[1].scatter(df.frequency.values[idx][m] + jitter, df.monetary.values[idx][m], s=6, alpha=0.6,
                        color=colors[n], edgecolors="none")
    for ax, xl in zip(axes, ["recency (days)", "frequency (orders, jittered)"]):
        ax.set_yscale("log")
        ax.set_xlabel(xl)
        ax.set_ylabel("monetary (R$, log)")
    axes[0].set_title("Recency vs Monetary (8k-customer sample)")
    axes[1].set_title("Frequency vs Monetary")
    axes[0].legend(markerscale=3, fontsize=7, loc="upper right", ncol=1)
    viz.save(fig, config.SEG_FIG / "segment_scatter.png")
