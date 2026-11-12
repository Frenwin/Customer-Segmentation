"""Central configuration: paths, analysis window, seeds, database.

Every number that shapes a result lives here so a run is fully described by this file + the dataset version.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------------------------- paths
RAW_DIR = ROOT / "02_data" / "raw"
INTERIM_DIR = ROOT / "02_data" / "interim"
PROCESSED_DIR = ROOT / "02_data" / "processed"
DICT_DIR = ROOT / "03_data_dictionary"
EDA_DIR = ROOT / "04_data_profiling_eda"
EDA_REPORTS = EDA_DIR / "reports"
EDA_FIG = EDA_REPORTS / "figures"
DE_DIR = ROOT / "05_data_engineering"
SQL_DIR = DE_DIR / "sql"
EXP_DIR = ROOT / "06_experimental_design"
SEG_DIR = ROOT / "07_customer_segmentation"
SEG_RESULTS = SEG_DIR / "results"
SEG_FIG = SEG_DIR / "figures"
ANALYTICS_DIR = ROOT / "08_customer_analytics"
KPI_DIR = ROOT / "09_kpi_framework"
INSIGHTS_DIR = ROOT / "10_business_insights"
POWERBI_DIR = ROOT / "11_powerbi"
DOCS_DIR = ROOT / "12_documentation"
ARTIFACTS = ROOT / "artifacts"
MODELS_DIR = ARTIFACTS / "models"

# ---------------------------------------------------------------------------------------------- dataset
DATASET_NAME = "Olist Brazilian E-Commerce Public Dataset (Kaggle: olistbr/brazilian-ecommerce)"
DATASET_URL = "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
DATASET_LICENSE = "CC BY-NC-SA 4.0"
RAW_FILES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

# ---------------------------------------------------------------------------------------------- analysis window
# 2016 has 329 orders and a 2-month collection gap (Nov 2016 = 0, Dec 2016 = 1); Sep/Oct 2018 hold 20 orders
# (export cut-off). Both tails are excluded so every month in the window is a complete, comparable month.
WINDOW_START = "2017-01-01"
WINDOW_END = "2018-09-01"          # exclusive
ANALYSIS_DATE = "2018-09-01"       # snapshot date for Recency / churn status
# Revenue is recognised only for delivered orders (the other statuses are in-flight or cancelled).
REVENUE_STATUSES = ("delivered",)

# ---------------------------------------------------------------------------------------------- experiments
SEED = 42
SEEDS = [0, 1, 2, 3, 4, 42, 123, 2024, 7, 99]
K_RANGE = list(range(2, 11))
SILHOUETTE_SAMPLE = 20_000         # silhouette is O(n^2); evaluated on a fixed stratified sample
HIER_SAMPLE = 20_000               # Ward linkage is O(n^2) memory -> fitted on a sample, rest assigned
BOOTSTRAP_ROUNDS = 10
BOOTSTRAP_FRACTION = 0.8
CORR_DROP_THRESHOLD = 0.80         # |Spearman rho| above this -> keep only one of the pair
MIN_CLUSTER_SHARE = 0.01           # clusters below 1% of customers are reviewed (niche vs anomaly)

# CLV (BG/NBD + Gamma-Gamma): calibration / holdout split for time-based validation
CLV_CALIBRATION_END = "2018-03-01"
CLV_HORIZON_DAYS = 365

# Market basket
BASKET_MIN_SUPPORT_COUNT = 10      # an itemset must appear in >= 10 baskets
BASKET_MIN_LIFT = 1.0

# ---------------------------------------------------------------------------------------------- currency (dashboard)
# Analysis runs in BRL (source currency). The Power BI layer shows Rupiah with ONE fixed rate so every ratio is
# preserved: annual average BRL->IDR rates weighted by each year's revenue (custseg.fx.brl_to_idr()).
FX_BRL_IDR_ANNUAL = {2017: 4192.2, 2018: 3889.8}
FX_SOURCE = "ValutaFX annual average BRL/IDR 2017 & 2018 (valutafx.com/history/brl-idr-2017, -2018)"

# ---------------------------------------------------------------------------------------------- database
DB_URL = os.environ.get("CUSTSEG_DB_URL", "postgresql+psycopg2://custseg:custseg@localhost:5435/custsegdb")
PG_HOST, PG_PORT, PG_DB = "localhost", 5435, "custsegdb"


def ensure_dirs() -> None:
    for p in [INTERIM_DIR, PROCESSED_DIR, EDA_FIG, SEG_RESULTS, SEG_FIG, MODELS_DIR, KPI_DIR, INSIGHTS_DIR, DOCS_DIR]:
        p.mkdir(parents=True, exist_ok=True)
