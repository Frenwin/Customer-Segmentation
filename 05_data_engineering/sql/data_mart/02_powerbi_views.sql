-- =====================================================================================================
-- SERVING LAYER for Power BI (schema `pbi`) - created after the Python steps have written their mart tables.
-- Star schema: fact_sales (line) & fact_orders (order) -> dim_customer, dim_product, dim_date, dim_payment_method;
--              dim_customer -> dim_location.  Plus small pre-aggregated tables (PRD 12.4).
-- Privacy (PRD 12.3): no customer_unique_id / zip code is exposed; customers appear as a surrogate customer_code.
-- Only revenue rows (delivered, in window) are exposed so every measure is revenue-consistent by construction.
-- Currency: the analysis runs in BRL; every money column here is shown in RUPIAH with one fixed rate
-- {{FX}} IDR/BRL (annual 2017/2018 averages weighted by revenue, see custseg.fx) - all ratios are unchanged.
-- =====================================================================================================
DROP SCHEMA IF EXISTS pbi CASCADE;
CREATE SCHEMA pbi;

CREATE VIEW pbi.dim_customer AS
SELECT c.customer_key,
       c.customer_code,
       c.location_key,
       c.acquisition_date,
       c.cohort_month,
       to_char(c.cohort_month, 'YYYY-MM')                       AS cohort,
       s.segment_id,
       s.segment_name,
       sp.color                                                 AS segment_color,
       s.rfm_segment,
       s.r_score, s.f_score, s.m_score, s.rfm_cell, s.rfm_score,
       s.churn_status,
       CASE WHEN s.churn_status = 'Active' THEN 0 ELSE 1 END    AS is_churned,
       r.recency_days, r.frequency, r.monetary * {{FX}} AS monetary, r.avg_order_value * {{FX}} AS avg_order_value,
       CASE WHEN r.frequency >= 2 THEN 1 ELSE 0 END             AS is_repeat,
       CASE WHEN r.frequency >= 2 THEN 'Repeat' ELSE 'One-time' END AS buyer_type,
       CASE WHEN r.monetary * {{FX}} < 200000 THEN '< Rp200rb' WHEN r.monetary * {{FX}} < 400000 THEN 'Rp200-400rb'
            WHEN r.monetary * {{FX}} < 800000 THEN 'Rp400-800rb' WHEN r.monetary * {{FX}} < 2000000 THEN 'Rp0,8-2jt'
            WHEN r.monetary * {{FX}} < 4000000 THEN 'Rp2-4jt' ELSE '>= Rp4jt' END AS clv_band,
       CASE WHEN r.monetary * {{FX}} < 200000 THEN 1 WHEN r.monetary * {{FX}} < 400000 THEN 2
            WHEN r.monetary * {{FX}} < 800000 THEN 3 WHEN r.monetary * {{FX}} < 2000000 THEN 4
            WHEN r.monetary * {{FX}} < 4000000 THEN 5 ELSE 6 END AS clv_band_order,
       CASE WHEN r.recency_days <= 30 THEN '0-30 d' WHEN r.recency_days <= 90 THEN '31-90 d'
            WHEN r.recency_days <= 180 THEN '91-180 d' WHEN r.recency_days <= {{CHURN_T}} THEN '181-{{CHURN_T}} d'
            WHEN r.recency_days <= 400 THEN '{{CHURN_T1}}-400 d' ELSE '> 400 d' END AS inactivity_band,
       CASE WHEN r.recency_days <= 30 THEN 1 WHEN r.recency_days <= 90 THEN 2 WHEN r.recency_days <= 180 THEN 3
            WHEN r.recency_days <= {{CHURN_T}} THEN 4 WHEN r.recency_days <= 400 THEN 5 ELSE 6 END AS inactivity_band_order,
       s.historical_clv * {{FX}} AS historical_clv, s.predicted_clv_12m * {{FX}} AS predicted_clv_12m, s.p_alive, s.clv_tier,
       CASE s.clv_tier WHEN 'Top 5%' THEN 1 WHEN 'High (80-95%)' THEN 2 WHEN 'Medium (50-80%)' THEN 3 ELSE 4 END AS clv_tier_order,
       b.top_category_group, b.avg_review_score, b.avg_installments, b.late_delivery_share,
       b.avg_purchase_interval_days,
       -- top-20% spenders whose inactivity is between 60% and 100% of T: still reachable before they churn
       CASE WHEN r.monetary >= q.p80 AND r.recency_days BETWEEN round({{CHURN_T}} * 0.6) AND {{CHURN_T}}
            THEN 1 ELSE 0 END                                   AS is_high_value_at_risk,
       CASE WHEN s.clv_tier = 'Top 5%' AND s.churn_status = 'Active' THEN 1 ELSE 0 END AS is_high_potential
FROM dw.dim_customer c
CROSS JOIN (SELECT percentile_cont(0.8) WITHIN GROUP (ORDER BY monetary) AS p80 FROM mart.customer_rfm) q
JOIN mart.customer_segmentation s USING (customer_key)
JOIN mart.customer_rfm r USING (customer_key)
JOIN mart.customer_behavior b USING (customer_key)
LEFT JOIN mart.segment_profile sp ON sp.segment_name = s.segment_name;

CREATE VIEW pbi.dim_location AS
SELECT location_key, city, state, region, geo_label, lat::double precision AS lat, lng::double precision AS lng
FROM dw.dim_location
WHERE location_key IN (SELECT location_key FROM dw.dim_customer WHERE is_purchasing_customer);

CREATE VIEW pbi.dim_product AS
SELECT product_key, category, category_group FROM dw.dim_product;

CREATE VIEW pbi.dim_date AS
SELECT date_key, date, year, quarter, year_quarter, month, month_name, year_month, month_start, day_of_week,
       day_name, is_weekend
FROM dw.dim_date WHERE is_in_window;

CREATE VIEW pbi.dim_payment_method AS
SELECT payment_method_key, payment_type, payment_method FROM dw.dim_payment_method;

CREATE VIEW pbi.fact_sales AS
SELECT sales_key, order_key, customer_key, product_key, date_key, payment_method_key,
       quantity, unit_price::double precision * {{FX}} AS unit_price, freight_value::double precision * {{FX}} AS freight_value,
       line_total::double precision * {{FX}} AS line_total
FROM dw.fact_sales WHERE is_revenue;

CREATE VIEW pbi.fact_orders AS
SELECT o.order_key, o.customer_key, o.date_key, o.payment_method_key, o.purchase_hour, o.n_items, o.n_categories,
       o.order_value::double precision * {{FX}} AS order_value, o.freight_value::double precision * {{FX}} AS freight_value,
       o.installments, o.review_score, o.delivery_days::double precision AS delivery_days,
       CASE WHEN o.is_late THEN 1 WHEN o.is_late = false THEN 0 END AS is_late,
       CASE WHEN o.order_key = f.first_order_key THEN 1 ELSE 0 END AS is_first_order
FROM dw.fact_orders o
JOIN (SELECT customer_key, min(order_key) AS first_order_key FROM dw.fact_orders WHERE is_revenue
      GROUP BY customer_key) f USING (customer_key)
WHERE o.is_revenue;

-- ---------------------------------------------------------------- pre-aggregated / analytical tables
CREATE VIEW pbi.segment_profile AS
SELECT segment_id, segment_name, segment_description, recommended_strategy, color, customers, customer_share,
       revenue * {{FX}} AS revenue, revenue_contribution, avg_recency_days, avg_frequency,
       avg_monetary * {{FX}} AS avg_monetary, avg_order_value * {{FX}} AS avg_order_value,
       avg_historical_clv * {{FX}} AS avg_historical_clv, avg_predicted_clv_12m * {{FX}} AS avg_predicted_clv_12m, retention_rate, churn_rate, avg_review_score, late_delivery_share,
       avg_installments, top_category_group, customers_prev_snapshot, segment_growth_rate,
       expected_purchases_12m
FROM mart.segment_profile;

CREATE VIEW pbi.segment_migration AS SELECT * FROM mart.segment_migration;
CREATE VIEW pbi.period_retention AS SELECT * FROM mart.period_retention;
CREATE VIEW pbi.cohort_retention AS
SELECT cohort, cohort_month, month_index, cohort_size, active_customers, retention_rate, revenue * {{FX}} AS revenue, orders
FROM mart.cohort_retention WHERE month_index BETWEEN 1 AND 12;
CREATE VIEW pbi.product_affinity AS SELECT * FROM mart.product_affinity;
CREATE VIEW pbi.revenue_pareto AS SELECT * FROM mart.revenue_pareto;
CREATE VIEW pbi.kpi_monthly AS
SELECT month, year_month, orders, purchasing_customers, new_customers, returning_customers, revenue * {{FX}} AS revenue,
       avg_order_value * {{FX}} AS avg_order_value, revenue_per_customer * {{FX}} AS revenue_per_customer,
       purchase_frequency, cumulative_customers, acquisition_rate, customer_growth_rate, revenue_growth_mom
FROM mart.customer_kpi_monthly;
CREATE VIEW pbi.kpi_dictionary AS
SELECT category, kpi, business_definition, formula, dax_measure, data_source, granularity, update_frequency, unit,
       baseline_display_idr AS baseline_display, target_display_idr AS target_display, target_basis, business_owner
FROM mart.kpi_dictionary;
CREATE VIEW pbi.model_comparison AS SELECT * FROM mart.model_comparison;
CREATE VIEW pbi.category_by_segment AS
SELECT s.segment_name, p.category_group, count(DISTINCT f.order_key) AS orders, sum(f.line_total) AS revenue
FROM pbi.fact_sales f JOIN mart.customer_segmentation s USING (customer_key) JOIN dw.dim_product p USING (product_key)
GROUP BY 1, 2;
CREATE VIEW pbi.meta AS
SELECT DATE '{{ANALYSIS_DATE}}' AS analysis_date, DATE '{{WINDOW_START}}' AS window_start,
       (DATE '{{WINDOW_END}}' - 1) AS window_end, now()::timestamp(0) AS refreshed_at,
       {{FX}}::double precision AS fx_brl_idr;
