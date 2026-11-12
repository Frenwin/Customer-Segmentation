"""Build and execute the PRD notebooks (narrative layer over the custseg package).

    python -m custseg.notebooks          # writes + executes 13 notebooks (needs the pipeline outputs + PostgreSQL)

Heavy computation lives in src/custseg (importable, reproducible); notebooks load its outputs, run light queries
and show the tables / figures with commentary.
"""
from __future__ import annotations

import nbformat
from nbclient import NotebookClient
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

from custseg import config

SETUP = """import sys, json, warnings
from pathlib import Path
ROOT = Path.cwd()
while not (ROOT / "src" / "custseg").exists():   # project root = folder that holds the package
    if ROOT == ROOT.parent:
        raise RuntimeError("run the notebook from inside the project folder")
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
from IPython.display import Image, Markdown, display
pd.set_option("display.max_columns", 40); pd.set_option("display.width", 200)
from custseg import config, db
img = lambda p, w=900: display(Image(filename=str(ROOT / p), width=w))"""

NB = {
    "04_data_profiling_eda/notebooks/01_data_profiling.ipynb": [
        ("md", "# 01 · Data Profiling\nProfile of the raw Olist files as loaded into schema `raw` (all TEXT)."),
        ("code", "man = json.loads((ROOT / '02_data/dataset_manifest.json').read_text())\n"
                 "pd.DataFrame({k: {'rows': v['rows'], 'columns': len(v['columns']), 'MB': round(v['bytes']/1e6, 1)} "
                 "for k, v in man['files'].items()}).T"),
        ("code", "prof = pd.read_csv(ROOT / '04_data_profiling_eda/reports/data_profiling.csv')\n"
                 "prof[['table','column','inferred_type','null_pct','distinct','min','p50','max']]"),
        ("code", "db.query(\"SELECT count(*) orders, count(DISTINCT customer_id) customer_ids FROM raw.orders\")"),
        ("code", "db.query(\"SELECT count(DISTINCT customer_unique_id) persons FROM raw.customers\")"),
        ("md", "**Takeaway:** `customer_id` is per order; the person is `customer_unique_id`. See "
               "`reports/data_profiling_report.md` for the full profile."),
    ],
    "04_data_profiling_eda/notebooks/02_data_quality.ipynb": [
        ("md", "# 02 · Data Quality\nResults of the 26 PRD 4.3 checks (`custseg.validation`)."),
        ("code", "dq = pd.read_csv(ROOT / '05_data_engineering/validation/data_quality_results.csv')\n"
                 "dq[['check_id','prd_rule','layer','description','violations','total','violation_share','status','handling']]"),
        ("code", "dq.status.value_counts()"),
        ("code", "pd.read_csv(ROOT / '05_data_engineering/validation/feature_reconciliation.csv')"),
        ("code", "db.query(\"SELECT order_status, count(*) n, sum(is_revenue::int) revenue_orders FROM dw.fact_orders "
                 "GROUP BY 1 ORDER BY 2 DESC\")"),
    ],
    "04_data_profiling_eda/notebooks/03_univariate_analysis.ipynb": [
        ("md", "# 03 · Univariate Analysis"),
        ("code", "pd.read_csv(ROOT / '04_data_profiling_eda/reports/univariate_summary.csv', index_col=0).round(2)"),
        ("code", "img('04_data_profiling_eda/reports/figures/univariate_distributions.png')"),
        ("code", "db.query(\"SELECT frequency, count(*) customers FROM mart.customer_rfm GROUP BY 1 ORDER BY 1\")"),
        ("md", "97 % of customers have exactly one delivered order; monetary is strongly right-skewed."),
    ],
    "04_data_profiling_eda/notebooks/04_bivariate_analysis.ipynb": [
        ("md", "# 04 · Bivariate Analysis"),
        ("code", "img('04_data_profiling_eda/reports/figures/bivariate_relationships.png')"),
        ("code", "s = json.loads((ROOT / '04_data_profiling_eda/reports/eda_summary.json').read_text())\n"
                 "{k: v for k, v in s.items() if k not in ('high_corr_pairs',)}"),
        ("code", "db.query(\"SELECT is_late, round(avg(review_score),2) review, count(*) orders FROM dw.fact_orders "
                 "WHERE is_revenue AND is_late IS NOT NULL GROUP BY 1\")"),
    ],
    "04_data_profiling_eda/notebooks/05_multivariate_analysis.ipynb": [
        ("md", "# 05 · Multivariate Analysis"),
        ("code", "img('04_data_profiling_eda/reports/figures/multivariate_correlation.png', 760)"),
        ("code", "pd.read_csv(ROOT / '04_data_profiling_eda/reports/pca_loadings.csv', index_col=0).round(3)"),
        ("code", "pd.DataFrame(json.loads((ROOT / '04_data_profiling_eda/reports/eda_summary.json').read_text())"
                 "['high_corr_pairs'], columns=['a','b','rho'])"),
    ],
    "07_customer_segmentation/01_rfm_analysis.ipynb": [
        ("md", "# 01 · RFM Analysis\nRecency = analysis date − last purchase; Frequency = distinct delivered orders; "
               "Monetary = Σ(items + freight)."),
        ("code", "rfm = db.query('SELECT recency_days, frequency, monetary FROM mart.customer_rfm')\nrfm.describe().round(2)"),
        ("code", "seg = pd.read_csv(ROOT / '02_data/processed/customer_segmentation.csv')\n"
                 "pd.crosstab(seg.r_score, seg.m_score)"),
        ("code", "seg.f_score.value_counts().sort_index()"),
        ("md", "F cannot be quantile-scored (all quintile edges = 1) → absolute tiers 1..5+."),
    ],
    "07_customer_segmentation/02_rfm_rule_based.ipynb": [
        ("md", "# 02 · Experiment 1 — RFM rule-based segmentation"),
        ("code", "from custseg.segmentation import RFM_RULES\npd.DataFrame([(n, d) for n, d, _ in RFM_RULES], "
                 "columns=['segment','rule (first match wins)'])"),
        ("code", "seg = pd.read_csv(ROOT / '02_data/processed/customer_segmentation.csv')\n"
                 "t = seg.groupby('rfm_segment').agg(customers=('customer_key','size'), revenue=('historical_clv','sum'))\n"
                 "t['customer_share'] = t.customers / t.customers.sum(); t['revenue_share'] = t.revenue / t.revenue.sum()\n"
                 "t.sort_values('revenue', ascending=False).round(3)"),
        ("code", "log = pd.read_csv(ROOT / '07_customer_segmentation/results/experiment_log.csv')\n"
                 "log[log.experiment_id == 'E1-rfm-rules'].T"),
    ],
    "07_customer_segmentation/03_kmeans_clustering.ipynb": [
        ("md", "# 03 · Experiment 2 — RFM + K-Means"),
        ("code", "g = pd.read_csv(ROOT / '07_customer_segmentation/results/grid_results.csv')\n"
                 "g[g.experiment.str.startswith('E2')][['space','k','inertia','silhouette','davies_bouldin',"
                 "'calinski_harabasz','stability_seed_ari','stability_bootstrap_ari','min_cluster_share','interpretability']].round(3)"),
        ("code", "img('07_customer_segmentation/figures/e2_kmeans_k_selection.png')"),
    ],
    "07_customer_segmentation/04_hierarchical_clustering.ipynb": [
        ("md", "# 04 · Hierarchical (Ward) clustering\nWard linkage is O(n²) in memory → fitted on 20k-customer "
               "samples; every customer assigned to the nearest sample-cluster centroid; stability = 5 different samples."),
        ("code", "g = pd.read_csv(ROOT / '07_customer_segmentation/results/grid_results.csv')\n"
                 "g[g.algorithm == 'ward'][['space','k','silhouette','davies_bouldin','stability_bootstrap_ari',"
                 "'min_cluster_share','interpretability']].round(3)"),
    ],
    "07_customer_segmentation/05_gaussian_mixture.ipynb": [
        ("md", "# 05 · Gaussian Mixture Models"),
        ("code", "g = pd.read_csv(ROOT / '07_customer_segmentation/results/grid_results.csv')\n"
                 "g[g.algorithm == 'gmm'][['space','k','bic','converged','silhouette','davies_bouldin',"
                 "'stability_seed_ari','stability_bootstrap_ari','min_cluster_share']].round(3)"),
    ],
    "07_customer_segmentation/06_behavioral_clustering.ipynb": [
        ("md", "# 06 · Experiment 3 — Behavioural clustering"),
        ("code", "pd.read_csv(ROOT / '07_customer_segmentation/results/feature_screening.csv')"),
        ("code", "img('07_customer_segmentation/figures/e3_behavioural_k_selection.png')"),
        ("code", "pd.read_csv(ROOT / '07_customer_segmentation/results/dbscan_results.csv')[['run_id','eps','n_clusters',"
                 "'noise_share','silhouette']].round(3)"),
    ],
    "07_customer_segmentation/07_model_evaluation.ipynb": [
        ("md", "# 07 · Model Evaluation (stage 1 & 2)"),
        ("code", "pd.read_csv(ROOT / '07_customer_segmentation/results/stage1_best_k_per_family.csv')[['run_id','silhouette',"
                 "'davies_bouldin','stability_bootstrap_ari','size_entropy','min_cluster_share','interpretability','composite']].round(3)"),
        ("code", "s2 = pd.read_csv(ROOT / '07_customer_segmentation/results/stage2_model_comparison.csv')\n"
                 "s2[['rank','run_id','k','own_silhouette','silhouette','davies_bouldin','calinski_harabasz',"
                 "'stability_bootstrap_ari','size_entropy','interpretability','composite']].round(3)"),
        ("code", "img('07_customer_segmentation/figures/stage2_composite.png', 700)"),
    ],
    "07_customer_segmentation/08_final_segmentation.ipynb": [
        ("md", "# 08 · Final Segmentation"),
        ("code", "json.loads((ROOT / '07_customer_segmentation/results/final_model.json').read_text())"),
        ("code", "p = pd.read_csv(ROOT / '07_customer_segmentation/results/segment_profile.csv')\n"
                 "p[['segment_id','segment_name','customers','customer_share','revenue_contribution','avg_recency_days',"
                 "'avg_frequency','avg_monetary','avg_order_value','repeat_rate','churn_rate','avg_review_score',"
                 "'late_delivery_share','avg_installments','avg_predicted_clv_12m','segment_growth_rate']].round(3)"),
        ("code", "img('07_customer_segmentation/figures/segment_customers_vs_revenue.png', 760)"),
        ("code", "img('07_customer_segmentation/figures/segment_profile_heatmap.png', 820)"),
        ("code", "img('07_customer_segmentation/figures/segment_scatter.png')"),
        ("code", "pd.read_csv(ROOT / '07_customer_segmentation/results/segment_migration_share.csv', index_col=0).round(3)"),
    ],
}


def build(execute: bool = True) -> None:
    for rel, cells in NB.items():
        nb = new_notebook()
        nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
        nb.cells = [new_code_cell(SETUP)] + [new_markdown_cell(c) if k == "md" else new_code_cell(c) for k, c in cells]
        path = config.ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if execute:
            NotebookClient(nb, timeout=600, kernel_name="python3",
                           resources={"metadata": {"path": str(path.parent)}}).execute()
        nbformat.write(nb, path)
        print(f"[nb] {rel}")


if __name__ == "__main__":
    build()
