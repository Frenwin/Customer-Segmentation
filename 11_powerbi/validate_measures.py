"""Validate every DAX measure of the open Power BI model against the SQL analytical layer (PRD 10.2 / 16).

    1. open 11_powerbi/CustomerSegmentation.pbip in Power BI Desktop (PostgreSQL container running)
    2. python 11_powerbi/validate_measures.py

Runs DAX through the Desktop's local Analysis Services instance (tools/run_dax.ps1, ADOMD.NET shipped with
Power BI Desktop), recomputes the same KPIs with SQL, and writes dax_measures/measure_validation.md.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
from custseg import db  # noqa: E402

spec = importlib.util.spec_from_file_location("build_pbip", HERE / "build_pbip.py")
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)

SEG_MEASURES = ["Customers (Snapshot)", "Total Revenue", "Revenue Contribution", "Total Orders", "Average Order Value",
                "Repeat Purchase Rate", "Churn Rate (Inactivity)", "Predicted CLV 12m"]


def run_dax(queries: dict[str, str]) -> dict:
    with tempfile.TemporaryDirectory() as td:
        qf, of = Path(td) / "q.dax", Path(td) / "out.json"
        qf.write_text("".join(f"-- QUERY {k}\n{v}\n" for k, v in queries.items()), encoding="utf-8")
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "tools" / "run_dax.ps1"),
                        "-QueryFile", str(qf), "-Out", str(of)], check=True, capture_output=True)
        res = json.loads(of.read_text(encoding="utf-8-sig"))
    res = res if isinstance(res, list) else [res]
    return {r["name"]: r for r in res}


def scalar(r):
    return list(r["rows"][0].values())[0] if r.get("ok") and r.get("rows") else None


def main() -> None:
    for build_page in B.ALL_PAGES:      # pages register the Indonesian "(label)" text measures
        build_page()
    q = {n: f'EVALUATE ROW("v", [{n}])' for _, n, _, _ in B.MEASURES}
    # group by the sort-by column too, exactly like a visual does (catches ALL()/sort-by-column bugs)
    q["__by_segment"] = ("EVALUATE SUMMARIZECOLUMNS('dim_customer'[segment_name], 'dim_customer'[segment_id], "
                         + ", ".join(f'"{m}", [{m}]' for m in SEG_MEASURES) + ")")
    q["__category_filter"] = ("EVALUATE CALCULATETABLE(ROW(\"rev\", [Total Revenue], \"cust\", [Total Customers]), "
                              "'dim_product'[category_group] = \"Health & Beauty\")")
    q["__top10"] = "EVALUATE FILTER(SUMMARIZECOLUMNS('dim_customer'[customer_code], \"t\", [Top 10 Revenue]), NOT ISBLANK([t]))"
    R = run_dax(q)

    T = int(db.query("SELECT min(recency_days) FROM mart.customer_rfm r JOIN mart.customer_segmentation s USING (customer_key) "
                     "WHERE s.churn_status <> 'Active'").iloc[0, 0]) - 1
    g = db.query(f"""
        SELECT (SELECT sum(line_total) FROM dw.fact_sales WHERE is_revenue)              AS revenue,
               (SELECT count(*) FROM mart.customer_rfm)                                 AS customers,
               (SELECT count(*) FROM dw.fact_orders WHERE is_revenue)                    AS orders,
               (SELECT avg((frequency >= 2)::int) FROM mart.customer_rfm)                AS repeat_rate,
               (SELECT avg((recency_days > {T})::int) FROM mart.customer_rfm)            AS churn_inactive,
               (SELECT avg(review_score) FROM dw.fact_orders WHERE is_revenue)           AS review,
               (SELECT avg(is_late::int) FROM dw.fact_orders WHERE is_revenue)           AS late,
               (SELECT avg(predicted_clv_12m) FROM mart.customer_clv)                    AS pclv,
               (SELECT sum(retained_customers)::float / sum(eligible_customers) FROM mart.period_retention) AS retention,
               (SELECT sum(reactivated_customers)::float / sum(inactive_customers) FROM mart.period_retention) AS reactivation,
               (SELECT count(*) FROM mart.customer_rfm WHERE frequency >= 2)             AS returning
    """).iloc[0]
    fx = float(db.query("SELECT fx_brl_idr FROM pbi.meta").iloc[0, 0])   # dashboard shows Rupiah at a fixed rate
    expected = {"Total Revenue": g.revenue * fx, "Total Customers": g.customers, "Total Orders": g.orders, "Orders": g.orders,
                "Average Order Value": g.revenue * fx / g.orders, "Average Revenue per Customer": g.revenue * fx / g.customers,
                "Purchase Frequency": g.orders / g.customers, "New Customers": g.customers,
                "Returning Customers": g.returning, "Customers (Snapshot)": g.customers,
                "Repeat Purchase Rate": g.repeat_rate, "Churn Rate (Inactivity)": g.churn_inactive,
                "Active Customer Rate": 1 - g.churn_inactive, "Average Review Score": g.review,
                "Late Delivery Share": g.late, "Historical CLV": g.revenue * fx / g.customers, "Predicted CLV 12m": g.pclv * fx,
                "Retention Rate": g.retention, "Churn Rate": 1 - g.retention, "Reactivation Rate": g.reactivation,
                "Revenue Contribution": 1.0, "Segment Distribution": 1.0}
    rows = []
    for _, n, _, _ in B.MEASURES:
        r = R.get(n, {})
        v = scalar(r)
        exp = expected.get(n)
        if not r.get("ok"):
            status = "ERROR: " + r.get("error", "missing")[:120]
        elif exp is None:
            status = "evaluates"
        else:
            status = "MATCH" if abs(float(v) - float(exp)) <= 1e-6 * max(1, abs(float(exp))) else "DIFF"
        rows.append({"measure": n, "dax_value": v, "sql_value": exp, "status": status})
    df = pd.DataFrame(rows)

    seg = pd.DataFrame(R["__by_segment"]["rows"])
    seg.columns = [c.split("[")[-1].rstrip("]") for c in seg.columns]
    sp = db.query("SELECT segment_name, customers, revenue, revenue_contribution, churn_rate, retention_rate, "
                  "avg_predicted_clv_12m FROM mart.segment_profile")
    m = seg.merge(sp, on="segment_name")
    seg_ok = bool(((m["Customers (Snapshot)"] - m.customers).abs().max() == 0)
                  and ((m["Total Revenue"] - m.revenue * fx).abs().max() < 1)
                  and ((m["Revenue Contribution"] - m.revenue_contribution).abs().max() < 1e-9)
                  and ((m["Churn Rate (Inactivity)"] - m.churn_rate).abs().max() < 1e-9)
                  and ((m["Repeat Purchase Rate"] - m.retention_rate).abs().max() < 1e-9)
                  and ((m["Predicted CLV 12m"] - m.avg_predicted_clv_12m * fx).abs().max() < 1e-6))
    cat = R["__category_filter"]["rows"][0]
    cat_sql = db.query("SELECT sum(s.line_total) rev, count(DISTINCT s.customer_key) c FROM dw.fact_sales s "
                       "JOIN dw.dim_product p USING (product_key) WHERE s.is_revenue AND p.category_group='Health & Beauty'").iloc[0]
    cat_ok = abs(list(cat.values())[0] - cat_sql.rev * fx) < 1 and list(cat.values())[1] == cat_sql.c
    top10 = len(R["__top10"]["rows"])

    n_err = int(df.status.str.startswith("ERROR").sum())
    n_match = int((df.status == "MATCH").sum())
    n_diff = int((df.status == "DIFF").sum())
    fmt = lambda x: "" if x is None or (isinstance(x, float) and pd.isna(x)) else (f"{x:,.6g}" if isinstance(x, (int, float)) else str(x)[:70])  # noqa: E731
    lines = ["# DAX Measure Validation", "",
             "Generated by `python 11_powerbi/validate_measures.py` against the model open in Power BI Desktop "
             "(DAX executed on the local Analysis Services instance, expected values recomputed in SQL; money in Rupiah "
             f"= BRL x {fx:,.1f}).", "",
             f"**Result:** {len(df)} measures · {n_err} errors · {n_match} matched against SQL · {n_diff} differences · "
             f"segment breakdown {'MATCH' if seg_ok else 'DIFF'} · category filter propagation {'MATCH' if cat_ok else 'DIFF'} · "
             f"Top-10 measure returns {top10} customers.", "",
             "| Measure | DAX | SQL | Status |", "|---|---:|---:|---|"]
    lines += [f"| {r.measure} | {fmt(r.dax_value)} | {fmt(r.sql_value)} | {r.status} |" for r in df.itertuples()]
    lines += ["", "## By segment (DAX)", "", "| " + " | ".join(seg.columns) + " |", "|" + "---|" * len(seg.columns)]
    lines += ["| " + " | ".join(fmt(v) for v in row) + " |" for row in seg.itertuples(index=False)]
    out = HERE / "dax_measures" / "measure_validation.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[validate] {len(df)} measures, {n_err} errors, {n_match} match, {n_diff} diff, segments {seg_ok}, "
          f"category filter {cat_ok}, top10 rows {top10} -> {out}")


if __name__ == "__main__":
    main()
