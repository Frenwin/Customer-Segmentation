# Data model

Star schema, DirectQuery on PostgreSQL schema `pbi` (localhost:5435 / custsegdb).

| From (many) | To (one) | Direction |
|---|---|---|
| `fact_sales.customer_key` | `dim_customer.customer_key` | single |
| `fact_sales.product_key` | `dim_product.product_key` | single |
| `fact_sales.date_key` | `dim_date.date_key` | single |
| `fact_sales.payment_method_key` | `dim_payment_method.payment_method_key` | single |
| `fact_orders.customer_key` | `dim_customer.customer_key` | single |
| `fact_orders.date_key` | `dim_date.date_key` | single |
| `fact_orders.payment_method_key` | `dim_payment_method.payment_method_key` | single |
| `dim_customer.location_key` | `dim_location.location_key` | single |

Disconnected (pre-aggregated) tables: `segment_profile`, `segment_migration`, `period_retention`, `cohort_retention`, `product_affinity`, `kpi_monthly`, `kpi_dictionary`, `model_comparison`, `category_by_segment`, `revenue_pareto`, `meta`

Filter propagation: `dim_location -> dim_customer -> fact_sales / fact_orders`; `dim_date`, `dim_product`, `dim_payment_method -> facts`. The product-category slicer filters `fact_sales` only (order-level experience measures on `fact_orders` are category-agnostic by design).
