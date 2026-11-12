-- =====================================================================================================
-- LAYER 3 - DATA WAREHOUSE (star schema, schema `dw`)
--   fact_sales          grain: 1 row per order line item (Olist: 1 line = 1 unit)        <- main fact
--   fact_orders         grain: 1 row per order (header: payment, delivery, review)        <- order-level measures
--   fact_cancellations  grain: 1 row per cancelled / unavailable order (lost demand)       <- replaces fact_returns:
--                       Olist has no return/refund records, cancellations are the closest available signal
--   dim_customer, dim_product, dim_date, dim_location, dim_payment_method
-- Revenue flag: is_revenue = order status in {{REVENUE_STATUSES}} AND purchase in [{{WINDOW_START}}, {{WINDOW_END}})
-- =====================================================================================================
DROP SCHEMA IF EXISTS dw CASCADE;
CREATE SCHEMA dw;

-- ---------------------------------------------------------------- dim_date
CREATE TABLE dw.dim_date AS
SELECT to_char(d, 'YYYYMMDD')::int                    AS date_key,
       d::date                                         AS date,
       extract(year FROM d)::int                       AS year,
       extract(quarter FROM d)::int                    AS quarter,
       'Q' || extract(quarter FROM d) || ' ' || extract(year FROM d) AS year_quarter,
       extract(month FROM d)::int                      AS month,
       to_char(d, 'Mon')                               AS month_name,
       to_char(d, 'YYYY-MM')                           AS year_month,
       date_trunc('month', d)::date                    AS month_start,
       extract(isodow FROM d)::int                     AS day_of_week,      -- 1 = Monday
       to_char(d, 'Dy')                                AS day_name,
       extract(isodow FROM d) IN (6, 7)                AS is_weekend,
       extract(week FROM d)::int                       AS iso_week,
       d >= DATE '{{WINDOW_START}}' AND d < DATE '{{WINDOW_END}}' AS is_in_window
FROM generate_series(DATE '2016-09-01', DATE '2018-12-31', INTERVAL '1 day') AS g(d);
ALTER TABLE dw.dim_date ADD PRIMARY KEY (date_key);

-- ---------------------------------------------------------------- dim_location (grain: city + state)
CREATE TABLE dw.dim_location AS
WITH city AS (
    SELECT c.state, c.city, avg(g.lat) AS lat, avg(g.lng) AS lng
    FROM staging.customers c LEFT JOIN staging.geolocation g USING (zip_prefix)
    GROUP BY c.state, c.city)
SELECT row_number() OVER (ORDER BY state, city)::int AS location_key,
       city, state,
       CASE WHEN state IN ('AC','AP','AM','PA','RO','RR','TO') THEN 'Norte'
            WHEN state IN ('AL','BA','CE','MA','PB','PE','PI','RN','SE') THEN 'Nordeste'
            WHEN state IN ('DF','GO','MT','MS') THEN 'Centro-Oeste'
            WHEN state IN ('ES','MG','RJ','SP') THEN 'Sudeste'
            WHEN state IN ('PR','RS','SC') THEN 'Sul' ELSE 'Unknown' END AS region,
       city || ', ' || state || ', Brazil' AS geo_label,
       round(lat::numeric, 5) AS lat, round(lng::numeric, 5) AS lng
FROM city;
ALTER TABLE dw.dim_location ADD PRIMARY KEY (location_key);

-- ---------------------------------------------------------------- dim_customer (grain: customer_unique_id)
-- Olist has no registration date -> acquisition date = first purchase (any status). Location = latest order address.
CREATE TABLE dw.dim_customer AS
WITH ord AS (
    SELECT c.customer_unique_id, c.city, c.state, o.purchase_ts, o.is_revenue_status AND o.is_in_window AS is_rev
    FROM staging.orders o JOIN staging.customers c USING (customer_id)),
latest AS (
    SELECT DISTINCT ON (customer_unique_id) customer_unique_id, city, state
    FROM ord ORDER BY customer_unique_id, purchase_ts DESC NULLS LAST),
agg AS (
    SELECT customer_unique_id, min(purchase_ts) AS first_purchase_ts,
           min(purchase_ts) FILTER (WHERE is_rev) AS first_revenue_ts,
           bool_or(is_rev) AS is_purchasing_customer
    FROM ord GROUP BY customer_unique_id)
SELECT row_number() OVER (ORDER BY a.first_purchase_ts, a.customer_unique_id)::int AS customer_key,
       'C' || lpad((row_number() OVER (ORDER BY a.first_purchase_ts, a.customer_unique_id))::text, 6, '0') AS customer_code,
       a.customer_unique_id,
       l.location_key,
       a.first_purchase_ts::date                              AS acquisition_date,
       date_trunc('month', a.first_revenue_ts)::date          AS cohort_month,
       coalesce(a.is_purchasing_customer, false)              AS is_purchasing_customer
FROM agg a
JOIN latest t USING (customer_unique_id)
JOIN dw.dim_location l ON l.city = t.city AND l.state = t.state;
ALTER TABLE dw.dim_customer ADD PRIMARY KEY (customer_key);
CREATE UNIQUE INDEX ON dw.dim_customer (customer_unique_id);

-- ---------------------------------------------------------------- dim_product
CREATE TABLE dw.dim_product AS
SELECT row_number() OVER (ORDER BY product_id)::int AS product_key,
       product_id, category, category_pt, category_group, photos_qty, weight_g,
       round((length_cm * height_cm * width_cm)::numeric, 0) AS volume_cm3
FROM staging.products;
ALTER TABLE dw.dim_product ADD PRIMARY KEY (product_key);
CREATE UNIQUE INDEX ON dw.dim_product (product_id);

-- ---------------------------------------------------------------- dim_payment_method
CREATE TABLE dw.dim_payment_method AS
SELECT row_number() OVER (ORDER BY payment_type)::int AS payment_method_key, payment_type,
       CASE payment_type WHEN 'credit_card' THEN 'Credit card' WHEN 'boleto' THEN 'Boleto (bank slip)'
                         WHEN 'voucher' THEN 'Voucher' WHEN 'debit_card' THEN 'Debit card'
                         ELSE 'Not defined' END AS payment_method
FROM (SELECT DISTINCT payment_type FROM staging.order_payments
      UNION SELECT 'not_defined') t;
ALTER TABLE dw.dim_payment_method ADD PRIMARY KEY (payment_method_key);

-- ---------------------------------------------------------------- fact_orders (order header)
CREATE TABLE dw.fact_orders AS
WITH items AS (
    SELECT i.order_id, count(*) AS n_items, count(DISTINCT i.seller_id) AS n_sellers,
           count(DISTINCT p.category) AS n_categories, sum(i.price) AS items_value, sum(i.freight_value) AS freight_value
    FROM staging.order_items i JOIN staging.products p USING (product_id) GROUP BY i.order_id),
pay AS (
    SELECT order_id, sum(payment_value) AS payment_value, max(payment_installments) AS installments,
           bool_or(payment_type = 'voucher') AS uses_voucher,
           (array_agg(payment_type ORDER BY payment_value DESC, payment_sequential))[1] AS primary_payment_type
    FROM staging.order_payments GROUP BY order_id)
SELECT row_number() OVER (ORDER BY o.purchase_ts, o.order_id)::int AS order_key,
       o.order_id,
       dc.customer_key,
       to_char(o.purchase_ts, 'YYYYMMDD')::int                AS date_key,
       pm.payment_method_key,
       o.order_status,
       o.purchase_ts,
       extract(hour FROM o.purchase_ts)::int                  AS purchase_hour,
       coalesce(it.n_items, 0)                                AS n_items,
       coalesce(it.n_sellers, 0)                              AS n_sellers,
       coalesce(it.n_categories, 0)                           AS n_categories,
       coalesce(it.items_value, 0)                            AS items_value,
       coalesce(it.freight_value, 0)                          AS freight_value,
       coalesce(it.items_value, 0) + coalesce(it.freight_value, 0) AS order_value,
       pay.payment_value,
       pay.installments,
       coalesce(pay.uses_voucher, false)                      AS uses_voucher,
       r.review_score,
       CASE WHEN o.dq_issue IN ('delivered_before_purchase') THEN NULL ELSE o.delivery_days END AS delivery_days,
       o.delay_days,
       o.is_late,
       o.is_revenue_status AND o.is_in_window                 AS is_revenue,
       o.is_in_window,
       o.dq_issue
FROM staging.orders o
JOIN staging.customers c USING (customer_id)
JOIN dw.dim_customer dc USING (customer_unique_id)
LEFT JOIN items it USING (order_id)
LEFT JOIN pay USING (order_id)
LEFT JOIN dw.dim_payment_method pm ON pm.payment_type = coalesce(pay.primary_payment_type, 'not_defined')
LEFT JOIN staging.order_reviews r USING (order_id);
ALTER TABLE dw.fact_orders ADD PRIMARY KEY (order_key);
CREATE UNIQUE INDEX ON dw.fact_orders (order_id);
CREATE INDEX ON dw.fact_orders (customer_key);
CREATE INDEX ON dw.fact_orders (date_key);

-- ---------------------------------------------------------------- fact_sales (line item grain)
CREATE TABLE dw.fact_sales AS
SELECT row_number() OVER (ORDER BY fo.order_key, i.order_item_id)::int AS sales_key,
       fo.order_key,
       i.order_id,
       i.order_item_id,
       fo.customer_key,
       dp.product_key,
       fo.date_key,
       fo.payment_method_key,
       dl.location_key,
       fo.order_status,
       1                                    AS quantity,
       i.price                              AS unit_price,
       i.freight_value,
       0::numeric(12, 2)                    AS discount_amount,   -- Olist carries no discount data (vouchers are a payment method)
       i.price                              AS product_revenue,
       i.price + i.freight_value            AS line_total,        -- = quantity * unit_price + freight - discount
       fo.is_revenue
FROM staging.order_items i
JOIN dw.fact_orders fo USING (order_id)
JOIN dw.dim_product dp USING (product_id)
JOIN dw.dim_customer dc ON dc.customer_key = fo.customer_key
JOIN dw.dim_location dl ON dl.location_key = dc.location_key;
ALTER TABLE dw.fact_sales ADD PRIMARY KEY (sales_key);
CREATE INDEX ON dw.fact_sales (customer_key);
CREATE INDEX ON dw.fact_sales (product_key);
CREATE INDEX ON dw.fact_sales (date_key);

-- ---------------------------------------------------------------- fact_cancellations
CREATE TABLE dw.fact_cancellations AS
SELECT order_key, order_id, customer_key, date_key, payment_method_key, order_status,
       n_items, order_value AS lost_value, payment_value
FROM dw.fact_orders
WHERE order_status IN ('canceled', 'unavailable') AND is_in_window;
ALTER TABLE dw.fact_cancellations ADD PRIMARY KEY (order_key);

ANALYZE;
