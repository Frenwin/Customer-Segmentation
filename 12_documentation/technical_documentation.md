# Technical Documentation

## Stack
Python 3.10 (pandas, NumPy, SciPy, scikit-learn, SQLAlchemy/psycopg2, matplotlib) · PostgreSQL 16 (Docker,
port 5435) · Power BI Desktop (PBIP: TMDL + PBIR, DirectQuery) · Jupyter (nbclient-executed notebooks).

## Code map (`src/custseg`)

| Module | Responsibility |
|---|---|
| `config.py` | every parameter (paths, window, analysis date, revenue statuses, seeds, K range, thresholds, DB URL) |
| `db.py` | engine, SQL-file runner with `{{PLACEHOLDER}}` substitution, COPY bulk loader |
| `ingest.py` | Layer 1 raw load (TEXT, as-is) + dataset manifest with SHA-256 |
| `warehouse.py` | executes staging → warehouse → data-mart SQL |
| `validation.py` | 26 data-quality checks (PRD 4.3) with severity/tolerance; FAIL stops the pipeline |
| `features.py` | customer features at any snapshot date; reconciliation with the SQL mart; screening rules |
| `eda.py` | raw profiling + univariate / bivariate / multivariate EDA |
| `segmentation.py` | E1/E2/E3 experiments, metrics, stability, interpretability, two-stage selection, experiment log |
| `clv.py` | BG/NBD + Gamma-Gamma (own MLE implementation), time-based validation |
| `final_segmentation.py` | rule-based naming, profiles, strategy library, migration, publishing to `mart` |
| `analytics.py` | churn threshold, period retention, cohort, churn drivers, market basket (Apriori), geography, patterns, Pareto |
| `kpi.py` | KPI dictionary with baselines and data-derived targets |
| `report.py` | all generated markdown deliverables + data dictionary |
| `notebooks.py` | builds and executes the 13 PRD notebooks |
| `viz.py` | shared figure style / palette |
| `pipeline.py` | orchestrator (`python -m custseg.pipeline [--reuse-experiments] [--from STEP]`) |

## Database schemas
`raw` (source copy) · `staging` (typed, flagged) · `dw` (star schema: `fact_sales`, `fact_orders`,
`fact_cancellations`, `dim_customer`, `dim_product`, `dim_date`, `dim_location`, `dim_payment_method`) ·
`mart` (customer analytics + Python outputs) · `pbi` (18 views for Power BI). Column-level documentation:
`03_data_dictionary/`.

## Reproducibility (PRD 12.1)
- Fixed seeds everywhere (`config.SEED`, `SEEDS`, bootstrap/sample seeds derived deterministically).
- Dataset version = hash of the source-file SHA-256s (`02_data/dataset_manifest.json`), stored in every experiment row.
- Every experiment configuration and metric is in `06_experimental_design/experiment_tracking.xlsx`.
- SQL ↔ pandas feature parity is asserted on every run.
- Power BI measures are validated against SQL (`11_powerbi/validate_measures.py`).

## Known limitations
- No cost, discount, demographic, campaign or web-activity data in Olist → revenue (not profit), no engagement KPIs
  beyond purchases, campaign performance only as a placeholder.
- 97 % one-time buyers: frequency is near-constant; retention metrics are structurally low.
- Inter-purchase gaps are right-censored by the 20-month window → T = 278 days is a lower bound.
- Ward and silhouette run on samples (O(n²)); DBSCAN was exploratory only.
