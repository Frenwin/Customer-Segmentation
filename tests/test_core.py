"""Fast unit tests for the analytical core (no database needed):  python -m pytest -q"""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from custseg import analytics, clv, fx, viz  # noqa: E402
from custseg import features as F  # noqa: E402
from custseg import final_segmentation as FS  # noqa: E402
from custseg import segmentation as S  # noqa: E402


# ---------------------------------------------------------------- E1 RFM rules
def test_rfm_rule_map_is_exhaustive_and_ordered():
    cells = list(itertools.product(range(1, 6), range(1, 6), range(1, 6)))
    sc = pd.DataFrame(cells, columns=["r_score", "f_score", "m_score"])
    seg = S.rfm_segment(sc)
    assert seg.notna().all()
    assert seg[(sc.f_score >= 2) & (sc.r_score >= 4) & (sc.m_score >= 4)].eq("Champions").all()
    assert seg[(sc.f_score == 1) & (sc.r_score == 1) & (sc.m_score <= 3)].eq("Lost").all()


def test_rfm_scores_direction():
    df = pd.DataFrame({"recency_days": [1, 400], "frequency": [7, 1], "monetary": [999.0, 10.0]})
    edges = {"recency": [50, 100, 200, 300], "monetary": [20, 50, 100, 200]}
    sc = S.rfm_scores(df, edges)
    assert sc.iloc[0][["r_score", "f_score", "m_score"]].tolist() == [5, 5, 5]   # recent, frequent, big
    assert sc.iloc[1][["r_score", "f_score", "m_score"]].tolist() == [1, 1, 1]


# ---------------------------------------------------------------- naming & colours
def test_segment_colours_follow_the_name_not_the_rank():
    a = FS.segment_colors(["At Risk", "Loyal Customers"])
    b = FS.segment_colors(["Loyal Customers", "Hibernating", "At Risk"])
    assert a["At Risk"] == b["At Risk"] == viz.SEGMENT_PALETTE["At Risk"]
    unknown = FS.segment_colors(["At Risk", "Something New"])
    assert unknown["Something New"] not in (unknown["At Risk"],)


def test_name_clusters_rules():
    df = pd.DataFrame({"monetary": [100.0] * 10, "recency_days": [200] * 10})
    prof = pd.DataFrame({
        "repeat_rate": [1.0, 1.0, 0.0, 0.0, 0.0], "avg_recency_days": [100, 180, 50, 300, 300],
        "median_monetary": [300, 300, 100, 60, 250], "late_delivery_share": [0.0] * 5, "avg_review_score": [4.5] * 5})
    z = pd.DataFrame(0.0, index=prof.index, columns=S.PROFILE_FEATURES)
    z.loc[2, "recency_days"] = -1.2
    names = FS.name_clusters(prof, df, threshold=278, z=z)
    # repeat + recent + high spend | repeat, older | recent one-timer | lapsing low spend | lapsing high spend
    assert names == {0: "Champions", 1: "Loyal Customers", 2: "New Customers", 3: "Hibernating", 4: "At Risk"}


# ---------------------------------------------------------------- currency
def test_rupiah_indonesian_format():
    assert fx.rupiah(1234567.4) == "Rp 1.234.567"
    assert fx.rupiah(1234.5, 2) == "Rp 1.234,50"


# ---------------------------------------------------------------- CLV formulas
P = {"r": 0.5, "alpha": 10.0, "a": 2.0, "b": 3.0}


def test_bgnbd_p_alive_properties():
    assert clv.p_alive(P, np.array([0.0]), np.array([0.0]), np.array([30.0]))[0] == pytest.approx(1.0)
    early = clv.p_alive(P, np.array([2.0]), np.array([28.0]), np.array([30.0]))[0]
    late = clv.p_alive(P, np.array([2.0]), np.array([2.0]), np.array([30.0]))[0]
    assert 0 < late < early < 1          # a long silence after the last purchase lowers P(alive)


def test_bgnbd_expectation_grows_with_horizon_and_frequency():
    e = lambda t, x: clv.bgnbd_expected(P, t, np.array([x]), np.array([20.0]), np.array([30.0]))[0]  # noqa: E731
    assert 0 < e(10, 1.0) < e(52, 1.0)
    assert e(52, 0.0) < e(52, 3.0)


def test_gamma_gamma_shrinks_to_population_mean():
    g = {"p": 6.0, "q": 3.0, "v": 50.0}
    pop = g["p"] * g["v"] / (g["q"] - 1)
    assert clv.gg_expected_value(g, np.array([0.0]), np.array([0.0]))[0] == pytest.approx(pop)
    one = clv.gg_expected_value(g, np.array([1.0]), np.array([500.0]))[0]
    many = clv.gg_expected_value(g, np.array([20.0]), np.array([500.0]))[0]
    assert pop < one < many < 500        # more purchases -> closer to the customer's own mean


# ---------------------------------------------------------------- market basket
def test_apriori_support_confidence_lift():
    baskets = [frozenset(b) for b in (["a", "b"], ["a", "b"], ["a"], ["c"])] * 5
    counts = analytics._apriori(baskets, min_count=5)
    rules = analytics._rules(counts, len(baskets), "order")
    r = rules[(rules.antecedent == "b") & (rules.consequent == "a")].iloc[0]
    assert r.support_count == 10 and r.confidence == pytest.approx(1.0)
    assert r.lift == pytest.approx(1.0 / (15 / 20))


# ---------------------------------------------------------------- feature screening
def test_screen_features_drops_redundant_constant_and_sparse():
    rng = np.random.default_rng(0)
    n = 1000
    x = rng.normal(size=n)
    df = pd.DataFrame({"keep": x, "dup": x * 2 + 0.01 * rng.normal(size=n), "const": np.r_[np.ones(n - 5), np.zeros(5)],
                       "sparse": np.r_[rng.normal(size=100), [np.nan] * (n - 100)], "other": rng.normal(size=n)})
    kept, log = F.screen_features(df, ["keep", "dup", "const", "sparse", "other"])
    assert kept == ["keep", "other"]
    assert set(log[log.decision == "drop"].feature) == {"dup", "const", "sparse"}
