"""KPI framework (PRD 8): dictionary + computed baselines + data-derived targets.

Targets are never invented: each target cites its basis (best observed period / cohort, or 'baseline only' when the
data offers no defensible benchmark - e.g. no campaign history exists to size an uplift).
"""
from __future__ import annotations

import pandas as pd

from custseg import config, db


def _fmt(v, kind):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    return {"pct": f"{v:.2%}", "brl": f"R$ {v:,.2f}", "int": f"{v:,.0f}", "num": f"{v:,.2f}",
            "days": f"{v:,.0f} days"}[kind]


def _fmt_id(v, kind):
    """Dashboard version: Rupiah at the fixed rate, Indonesian separators (1.234.567 / 12,3%)."""
    from custseg import fx
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    if kind == "brl":
        return fx.rupiah(v * fx.brl_to_idr())
    swap = lambda s: s.replace(",", "_").replace(".", ",").replace("_", ".")  # noqa: E731
    return swap({"pct": f"{v:.2%}", "int": f"{v:,.0f}", "num": f"{v:,.2f}", "days": f"{v:,.0f} hari"}[kind])


def build(ctx: dict) -> pd.DataFrame:
    k = db.query("SELECT * FROM mart.customer_kpi_monthly ORDER BY month")
    cm = db.query("SELECT count(*) n, sum(monetary) rev, sum(frequency) orders, avg((frequency>=2)::int) rep "
                  "FROM mart.customer_rfm").iloc[0]
    reg = int(db.query("SELECT count(*) FROM dw.dim_customer").iloc[0, 0])
    pr = ctx["period_retention"]   # pooled over periods = identical to the DAX measures
    prof = ctx["profile"]
    trend = ctx["repeat_6m_by_cohort"]
    T = ctx["threshold"]
    last3 = k.tail(3)
    rows = [
        # ---------------------------------------------------------------- acquisition
        ("Acquisition", "Total Customers", "Distinct customers (customer_unique_id) with >= 1 delivered order in the window",
         "DISTINCTCOUNT(customer_key) over revenue orders", "Total Customers", "mart.customer_rfm / pbi.fact_orders",
         "Customer; any period", "Daily", cm.n, "int", None, "Baseline only (volume KPI)", "Management"),
        ("Acquisition", "Registered Customers", "All persons who ever placed an order (any status) - Olist has no sign-up table",
         "COUNTROWS(dim_customer)", "Registered Customers", "dw.dim_customer", "Customer", "Daily", reg, "int", None,
         "Baseline only", "Management"),
        ("Acquisition", "New Customers", "Customers whose first delivered order falls in the period",
         "COUNT customers WHERE first revenue order in period", "New Customers", "mart.customer_kpi_monthly",
         "Month", "Monthly", last3.new_customers.mean(), "int", k.new_customers.max(),
         f"best observed month ({k.loc[k.new_customers.idxmax(), 'year_month']}, Black Friday)", "Marketing"),
        ("Acquisition", "Customer Acquisition Rate", "New customers / customers acquired before the period start",
         "New Customers(t) / Cumulative Customers(t-1)", "Customer Acquisition Rate", "mart.customer_kpi_monthly",
         "Month", "Monthly", last3.acquisition_rate.mean(), "pct", None,
         "Baseline only - structurally declines as the base grows", "Marketing"),
        ("Acquisition", "Customer Growth Rate", "Month-over-month growth of purchasing (active) customers",
         "(Purchasing(t) - Purchasing(t-1)) / Purchasing(t-1)", "Customer Growth Rate", "mart.customer_kpi_monthly",
         "Month", "Monthly", k.customer_growth_rate.tail(6).mean(), "pct", 0.0,
         "guardrail: >= 0% (no decline); last 6 months averaged ~0%", "Management"),
        # ---------------------------------------------------------------- value
        ("Value", "Total Revenue", "Items + freight of delivered orders (GMV paid by the customer). Not profit: "
         "Olist has no cost data", "SUM(fact_sales.line_total) WHERE is_revenue", "Total Revenue", "pbi.fact_sales",
         "Order line; any period", "Daily", cm.rev, "brl", None, "Baseline only (no cost / margin data)", "Management"),
        ("Value", "Average Order Value", "Revenue / number of orders", "Total Revenue / Total Orders",
         "Average Order Value", "pbi.fact_sales", "Order", "Daily", cm.rev / cm.orders, "brl", cm.rev / cm.orders,
         "guardrail: hold at baseline while growing order volume", "Marketing"),
        ("Value", "Average Revenue per Customer", "Revenue / unique purchasing customers",
         "Total Revenue / Total Customers", "Average Revenue per Customer", "pbi.fact_sales", "Customer", "Monthly",
         cm.rev / cm.n, "brl", None, "Baseline only", "Business Analyst"),
        ("Value", "Purchase Frequency", "Orders / unique purchasing customers", "Total Orders / Total Customers",
         "Purchase Frequency", "pbi.fact_orders", "Customer", "Monthly", cm.orders / cm.n, "num", None,
         "Baseline only", "CRM"),
        ("Value", "Historical CLV", "Cumulative revenue of a customer to date", "SUM(monetary) per customer",
         "Historical CLV", "mart.customer_segmentation", "Customer", "Monthly", ctx["clv"]["historical_revenue_total"] / cm.n,
         "brl", None, "Baseline only", "CRM"),
        ("Value", "Predicted CLV (12 months)", "Expected revenue in the next 12 months (BG/NBD x Gamma-Gamma)",
         "E[purchases 12m] x E[value per purchase]", "Predicted CLV 12m", "mart.customer_segmentation", "Customer",
         "Monthly (refit)", ctx["clv"]["predicted_revenue_12m_total"] / cm.n, "brl", None,
         "Baseline only - model output, validated on a 6-month holdout", "CRM"),
        ("Value", "Revenue Contribution", "Segment revenue / total revenue", "Revenue(segment) / Revenue(all)",
         "Revenue Contribution", "pbi.fact_sales", "Segment", "Monthly", None, "pct", None, "see segment table",
         "Management"),
        # ---------------------------------------------------------------- retention
        ("Retention", "Repeat Purchase Rate", "Customers with 2+ delivered orders / purchasing customers",
         "COUNT(frequency >= 2) / COUNT(customers)", "Repeat Purchase Rate", "dw.dim_customer (pbi)", "Customer",
         "Monthly", cm.rep, "pct", None, "Baseline only - lifetime rate depends on customer age; steer with the 6-month rate",
         "CRM"),
        ("Retention", "6-Month Repeat Rate", "Customers who make a second purchase within 182 days of the first "
         "(cohorts with >= 6 months of observation) - age-neutral, comparable across cohorts",
         "COUNT(2nd order <= 182 d after 1st) / cohort customers", "-", "08_customer_analytics/retention_analysis",
         "Acquisition quarter", "Quarterly", trend.repeat_6m.mean(), "pct", trend.repeat_6m.max(),
         f"best acquisition quarter ({trend.repeat_6m.idxmax()})", "CRM"),
        ("Retention", "Retention Rate (3-month)", "Customers who purchased in period P-1 and again in P / customers "
         "who purchased in P-1", "Retained / Eligible", "Retention Rate", "pbi.period_retention", "3-month period",
         "Quarterly", pr.retained_customers.sum() / pr.eligible_customers.sum(), "pct", pr.retention_rate.max(),
         f"best observed period ({pr.loc[pr.retention_rate.idxmax(), 'period']})", "CRM"),
        ("Retention", "Churn Rate (3-month)", "1 - Retention Rate on the same eligible base",
         "(Eligible - Retained) / Eligible", "Churn Rate", "pbi.period_retention", "3-month period", "Quarterly",
         1 - pr.retained_customers.sum() / pr.eligible_customers.sum(), "pct", 1 - pr.retention_rate.max(), "mirror of the retention target", "CRM"),
        ("Retention", "Inactive (Churned) Customer Share", f"Customers with no purchase for more than T = {T} days "
         "(P90 of inter-purchase gaps). Rule-based status, not a prediction", f"COUNT(recency_days > {T}) / COUNT(customers)",
         "Churn Rate (Inactivity)", "dw.dim_customer (pbi)", "Customer snapshot", "Monthly",
         ctx["churn_snapshot"], "pct", None, "Baseline only - driven by the age of the customer base", "CRM"),
        ("Retention", "Reactivation Rate", "Customers inactive in P-1 (bought before) who buy in P / those inactive",
         "Reactivated / Inactive eligible", "Reactivation Rate", "pbi.period_retention", "3-month period", "Quarterly",
         pr.reactivated_customers.sum() / pr.inactive_customers.sum(), "pct", pr.reactivation_rate.max(),
         f"best observed period ({pr.loc[pr.reactivation_rate.idxmax(), 'period']})", "CRM"),
        ("Retention", "Average Purchase Interval", "Mean days between consecutive purchase occasions (gaps >= 1 day)",
         "AVG(gap days)", "Average Purchase Interval", "mart.customer_behavior", "Customer", "Monthly",
         ctx["avg_interval"], "days", None, "Baseline only", "Business Analyst"),
        # ---------------------------------------------------------------- engagement / experience (driver KPIs)
        ("Engagement", "Active Customer Rate", f"Customers with a purchase in the last {T} days / purchasing customers",
         f"COUNT(recency_days <= {T}) / COUNT(customers)", "Active Customer Rate", "dw.dim_customer (pbi)",
         "Customer snapshot", "Monthly", 1 - ctx["churn_snapshot"], "pct", None, "Baseline only", "Marketing"),
        ("Engagement", "Late Delivery Share (driver)", "Delivered orders that arrived after the estimated date",
         "COUNT(is_late) / COUNT(delivered orders)", "Late Delivery Share", "pbi.fact_orders", "Order", "Weekly",
         ctx["late_share"], "pct", ctx["late_share_best"],
         "top-quartile month (P25 of monthly late share); late orders average ~2 review stars less", "Operations"),
        ("Engagement", "Average Review Score (driver)", "Mean 1-5 review score of delivered orders",
         "AVG(review_score)", "Average Review Score", "pbi.fact_orders", "Order", "Weekly", ctx["avg_review"], "num",
         ctx["avg_review_best"], "top-quartile month (P75 of monthly averages)", "Operations"),
    ]
    cols = ["category", "kpi", "business_definition", "formula", "dax_measure", "data_source", "granularity",
            "update_frequency", "baseline_value", "unit", "target_value", "target_basis", "business_owner"]
    df = pd.DataFrame(rows, columns=cols)
    df["baseline_display"] = [_fmt(v, u) for v, u in zip(df.baseline_value, df.unit)]
    df["baseline_display_idr"] = [_fmt_id(v, u) for v, u in zip(df.baseline_value, df.unit)]
    df["target_display_idr"] = [_fmt_id(v, u) for v, u in zip(df.target_value, df.unit)]
    df["target_display"] = [_fmt(v, u) for v, u in zip(df.target_value, df.unit)]
    df["baseline_period"] = f"{config.WINDOW_START} .. {config.ANALYSIS_DATE} (monthly KPIs: last 3 months)"
    # segment performance KPIs (PRD 8.5)
    seg = prof[["segment_id", "segment_name", "customers", "customer_share", "revenue_contribution", "avg_monetary",
                "avg_frequency", "avg_order_value", "retention_rate", "churn_rate", "avg_historical_clv",
                "avg_predicted_clv_12m", "segment_growth_rate"]].copy()
    return df, seg


def write(df: pd.DataFrame, seg: pd.DataFrame) -> None:
    out = config.KPI_DIR
    out.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out / "kpi_dictionary.xlsx") as xw:
        df.drop(columns=["baseline_display", "target_display"]).to_excel(xw, sheet_name="kpi_dictionary", index=False)
        seg.to_excel(xw, sheet_name="segment_performance", index=False)
    db.load_df(df.drop(columns=["baseline_value", "target_value"]), "kpi_dictionary", "mart")
    lines = ["# KPI Definitions", "",
             "Every KPI is computed from the analytical layer and implemented as a DAX measure of the same name "
             "in `11_powerbi` (see `11_powerbi/dax_measures/measures.dax`). Generated by `custseg.kpi`.", "",
             "**Target policy (PRD 8.6):** a target is set only when the data provides a defensible benchmark "
             "(best observed period/cohort). Otherwise the KPI is *baseline only* until a controlled campaign "
             "(A/B test with hold-out) establishes an achievable uplift.", ""]
    for cat, g in df.groupby("category", sort=False):
        lines += [f"## {cat} KPIs", ""]
        for r in g.itertuples():
            lines += [f"### {r.kpi}", "",
                      "| Attribute | Value |", "|---|---|",
                      f"| Business definition | {r.business_definition} |",
                      f"| Formula | `{r.formula}` |",
                      f"| DAX measure | `[{r.dax_measure}]` |",
                      f"| Data source | {r.data_source} |",
                      f"| Granularity | {r.granularity} |",
                      f"| Update frequency | {r.update_frequency} |",
                      f"| Baseline | {r.baseline_display} |",
                      f"| Target | {r.target_display} — {r.target_basis} |",
                      f"| Business owner | {r.business_owner} |", ""]
    (out / "kpi_definitions.md").write_text("\n".join(lines), encoding="utf-8")
    lines = ["# Business Metrics — Current Values", "",
             f"Snapshot date {config.ANALYSIS_DATE}; window {config.WINDOW_START} .. 2018-08-31.", "",
             "| Category | KPI | Baseline | Target | Target basis | Owner |", "|---|---|---:|---:|---|---|"]
    for r in df.itertuples():
        lines.append(f"| {r.category} | {r.kpi} | {r.baseline_display} | {r.target_display} | {r.target_basis} | "
                     f"{r.business_owner} |")
    lines += ["", "## Segment performance KPIs (PRD 8.5)", "",
              "| Segment | Customers | % customers | Revenue contribution | Avg spend | Purchase freq. | AOV | "
              "Retention (repeat) | Churn (inactive) | Hist. CLV | Pred. CLV 12m | Growth vs 6 mo. earlier |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in seg.itertuples():
        lines.append(f"| {r.segment_id} {r.segment_name} | {r.customers:,} | {r.customer_share:.1%} | "
                     f"{r.revenue_contribution:.1%} | R$ {r.avg_monetary:,.0f} | {r.avg_frequency:.2f} | "
                     f"R$ {r.avg_order_value:,.0f} | {r.retention_rate:.1%} | {r.churn_rate:.1%} | "
                     f"R$ {r.avg_historical_clv:,.0f} | R$ {r.avg_predicted_clv_12m:,.2f} | "
                     f"{'n/a' if pd.isna(r.segment_growth_rate) else f'{r.segment_growth_rate:+.1%}'} |")
    (out / "business_metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def driver_context() -> dict:
    m = db.query("""
        SELECT to_char(date_trunc('month', purchase_ts), 'YYYY-MM') ym, avg(is_late::int) late, avg(review_score) rv,
               count(*) n
        FROM dw.fact_orders WHERE is_revenue GROUP BY 1 HAVING count(*) >= 1000 ORDER BY 1""")
    tot = db.query("SELECT avg(is_late::int) late, avg(review_score) rv FROM dw.fact_orders WHERE is_revenue").iloc[0]
    # targets = top-quartile month (robust to one exceptional month)
    return {"late_share": float(tot.late), "avg_review": float(tot.rv), "late_share_best": float(m.late.quantile(0.25)),
            "avg_review_best": float(m.rv.quantile(0.75)), "monthly_experience": m}
