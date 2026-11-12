"""Customer Lifetime Value (PRD 6.2).

Historical CLV   = total historical revenue per customer (mart.customer_rfm.monetary)
Predictive CLV   = BG/NBD (expected repeat purchases) x Gamma-Gamma (expected value per purchase), 12-month horizon

Both models are implemented from the original papers (Fader, Hardie & Lee 2005a "Counting your customers the easy
way"; Fader, Hardie & Lee 2005b "RFM and CLV") with SciPy maximum likelihood - no unmaintained dependency.
Time unit = weeks. A "transaction" = a distinct purchase day (same-day re-orders are one purchase occasion).

Validation is time-based: fit on orders before CLV_CALIBRATION_END, predict the holdout window, compare to actuals,
and compare against a naive run-rate baseline. The Gamma-Gamma independence assumption (spend per purchase does not
depend on frequency) is tested before use.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import minimize
from scipy.special import gammaln, hyp2f1

from custseg import config, viz
from custseg.features import revenue_orders

OUT = config.ANALYTICS_DIR / "customer_lifetime_value"
WEEK = 7.0


# ============================================================================================ data
def rft(as_of: str, start: str | None = None) -> pd.DataFrame:
    """Per customer: x = repeat purchase days, t_x = weeks first->last, age (T) = weeks first->as_of, m = mean repeat value."""
    o = revenue_orders()
    o = o[o.purchase_ts < pd.Timestamp(as_of)]
    if start:
        o = o[o.purchase_ts >= pd.Timestamp(start)]
    day = o.assign(d=o.purchase_ts.dt.normalize()).groupby(["customer_key", "d"]).order_value.sum().reset_index()
    day = day.sort_values(["customer_key", "d"])
    g = day.groupby("customer_key")
    first, last = g.d.min(), g.d.max()
    n = g.size()
    # mean value of *repeat* purchase days (first purchase excluded, as in the Gamma-Gamma paper)
    rep = day[day.d > day.customer_key.map(first)].groupby("customer_key").order_value.mean()
    out = pd.DataFrame({"x": n - 1, "t_x": (last - first).dt.days / WEEK,
                        "age": (pd.Timestamp(as_of) - first).dt.days / WEEK, "m": rep})
    out["first_value"] = day.drop_duplicates("customer_key").set_index("customer_key").order_value
    return out


# ============================================================================================ BG/NBD
def _bgnbd_nll(logp, x, tx, T, w):
    r, alpha, a, b = np.exp(logp)
    a1 = gammaln(r + x) - gammaln(r) + r * np.log(alpha)
    a2 = gammaln(a + b) + gammaln(b + x) - gammaln(b) - gammaln(a + b + x)
    a3 = -(r + x) * np.log(alpha + T)
    with np.errstate(divide="ignore", invalid="ignore"):
        a4 = np.where(x > 0, np.log(a) - np.log(np.maximum(b + x - 1, 1e-12)) - (r + x) * np.log(alpha + tx), -np.inf)
    return -(w * (a1 + a2 + np.logaddexp(a3, a4))).sum()


def fit_bgnbd(d: pd.DataFrame) -> dict:
    # likelihood over unique (x, t_x, T) rows weighted by count: identical result, ~50x fewer evaluations
    u = d.groupby(["x", "t_x", "age"]).size().reset_index(name="w")
    x, tx, T, w = u.x.values.astype(float), u.t_x.values, u["age"].values, u.w.values.astype(float)
    best = None
    for start in ([0.0, 1.0, 0.0, 0.0], [-1.0, 2.0, -1.0, 1.0], [0.5, 3.0, 0.5, 2.0]):
        r = minimize(_bgnbd_nll, np.array(start), args=(x, tx, T, w), method="L-BFGS-B",
                     bounds=[(-8, 8), (-8, 12), (-8, 8), (-8, 8)])
        if best is None or r.fun < best.fun:
            best = r
    r_, alpha, a, b = np.exp(best.x)
    return {"r": r_, "alpha": alpha, "a": a, "b": b, "nll": float(best.fun), "converged": bool(best.success)}


def bgnbd_expected(p: dict, t: float, x, tx, T) -> np.ndarray:
    """E[# repeat purchases in (T, T+t] | x, t_x, T]."""
    r, alpha, a, b = p["r"], p["alpha"], p["a"], p["b"]
    x = np.asarray(x, float)
    hyp = hyp2f1(r + x, b + x, a + b + x - 1, t / (alpha + T + t))
    num = (a + b + x - 1) / (a - 1) * (1 - ((alpha + T) / (alpha + T + t)) ** (r + x) * hyp)
    return num * p_alive(p, x, tx, T)


def p_alive(p: dict, x, tx, T) -> np.ndarray:
    r, alpha, a, b = p["r"], p["alpha"], p["a"], p["b"]
    x = np.asarray(x, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(x > 0, a / (b + x - 1) * ((alpha + T) / (alpha + tx)) ** (r + x), 0.0)
    return 1.0 / (1.0 + term)


# ============================================================================================ Gamma-Gamma
def _gg_nll(logp, x, m):
    p, q, v = np.exp(logp)
    ll = (gammaln(p * x + q) - gammaln(p * x) - gammaln(q) + q * np.log(v) + (p * x - 1) * np.log(m)
          + (p * x) * np.log(x) - (p * x + q) * np.log(x * m + v))
    return -ll.sum()


def fit_gamma_gamma(d: pd.DataFrame) -> dict:
    rep = d[d.x > 0]
    x, m = rep.x.values.astype(float), rep.m.values
    best = None
    for start in ([0.0, 0.0, 0.0], [1.0, 1.0, 3.0], [2.0, 1.0, 5.0]):
        r = minimize(_gg_nll, np.array(start), args=(x, m), method="L-BFGS-B", bounds=[(-8, 8), (-8, 8), (-8, 12)])
        if best is None or r.fun < best.fun:
            best = r
    p, q, v = np.exp(best.x)
    return {"p": p, "q": q, "v": v, "nll": float(best.fun), "converged": bool(best.success), "n_fit": int(len(rep))}


def gg_expected_value(g: dict, x, m) -> np.ndarray:
    p, q, v = g["p"], g["q"], g["v"]
    x = np.asarray(x, float)
    m = np.nan_to_num(np.asarray(m, float))
    return (p * v + p * x * m) / (p * x + q - 1)


# ============================================================================================ run
def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    cal_end, end = config.CLV_CALIBRATION_END, config.ANALYSIS_DATE
    holdout_weeks = (pd.Timestamp(end) - pd.Timestamp(cal_end)).days / WEEK

    # ---- 1. time-based validation of BG/NBD
    cal = rft(cal_end)
    hold = rft(end)  # full-period stats; holdout repeat days = full x - calibration x for calibration customers
    cal["actual_holdout"] = (hold.x.reindex(cal.index) - cal.x).clip(lower=0)
    pc = fit_bgnbd(cal)
    cal["pred_holdout"] = bgnbd_expected(pc, holdout_weeks, cal.x, cal.t_x, cal.age)
    cal["naive_holdout"] = cal.x / cal.age.clip(lower=1) * holdout_weeks   # run-rate baseline
    cal["x_group"] = np.where(cal.x >= 3, "3+", cal.x.astype(int).astype(str))
    by = cal.groupby("x_group")[["actual_holdout", "pred_holdout", "naive_holdout"]].mean()
    by["customers"] = cal.groupby("x_group").size()
    val = {
        "calibration_customers": int(len(cal)), "holdout_weeks": round(holdout_weeks, 1),
        "actual_total": float(cal.actual_holdout.sum()), "bgnbd_total": float(cal.pred_holdout.sum()),
        "naive_total": float(cal.naive_holdout.sum()),
        "bgnbd_mae": float((cal.pred_holdout - cal.actual_holdout).abs().mean()),
        "naive_mae": float((cal.naive_holdout - cal.actual_holdout).abs().mean()),
        "bgnbd_spearman": float(stats.spearmanr(cal.pred_holdout, cal.actual_holdout).statistic),
        "naive_spearman": float(stats.spearmanr(cal.naive_holdout, cal.actual_holdout).statistic),
        "share_customers_repeating_in_holdout": float((cal.actual_holdout > 0).mean()),
    }
    # ranking quality: top-decile capture of holdout repeaters
    top = cal.pred_holdout.rank(ascending=False, method="first") <= len(cal) * 0.1
    val["bgnbd_top10pct_capture"] = float(cal.actual_holdout[top].sum() / max(cal.actual_holdout.sum(), 1))
    by.to_csv(OUT / "bgnbd_holdout_by_frequency.csv")

    # ---- 2. Gamma-Gamma assumption check + full-period fit
    full = rft(end)
    rep = full[full.x > 0]
    corr = stats.pearsonr(rep.x, rep.m)
    assumption = {"repeat_customers": int(len(rep)), "pearson_r_frequency_vs_value": float(corr.statistic),
                  "p_value": float(corr.pvalue), "passes": bool(abs(corr.statistic) < 0.3)}
    pf = fit_bgnbd(full)
    gg = fit_gamma_gamma(full)
    horizon = config.CLV_HORIZON_DAYS / WEEK
    full["expected_purchases_12m"] = bgnbd_expected(pf, horizon, full.x, full.t_x, full.age)
    full["p_alive"] = p_alive(pf, full.x, full.t_x, full.age)
    full["expected_value_per_purchase"] = gg_expected_value(gg, full.x, full.m)
    full["predicted_clv_12m"] = full.expected_purchases_12m * full.expected_value_per_purchase
    hist = revenue_orders().groupby("customer_key").order_value.sum()
    full["historical_clv"] = hist.reindex(full.index).round(2)
    full["clv_tier"] = pd.qcut(full.predicted_clv_12m.rank(method="first"), [0, .5, .8, .95, 1],
                               labels=["Low (bottom 50%)", "Medium (50-80%)", "High (80-95%)", "Top 5%"])
    res = full.reset_index().rename(columns={"index": "customer_key"})
    res = res[["customer_key", "x", "t_x", "age", "historical_clv", "expected_purchases_12m", "p_alive",
               "expected_value_per_purchase", "predicted_clv_12m", "clv_tier"]].rename(
        columns={"x": "repeat_purchase_days", "t_x": "t_x_weeks", "age": "age_weeks"})
    res.to_csv(OUT / "customer_clv.csv", index=False)

    summary = {"bgnbd_calibration_params": pc, "bgnbd_full_params": pf, "gamma_gamma_params": gg,
               "validation": val, "gamma_gamma_assumption": assumption,
               "population_mean_value_gg": float(gg["p"] * gg["v"] / (gg["q"] - 1)),
               "predicted_revenue_12m_total": float(res.predicted_clv_12m.sum()),
               "expected_purchases_12m_total": float(res.expected_purchases_12m.sum()),
               "historical_revenue_total": float(res.historical_clv.sum()),
               "historical_clv_quantiles": res.historical_clv.quantile([.5, .8, .9, .99]).round(2).to_dict()}
    (OUT / "clv_summary.json").write_text(json.dumps(summary, indent=2, default=float), encoding="utf-8")
    _figures(cal, by, res)
    print(f"[clv] BG/NBD holdout: actual {val['actual_total']:.0f} vs predicted {val['bgnbd_total']:.0f} repeat days "
          f"(naive {val['naive_total']:.0f}); GG corr r={assumption['pearson_r_frequency_vs_value']:.3f}")
    return {"customers": res, "summary": summary, "by_frequency": by}


def _figures(cal, by, res) -> None:
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    xs = np.arange(len(by))
    w = 0.27
    for i, (col, lab, c) in enumerate([("actual_holdout", "Actual", viz.NEUTRAL), ("pred_holdout", "BG/NBD", viz.BLUE),
                                        ("naive_holdout", "Run-rate baseline", viz.ORANGE)]):
        ax.bar(xs + (i - 1) * w, by[col], width=w - 0.03, color=c, label=lab)
    ax.set_xticks(xs, [f"{g}\n(n={n:,})" for g, n in zip(by.index, by.customers)])
    ax.set_xlabel("repeat purchase days in calibration period")
    ax.set_ylabel("mean repeat purchases in holdout")
    ax.set_title("BG/NBD holdout validation (calibration < 2018-03-01, holdout 6 months)")
    ax.legend(loc="upper left")
    viz.save(fig, OUT / "bgnbd_holdout_validation.png")

    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    v = res.historical_clv.clip(upper=res.historical_clv.quantile(0.99))
    ax.hist(v, bins=60, color=viz.BLUE, edgecolor=viz.SURFACE, linewidth=0.5)
    ax.axvline(res.historical_clv.median(), color=viz.INK2, lw=1, ls="--")
    ax.text(res.historical_clv.median(), ax.get_ylim()[1] * 0.92, f"  median R$ {res.historical_clv.median():,.0f}",
            fontsize=8, color=viz.INK2)
    ax.set_xlabel("historical CLV (R$, clipped at p99)")
    ax.set_ylabel("customers")
    ax.set_title("Historical CLV distribution")
    viz.save(fig, OUT / "historical_clv_distribution.png")
