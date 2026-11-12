"""Fixed BRL -> IDR rate for the dashboard: annual averages weighted by revenue per year (see config.FX_*)."""
from __future__ import annotations

from functools import lru_cache

from custseg import config, db


@lru_cache(maxsize=1)
def brl_to_idr() -> float:
    rev = db.query("""SELECT extract(year FROM d.date)::int AS year, sum(s.line_total) AS revenue
                      FROM dw.fact_sales s JOIN dw.dim_date d USING (date_key) WHERE s.is_revenue GROUP BY 1""")
    w = {int(r.year): float(r.revenue) for r in rev.itertuples()}
    tot = sum(w[y] for y in config.FX_BRL_IDR_ANNUAL if y in w)
    return round(sum(config.FX_BRL_IDR_ANNUAL[y] * w[y] for y in config.FX_BRL_IDR_ANNUAL if y in w) / tot, 1)


def rupiah(x: float, decimals: int = 0) -> str:
    """Indonesian formatting: Rp 1.234.567 (dot thousands, comma decimals)."""
    s = f"{x:,.{decimals}f}"
    return "Rp " + s.replace(",", "_").replace(".", ",").replace("_", ".")
