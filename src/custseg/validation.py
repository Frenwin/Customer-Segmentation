"""Data-quality validation (PRD 4.3). Every check is a SQL count of violating rows.

severity = error  -> pipeline stops if the violation share exceeds the tolerance
severity = warn   -> reported, handled by an explicit rule (documented in `handling`)
severity = info   -> descriptive, expected property of the source
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import pandas as pd

from custseg import config, db


@dataclass
class Check:
    check_id: str
    prd_rule: str
    layer: str
    description: str
    violations_sql: str
    total_sql: str
    severity: str
    tolerance: float      # max allowed violation share
    handling: str


CHECKS = [
    Check("DQ01", "Customer ID", "raw", "customer_id is null/empty",
          "SELECT count(*) FROM raw.customers WHERE nullif(trim(customer_id),'') IS NULL",
          "SELECT count(*) FROM raw.customers", "error", 0, "rows would be rejected in staging"),
    Check("DQ02", "Customer ID", "raw", "customer_unique_id is null/empty",
          "SELECT count(*) FROM raw.customers WHERE nullif(trim(customer_unique_id),'') IS NULL",
          "SELECT count(*) FROM raw.customers", "error", 0, "rows would be rejected in staging"),
    Check("DQ03", "Transaction ID", "raw", "duplicated order_id in orders",
          "SELECT count(*) - count(DISTINCT order_id) FROM raw.orders", "SELECT count(*) FROM raw.orders",
          "error", 0, "DISTINCT ON (order_id) in staging"),
    Check("DQ04", "Transaction ID", "raw", "duplicated (order_id, order_item_id) line",
          "SELECT count(*) - count(DISTINCT (order_id, order_item_id)) FROM raw.order_items",
          "SELECT count(*) FROM raw.order_items", "error", 0, "DISTINCT ON in staging"),
    Check("DQ05", "Transaction Date", "staging", "purchase timestamp missing / unparseable",
          "SELECT count(*) FROM staging.orders WHERE purchase_ts IS NULL", "SELECT count(*) FROM staging.orders",
          "error", 0, "cast fails loudly in staging; null -> dq_issue"),
    Check("DQ06", "Transaction Date", "staging", "delivered before purchase (impossible lifecycle)",
          "SELECT count(*) FROM staging.orders WHERE delivered_ts < purchase_ts", "SELECT count(*) FROM staging.orders",
          "warn", 0.001, "delivery_days set NULL in fact_orders; revenue kept"),
    Check("DQ07", "Transaction Date", "staging", "approved before purchase",
          "SELECT count(*) FROM staging.orders WHERE approved_ts < purchase_ts", "SELECT count(*) FROM staging.orders",
          "warn", 0.001, "flag only (approval time not used in analysis)"),
    Check("DQ08", "Transaction Date", "staging", "status 'delivered' without delivery date",
          "SELECT count(*) FROM staging.orders WHERE order_status='delivered' AND delivered_ts IS NULL",
          "SELECT count(*) FROM staging.orders WHERE order_status='delivered'", "warn", 0.001,
          "kept as revenue (status is authoritative); excluded from delivery-time metrics"),
    Check("DQ09", "Quantity", "warehouse", "quantity <= 0 on a sales line",
          "SELECT count(*) FROM dw.fact_sales WHERE quantity <= 0", "SELECT count(*) FROM dw.fact_sales",
          "error", 0, "Olist: 1 line = 1 unit"),
    Check("DQ10", "Unit Price", "staging", "negative or zero item price",
          "SELECT count(*) FROM staging.order_items WHERE price <= 0", "SELECT count(*) FROM staging.order_items",
          "error", 0, "would be rejected"),
    Check("DQ11", "Unit Price", "staging", "negative freight value",
          "SELECT count(*) FROM staging.order_items WHERE freight_value < 0", "SELECT count(*) FROM staging.order_items",
          "error", 0, "would be rejected"),
    Check("DQ12", "Transaction Amount", "warehouse", "line_total <> quantity*unit_price + freight - discount",
          "SELECT count(*) FROM dw.fact_sales WHERE abs(line_total - (quantity*unit_price + freight_value - discount_amount)) > 0.005",
          "SELECT count(*) FROM dw.fact_sales", "error", 0, "-"),
    Check("DQ13", "Transaction Amount", "warehouse", "|payment_value - (items + freight)| > R$1 on revenue orders",
          "SELECT count(*) FROM dw.fact_orders WHERE is_revenue AND abs(coalesce(payment_value,0) - order_value) > 1",
          "SELECT count(*) FROM dw.fact_orders WHERE is_revenue", "warn", 0.01,
          "installment interest / vouchers; revenue measured as items + freight (line level)"),
    Check("DQ14", "Customer Relationship", "staging", "order references unknown customer_id",
          "SELECT count(*) FROM staging.orders o LEFT JOIN staging.customers c USING (customer_id) WHERE c.customer_id IS NULL",
          "SELECT count(*) FROM staging.orders", "error", 0, "-"),
    Check("DQ15", "Customer Relationship", "staging", "order item references unknown order / product",
          "SELECT count(*) FROM staging.order_items i LEFT JOIN staging.orders o USING (order_id) "
          "LEFT JOIN staging.products p USING (product_id) WHERE o.order_id IS NULL OR p.product_id IS NULL",
          "SELECT count(*) FROM staging.order_items", "error", 0, "-"),
    Check("DQ16", "Customer Relationship", "warehouse", "fact_sales customer_key missing in dim_customer",
          "SELECT count(*) FROM dw.fact_sales s LEFT JOIN dw.dim_customer c USING (customer_key) WHERE c.customer_key IS NULL",
          "SELECT count(*) FROM dw.fact_sales", "error", 0, "-"),
    Check("DQ17", "Order Status", "staging", "order status outside the known set",
          "SELECT count(*) FROM staging.orders WHERE order_status NOT IN "
          "('delivered','shipped','canceled','unavailable','invoiced','processing','created','approved')",
          "SELECT count(*) FROM staging.orders", "error", 0, "-"),
    Check("DQ18", "Order Status", "staging", "orders not recognised as revenue (in-flight / cancelled)",
          "SELECT count(*) FROM staging.orders WHERE NOT is_revenue_status", "SELECT count(*) FROM staging.orders",
          "info", 1, "is_revenue = false (cancelled -> fact_cancellations)"),
    Check("DQ19", "Order Status", "staging", "revenue order without any item line",
          "SELECT count(*) FROM staging.orders WHERE is_revenue_status AND dq_issue = 'order_without_items'",
          "SELECT count(*) FROM staging.orders WHERE is_revenue_status", "error", 0, "-"),
    Check("DQ20", "Duplicate Records", "raw", "duplicated review_id in reviews",
          "SELECT count(*) - count(DISTINCT review_id) FROM raw.order_reviews", "SELECT count(*) FROM raw.order_reviews",
          "warn", 0.02, "one review per order kept (latest answer)"),
    Check("DQ21", "Duplicate Records", "raw", "orders with more than one review",
          "SELECT count(*) - count(DISTINCT order_id) FROM raw.order_reviews", "SELECT count(*) FROM raw.order_reviews",
          "warn", 0.02, "latest answer kept"),
    Check("DQ22", "Duplicate Records", "raw", "duplicated geolocation rows per zip prefix",
          "SELECT count(*) - count(DISTINCT geolocation_zip_code_prefix) FROM raw.geolocation",
          "SELECT count(*) FROM raw.geolocation", "info", 1, "median lat/lng per zip prefix"),
    Check("DQ23", "Valid values", "raw", "geolocation outside Brazil bounding box",
          "SELECT count(*) FROM raw.geolocation WHERE NOT (geolocation_lat::float BETWEEN -34 AND 5.5 "
          "AND geolocation_lng::float BETWEEN -74 AND -34.5)", "SELECT count(*) FROM raw.geolocation",
          "warn", 0.001, "excluded before aggregation"),
    Check("DQ24", "Valid values", "staging", "product without category",
          "SELECT count(*) FROM staging.products WHERE category = 'uncategorized'", "SELECT count(*) FROM staging.products",
          "warn", 0.03, "category = 'uncategorized', group = 'Other'"),
    Check("DQ25", "Customer Relationship", "raw", "repeat persons: customer_unique_id with >1 customer_id",
          "SELECT count(*) - count(DISTINCT customer_unique_id) FROM raw.customers", "SELECT count(*) FROM raw.customers",
          "info", 1, "customer grain = customer_unique_id (dim_customer)"),
    Check("DQ26", "Reconciliation", "mart", "revenue fact_sales vs fact_orders vs mart.customer_rfm (R$ diff)",
          "SELECT round(abs((SELECT sum(line_total) FROM dw.fact_sales WHERE is_revenue) - (SELECT sum(order_value) FROM dw.fact_orders WHERE is_revenue))"
          " + abs((SELECT sum(order_value) FROM dw.fact_orders WHERE is_revenue) - (SELECT sum(monetary) FROM mart.customer_rfm)))::bigint",
          "SELECT 1", "error", 0.5, "-"),
]


def run() -> pd.DataFrame:
    rows = []
    for ch in CHECKS:
        v = int(db.query(ch.violations_sql).iloc[0, 0] or 0)
        t = int(db.query(ch.total_sql).iloc[0, 0] or 0)
        share = v / t if t else 0.0
        if ch.severity == "info":
            status = "INFO"
        elif share <= ch.tolerance:
            status = "PASS"
        else:
            status = "FAIL" if ch.severity == "error" else "WARN"
        rows.append({**{k: x for k, x in asdict(ch).items() if not k.endswith("_sql")},
                     "violations": v, "total": t, "violation_share": round(share, 6), "status": status})
    df = pd.DataFrame(rows)
    write_report(df)
    failed = df[df.status == "FAIL"]
    print(f"[dq] {len(df)} checks: " + ", ".join(f"{s}={n}" for s, n in df.status.value_counts().items()))
    if len(failed):
        raise SystemExit(f"data-quality FAIL: {failed.check_id.tolist()}")
    return df


def write_report(df: pd.DataFrame) -> None:
    out = config.DE_DIR / "validation"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "data_quality_results.csv", index=False)
    (out / "data_quality_results.json").write_text(json.dumps(df.to_dict("records"), indent=2), encoding="utf-8")
    lines = ["# Data Quality Validation Report", "",
             "Generated by `python -m custseg.validation` (also run inside `python -m custseg.pipeline`).", "",
             "Status: **PASS** = within tolerance · **WARN** = violation handled by an explicit rule · "
             "**INFO** = expected property of the source · **FAIL** = pipeline stops.", "",
             "| ID | PRD rule | Layer | Check | Violations | Total | Share | Status | Handling |",
             "|---|---|---|---|---:|---:|---:|---|---|"]
    for r in df.itertuples():
        lines.append(f"| {r.check_id} | {r.prd_rule} | {r.layer} | {r.description} | {r.violations:,} | {r.total:,} | "
                     f"{r.violation_share:.4%} | {r.status} | {r.handling} |")
    (out / "data_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run()
