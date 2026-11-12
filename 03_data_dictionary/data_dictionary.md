# Data Dictionary (analytical layers)

Generated from `information_schema` by `custseg.report.data_dictionary()`. Excel versions: `customer_dictionary.xlsx`, `transaction_dictionary.xlsx`, `product_dictionary.xlsx`, `full_data_dictionary.xlsx`. Source-file fields: `data_source_documentation.md`.

## dw.dim_customer

| Column | Type | Description |
|---|---|---|
| customer_key | integer | Surrogate key of the person (customer_unique_id) |
| customer_code | text | Public pseudonymous code (C000123) |
| customer_unique_id | text | Olist person identifier (hashed) |
| location_key | integer | FK to dim_location |
| acquisition_date | date | Date of first order (any status) - registration proxy |
| cohort_month | date | Month of first delivered order |
| is_purchasing_customer | boolean | Has >= 1 delivered order in the window |

## dw.dim_date

| Column | Type | Description |
|---|---|---|
| date_key | integer | FK to dim_date (YYYYMMDD of purchase) |
| date | date | Calendar date |
| year | integer |  |
| quarter | integer |  |
| year_quarter | text |  |
| month | integer |  |
| month_name | text |  |
| year_month | text | YYYY-MM |
| month_start | date |  |
| day_of_week | integer |  |
| day_name | text |  |
| is_weekend | boolean |  |
| iso_week | integer |  |
| is_in_window | boolean |  |

## dw.dim_location

| Column | Type | Description |
|---|---|---|
| location_key | integer | FK to dim_location |
| city | text | City |
| state | text | State (UF) |
| region | text | Brazilian macro-region |
| geo_label | text | City, State, Brazil (map label) |
| lat | numeric | Latitude (median of zip prefixes) |
| lng | numeric | Longitude |

## dw.dim_payment_method

| Column | Type | Description |
|---|---|---|
| payment_method_key | integer | FK to dim_payment_method (primary payment type = largest payment of the order) |
| payment_type | text | Olist payment type code |
| payment_method | text | Payment method label |

## dw.dim_product

| Column | Type | Description |
|---|---|---|
| product_key | integer | FK to dim_product |
| product_id | text |  |
| category | text | Product category (English) |
| category_pt | text | Product category (Portuguese) |
| category_group | text | Macro category group (15 groups) |
| photos_qty | integer | Product photos |
| weight_g | numeric | Weight (g) |
| volume_cm3 | numeric | Package volume (cm3) |

## dw.fact_cancellations

| Column | Type | Description |
|---|---|---|
| order_key | integer | Surrogate key of the order |
| order_id | text | Olist order id |
| customer_key | integer | Surrogate key of the person (customer_unique_id) |
| date_key | integer | FK to dim_date (YYYYMMDD of purchase) |
| payment_method_key | integer | FK to dim_payment_method (primary payment type = largest payment of the order) |
| order_status | text | Olist status (delivered, shipped, canceled, ...) |
| n_items | bigint | Items in the order |
| lost_value | numeric | Value of the cancelled order (R$) |
| payment_value | numeric | Sum of payments (R$) |

## dw.fact_orders

| Column | Type | Description |
|---|---|---|
| order_key | integer | Surrogate key of the order |
| order_id | text | Olist order id |
| customer_key | integer | Surrogate key of the person (customer_unique_id) |
| date_key | integer | FK to dim_date (YYYYMMDD of purchase) |
| payment_method_key | integer | FK to dim_payment_method (primary payment type = largest payment of the order) |
| order_status | text | Olist status (delivered, shipped, canceled, ...) |
| purchase_ts | timestamp without time zone | Purchase timestamp |
| purchase_hour | integer | Hour of purchase |
| n_items | bigint | Items in the order |
| n_sellers | bigint | Distinct sellers in the order |
| n_categories | bigint | Distinct product categories |
| items_value | numeric | Sum of item prices (R$) |
| freight_value | numeric | Freight charged (R$) |
| order_value | numeric | items_value + freight_value (R$) |
| payment_value | numeric | Sum of payments (R$) |
| installments | integer | Max number of installments |
| uses_voucher | boolean | Any voucher payment |
| review_score | integer | Latest review score 1-5 |
| delivery_days | numeric | Purchase -> delivery (days) |
| delay_days | numeric | Delivered - estimated date (days, + = late) |
| is_late | boolean | Delivered after the estimated date |
| is_revenue | boolean | Delivered AND purchased inside the analysis window |
| is_in_window | boolean |  |
| dq_issue | text | First data-quality issue flagged in staging |

## dw.fact_sales

| Column | Type | Description |
|---|---|---|
| sales_key | integer |  |
| order_key | integer | Surrogate key of the order |
| order_id | text | Olist order id |
| order_item_id | integer | Line number within the order |
| customer_key | integer | Surrogate key of the person (customer_unique_id) |
| product_key | integer | FK to dim_product |
| date_key | integer | FK to dim_date (YYYYMMDD of purchase) |
| payment_method_key | integer | FK to dim_payment_method (primary payment type = largest payment of the order) |
| location_key | integer | FK to dim_location |
| order_status | text | Olist status (delivered, shipped, canceled, ...) |
| quantity | integer | Units on the line (always 1 in Olist) |
| unit_price | numeric | Item price (R$) |
| freight_value | numeric | Freight charged (R$) |
| discount_amount | numeric | Not available in Olist (0) |
| product_revenue | numeric | Item price (R$) |
| line_total | numeric | price + freight (R$) - revenue measure |
| is_revenue | boolean | Delivered AND purchased inside the analysis window |

## mart.cohort_retention

| Column | Type | Description |
|---|---|---|
| cohort_month | date | Month of first delivered order |
| cohort | text |  |
| month_index | integer |  |
| cohort_size | bigint |  |
| active_customers | bigint |  |
| retention_rate | double precision |  |
| revenue | double precision |  |
| orders | bigint |  |

## mart.customer_behavior

| Column | Type | Description |
|---|---|---|
| customer_key | integer | Surrogate key of the person (customer_unique_id) |
| recency_days | integer | Days from last purchase to the analysis date |
| frequency | integer | Delivered orders in the window |
| monetary | double precision | Revenue of the customer (R$) |
| avg_order_value | double precision | monetary / frequency |
| tenure_days | integer | Days from first purchase to the analysis date |
| activity_period_days | integer |  |
| avg_monthly_spending | double precision |  |
| is_repeat_customer | boolean |  |
| n_categories | bigint | Distinct product categories |
| n_category_groups | bigint |  |
| n_unique_products | bigint |  |
| is_cross_category | boolean |  |
| top_category_group | text |  |
| top_category_spend_ratio | double precision |  |
| avg_purchase_interval_days | double precision |  |
| std_purchase_interval_days | double precision |  |
| avg_installments | double precision |  |
| voucher_order_share | double precision |  |
| credit_card_order_share | double precision |  |
| boleto_order_share | double precision |  |
| avg_review_score | double precision |  |
| min_review_score | integer |  |
| late_delivery_share | double precision |  |
| avg_delivery_days | double precision |  |
| freight_ratio | double precision |  |
| avg_items_per_order | double precision |  |
| active_months | bigint |  |

## mart.customer_clv

| Column | Type | Description |
|---|---|---|
| customer_key | bigint | Surrogate key of the person (customer_unique_id) |
| repeat_purchase_days | bigint |  |
| t_x_weeks | double precision |  |
| age_weeks | double precision |  |
| historical_clv | double precision |  |
| expected_purchases_12m | double precision |  |
| p_alive | double precision |  |
| expected_value_per_purchase | double precision |  |
| predicted_clv_12m | double precision |  |
| clv_tier | text |  |

## mart.customer_kpi_monthly

| Column | Type | Description |
|---|---|---|
| month | date |  |
| year_month | text | YYYY-MM |
| orders | bigint |  |
| purchasing_customers | bigint |  |
| new_customers | bigint |  |
| returning_customers | bigint |  |
| revenue | double precision |  |
| avg_order_value | double precision | monetary / frequency |
| revenue_per_customer | double precision |  |
| purchase_frequency | double precision |  |
| cumulative_customers | integer |  |
| acquisition_rate | double precision |  |
| customer_growth_rate | double precision |  |
| revenue_growth_mom | double precision |  |

## mart.customer_rfm

| Column | Type | Description |
|---|---|---|
| customer_key | integer | Surrogate key of the person (customer_unique_id) |
| first_purchase_date | date | First delivered order date |
| last_purchase_date | date | Last delivered order date |
| recency_days | integer | Days from last purchase to the analysis date |
| frequency | integer | Delivered orders in the window |
| monetary | double precision | Revenue of the customer (R$) |
| avg_order_value | double precision | monetary / frequency |
| total_items | integer | Items purchased |
| tenure_days | integer | Days from first purchase to the analysis date |

## mart.customer_segmentation

| Column | Type | Description |
|---|---|---|
| customer_key | bigint | Surrogate key of the person (customer_unique_id) |
| segment_name | text |  |
| segment_id | text |  |
| r_score | bigint |  |
| f_score | bigint |  |
| m_score | bigint |  |
| rfm_cell | text |  |
| rfm_score | bigint |  |
| rfm_segment | text |  |
| e2_cluster | bigint |  |
| e3_cluster | bigint |  |
| churn_status | text |  |
| historical_clv | double precision |  |
| predicted_clv_12m | double precision |  |
| p_alive | double precision |  |
| clv_tier | text |  |

## mart.kpi_dictionary

| Column | Type | Description |
|---|---|---|
| category | text | Product category (English) |
| kpi | text |  |
| business_definition | text |  |
| formula | text |  |
| dax_measure | text |  |
| data_source | text |  |
| granularity | text |  |
| update_frequency | text |  |
| unit | text |  |
| target_basis | text |  |
| business_owner | text |  |
| baseline_display | text |  |
| baseline_display_idr | text |  |
| target_display_idr | text |  |
| target_display | text |  |
| baseline_period | text |  |

## mart.model_comparison

| Column | Type | Description |
|---|---|---|
| run_id | text |  |
| experiment | text |  |
| space | text |  |
| algorithm | text |  |
| k | bigint |  |
| own_silhouette | double precision |  |
| silhouette@rfm-original-standard | double precision |  |
| silhouette@rfm-original-robust | double precision |  |
| silhouette@rfm-log-standard | double precision |  |
| silhouette@rfm-log-robust | double precision |  |
| silhouette@beh-value-lifecycle | double precision |  |
| silhouette@beh-value-experience | double precision |  |
| silhouette@beh-full-pool | double precision |  |
| silhouette | double precision |  |
| davies_bouldin | double precision |  |
| calinski_harabasz | double precision |  |
| stability_bootstrap_ari | double precision |  |
| stability_seed_ari | double precision |  |
| size_entropy | double precision |  |
| min_cluster_share | double precision |  |
| interpretability | double precision |  |
| composite | double precision |  |
| rank | bigint |  |

## mart.period_retention

| Column | Type | Description |
|---|---|---|
| period_start | timestamp without time zone |  |
| period_end | timestamp without time zone |  |
| period | text |  |
| eligible_customers | bigint |  |
| retained_customers | bigint |  |
| retention_rate | double precision |  |
| churned_customers | bigint |  |
| churn_rate | double precision |  |
| inactive_customers | bigint |  |
| reactivated_customers | bigint |  |
| reactivation_rate | double precision |  |
| purchasing_customers | bigint |  |
| new_customers | bigint |  |

## mart.product_affinity

| Column | Type | Description |
|---|---|---|
| level | text |  |
| antecedent | text |  |
| consequent | text |  |
| itemset_size | bigint |  |
| support_count | bigint |  |
| support | double precision |  |
| confidence | double precision |  |
| lift | double precision |  |
| antecedent_count | bigint |  |
| consequent_count | bigint |  |

## mart.revenue_pareto

| Column | Type | Description |
|---|---|---|
| customer_pct | double precision |  |
| cum_revenue_share | double precision |  |

## mart.segment_migration

| Column | Type | Description |
|---|---|---|
| segment_prev | text |  |
| segment_now | text |  |
| customers | bigint |  |

## mart.segment_profile

| Column | Type | Description |
|---|---|---|
| cluster | bigint |  |
| segment_id | text |  |
| segment_name | text |  |
| customers | bigint |  |
| avg_recency_days | double precision |  |
| median_recency_days | double precision |  |
| avg_frequency | double precision |  |
| avg_monetary | double precision |  |
| median_monetary | double precision |  |
| revenue | double precision |  |
| orders | bigint |  |
| repeat_rate | double precision |  |
| churn_rate | double precision |  |
| avg_items_per_order | double precision |  |
| avg_installments | double precision |  |
| avg_review_score | double precision |  |
| late_delivery_share | double precision |  |
| avg_delivery_days | double precision |  |
| freight_ratio | double precision |  |
| credit_card_share | double precision |  |
| voucher_share | double precision |  |
| cross_category_share | double precision |  |
| top_category_group | text |  |
| top_category_group_share | double precision |  |
| top_state | text |  |
| sudeste_share | double precision |  |
| customer_share | double precision |  |
| revenue_contribution | double precision |  |
| avg_order_value | double precision | monetary / frequency |
| avg_historical_clv | double precision |  |
| avg_predicted_clv_12m | double precision |  |
| avg_p_alive | double precision |  |
| expected_purchases_12m | double precision |  |
| retention_rate | double precision |  |
| segment_description | text |  |
| recommended_strategy | text |  |
| color | text |  |
| customers_prev_snapshot | bigint |  |
| segment_growth_rate | double precision |  |

## mart.v_revenue_orders

| Column | Type | Description |
|---|---|---|
| order_key | integer | Surrogate key of the order |
| order_id | text | Olist order id |
| customer_key | integer | Surrogate key of the person (customer_unique_id) |
| date_key | integer | FK to dim_date (YYYYMMDD of purchase) |
| payment_method_key | integer | FK to dim_payment_method (primary payment type = largest payment of the order) |
| order_status | text | Olist status (delivered, shipped, canceled, ...) |
| purchase_ts | timestamp without time zone | Purchase timestamp |
| purchase_hour | integer | Hour of purchase |
| n_items | bigint | Items in the order |
| n_sellers | bigint | Distinct sellers in the order |
| n_categories | bigint | Distinct product categories |
| items_value | numeric | Sum of item prices (R$) |
| freight_value | numeric | Freight charged (R$) |
| order_value | numeric | items_value + freight_value (R$) |
| payment_value | numeric | Sum of payments (R$) |
| installments | integer | Max number of installments |
| uses_voucher | boolean | Any voucher payment |
| review_score | integer | Latest review score 1-5 |
| delivery_days | numeric | Purchase -> delivery (days) |
| delay_days | numeric | Delivered - estimated date (days, + = late) |
| is_late | boolean | Delivered after the estimated date |
| is_revenue | boolean | Delivered AND purchased inside the analysis window |
| is_in_window | boolean |  |
| dq_issue | text | First data-quality issue flagged in staging |
