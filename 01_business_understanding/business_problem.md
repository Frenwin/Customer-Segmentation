# Business Problem

**Context.** Olist is a Brazilian marketplace integrator: small and medium sellers list products through Olist on
large Brazilian marketplaces, and Olist handles the order flow, payment and logistics contracts. The public dataset
covers ~100k orders (Sep 2016 – Oct 2018) with customers, items, payments, reviews, products, sellers and
geolocation.

**Problem.** Olist holds rich transaction data but no customer-level view of it. Marketing and CRM teams cannot
answer which customers are valuable, which are slipping away, what drives a second purchase, or how to tailor
campaigns. Every customer is treated the same, so budget is spread evenly across customers with very different
value and behaviour.

**What this project delivers.** A reproducible customer analytics platform (PostgreSQL warehouse + Python
analytics + Power BI) that:

1. builds a clean customer-level dataset from the transactional tables,
2. compares three segmentation approaches (RFM rules, RFM + K-Means, behavioural clustering) in one framework,
3. profiles each final segment with KPIs and a recommended strategy,
4. adds CLV, retention, churn, cohort, basket, geographic and purchase-pattern analysis,
5. exposes all of it in an interactive dashboard.

**Constraints of the data (shape the scope):**

| Not in the dataset | Consequence |
|---|---|
| Product cost / margin | revenue contribution only — never called profit |
| Customer demographics, registration date | acquisition date = first purchase; no age/gender segmentation |
| Discounts | `discount_amount = 0`; vouchers analysed as a payment method |
| Marketing campaigns, web/app activity | engagement KPIs (PRD 8.4) limited to purchase-based activity; campaign performance must be measured with future A/B tests |
| Returns / refunds | cancellations used as the closest signal (`fact_cancellations`) |
