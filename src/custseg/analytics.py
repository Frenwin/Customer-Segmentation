"""Comprehensive customer analytics (PRD 6.3 - 6.8): retention, churn, cohort, market basket, geography, patterns.

Definitions (used identically in the KPI dictionary, the data mart and the Power BI measures):

* Inactivity (churn) threshold T  = P90 of the gap between consecutive purchase occasions of repeat customers
                                    (gaps < 1 day are split orders of one occasion and are excluded)
* Churned (snapshot)              = recency_days > T at the analysis date. Rule-based status, NOT a prediction.
* Period retention (3-month)      = eligible = customers who purchased in period P-1;
                                    retention = eligible who purchase again in P / eligible; churn = 1 - retention
* Reactivation rate               = customers inactive in P-1 (purchased before P-1, not in P-1) who purchase in P
                                    / those inactive customers
"""
from __future__ import annotations

import itertools
import json
from collections import Counter

import numpy as np
import pandas as pd
from scipy import stats

from custseg import config, db, viz
from custseg.features import customer_mart, revenue_lines, revenue_orders

A = config.ANALYTICS_DIR


def _out(sub: str):
    p = A / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


# ============================================================================================ churn threshold
def purchase_gaps() -> pd.Series:
    o = revenue_orders().sort_values(["customer_key", "purchase_ts"])
    gap = o.groupby("customer_key").purchase_ts.diff().dt.total_seconds() / 86400
    return gap.dropna()


def churn_threshold() -> dict:
    g = purchase_gaps()
    real = g[g >= 1]
    t = int(np.ceil(real.quantile(0.90)))
    return {"threshold_days": t, "n_gaps": int(len(g)), "n_gaps_ge_1d": int(len(real)),
            "share_same_day_gaps": float((g < 1).mean()),
            "gap_quantiles": {f"p{int(q * 100)}": float(real.quantile(q)) for q in (.25, .5, .75, .8, .9, .95)},
            "rule": "P90 of inter-purchase gaps >= 1 day among repeat customers",
            "caveat": "gaps are right-censored by the 20-month window, so long gaps are under-observed; "
                      "T is therefore a lower bound of the true purchase cycle"}


# ============================================================================================ retention
PERIOD_MONTHS = 3


def periods() -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Consecutive 3-month periods ending exactly at the window end (2018-06..08 is the last one)."""
    end = pd.Timestamp(config.WINDOW_END)
    start = pd.Timestamp(config.WINDOW_START)
    out = []
    e = end
    while e - pd.DateOffset(months=PERIOD_MONTHS) >= start:
        s = e - pd.DateOffset(months=PERIOD_MONTHS)
        out.append((s, e))
        e = s
    return out[::-1]


def period_retention() -> pd.DataFrame:
    o = revenue_orders()
    ps = periods()
    buyers = [set(o[(o.purchase_ts >= s) & (o.purchase_ts < e)].customer_key) for s, e in ps]
    rows = []
    for i in range(1, len(ps)):
        s, e = ps[i]
        prev = buyers[i - 1]
        before_prev = set(o[o.purchase_ts < ps[i - 1][0]].customer_key)
        inactive = before_prev - prev
        cur = buyers[i]
        retained = len(prev & cur)
        react = len(inactive & cur)
        rows.append({"period_start": s.date(), "period_end": (e - pd.Timedelta(days=1)).date(),
                     "period": f"{s:%b}–{(e - pd.Timedelta(days=1)):%b %y}",
                     "eligible_customers": len(prev), "retained_customers": retained,
                     "retention_rate": retained / len(prev), "churned_customers": len(prev) - retained,
                     "churn_rate": 1 - retained / len(prev), "inactive_customers": len(inactive),
                     "reactivated_customers": react, "reactivation_rate": react / len(inactive) if inactive else np.nan,
                     "purchasing_customers": len(cur), "new_customers": len(cur - prev - before_prev)})
    return pd.DataFrame(rows)


def retention_analysis(seg: pd.Series | None = None) -> dict:
    out = _out("retention_analysis")
    pr = period_retention()
    pr.to_csv(out / "period_retention.csv", index=False)
    cm = customer_mart()
    rep = float(cm.is_repeat_customer.mean())
    res = {"repeat_purchase_rate": rep, "repeat_customers": int(cm.is_repeat_customer.sum()),
           "one_time_customers": int((~cm.is_repeat_customer).sum()), "period_retention": pr}
    # repeat-purchase rate trend by acquisition cohort quarter, only cohorts with >= 6 months of observation
    cm2 = cm.assign(cq=cm.cohort_month.dt.to_period("Q").astype(str))
    obs_ok = cm2.cohort_month <= pd.Timestamp(config.ANALYSIS_DATE) - pd.DateOffset(months=6)
    # 6-month repeat rate per cohort (equal observation length -> comparable over time)
    o = revenue_orders().sort_values("purchase_ts")
    first = o.groupby("customer_key").purchase_ts.min()
    second = o.groupby("customer_key").purchase_ts.apply(lambda s: s.iloc[1] if len(s) > 1 else pd.NaT)
    within6 = (second - first).dt.days <= 182
    cm2["repeat_within_6m"] = within6.reindex(cm2.index).fillna(False)
    trend = cm2[obs_ok].groupby("cq").agg(customers=("frequency", "size"), repeat_6m=("repeat_within_6m", "mean"))
    trend.to_csv(out / "repeat_rate_6m_by_cohort_quarter.csv")
    res["repeat_6m_by_cohort"] = trend
    if seg is not None:
        res["by_segment"] = cm.groupby(seg).is_repeat_customer.mean()
    _fig_retention(pr, trend, out)
    return res


def _fig_retention(pr, trend, out):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.2))
    ax = axes[0]
    ax.plot(range(len(pr)), pr.retention_rate * 100, color=viz.BLUE, marker="o", ms=5, label="retention")
    ax.plot(range(len(pr)), pr.reactivation_rate * 100, color=viz.ORANGE, marker="o", ms=5, label="reactivation")
    ax.set_xticks(range(len(pr)), [p.replace("-", "\n") for p in pr.period], fontsize=7)
    ax.set_ylabel("% of eligible customers")
    ax.set_title("3-month period retention & reactivation")
    ax.legend()
    ax = axes[1]
    ax.bar(range(len(trend)), trend.repeat_6m * 100, color=viz.BLUE, width=0.65)
    ax.set_xticks(range(len(trend)), trend.index, fontsize=7)
    for i, v in enumerate(trend.repeat_6m * 100):
        ax.text(i, v, f"{v:.1f}%", ha="center", va="bottom", fontsize=7, color=viz.INK2)
    ax.set_ylabel("% repeating within 6 months")
    ax.set_title("Second purchase within 6 months, by acquisition quarter")
    viz.save(fig, out / "retention_overview.png")


# ============================================================================================ cohort
def cohort_analysis() -> dict:
    out = _out("cohort_analysis")
    c = db.query("SELECT * FROM mart.cohort_retention ORDER BY cohort_month, month_index")
    mat = c.pivot(index="cohort", columns="month_index", values="retention_rate")
    rev = c.pivot(index="cohort", columns="month_index", values="revenue")
    sizes = c.groupby("cohort").cohort_size.first()
    mat.to_csv(out / "cohort_retention_matrix.csv")
    rev.to_csv(out / "cohort_revenue_matrix.csv")
    summary = pd.DataFrame({"cohort_size": sizes, "month1_retention": mat.get(1), "month3_retention": mat.get(3),
                            "revenue_m0": rev.get(0), "revenue_total": rev.sum(axis=1)})
    summary["revenue_after_m0_share"] = 1 - summary.revenue_m0 / summary.revenue_total
    summary.to_csv(out / "cohort_summary.csv")
    import matplotlib.pyplot as plt
    show = mat.drop(columns=[0]).iloc[:, :12] * 100
    fig, ax = plt.subplots(figsize=(9, 5.2))
    im = ax.imshow(show.values, cmap=viz.BLUES, aspect="auto", vmin=0, vmax=np.nanpercentile(show.values, 98))
    ax.set_xticks(range(show.shape[1]), show.columns)
    ax.set_yticks(range(len(show)), [f"{i}  (n={sizes[i]:,})" for i in show.index], fontsize=7)
    for (i, j), v in np.ndenumerate(show.values):
        if not np.isnan(v):
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6,
                    color="#ffffff" if v > np.nanpercentile(show.values, 70) else viz.INK2)
    ax.grid(False)
    ax.set_xlabel("months since first purchase")
    ax.set_title("Monthly cohort retention (% of cohort purchasing again in month k)")
    fig.colorbar(im, ax=ax, shrink=0.7, label="%")
    viz.save(fig, out / "cohort_retention_heatmap.png")
    return {"matrix": mat, "revenue": rev, "summary": summary,
            "avg_month1_retention": float(mat[1].mean()), "avg_month3_retention": float(mat[3].mean())}


# ============================================================================================ churn
def churn_analysis(threshold: int) -> dict:
    """Snapshot churn status + which first-order experiences go with never coming back (PRD 6.5)."""
    out = _out("churn_analysis")
    cm = customer_mart().copy()
    cm["is_churned"] = cm.recency_days > threshold
    res = {"threshold_days": threshold, "churned_customers": int(cm.is_churned.sum()),
           "active_customers": int((~cm.is_churned).sum()), "churn_rate_snapshot": float(cm.is_churned.mean())}
    # inactivity distribution
    bins = [0, 30, 90, 180, threshold, 400, 10_000]
    labels = ["0-30", "31-90", "91-180", f"181-{threshold}", f"{threshold + 1}-400", ">400"]
    cm["inactivity_band"] = pd.cut(cm.recency_days, bins, labels=labels, include_lowest=True)
    inact = cm.inactivity_band.value_counts().reindex(labels)
    inact.to_csv(out / "inactivity_distribution.csv")
    res["inactivity_distribution"] = inact

    # behavioural patterns: customers with a full observation window (first purchase >= T days ago);
    # outcome = never returned within T days of the first purchase
    o = revenue_orders().sort_values("purchase_ts")
    first = o.drop_duplicates("customer_key").set_index("customer_key")
    second_ts = o.groupby("customer_key").purchase_ts.apply(lambda s: s.iloc[1] if len(s) > 1 else pd.NaT)
    eligible = first[first.purchase_ts <= pd.Timestamp(config.ANALYSIS_DATE) - pd.Timedelta(days=threshold)].copy()
    eligible["returned"] = ((second_ts.reindex(eligible.index) - eligible.purchase_ts).dt.days <= threshold)
    eligible["returned"] = eligible.returned.fillna(False)
    lines = revenue_lines()
    top_cat = lines.merge(first[["order_key"]].reset_index(), on=["order_key", "customer_key"]) \
        .sort_values("line_total", ascending=False).drop_duplicates("customer_key").set_index("customer_key")
    eligible["first_category_group"] = top_cat.category_group.reindex(eligible.index)
    eligible["review_band"] = eligible.review_score.map(lambda s: "no review" if pd.isna(s) else f"{int(s)} star")
    eligible["delivery"] = eligible.is_late.map({True: "late", False: "on time"}).fillna("not delivered/unknown")
    eligible["installments_band"] = pd.cut(eligible.installments.fillna(1), [-1, 1, 3, 6, 30],
                                           labels=["1x", "2-3x", "4-6x", "7x+"])
    eligible["value_band"] = pd.qcut(eligible.order_value, 4, labels=["Q1 low", "Q2", "Q3", "Q4 high"])
    eligible["state"] = customer_mart().state.reindex(eligible.index)
    tests, tables = [], {}
    base = eligible.returned.mean()
    for dim in ["review_band", "delivery", "payment_type", "installments_band", "value_band", "first_category_group",
                "state"]:
        t = eligible.groupby(dim, observed=True).returned.agg(["size", "mean"]).rename(
            columns={"size": "customers", "mean": "return_rate"})
        t = t[t.customers >= 200]
        t["lift_vs_base"] = t.return_rate / base
        tables[dim] = t.sort_values("return_rate", ascending=False)
        ct = pd.crosstab(eligible[dim], eligible.returned)
        ct = ct[ct.sum(axis=1) >= 200]
        chi2, p, dof, _ = stats.chi2_contingency(ct)
        n = ct.values.sum()
        v = np.sqrt(chi2 / (n * (min(ct.shape) - 1)))
        tests.append({"dimension": dim, "chi2": chi2, "dof": dof, "p_value": p, "cramers_v": v,
                      "min_rate": t.return_rate.min(), "max_rate": t.return_rate.max()})
    tests = pd.DataFrame(tests).sort_values("cramers_v", ascending=False)
    tests.to_csv(out / "churn_driver_tests.csv", index=False)
    pd.concat({k: v for k, v in tables.items()}, names=["dimension", "value"]).to_csv(out / "return_rate_by_dimension.csv")
    # continuous: Mann-Whitney on review score / delivery days / value
    mw = []
    for c in ["review_score", "delivery_days", "order_value", "freight_value", "installments"]:
        a = eligible.loc[eligible.returned, c].dropna()
        b = eligible.loc[~eligible.returned, c].dropna()
        u = stats.mannwhitneyu(a, b)
        mw.append({"feature": c, "median_returned": a.median(), "median_not_returned": b.median(),
                   "mean_returned": a.mean(), "mean_not_returned": b.mean(), "p_value": u.pvalue,
                   "rank_biserial": 1 - 2 * u.statistic / (len(a) * len(b))})
    mw = pd.DataFrame(mw)
    mw.to_csv(out / "churn_driver_mannwhitney.csv", index=False)
    res.update({"eligible_customers": int(len(eligible)), "base_return_rate": float(base),
                "historical_churn_rate": float(1 - base), "tests": tests, "tables": tables, "mannwhitney": mw})
    _fig_churn(inact, tables, base, out)
    return res


def _fig_churn(inact, tables, base, out):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.3))
    viz.hbar(axes[0], list(inact.index)[::-1][::-1], list(inact.values), title="Customers by days since last purchase")
    for ax, dim, title in [(axes[1], "review_band", "Return rate by first-order review"),
                           (axes[2], "delivery", "Return rate by first-order delivery")]:
        t = tables[dim].sort_index() if dim == "review_band" else tables[dim]
        viz.hbar(ax, list(t.index), list(t.return_rate * 100), fmt="{:.2f}%", title=title)
        ax.axvline(base * 100, color=viz.INK2, lw=1, ls="--")
    viz.save(fig, out / "churn_overview.png")


# ============================================================================================ market basket
def _apriori(baskets: list[frozenset], min_count: int, max_len: int = 3) -> dict[frozenset, int]:
    counts: dict[frozenset, int] = {}
    c1 = Counter(i for b in baskets for i in b)
    freq = {frozenset([i]): n for i, n in c1.items() if n >= min_count}
    counts.update(freq)
    level = list(freq)
    for size in range(2, max_len + 1):
        items = sorted({i for s in level for i in s})
        cand = Counter()
        for b in baskets:
            bi = sorted(i for i in b if i in items)
            if len(bi) < size:
                continue
            for comb in itertools.combinations(bi, size):
                fs = frozenset(comb)
                if all(frozenset(sub) in counts for sub in itertools.combinations(comb, size - 1)):
                    cand[fs] += 1
        level = [s for s, n in cand.items() if n >= min_count]
        counts.update({s: cand[s] for s in level})
        if not level:
            break
    return counts


def _rules(counts: dict[frozenset, int], n: int, level: str) -> pd.DataFrame:
    rows = []
    for s, nxy in counts.items():
        if len(s) < 2:
            continue
        for k in range(1, len(s)):
            for ante in itertools.combinations(sorted(s), k):
                a = frozenset(ante)
                c = s - a
                na, nc = counts.get(a), counts.get(c)
                if not na or not nc:
                    continue
                conf = nxy / na
                lift = conf / (nc / n)
                rows.append({"level": level, "antecedent": " + ".join(sorted(a)), "consequent": " + ".join(sorted(c)),
                             "itemset_size": len(s), "support_count": nxy, "support": nxy / n, "confidence": conf,
                             "lift": lift, "antecedent_count": na, "consequent_count": nc})
    return pd.DataFrame(rows)


def market_basket() -> dict:
    """Category-level association rules on (a) single orders and (b) a customer's whole purchase history."""
    out = _out("market_basket_analysis")
    lines = revenue_lines()
    order_b = lines.groupby("order_key").category.apply(frozenset)
    cust_b = lines.groupby("customer_key").category.apply(frozenset)
    res = {}
    frames = []
    for level, baskets in [("order", order_b), ("customer", cust_b)]:
        bl = list(baskets)
        n = len(bl)
        multi = sum(len(b) > 1 for b in bl)
        counts = _apriori(bl, config.BASKET_MIN_SUPPORT_COUNT)
        r = _rules(counts, n, level)
        if len(r):
            r = r[r.lift > config.BASKET_MIN_LIFT].sort_values(["lift", "support_count"], ascending=False)
        frames.append(r)
        res[level] = {"baskets": n, "multi_category_baskets": multi, "multi_category_share": multi / n,
                      "rules": int(len(r))}
    rules = pd.concat(frames, ignore_index=True)
    rules.to_csv(out / "association_rules.csv", index=False)
    # basket size distribution
    bs = lines.groupby("order_key").size().clip(upper=6).value_counts().sort_index()
    bs.index = [str(i) if i < 6 else "6+" for i in bs.index]
    bs.to_csv(out / "basket_size_distribution.csv")
    res["rules"] = rules
    res["basket_size"] = bs
    _fig_basket(rules, out)
    return res


def _fig_basket(rules, out):
    import matplotlib.pyplot as plt
    top = rules[rules.itemset_size == 2].sort_values("support_count", ascending=False)
    top = top[top.antecedent < top.consequent].head(12)  # one direction per pair
    if not len(top):
        return
    fig, ax = plt.subplots(figsize=(7.5, 4))
    viz.hbar(ax, [f"{a} + {c}  [{lv}]" for a, c, lv in zip(top.antecedent, top.consequent, top.level)],
             list(top.lift), fmt="lift {:.1f}", title="Top category pairs by co-purchase count (label = lift)")
    viz.save(fig, out / "top_category_pairs.png")


# ============================================================================================ geography
def geographic(seg: pd.Series | None = None) -> dict:
    out = _out("geographic_analysis")
    cm = customer_mart()
    g = cm.groupby(["region", "state"]).agg(customers=("monetary", "size"), revenue=("monetary", "sum"),
                                            avg_spend=("monetary", "mean"), aov=("avg_order_value", "mean"),
                                            repeat_rate=("is_repeat_customer", "mean"),
                                            avg_review=("avg_review_score", "mean"),
                                            avg_delivery_days=("avg_delivery_days", "mean"),
                                            late_share=("late_delivery_share", "mean"),
                                            avg_freight_ratio=("freight_ratio", "mean")).reset_index()
    g["customer_share"] = g.customers / g.customers.sum()
    g["revenue_share"] = g.revenue / g.revenue.sum()
    g = g.sort_values("revenue", ascending=False)
    g.to_csv(out / "state_summary.csv", index=False)
    reg = cm.groupby("region").agg(customers=("monetary", "size"), revenue=("monetary", "sum"),
                                   avg_spend=("monetary", "mean"), avg_delivery_days=("avg_delivery_days", "mean"),
                                   avg_review=("avg_review_score", "mean"), repeat_rate=("is_repeat_customer", "mean"))
    reg["revenue_share"] = reg.revenue / reg.revenue.sum()
    reg.to_csv(out / "region_summary.csv")
    cities = cm.groupby(["city", "state"]).agg(customers=("monetary", "size"), revenue=("monetary", "sum")) \
        .sort_values("revenue", ascending=False).head(20)
    cities.to_csv(out / "top20_cities.csv")
    rho = stats.spearmanr(g.avg_delivery_days, g.avg_review)
    res = {"states": g, "regions": reg, "cities": cities,
           "delivery_vs_review_spearman": float(rho.statistic), "delivery_vs_review_p": float(rho.pvalue)}
    if seg is not None:
        sd = pd.crosstab(cm.state, seg, normalize="index")
        sd.to_csv(out / "segment_distribution_by_state.csv")
        res["segment_by_state"] = sd
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    top = g.head(12)
    viz.hbar(axes[0], list(top.state), list(top.revenue / 1e6), fmt="R$ {:.2f} M", title="Revenue by state (top 12)")
    ax = axes[1]
    ax.scatter(g.avg_delivery_days, g.avg_review, s=np.sqrt(g.customers) * 2.2, color=viz.BLUE, alpha=0.75,
               edgecolor=viz.SURFACE, linewidth=1)
    for r in g.itertuples():
        ax.annotate(r.state, (r.avg_delivery_days, r.avg_review), fontsize=7, color=viz.INK2,
                    xytext=(3, 2), textcoords="offset points")
    ax.set_xlabel("average delivery time (days)")
    ax.set_ylabel("average review score")
    ax.set_title(f"Delivery time vs satisfaction by state (Spearman rho = {rho.statistic:.2f})")
    viz.save(fig, out / "geographic_overview.png")
    return res


# ============================================================================================ purchase patterns
def purchase_patterns() -> dict:
    out = _out("purchase_behavior")
    o = revenue_orders()
    k = db.query("SELECT * FROM mart.customer_kpi_monthly ORDER BY month")
    dow = o.groupby(o.purchase_ts.dt.dayofweek).agg(orders=("order_key", "size"), revenue=("order_value", "sum"))
    dow.index = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    hour = o.groupby("purchase_hour").agg(orders=("order_key", "size"))
    lines = revenue_lines()
    cat = lines.groupby("category_group").agg(lines=("line_total", "size"), revenue=("line_total", "sum"),
                                              customers=("customer_key", "nunique")).sort_values("revenue",
                                                                                                 ascending=False)
    cat["revenue_share"] = cat.revenue / cat.revenue.sum()
    top_cats = lines.groupby("category").agg(revenue=("line_total", "sum"), lines=("line_total", "size")) \
        .sort_values("revenue", ascending=False).head(15)
    gaps = purchase_gaps()
    for name, df in [("monthly_kpi", k), ("day_of_week", dow), ("hour_of_day", hour), ("category_group", cat),
                     ("top15_categories", top_cats)]:
        df.to_csv(out / f"{name}.csv")
    peak = k.loc[k.revenue.idxmax()]
    res = {"monthly": k, "dow": dow, "hour": hour, "category_group": cat, "top_categories": top_cats,
           "peak_month": str(peak.year_month), "peak_month_revenue": float(peak.revenue),
           "peak_month_orders": int(peak.orders),
           "avg_purchase_interval_days": float(gaps[gaps >= 1].mean()),
           "median_purchase_interval_days": float(gaps[gaps >= 1].median()),
           "avg_items_per_order": float(o.n_items.mean()), "aov": float(o.order_value.mean()),
           "credit_card_share": float((o.payment_type == "credit_card").mean()),
           "avg_installments": float(o.installments.mean())}
    # H1 2017 vs H1 2018 growth (same months -> no seasonality bias)
    h17 = k[(k.month >= pd.Timestamp("2017-01-01").date()) & (k.month < pd.Timestamp("2017-09-01").date())]
    h18 = k[(k.month >= pd.Timestamp("2018-01-01").date()) & (k.month < pd.Timestamp("2018-09-01").date())]
    res["jan_aug_revenue_growth_yoy"] = float(h18.revenue.sum() / h17.revenue.sum() - 1)
    res["jan_aug_orders_growth_yoy"] = float(h18.orders.sum() / h17.orders.sum() - 1)
    _fig_patterns(k, dow, hour, cat, out)
    return res


def _fig_patterns(k, dow, hour, cat, out):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(12, 6.6))
    ax = axes[0, 0]
    x = pd.to_datetime(k.month)
    ax.plot(x, k.revenue / 1e3, color=viz.BLUE)
    ax.set_title("Monthly revenue (R$ thousand)")
    i = k.revenue.idxmax()
    ax.annotate(f"peak {k.year_month[i]}\nR$ {k.revenue[i] / 1e6:.2f} M", (x[i], k.revenue[i] / 1e3), fontsize=7,
                color=viz.INK2, xytext=(8, -18), textcoords="offset points")
    ax = axes[0, 1]
    ax.plot(x, k.new_customers, color=viz.BLUE, label="new customers")
    ax.plot(x, k.returning_customers, color=viz.ORANGE, label="returning customers")
    ax.set_title("Monthly purchasing customers: new vs returning")
    ax.legend()
    ax = axes[1, 0]
    ax.bar(dow.index, dow.orders, color=viz.BLUE, width=0.65)
    ax.set_title("Orders by day of week")
    ax2 = axes[1, 1]
    ax2.bar(hour.index, hour.orders, color=viz.BLUE, width=0.75)
    ax2.set_title("Orders by hour of day")
    ax2.set_xticks(range(0, 24, 3))
    fig.tight_layout()
    viz.save(fig, out / "purchase_patterns.png")
    fig, ax = plt.subplots(figsize=(7, 4.4))
    viz.hbar(ax, list(cat.index), list(cat.revenue / 1e6), fmt="R$ {:.2f} M", title="Revenue by category group")
    viz.save(fig, out / "category_group_revenue.png")


def revenue_pareto() -> pd.DataFrame:
    """Cumulative revenue share vs share of customers ranked by revenue (1% steps)."""
    m = customer_mart().monetary.sort_values(ascending=False).values
    cum = np.cumsum(m) / m.sum()
    pct = np.arange(1, 101) / 100
    idx = np.ceil(pct * len(m)).astype(int) - 1
    out = pd.DataFrame({"customer_pct": pct.round(2), "cum_revenue_share": cum[idx]})
    out.to_csv(_out("customer_lifetime_value") / "revenue_pareto.csv", index=False)
    return out


def run_all(seg: pd.Series | None, threshold: int) -> dict:
    res = {"pareto": revenue_pareto(), "retention": retention_analysis(seg), "cohort": cohort_analysis(), "churn": churn_analysis(threshold),
           "basket": market_basket(), "geo": geographic(seg), "patterns": purchase_patterns()}
    summ = {
        "repeat_purchase_rate": res["retention"]["repeat_purchase_rate"],
        "pooled_period_retention": float(res["retention"]["period_retention"].retained_customers.sum() / res["retention"]["period_retention"].eligible_customers.sum()),
        "pooled_reactivation_rate": float(res["retention"]["period_retention"].reactivated_customers.sum() / res["retention"]["period_retention"].inactive_customers.sum()),
        "avg_month1_cohort_retention": res["cohort"]["avg_month1_retention"],
        "churn_rate_snapshot": res["churn"]["churn_rate_snapshot"],
        "historical_churn_rate": res["churn"]["historical_churn_rate"],
        "basket": {k: v for k, v in res["basket"].items() if k in ("order", "customer")},
        "delivery_vs_review_spearman": res["geo"]["delivery_vs_review_spearman"],
        "peak_month": res["patterns"]["peak_month"],
        "jan_aug_revenue_growth_yoy": res["patterns"]["jan_aug_revenue_growth_yoy"],
    }
    (A / "analytics_summary.json").write_text(json.dumps(summ, indent=2, default=float), encoding="utf-8")
    return res
