"""Build staging -> warehouse -> data mart by executing the SQL files in order."""
from __future__ import annotations

import time

from custseg import config, db

SQL_FILES = [
    config.SQL_DIR / "staging" / "01_staging.sql",
    config.SQL_DIR / "warehouse" / "01_warehouse.sql",
    config.SQL_DIR / "data_mart" / "01_data_mart.sql",
]


def build() -> None:
    db.wait_ready()
    for f in SQL_FILES:
        t0 = time.time()
        db.run_sql_file(f)
        print(f"[sql] {f.relative_to(config.ROOT)}  ({time.time() - t0:.1f}s)")
    counts = db.query("""
        SELECT 'dw.dim_customer' t, count(*) n FROM dw.dim_customer UNION ALL
        SELECT 'dw.dim_product', count(*) FROM dw.dim_product UNION ALL
        SELECT 'dw.dim_location', count(*) FROM dw.dim_location UNION ALL
        SELECT 'dw.dim_date', count(*) FROM dw.dim_date UNION ALL
        SELECT 'dw.fact_orders', count(*) FROM dw.fact_orders UNION ALL
        SELECT 'dw.fact_sales', count(*) FROM dw.fact_sales UNION ALL
        SELECT 'dw.fact_cancellations', count(*) FROM dw.fact_cancellations UNION ALL
        SELECT 'mart.customer_rfm', count(*) FROM mart.customer_rfm UNION ALL
        SELECT 'mart.customer_behavior', count(*) FROM mart.customer_behavior""")
    for r in counts.itertuples():
        print(f"      {r.t:<26} {r.n:>9,}")


if __name__ == "__main__":
    build()
