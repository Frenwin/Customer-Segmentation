"""End-to-end pipeline.

    python -m custseg.pipeline                 # everything (experiments take ~25-35 min)
    python -m custseg.pipeline --reuse-experiments   # skip the experiment grid if artifacts/segmentation_results.joblib exists
    python -m custseg.pipeline --from final    # start at a later step (earlier outputs must exist)

Steps: ingest -> warehouse -> validate -> features -> eda -> experiments -> clv -> final -> analytics -> kpi
       -> serving (pbi views) -> report
"""
from __future__ import annotations

import argparse
import json
import time

import pandas as pd

from custseg import config, db

STEPS = ["ingest", "warehouse", "validate", "features", "eda", "experiments", "clv", "final", "analytics", "kpi",
         "serving", "report"]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="ingest", choices=STEPS)
    ap.add_argument("--reuse-experiments", action="store_true")
    a = ap.parse_args(argv)
    todo = STEPS[STEPS.index(a.start):]
    config.ensure_dirs()
    ctx: dict = {}
    t_all = time.time()

    def step(name):
        print(f"\n=== {name} " + "=" * (60 - len(name)))
        return name in todo

    if step("ingest"):
        from custseg import ingest
        ingest.load_raw()
    if step("warehouse"):
        from custseg import warehouse
        warehouse.build()
    if step("validate"):
        from custseg import validation
        validation.run()
    if step("features"):
        from custseg import features
        r = features.reconcile()
        r.to_csv(config.DE_DIR / "validation" / "feature_reconciliation.csv", index=False)
        print(f"[features] SQL mart == pandas builder on {len(r)} features (0 mismatches)")
    if step("eda"):
        from custseg import eda
        eda.run_all()
    if step("experiments"):
        from custseg import segmentation
        if a.reuse_experiments and segmentation.RESULTS_PKL.exists():
            print(f"[experiments] reusing {segmentation.RESULTS_PKL}")
        else:
            segmentation.main()

    # steps below share the churn threshold + CLV
    from custseg import analytics, clv
    th = analytics.churn_threshold()
    (config.ANALYTICS_DIR / "churn_analysis").mkdir(parents=True, exist_ok=True)
    (config.ANALYTICS_DIR / "churn_analysis" / "churn_threshold.json").write_text(json.dumps(th, indent=2))
    T = th["threshold_days"]
    if step("clv") or any(s in todo for s in ("final", "analytics", "kpi", "report")):
        ctx["clv"] = clv.run()
        db.load_df(ctx["clv"]["customers"].assign(clv_tier=lambda d: d.clv_tier.astype(str)), "customer_clv", "mart")
    if step("final") or any(s in todo for s in ("analytics", "kpi", "report")):
        from custseg import final_segmentation
        ctx["final"] = final_segmentation.run(T, ctx["clv"]["customers"])
        stage2 = ctx["final"]["res"]["stage2"]
        db.load_df(stage2, "model_comparison", "mart")
    if step("analytics") or any(s in todo for s in ("kpi", "report")):
        seg = ctx["final"]["customers"].set_index("customer_key").segment_name
        ctx["analytics"] = analytics.run_all(seg, T)
        db.load_df(ctx["analytics"]["retention"]["period_retention"].assign(
            period_start=lambda d: pd.to_datetime(d.period_start), period_end=lambda d: pd.to_datetime(d.period_end)),
            "period_retention", "mart")
        db.load_df(ctx["analytics"]["basket"]["rules"], "product_affinity", "mart")
        db.load_df(ctx["analytics"]["pareto"], "revenue_pareto", "mart")
    if step("kpi") or "report" in todo:
        from custseg import kpi
        drv = kpi.driver_context()
        kctx = {"period_retention": ctx["analytics"]["retention"]["period_retention"],
                "profile": ctx["final"]["profile"], "repeat_6m_by_cohort": ctx["analytics"]["retention"]["repeat_6m_by_cohort"],
                "threshold": T, "clv": ctx["clv"]["summary"], "churn_snapshot": ctx["analytics"]["churn"]["churn_rate_snapshot"],
                "avg_interval": ctx["analytics"]["patterns"]["avg_purchase_interval_days"], **drv}
        ctx["kpi"], ctx["kpi_segments"] = kpi.build(kctx)
        kpi.write(ctx["kpi"], ctx["kpi_segments"])
        ctx["drivers"] = drv
    if step("serving"):
        from custseg import fx
        db.run_sql_file(config.SQL_DIR / "data_mart" / "02_powerbi_views.sql",
                        {"CHURN_T": str(T), "CHURN_T1": str(T + 1), "FX": str(fx.brl_to_idr())})
        print(f"[serving] dashboard currency: Rupiah at fixed {fx.brl_to_idr():,.1f} IDR/BRL")
        n = db.query("SELECT count(*) FROM information_schema.views WHERE table_schema='pbi'").iloc[0, 0]
        print(f"[serving] {n} views in schema pbi")
    if step("report"):
        from custseg import report
        report.write_all(ctx, th)
    print(f"\n[pipeline] done in {(time.time() - t_all) / 60:.1f} min")


if __name__ == "__main__":
    main()
