-- =====================================================================================================
-- LAYER 2 - STAGING
-- Type standardisation, null handling, de-duplication, text normalisation, date normalisation.
-- Every rule below is documented in 05_data_engineering/documentation/data_cleaning_rules.md.
-- Rows are NOT silently dropped here: invalid rows are flagged (is_valid_* / dq_issue) so the validation layer
-- can count them and the warehouse layer can filter them explicitly.
-- =====================================================================================================
DROP SCHEMA IF EXISTS staging CASCADE;
CREATE SCHEMA staging;

-- ---------------------------------------------------------------- customers (1 row per order-level customer_id)
-- Olist issues a new customer_id for every order; customer_unique_id identifies the person.
CREATE TABLE staging.customers AS
SELECT DISTINCT ON (trim(customer_id))
       trim(customer_id)                                   AS customer_id,
       trim(customer_unique_id)                            AS customer_unique_id,
       lpad(trim(customer_zip_code_prefix), 5, '0')        AS zip_prefix,
       initcap(trim(customer_city))                        AS city,
       upper(trim(customer_state))                         AS state
FROM raw.customers
WHERE nullif(trim(customer_id), '') IS NOT NULL
ORDER BY trim(customer_id);
ALTER TABLE staging.customers ADD PRIMARY KEY (customer_id);
CREATE INDEX ON staging.customers (customer_unique_id);

-- ---------------------------------------------------------------- orders
CREATE TABLE staging.orders AS
SELECT DISTINCT ON (trim(order_id))
       trim(order_id)                                          AS order_id,
       trim(customer_id)                                       AS customer_id,
       lower(trim(order_status))                               AS order_status,
       nullif(order_purchase_timestamp, '')::timestamp         AS purchase_ts,
       nullif(order_approved_at, '')::timestamp                AS approved_ts,
       nullif(order_delivered_carrier_date, '')::timestamp     AS carrier_ts,
       nullif(order_delivered_customer_date, '')::timestamp    AS delivered_ts,
       nullif(order_estimated_delivery_date, '')::timestamp    AS estimated_delivery_ts
FROM raw.orders
WHERE nullif(trim(order_id), '') IS NOT NULL
ORDER BY trim(order_id), order_purchase_timestamp;
ALTER TABLE staging.orders ADD PRIMARY KEY (order_id);
ALTER TABLE staging.orders
    ADD COLUMN purchase_date        date,
    ADD COLUMN delivery_days        numeric,
    ADD COLUMN delay_days           numeric,
    ADD COLUMN is_late              boolean,
    ADD COLUMN is_in_window         boolean,
    ADD COLUMN is_revenue_status    boolean,
    ADD COLUMN dq_issue             text;
UPDATE staging.orders SET
    purchase_date     = purchase_ts::date,
    delivery_days     = round((extract(epoch FROM delivered_ts - purchase_ts) / 86400)::numeric, 2),
    delay_days        = round((extract(epoch FROM delivered_ts - estimated_delivery_ts) / 86400)::numeric, 2),
    is_late           = CASE WHEN delivered_ts IS NULL THEN NULL ELSE delivered_ts::date > estimated_delivery_ts::date END,
    is_in_window      = purchase_ts >= DATE '{{WINDOW_START}}' AND purchase_ts < DATE '{{WINDOW_END}}',
    is_revenue_status = order_status IN ({{REVENUE_STATUSES}});
-- data-quality flags (first matching issue wins)
UPDATE staging.orders SET dq_issue = CASE
    WHEN purchase_ts IS NULL                                         THEN 'missing_purchase_ts'
    WHEN order_status = 'delivered' AND delivered_ts IS NULL         THEN 'delivered_without_delivery_date'
    WHEN delivered_ts < purchase_ts                                  THEN 'delivered_before_purchase'
    WHEN approved_ts < purchase_ts                                   THEN 'approved_before_purchase'
    WHEN NOT EXISTS (SELECT 1 FROM raw.order_items i WHERE i.order_id = orders.order_id) THEN 'order_without_items'
    ELSE NULL END;
CREATE INDEX ON staging.orders (customer_id);

-- ---------------------------------------------------------------- order items (1 row = 1 unit sold)
CREATE TABLE staging.order_items AS
SELECT DISTINCT ON (trim(order_id), order_item_id::int)
       trim(order_id)                               AS order_id,
       order_item_id::int                           AS order_item_id,
       trim(product_id)                             AS product_id,
       trim(seller_id)                              AS seller_id,
       nullif(shipping_limit_date, '')::timestamp   AS shipping_limit_ts,
       price::numeric(12, 2)                        AS price,
       freight_value::numeric(12, 2)                AS freight_value
FROM raw.order_items
ORDER BY trim(order_id), order_item_id::int;
ALTER TABLE staging.order_items ADD PRIMARY KEY (order_id, order_item_id);
CREATE INDEX ON staging.order_items (product_id);

-- ---------------------------------------------------------------- payments
CREATE TABLE staging.order_payments AS
SELECT trim(order_id)                          AS order_id,
       payment_sequential::int                 AS payment_sequential,
       lower(trim(payment_type))               AS payment_type,
       payment_installments::int               AS payment_installments,
       payment_value::numeric(12, 2)           AS payment_value
FROM raw.order_payments;
CREATE INDEX ON staging.order_payments (order_id);

-- ---------------------------------------------------------------- reviews: keep the latest answer per order
-- raw has 814 duplicated review_id and 551 orders with >1 review (customer re-reviewed).
CREATE TABLE staging.order_reviews AS
SELECT DISTINCT ON (trim(order_id))
       trim(review_id)                                AS review_id,
       trim(order_id)                                 AS order_id,
       review_score::int                              AS review_score,
       nullif(review_comment_message, '') IS NOT NULL AS has_comment,
       nullif(review_creation_date, '')::timestamp    AS review_created_ts,
       nullif(review_answer_timestamp, '')::timestamp AS review_answered_ts
FROM raw.order_reviews
ORDER BY trim(order_id), review_answer_timestamp DESC NULLS LAST;
ALTER TABLE staging.order_reviews ADD PRIMARY KEY (order_id);

-- ---------------------------------------------------------------- products (+ English category, macro group)
CREATE TABLE staging.products AS
SELECT trim(p.product_id)                                             AS product_id,
       coalesce(nullif(p.product_category_name, ''), 'sem_categoria') AS category_pt,
       coalesce(t.product_category_name_english,
                CASE p.product_category_name
                    WHEN 'pc_gamer' THEN 'pc_gamer'
                    WHEN 'portateis_cozinha_e_preparadores_de_alimentos' THEN 'kitchen_portables_and_food_preparers'
                END,
                'uncategorized')                                      AS category,
       nullif(p.product_photos_qty, '')::numeric::int                AS photos_qty,
       nullif(p.product_weight_g, '')::numeric                       AS weight_g,
       nullif(p.product_length_cm, '')::numeric                      AS length_cm,
       nullif(p.product_height_cm, '')::numeric                      AS height_cm,
       nullif(p.product_width_cm, '')::numeric                       AS width_cm
FROM raw.products p
LEFT JOIN raw.category_translation t ON t.product_category_name = p.product_category_name;
ALTER TABLE staging.products ADD PRIMARY KEY (product_id);
ALTER TABLE staging.products ADD COLUMN category_group text;
UPDATE staging.products SET category_group = CASE
    WHEN category ~ '^(bed_bath_table|furniture|home_|housewares|kitchen|la_cuisine|office_furniture|air_conditioning)' THEN 'Home & Furniture'
    WHEN category ~ '^(health_beauty|perfumery|diapers)'                                                      THEN 'Health & Beauty'
    WHEN category ~ '^(computers|electronics|telephony|fixed_telephony|tablets|pc_gamer|consoles|audio|cine_photo|signaling)' THEN 'Electronics & Tech'
    WHEN category ~ '^(small_appliances|home_appliances|kitchen_portables)'                                   THEN 'Appliances'
    WHEN category ~ '^(sports_leisure|fashion_sport)'                                                        THEN 'Sports & Leisure'
    WHEN category ~ '^(fashio|luggage)'                                                                      THEN 'Fashion & Accessories'
    WHEN category ~ '^(watches_gifts|cool_stuff|christmas|party|flowers|art)'                                THEN 'Gifts & Lifestyle'
    WHEN category ~ '^(toys|baby)'                                                                           THEN 'Toys & Baby'
    WHEN category ~ '^(garden_tools|costruction|construction|home_construction|security)'                    THEN 'Construction & Garden'
    WHEN category ~ '^(auto)'                                                                                THEN 'Auto'
    WHEN category ~ '^(food|drinks)'                                                                         THEN 'Food & Drinks'
    WHEN category ~ '^(books|stationery|cds|dvds|music)'                                                     THEN 'Books, Media & Stationery'
    WHEN category ~ '^(pet_shop)'                                                                            THEN 'Pet Shop'
    WHEN category ~ '^(agro|industry|market_place)'                                                          THEN 'Business & Industry'
    ELSE 'Other' END;

-- ---------------------------------------------------------------- sellers
CREATE TABLE staging.sellers AS
SELECT DISTINCT ON (trim(seller_id))
       trim(seller_id) AS seller_id, lpad(trim(seller_zip_code_prefix), 5, '0') AS zip_prefix,
       initcap(trim(seller_city)) AS city, upper(trim(seller_state)) AS state
FROM raw.sellers ORDER BY trim(seller_id);
ALTER TABLE staging.sellers ADD PRIMARY KEY (seller_id);

-- ---------------------------------------------------------------- geolocation: 1 point per zip prefix
-- raw has ~1M rows (many duplicates per prefix) and some coordinates outside Brazil -> bounding-box filter + median.
CREATE TABLE staging.geolocation AS
SELECT lpad(trim(geolocation_zip_code_prefix), 5, '0')                                   AS zip_prefix,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY geolocation_lat::double precision)     AS lat,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY geolocation_lng::double precision)     AS lng,
       count(*)                                                                           AS n_points
FROM raw.geolocation
WHERE geolocation_lat::double precision BETWEEN -34.0 AND 5.5
  AND geolocation_lng::double precision BETWEEN -74.0 AND -34.5
GROUP BY 1;
ALTER TABLE staging.geolocation ADD PRIMARY KEY (zip_prefix);

ANALYZE;
