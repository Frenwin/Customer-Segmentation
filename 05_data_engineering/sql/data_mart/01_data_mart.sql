-- =====================================================================================================
-- LAYER 4 - DATA MART (schema `mart`) - aggregations done in SQL (PRD 12.2)
--   mart.customer_rfm         1 row / purchasing customer : Recency, Frequency, Monetary, AOV, tenure
--   mart.customer_behavior    1 row / purchasing customer : product, payment, satisfaction, lifecycle features
--   mart.customer_kpi_monthly 1 row / month               : acquisition, activity, value KPIs
--   mart.cohort_retention     1 row / cohort x month index : monthly cohort retention + revenue
-- Python adds: customer_segmentation, segment_profile, customer_clv, period_retention, product_affinity,
--              experiment_results (see src/custseg). Only revenue orders (dw.fact_orders.is_revenue) are used.
-- Analysis (snapshot) date: {{ANALYSIS_DATE}}
-- =====================================================================================================
DROP SCHEMA IF EXISTS mart CASCADE;
CREATE SCHEMA mart;

CREATE VIEW mart.v_revenue_orders AS
SELECT * FROM dw.fact_orders WHERE is_revenue;

-- ---------------------------------------------------------------- customer_rfm
CREATE TABLE mart.customer_rfm AS
SELECT o.customer_key,
       min(o.purchase_ts)::date                                       AS first_purchase_date,
       max(o.purchase_ts)::date                                       AS last_purchase_date,
       (DATE '{{ANALYSIS_DATE}}' - max(o.purchase_ts)::date)          AS recency_days,
       count(*)::int                                                  AS frequency,
       round(sum(o.order_value), 2)::double precision                 AS monetary,
       round(avg(o.order_value), 2)::double precision                 AS avg_order_value,
       sum(o.n_items)::int                                            AS total_items,
       (DATE '{{ANALYSIS_DATE}}' - min(o.purchase_ts)::date)          AS tenure_days
FROM mart.v_revenue_orders o
GROUP BY o.customer_key;
ALTER TABLE mart.customer_rfm ADD PRIMARY KEY (customer_key);

-- ---------------------------------------------------------------- customer_behavior
CREATE TABLE mart.customer_behavior AS
WITH lines AS (
    SELECT s.customer_key, p.category, p.category_group, s.product_key, s.line_total
    FROM dw.fact_sales s JOIN dw.dim_product p USING (product_key) WHERE s.is_revenue),
cat_spend AS (
    SELECT customer_key, category_group, sum(line_total) AS spend,
           row_number() OVER (PARTITION BY customer_key ORDER BY sum(line_total) DESC, category_group) AS rk
    FROM lines GROUP BY customer_key, category_group),
prod AS (
    SELECT customer_key, count(DISTINCT category) AS n_categories, count(DISTINCT category_group) AS n_category_groups,
           count(DISTINCT product_key) AS n_unique_products, sum(line_total) AS spend
    FROM lines GROUP BY customer_key),
intervals AS (
    SELECT customer_key,
           extract(epoch FROM purchase_ts - lag(purchase_ts) OVER (PARTITION BY customer_key ORDER BY purchase_ts)) / 86400 AS gap_days
    FROM mart.v_revenue_orders),
gap AS (
    SELECT customer_key, avg(gap_days) AS avg_purchase_interval_days, stddev_samp(gap_days) AS std_purchase_interval_days
    FROM intervals WHERE gap_days IS NOT NULL GROUP BY customer_key),
ord AS (
    SELECT customer_key,
           avg(installments)                                        AS avg_installments,
           avg(uses_voucher::int)                                   AS voucher_order_share,
           avg((pm.payment_type = 'credit_card')::int)              AS credit_card_order_share,
           avg((pm.payment_type = 'boleto')::int)                   AS boleto_order_share,
           avg(review_score)                                        AS avg_review_score,
           min(review_score)                                        AS min_review_score,
           avg(is_late::int)                                        AS late_delivery_share,
           avg(delivery_days)                                       AS avg_delivery_days,
           sum(freight_value) / nullif(sum(order_value), 0)         AS freight_ratio,
           avg(n_items)                                             AS avg_items_per_order,
           count(DISTINCT date_trunc('month', purchase_ts))         AS active_months
    FROM mart.v_revenue_orders o LEFT JOIN dw.dim_payment_method pm USING (payment_method_key)
    GROUP BY customer_key)
SELECT r.customer_key,
       r.recency_days, r.frequency, r.monetary, r.avg_order_value, r.tenure_days,
       (r.last_purchase_date - r.first_purchase_date)                             AS activity_period_days,
       round((r.monetary / greatest(1, r.tenure_days / 30.4375))::numeric, 2)::double precision AS avg_monthly_spending,
       (r.frequency >= 2)                                                          AS is_repeat_customer,
       p.n_categories, p.n_category_groups, p.n_unique_products,
       (p.n_categories > 1)                                                        AS is_cross_category,
       cs.category_group                                                           AS top_category_group,
       round((cs.spend / nullif(p.spend, 0))::numeric, 4)::double precision        AS top_category_spend_ratio,
       round(g.avg_purchase_interval_days::numeric, 2)::double precision          AS avg_purchase_interval_days,
       round(g.std_purchase_interval_days::numeric, 2)::double precision          AS std_purchase_interval_days,
       round(o.avg_installments::numeric, 3)::double precision                     AS avg_installments,
       round(o.voucher_order_share::numeric, 4)::double precision                  AS voucher_order_share,
       round(o.credit_card_order_share::numeric, 4)::double precision              AS credit_card_order_share,
       round(o.boleto_order_share::numeric, 4)::double precision                   AS boleto_order_share,
       round(o.avg_review_score::numeric, 3)::double precision                     AS avg_review_score,
       o.min_review_score,
       round(o.late_delivery_share::numeric, 4)::double precision                  AS late_delivery_share,
       round(o.avg_delivery_days::numeric, 2)::double precision                    AS avg_delivery_days,
       round(o.freight_ratio::numeric, 4)::double precision                        AS freight_ratio,
       round(o.avg_items_per_order::numeric, 3)::double precision                  AS avg_items_per_order,
       o.active_months
FROM mart.customer_rfm r
JOIN prod p USING (customer_key)
JOIN cat_spend cs ON cs.customer_key = r.customer_key AND cs.rk = 1
JOIN ord o ON o.customer_key = r.customer_key
LEFT JOIN gap g ON g.customer_key = r.customer_key;
ALTER TABLE mart.customer_behavior ADD PRIMARY KEY (customer_key);

-- ---------------------------------------------------------------- customer_kpi_monthly
CREATE TABLE mart.customer_kpi_monthly AS
WITH o AS (
    SELECT customer_key, date_trunc('month', purchase_ts)::date AS month, order_value
    FROM mart.v_revenue_orders),
first_m AS (SELECT customer_key, min(month) AS first_month FROM o GROUP BY customer_key),
m AS (
    SELECT o.month,
           count(*)                                                     AS orders,
           count(DISTINCT o.customer_key)                               AS purchasing_customers,
           count(DISTINCT o.customer_key) FILTER (WHERE f.first_month = o.month) AS new_customers,
           count(DISTINCT o.customer_key) FILTER (WHERE f.first_month < o.month) AS returning_customers,
           sum(o.order_value)                                           AS revenue
    FROM o JOIN first_m f USING (customer_key) GROUP BY o.month),
c AS (SELECT m.*, sum(new_customers) OVER (ORDER BY month) AS cumulative_customers FROM m)
SELECT month,
       to_char(month, 'YYYY-MM')                                                AS year_month,
       orders, purchasing_customers, new_customers, returning_customers,
       round(revenue::numeric, 2)::double precision                             AS revenue,
       round((revenue / orders)::numeric, 2)::double precision                  AS avg_order_value,
       round((revenue / purchasing_customers)::numeric, 2)::double precision    AS revenue_per_customer,
       round((orders::numeric / purchasing_customers), 4)::double precision     AS purchase_frequency,
       cumulative_customers::int                                                AS cumulative_customers,
       -- PRD 8.1: acquisition rate = new customers / customers at beginning of period
       round((new_customers::numeric / nullif(lag(cumulative_customers) OVER (ORDER BY month), 0)), 4)::double precision
                                                                                AS acquisition_rate,
       -- growth of the *active* (purchasing) base month over month; cumulative growth would equal acquisition_rate
       round((purchasing_customers::numeric / nullif(lag(purchasing_customers) OVER (ORDER BY month), 0) - 1), 4)::double precision
                                                                                AS customer_growth_rate,
       round((revenue / nullif(lag(revenue) OVER (ORDER BY month), 0) - 1)::numeric, 4)::double precision
                                                                                AS revenue_growth_mom
FROM c ORDER BY month;

-- ---------------------------------------------------------------- cohort_retention (monthly)
CREATE TABLE mart.cohort_retention AS
WITH o AS (
    SELECT o.customer_key, date_trunc('month', o.purchase_ts)::date AS month, o.order_value, c.cohort_month
    FROM mart.v_revenue_orders o JOIN dw.dim_customer c USING (customer_key)),
sizes AS (SELECT cohort_month, count(DISTINCT customer_key) AS cohort_size FROM o GROUP BY cohort_month)
SELECT o.cohort_month,
       to_char(o.cohort_month, 'YYYY-MM')                                        AS cohort,
       ((extract(year FROM o.month) - extract(year FROM o.cohort_month)) * 12
         + extract(month FROM o.month) - extract(month FROM o.cohort_month))::int AS month_index,
       s.cohort_size,
       count(DISTINCT o.customer_key)                                            AS active_customers,
       round((count(DISTINCT o.customer_key)::numeric / s.cohort_size), 5)::double precision AS retention_rate,
       round(sum(o.order_value)::numeric, 2)::double precision                   AS revenue,
       count(*)                                                                  AS orders
FROM o JOIN sizes s USING (cohort_month)
GROUP BY o.cohort_month, s.cohort_size, month_index
ORDER BY o.cohort_month, month_index;

ANALYZE;
