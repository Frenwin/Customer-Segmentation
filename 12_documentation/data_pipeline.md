# Data Pipeline

```
02_data/raw/*.csv ──ingest──▶ raw.*  ──01_staging.sql──▶ staging.*  ──01_warehouse.sql──▶ dw.* (star schema)
                                                                                   │
                                     01_data_mart.sql ◀────────────────────────────┘
                                            │
                       mart.customer_rfm / customer_behavior / customer_kpi_monthly / cohort_retention
                                            │
                 Python (src/custseg): validation · features · experiments · CLV · final segmentation ·
                 analytics · KPI  ──▶ mart.customer_segmentation / segment_profile / segment_migration /
                 customer_clv / period_retention / product_affinity / revenue_pareto / model_comparison /
                 kpi_dictionary
                                            │
                                 02_powerbi_views.sql ──▶ pbi.* ──DirectQuery──▶ Power BI
```

| Step (`python -m custseg.pipeline`) | Module / SQL | Output | Time* |
|---|---|---|---:|
| ingest | `custseg.ingest` | `raw.*` (TEXT, as-is) + `02_data/dataset_manifest.json` (SHA-256) | ~25 s |
| warehouse | `05_.../sql/staging`, `warehouse`, `data_mart` | `staging.*`, `dw.*`, `mart.*` | ~50 s |
| validate | `custseg.validation` | 26 data-quality checks → `05_.../validation/` (stops on FAIL) | ~10 s |
| features | `custseg.features.reconcile` | SQL mart vs pandas features, 0 mismatches | ~15 s |
| eda | `custseg.eda` | profiling + EDA figures/tables → `04_.../reports/` | ~40 s |
| experiments | `custseg.segmentation` | E1–E3 grid, stability, selection → `07_.../results/`, `06_.../experiment_tracking.xlsx`, `artifacts/` | ~26 min |
| clv | `custseg.clv` | BG/NBD + Gamma-Gamma with holdout validation → `08_.../customer_lifetime_value/` | ~10 s |
| final | `custseg.final_segmentation` | names, profiles, migration → `mart.customer_segmentation`, `mart.segment_profile` | ~1 min |
| analytics | `custseg.analytics` | retention, cohort, churn, basket, geo, patterns → `08_customer_analytics/` | ~25 s |
| kpi | `custseg.kpi` | `09_kpi_framework/` + `mart.kpi_dictionary` | ~2 s |
| serving | `02_powerbi_views.sql` | `pbi.*` views | ~1 s |
| report | `custseg.report` | all results markdown + data dictionary | ~20 s |

\* Windows 11, 16 logical cores, PostgreSQL 16 in Docker.

Options: `--reuse-experiments` (skip the 26-minute grid when `artifacts/segmentation_results.joblib` exists),
`--from <step>`. Selection only: `python -m custseg.segmentation --reselect`.

**Configuration** lives in one place: `src/custseg/config.py` (window, analysis date, revenue statuses, seeds,
K range, sample sizes, thresholds, DB URL). SQL files receive the same values through `{{PLACEHOLDER}}`
substitution (`custseg.db.run_sql_file`), so Python and SQL can never disagree on the window or revenue definition.

**Scalability (PRD 12.2):** every customer-level aggregation is SQL (`mart`), indexes on all fact foreign keys,
COPY-based bulk loads, Power BI reads pre-aggregated tables for cohort/retention/affinity/Pareto and only
revenue rows from the facts. O(n²) algorithms (Ward, silhouette, DBSCAN) run on fixed-seed samples.
