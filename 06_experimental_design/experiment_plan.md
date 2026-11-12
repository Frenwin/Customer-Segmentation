# Experiment Plan

**Objective (PRD 5.1).** Find a segmentation whose groups are internally homogeneous, clearly different from each
other, stable under data perturbation, explainable in business terms and actionable.

**Dataset.** Olist Brazilian E-Commerce Public Dataset (Kaggle: olistbr/brazilian-ecommerce), version `ca930db9b5cf`
(SHA-256 of the 9 source files). Unit of analysis: `customer_unique_id` with ≥ 1 delivered order between
2017-01-01 and 2018-08-31 → **93,104 customers**.
Snapshot (analysis) date 2018-09-01.

| ID | Approach | What varies | Runs |
|---|---|---|---:|
| E1 | RFM rule-based | quintile R & M scores, absolute F tiers (1..5+), 10-rule segment map | 1 |
| E2 | RFM + K-Means | transform {original, log1p} × scaler {Standard, Robust} × K 2–10; k-means++, n_init 10 | 36 |
| E3 | Behavioural clustering | 3 screened feature configurations × {K-Means, GMM, Ward} × K 2–10, + DBSCAN (exploratory) | 90 |

Stability for every K in the selection range 3–8: **multi-seed** (5 seeds, mean ARI vs seed 42) and
**bootstrap** (5 × 80 % subsamples, model refitted and applied to all customers, mean ARI vs the full-data labels).
Every run is logged with experiment ID, dataset version, features, preprocessing, algorithm, hyper-parameters,
metrics and cluster distribution in [experiment_tracking.xlsx](experiment_tracking.xlsx) (sheet `runs`,
127 rows). Fitted finalist models are stored in `artifacts/models/*.joblib`.

Random seeds: global seed 42; stability seeds [0, 1, 2, 3, 4]; bootstrap seeds 1000–1004; Ward
samples 2000–2004; silhouette sample seed 42 (20,000 customers).

Reproduce: `python -m custseg.segmentation` (~26 min on 16 threads) or
`python -m custseg.segmentation --reselect` (re-runs only the selection on the saved grid).
