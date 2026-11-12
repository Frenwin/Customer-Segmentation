"""Customer-level feature engineering.

The SQL data mart (mart.customer_rfm / mart.customer_behavior) is the source of truth at the analysis date.
`build_features(as_of)` re-computes the same features in pandas for *any* snapshot date (needed for segment
growth / migration and CLV calibration); `reconcile()` asserts both implementations agree at the analysis date.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from custseg import config, db

# Candidate features grouped as in PRD 5.2 (Experiment 3). Order = priority when a correlated pair is dropped.
CANDIDATES = {
    "Transaction Behavior": ["recency_days", "frequency", "monetary", "avg_order_value", "avg_purchase_interval_days",
                             "std_purchase_interval_days", "avg_items_per_order"],
    "Product Behavior": ["n_categories", "n_unique_products", "top_category_spend_ratio", "n_category_groups"],
    "Customer Lifecycle": ["tenure_days", "activity_period_days", "active_months"],
    "Value Metrics": ["avg_monthly_spending"],
    "Payment Behavior": ["avg_installments", "credit_card_order_share", "boleto_order_share", "voucher_order_share"],
    "Experience (feedback & delivery)": ["avg_review_score", "min_review_score", "late_delivery_share",
                                         "avg_delivery_days", "freight_ratio"],
}
ALL_CANDIDATES = [f for g in CANDIDATES.values() for f in g]


@lru_cache(maxsize=1)
def customer_mart() -> pd.DataFrame:
    """mart.customer_behavior + customer attributes (location) at the analysis date."""
    df = db.query("""
        SELECT b.*, c.customer_code, c.cohort_month, l.state, l.region, l.city
        FROM mart.customer_behavior b
        JOIN dw.dim_customer c USING (customer_key)
        JOIN dw.dim_location l USING (location_key)
        ORDER BY b.customer_key""")
    df["cohort_month"] = pd.to_datetime(df["cohort_month"])
    return df.set_index("customer_key")


@lru_cache(maxsize=1)
def revenue_orders() -> pd.DataFrame:
    df = db.query("""
        SELECT o.order_key, o.order_id, o.customer_key, o.purchase_ts, o.purchase_hour, o.n_items, o.n_categories,
               o.items_value, o.freight_value, o.order_value, o.installments, o.uses_voucher, o.review_score,
               o.delivery_days, o.is_late, pm.payment_type
        FROM dw.fact_orders o LEFT JOIN dw.dim_payment_method pm USING (payment_method_key)
        WHERE o.is_revenue ORDER BY o.purchase_ts""")
    df["purchase_ts"] = pd.to_datetime(df["purchase_ts"])
    return df


@lru_cache(maxsize=1)
def revenue_lines() -> pd.DataFrame:
    return db.query("""
        SELECT s.order_key, s.customer_key, s.product_key, s.line_total, p.category, p.category_group
        FROM dw.fact_sales s JOIN dw.dim_product p USING (product_key) WHERE s.is_revenue""")


def build_features(as_of: str | pd.Timestamp) -> pd.DataFrame:
    """Features using only orders purchased strictly before `as_of` (snapshot at 00:00 of as_of)."""
    as_of = pd.Timestamp(as_of)
    o = revenue_orders()
    o = o[o.purchase_ts < as_of].copy()
    o["pdate"] = o.purchase_ts.dt.normalize()
    g = o.groupby("customer_key")
    f = pd.DataFrame({
        "first_purchase_date": g.pdate.min(),
        "last_purchase_date": g.pdate.max(),
        "frequency": g.size(),
        "monetary": g.order_value.sum().round(2),
        "avg_order_value": g.order_value.mean().round(2),
        "avg_items_per_order": g.n_items.mean(),
        "avg_installments": g.installments.mean(),
        "voucher_order_share": g.uses_voucher.mean(),
        "credit_card_order_share": g.payment_type.apply(lambda s: (s == "credit_card").mean()),
        "avg_review_score": g.review_score.mean(),
        "late_delivery_share": g.is_late.apply(lambda s: s.dropna().astype(float).mean()),
        "avg_delivery_days": g.delivery_days.mean(),
        "freight_ratio": g.freight_value.sum() / g.order_value.sum(),
    })
    f["recency_days"] = (as_of - f.last_purchase_date).dt.days
    f["tenure_days"] = (as_of - f.first_purchase_date).dt.days
    f["is_repeat_customer"] = f.frequency >= 2
    lines = revenue_lines()
    lines = lines[lines.order_key.isin(o.order_key)]
    f["n_categories"] = lines.groupby("customer_key").category.nunique()
    f["n_unique_products"] = lines.groupby("customer_key").product_key.nunique()
    f["active_months"] = g.purchase_ts.apply(lambda s: s.dt.to_period("M").nunique())
    f["avg_monthly_spending"] = (f.monetary / np.maximum(1, f.tenure_days / 30.4375)).round(2)
    spend = lines.groupby(["customer_key", "category_group"]).line_total.sum().reset_index()
    spend = spend.sort_values(["customer_key", "line_total", "category_group"], ascending=[True, False, True])
    f["top_category_group"] = spend.drop_duplicates("customer_key").set_index("customer_key").category_group
    return f


def reconcile(tol: float = 0.011) -> pd.DataFrame:
    """SQL mart vs pandas builder at the analysis date (tolerance = SQL 2-decimal rounding)."""
    sql = customer_mart()
    py = build_features(config.ANALYSIS_DATE).reindex(sql.index)
    rows = []
    for c in ["recency_days", "frequency", "monetary", "avg_order_value", "tenure_days", "avg_items_per_order",
              "n_categories", "avg_installments", "voucher_order_share", "credit_card_order_share",
              "avg_review_score", "late_delivery_share", "avg_delivery_days", "freight_ratio"]:
        a, b = sql[c].astype(float), py[c].astype(float)
        diff = (a - b).abs()
        both_nan = a.isna() & b.isna()
        bad = int(((diff > tol) | (a.isna() ^ b.isna())).sum())
        rows.append({"feature": c, "max_abs_diff": float(diff[~both_nan].max() or 0), "mismatches": bad})
    out = pd.DataFrame(rows)
    if out.mismatches.sum():
        raise AssertionError(f"SQL mart and pandas features disagree:\n{out}")
    return out


def screen_features(df: pd.DataFrame, candidates: list[str] = ALL_CANDIDATES,
                    max_missing: float = 0.5, max_mode_share: float = 0.99,
                    corr_threshold: float = config.CORR_DROP_THRESHOLD) -> tuple[list[str], pd.DataFrame]:
    """PRD 5.2 'avoid redundant / highly correlated features': three explicit screening rules, in order."""
    log = []
    kept = []
    for c in candidates:
        s = df[c].astype(float)
        miss = s.isna().mean()
        mode_share = s.value_counts(normalize=True, dropna=True).iloc[0]
        if miss > max_missing:
            log.append({"feature": c, "decision": "drop", "rule": f"undefined for {miss:.1%} of customers (> {max_missing:.0%})"})
            continue
        if mode_share > max_mode_share:
            log.append({"feature": c, "decision": "drop", "rule": f"near-constant: {mode_share:.1%} share one value"})
            continue
        kept.append(c)
    rho = df[kept].astype(float).corr("spearman")
    final = []
    for c in kept:  # priority order: earlier candidate wins
        clash = [k for k in final if abs(rho.loc[c, k]) > corr_threshold]
        if clash:
            log.append({"feature": c, "decision": "drop",
                        "rule": f"|Spearman rho| = {abs(rho.loc[c, clash[0]]):.2f} with {clash[0]} (> {corr_threshold})"})
        else:
            final.append(c)
            log.append({"feature": c, "decision": "keep", "rule": "passes missing / variance / correlation screens"})
    order = {c: i for i, c in enumerate(candidates)}
    log_df = pd.DataFrame(log).sort_values("feature", key=lambda s: s.map(order)).reset_index(drop=True)
    group_of = {f: g for g, fs in CANDIDATES.items() for f in fs}
    log_df.insert(1, "group", log_df.feature.map(group_of))
    return final, log_df


def skewed(df: pd.DataFrame, cols: list[str], threshold: float = 1.0) -> list[str]:
    return [c for c in cols if abs(df[c].astype(float).skew()) > threshold]


def log_transform(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        out[c] = np.log1p(out[c].astype(float).clip(lower=0))
    return out
