# Executive Summary — Customer Segmentation & Analytics (Olist)

**Scope.** 93,104 customers, 96,211 delivered orders, R$ 15,373,120 revenue (items + freight), Jan 2017 – Aug 2018. Brazilian marketplace data; no cost, demographic or campaign data → revenue (not profit) contribution only.

## Headline numbers

| KPI | Value |
|---|---:|
| Purchasing customers | 93,104 |
| Average order value | R$ 159.79 |
| Repeat purchase rate | 3.00% |
| 3-month retention rate | 0.92% |
| Inactive > 278 days | 37.42% |
| Revenue from top 20 % customers | 53.5% |
| Predicted 12-month repeat revenue (existing base) | R$ 230,277 |

## Segmentation

Three approaches were compared (127 logged runs). Selected: **E2-rfm-log-standard-kmeans-k4** (best composite of separation, stability, size balance and business interpretability, scored across all candidate feature spaces). RFM-only approaches were stable but reduce to recency × spend bins because 97 % of customers buy once.

| segment_id | segment_name | customers | customer_share | revenue_contribution | avg_order_value | avg_review_score |
|---|---|---|---|---|---|---|
| S1 | At Risk | 31,608 | 33.9% | 61.2% | R$ 297.68 | 4.04 |
| S2 | Hibernating | 41,746 | 44.8% | 18.6% | R$ 68.32 | 4.17 |
| S3 | New Customers | 16,961 | 18.2% | 14.6% | R$ 132.75 | 4.31 |
| S4 | Loyal Customers | 2,789 | 3.0% | 5.6% | R$ 145.95 | 4.20 |

## What to do

1. **Almost every customer buys once.** Make the **second purchase** the north-star CRM metric (6-month repeat rate, baseline 3.13%, best cohort 3.56%).
2. **61.2% of revenue sits in 'At Risk'.** Win-back for 'At Risk' in the original category, incentive capped by the expected value; start with the high-value-at-risk list (top-20 % spenders, inactive 167-278 days).
3. **Late delivery is the strongest controllable driver of dissatisfaction.** Service recovery for the 6,495 customers with a late order before any promotion (apology + voucher, carrier escalation); flag them with `late_delivery_share` in `dim_customer`.
4. **Freight is a hidden price for small baskets.** Free-shipping threshold set just above the typical small basket to lift AOV.
5. **Cross-selling signal is weak in this data.** Run bundling / 'frequently bought together' as an A/B test (home: bed_bath_table + home_comfort is the most consistent pair) rather than a roll-out.
6. **Segments are lifecycle stages: 'New' customers lapse within months.** Act while customers are 'New': onboarding and second-purchase offer in the first 90 days.

Details: `customer_insights.md`, `segment_profiles.md`, `marketing_recommendations.md`; dashboard: `11_powerbi/CustomerSegmentation.pbip`.
