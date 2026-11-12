# Data Cleaning Rules (staging layer)

Implemented in `05_data_engineering/sql/staging/01_staging.sql`; verified by `custseg.validation` (26 checks,
report in `05_data_engineering/validation/data_quality_report.md`). Rows are **flagged, not silently dropped**;
the warehouse filters explicitly with `is_revenue`.

| # | Table | Rule | Reason |
|---|---|---|---|
| C1 | all | `trim()` every id; `NULLIF(x,'')` before casting | CSV empty strings → NULL |
| C2 | all | explicit casts (`::timestamp`, `::numeric(12,2)`, `::int`) — a bad value fails the build loudly | type standardisation |
| C3 | customers, orders, items, sellers | `DISTINCT ON (business key)` | duplicate protection (0 found) |
| C4 | customers / sellers | zip prefix left-padded to 5 digits; city `initcap`, state `upper` | text normalisation |
| C5 | orders | `order_status` lower-cased; `purchase_date = purchase_ts::date` | date normalisation |
| C6 | orders | `is_in_window = purchase in [2017-01-01, 2018-09-01)` | 2016 has a collection gap, Sep/Oct 2018 is truncated |
| C7 | orders | `is_revenue_status = status = 'delivered'` | other statuses are in flight or cancelled |
| C8 | orders | `dq_issue` = first of: missing purchase ts · delivered without date · delivered before purchase · approved before purchase · order without items | invalid-transaction flagging |
| C9 | orders | `delivery_days`, `delay_days`, `is_late` (delivered date > estimated date) | delivery experience features |
| C10 | reviews | one review per order: latest `review_answer_timestamp` | 814 duplicated review ids, 551 re-reviewed orders |
| C11 | products | category → English translation; 2 missing translations mapped manually; NULL → `uncategorized`; 71 categories → 15 `category_group`s | readable reporting |
| C12 | geolocation | keep points inside Brazil's bounding box (lat −34..5.5, lng −74..−34.5), one **median** point per zip prefix | 1M duplicated rows, 42 points outside Brazil |
| C13 | warehouse | `delivery_days = NULL` when delivered before purchase | impossible lifecycle (0 found) |
| C14 | warehouse | customer grain = `customer_unique_id`; location = address of the latest order | `customer_id` is per order |
| C15 | warehouse | revenue = items + freight at line level; `payment_value` kept for reconciliation (0.25 % of orders differ by > R$1: installment interest) | consistent revenue definition |
