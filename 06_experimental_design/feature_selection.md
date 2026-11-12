# Feature Selection

Candidate features follow the PRD 5.2 groups (transaction, product, lifecycle, value) plus two groups the Olist data
makes available: **payment behaviour** and **experience** (review score, delivery). They are computed in SQL
(`mart.customer_behavior`) and re-computed in pandas for other snapshot dates; both implementations are reconciled
(0 mismatches, `05_data_engineering/validation/feature_reconciliation.csv`).

## Screening rules (applied in order, candidate order = priority)

1. **Undefined for > 50 % of customers** → drop (purchase-interval features only exist for repeat buyers).
2. **Near-constant**: one value shared by > 99 % of customers → drop.
3. **Redundancy**: |Spearman ρ| > 0.8 with an already kept feature → drop the later one.

| feature | group | decision | rule |
|---|---|---|---|
| recency_days | Transaction Behavior | keep | passes missing / variance / correlation screens |
| frequency | Transaction Behavior | keep | passes missing / variance / correlation screens |
| monetary | Transaction Behavior | keep | passes missing / variance / correlation screens |
| avg_order_value | Transaction Behavior | drop | |Spearman rho| = 0.99 with monetary (> 0.8) |
| avg_purchase_interval_days | Transaction Behavior | drop | undefined for 97.0% of customers (> 50%) |
| std_purchase_interval_days | Transaction Behavior | drop | undefined for 99.8% of customers (> 50%) |
| avg_items_per_order | Transaction Behavior | keep | passes missing / variance / correlation screens |
| n_categories | Product Behavior | keep | passes missing / variance / correlation screens |
| n_unique_products | Product Behavior | keep | passes missing / variance / correlation screens |
| top_category_spend_ratio | Product Behavior | drop | |Spearman rho| = 0.88 with n_categories (> 0.8) |
| n_category_groups | Product Behavior | drop | |Spearman rho| = 0.88 with n_categories (> 0.8) |
| tenure_days | Customer Lifecycle | drop | |Spearman rho| = 0.99 with recency_days (> 0.8) |
| activity_period_days | Customer Lifecycle | drop | |Spearman rho| = 0.84 with frequency (> 0.8) |
| active_months | Customer Lifecycle | keep | passes missing / variance / correlation screens |
| avg_monthly_spending | Value Metrics | keep | passes missing / variance / correlation screens |
| avg_installments | Payment Behavior | keep | passes missing / variance / correlation screens |
| credit_card_order_share | Payment Behavior | keep | passes missing / variance / correlation screens |
| boleto_order_share | Payment Behavior | drop | |Spearman rho| = 0.88 with credit_card_order_share (> 0.8) |
| voucher_order_share | Payment Behavior | keep | passes missing / variance / correlation screens |
| avg_review_score | Experience (feedback & delivery) | keep | passes missing / variance / correlation screens |
| min_review_score | Experience (feedback & delivery) | drop | |Spearman rho| = 1.00 with avg_review_score (> 0.8) |
| late_delivery_share | Experience (feedback & delivery) | keep | passes missing / variance / correlation screens |
| avg_delivery_days | Experience (feedback & delivery) | keep | passes missing / variance / correlation screens |
| freight_ratio | Experience (feedback & delivery) | keep | passes missing / variance / correlation screens |

**Screened pool (15):** `recency_days`, `frequency`, `monetary`, `avg_items_per_order`, `n_categories`, `n_unique_products`, `active_months`, `avg_monthly_spending`, `avg_installments`, `credit_card_order_share`, `voucher_order_share`, `avg_review_score`, `late_delivery_share`, `avg_delivery_days`, `freight_ratio`

## Feature configurations tested in E3

| Configuration | Features | Rationale |
|---|---|---|
| `beh-value-lifecycle` | recency_days, frequency, monetary, avg_items_per_order, avg_installments | RFM + basket size + financing behaviour |
| `beh-value-experience` | recency_days, frequency, monetary, avg_items_per_order, avg_installments, avg_review_score, late_delivery_share, freight_ratio | adds satisfaction, delivery experience, freight burden |
| `beh-full-pool` | all 15 screened features | tests whether more features help (curse of dimensionality) |

E2 uses only `recency_days`, `frequency`, `monetary`.

**Why frequency is kept although 97 % of customers have one order:** it is the only loyalty signal; it passes the
99 % near-constant rule (97.0 %). Its near-degeneracy is the main structural property of this dataset and is
discussed in every result.
