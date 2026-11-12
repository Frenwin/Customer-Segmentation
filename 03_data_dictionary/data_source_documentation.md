# Data Source Documentation

**Source:** Brazilian E-Commerce Public Dataset by Olist — https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
(license CC BY-NC-SA 4.0). Real, anonymised commercial data (company and partner names replaced). Version and
SHA-256 hashes: `02_data/dataset_manifest.json`.

| File | Grain | Key fields used | PRD mapping |
|---|---|---|---|
| olist_customers_dataset | one row per order-customer | customer_id, **customer_unique_id**, zip prefix, city, state | Customer dataset (customer_id, city, state) |
| olist_orders_dataset | order | order_id, customer_id, order_status, purchase / approved / carrier / delivered / estimated timestamps | Transaction: transaction_id, date, order_status |
| olist_order_items_dataset | order line (1 unit) | order_id, order_item_id, product_id, seller_id, price, freight_value | Transaction: product_id, quantity (= 1), unit_price, total_amount |
| olist_order_payments_dataset | payment of an order | payment_type, payment_installments, payment_value | Transaction: payment_method |
| olist_order_reviews_dataset | review | review_score, comment presence, timestamps | Additional: customer feedback |
| olist_products_dataset | product | category (PT), photos, weight, dimensions | Product: product_id, category |
| product_category_name_translation | category | PT → EN | Product: category name |
| olist_sellers_dataset | seller | seller zip, city, state | (seller analysis — out of scope) |
| olist_geolocation_dataset | zip-prefix point | lat, lng | Location (aggregated per city) |

**Not available** (PRD fields marked optional / recommended): registration_date, gender, age, customer_type, discount,
product name, subcategory, cost price, campaigns, web/app activity, support records, loyalty data, returns/refunds.
How each gap is handled: `01_business_understanding/business_problem.md`.
