# Preprocessing Strategy

| Step | Rule | Why |
|---|---|---|
| Missing values | median imputation (only `avg_review_score` 0.8 %, `avg_delivery_days` / `late_delivery_share` < 0.1 %) | orders without review / delivery date |
| Skew handling | `log1p` on features with \|skew\| > 1 (E3); E2 compares original vs log on all three RFM features | monetary skew ≈ 9, frequency skew ≈ 12 |
| Scaling | E2: StandardScaler vs RobustScaler; E3: StandardScaler | distance-based algorithms need comparable scales |
| Outliers | kept (no clipping) — tested indirectly by RobustScaler and by the small-cluster review (PRD 5.4) | high spenders are real customers, not errors |

Log-transformed columns per space:

| space | log1p columns |
|---|---|
| rfm-original-standard | - |
| rfm-original-robust | - |
| rfm-log-standard | recency_days, frequency, monetary |
| rfm-log-robust | recency_days, frequency, monetary |
| beh-value-lifecycle | frequency, monetary, avg_items_per_order, avg_installments |
| beh-value-experience | frequency, monetary, avg_items_per_order, avg_installments, avg_review_score, late_delivery_share, freight_ratio |
| beh-full-pool | frequency, monetary, avg_items_per_order, n_categories, n_unique_products, active_months, avg_monthly_spending, avg_installments, credit_card_order_share, voucher_order_share, avg_review_score, late_delivery_share, avg_delivery_days, freight_ratio |

RobustScaler caveat: `frequency` has IQR = 0 (Q1 = Q3 = 1), so RobustScaler leaves it unscaled; with log it becomes
0 / 0.69 / 1.1 … — this is why the robust variants split almost purely on repeat-vs-one-time.
