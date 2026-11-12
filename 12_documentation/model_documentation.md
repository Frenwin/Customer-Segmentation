# Model Documentation

## Final segmentation model

| Item | Value |
|---|---|
| Run id | `E2-rfm-log-standard-kmeans-k4` |
| Algorithm | K-Means (k-means++, n_init = 10, random_state = 42), K = 4 |
| Features | `recency_days`, `frequency`, `monetary` (customer level, `mart.customer_rfm`) |
| Preprocessing | `log1p` on all three → StandardScaler (fitted on 93,104 customers) |
| Stability | bootstrap ARI 0.992 (5 × 80 % refits), multi-seed ARI 0.990 |
| Artifact | `artifacts/models/final_segmentation_model.joblib` → `{model, scaler, space, algorithm, k, segment_names}` |
| Scoring new data | `custseg.final_segmentation.predict(res, run_id, custseg.features.build_features(as_of))` |
| Output | `mart.customer_segmentation` (one row per customer) and `mart.segment_profile` |

Segment names are assigned by explicit rules on the cluster profile (`name_clusters`), not by hand:

| Rule (priority order) | Name |
|---|---|
| repeat rate ≥ 50 % → recency vs T, spend | Loyal Customers / Champions / At Risk Repeaters |
| late-delivery share ≥ 40 % or review ≤ 3 | Unhappy Customers |
| installments / basket size / freight burden ≥ 0.8 SD | Big-Ticket Installment Buyers / Multi-Item Basket Buyers / Low-Ticket Freight-Sensitive |
| average recency > 1.3 T | Lost Customers |
| average recency > 0.9 T | At Risk (median spend ≥ 1.5× population) · Hibernating (< 1×) · Need Attention |
| recency ≤ −0.8 SD | New Customers (spend < 1.2×) · Promising |
| otherwise | Big Spenders (spend ≥ 2×) · Core One-Time Buyers |

With T = 278 days this run produces **At Risk, Hibernating, New Customers, Loyal Customers**.

**Limitations.** (1) RFM clusters on a 97 % one-time-buyer base are essentially lifecycle stages; customers move
New → At Risk/Hibernating as their only order ages (see migration table). (2) Selection margin over the behavioural
K = 6 model is 0.015 composite points — the behavioural labels are kept (`e3_cluster`). (3) Features use orders
known by the snapshot; reviews/delivery of orders placed shortly before the snapshot may be incomplete.

## Alternative models kept

| Label column | Model | Use |
|---|---|---|
| `rfm_segment`, `r_score`, `f_score`, `m_score`, `rfm_cell` | E1 rule-based RFM (quintile R/M, tiered F) | CRM list pulls by recency × value |
| `e2_cluster` | best E2 model (= final) | – |
| `e3_cluster` | `E3-beh-value-lifecycle-kmeans-k6` | behavioural lens: financing, basket size |

## CLV models (BG/NBD + Gamma-Gamma)

Implemented in `custseg.clv` from Fader, Hardie & Lee (2005a, 2005b) with SciPy L-BFGS-B on the log-parameters,
likelihood aggregated over unique (x, tₓ, T) rows. Unit: week; transaction = purchase day.

| Model | Parameters (full period) |
|---|---|
| BG/NBD | r = 0.0157, α = 9.52, a = 2.06, b = 0.351 |
| Gamma-Gamma | p = 5.99, q = 2.81, v = 46.1 (fitted on 2,005 repeat customers) |

Validation (calibration < 2018-03-01, 26-week holdout, 55,267 customers): predicted 734 vs actual 696 repeat
purchases (+5 %); naive run-rate 1,485 (+113 %). Gamma-Gamma independence check r = 0.002 (p = 0.92).
Note: BG/NBD assigns P(alive) = 1 to customers without repeat purchases (model property) — use `predicted_clv_12m`,
not `p_alive`, to rank one-time buyers.

## Churn definition

Inactivity threshold T = P90 of gaps ≥ 1 day between consecutive purchase occasions = **278 days**. Churned =
`recency_days > T`. This is a rule-based status. A predictive churn model was not built: with 3 % repeat buyers the
label is extremely imbalanced, and BG/NBD already provides a time-validated probabilistic view of repeat purchasing.
