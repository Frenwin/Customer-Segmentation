# Segment Profiles

Final model: **E2-rfm-log-standard-kmeans-k4**. Snapshot 2018-09-01. Churn = inactive > 278 days. Retention rate (segment) = share of the segment with ≥ 2 orders. CLV: historical = revenue to date; predicted = next 12 months (BG/NBD × Gamma-Gamma). Revenue = items + freight (no cost data → revenue contribution, not profit).

## S1 · At Risk

*High-spend one-time buyers whose typical last purchase is at or past the inactivity threshold - previously valuable, now slipping away.*

| Attribute | Value |
|---|---|
| Segment ID | S1 |
| Customer count | 31,608 |
| % of total customers | 33.9% |
| Average recency | 275 days |
| Average frequency | 1.00 orders |
| Average monetary | R$ 297.68 (median R$ 200.43) |
| Revenue contribution | 61.2% (R$ 9,409,113) |
| Average order value | R$ 297.68 |
| Average CLV | historical R$ 297.68 · predicted 12 m R$ 1.98 |
| Retention rate (repeat) | 0.00% |
| Churn rate (inactive > 278 d) | 43.7% |
| Experience | review 4.04 · late deliveries 8.4% · 14.5 delivery days |
| Payment / basket | 4.0 installments · 1.26 items/order · freight 13.0% of value |
| Top category group | Home & Furniture (25.7% of segment) |
| Size 6 months earlier → now | 15,164 → 31,608 (+108.4%) |
| **Recommended strategy** | Targeted win-back in the original category with a personalised incentive capped by expected value; prioritise the high-value-at-risk list (top-20 % spenders still inside the threshold); measure reactivation against a hold-out group. |

## S2 · Hibernating

*One low-value purchase; the typical member is at or past the inactivity threshold.*

| Attribute | Value |
|---|---|
| Segment ID | S2 |
| Customer count | 41,746 |
| % of total customers | 44.8% |
| Average recency | 291 days |
| Average frequency | 1.00 orders |
| Average monetary | R$ 68.32 (median R$ 65.95) |
| Revenue contribution | 18.6% (R$ 2,851,883) |
| Average order value | R$ 68.32 |
| Average CLV | historical R$ 68.32 · predicted 12 m R$ 1.89 |
| Retention rate (repeat) | 0.00% |
| Churn rate (inactive > 278 d) | 48.2% |
| Experience | review 4.17 · late deliveries 6.9% · 12.7 delivery days |
| Payment / basket | 2.2 installments · 1.06 items/order · freight 26.4% of value |
| Top category group | Home & Furniture (24.8% of segment) |
| Size 6 months earlier → now | 19,718 → 41,746 (+111.7%) |
| **Recommended strategy** | Low-cost reactivation (newsletter, seasonal campaigns such as Black Friday). |

## S3 · New Customers

*Recently acquired (last ~3 months), one purchase, typical basket.*

| Attribute | Value |
|---|---|
| Segment ID | S3 |
| Customer count | 16,961 |
| % of total customers | 18.2% |
| Average recency | 47 days |
| Average frequency | 1.00 orders |
| Average monetary | R$ 132.75 (median R$ 103.87) |
| Revenue contribution | 14.6% (R$ 2,251,590) |
| Average order value | R$ 132.75 |
| Average CLV | historical R$ 132.75 · predicted 12 m R$ 3.79 |
| Retention rate (repeat) | 0.00% |
| Churn rate (inactive > 278 d) | 0.0% |
| Experience | review 4.31 · late deliveries 4.0% · 8.7 delivery days |
| Payment / basket | 2.7 installments · 1.12 items/order · freight 21.7% of value |
| Top category group | Home & Furniture (26.9% of segment) |
| Size 6 months earlier → now | 18,771 → 16,961 (-9.6%) |
| **Recommended strategy** | Onboarding journey and second-purchase incentive inside the 0-90 day window where most second purchases happen; ensure the first delivery is on time. |

## S4 · Loyal Customers

*Customers with two or more delivered orders - the only group with proven repeat behaviour.*

| Attribute | Value |
|---|---|
| Segment ID | S4 |
| Customer count | 2,789 |
| % of total customers | 3.0% |
| Average recency | 222 days |
| Average frequency | 2.11 orders |
| Average monetary | R$ 308.55 (median R$ 225.63) |
| Revenue contribution | 5.6% (R$ 860,533) |
| Average order value | R$ 145.95 |
| Average CLV | historical R$ 308.55 · predicted 12 m R$ 8.79 |
| Retention rate (repeat) | 100.00% |
| Churn rate (inactive > 278 d) | 32.8% |
| Experience | review 4.20 · late deliveries 5.8% · 12.3 delivery days |
| Payment / basket | 3.3 installments · 1.21 items/order · freight 19.9% of value |
| Top category group | Home & Furniture (35.7% of segment) |
| Size 6 months earlier → now | 1,614 → 2,789 (+72.8%) |
| **Recommended strategy** | Membership / loyalty points on the 2nd-to-3rd order, category cross-sell based on their history, review-request after on-time delivery. |

## Segment migration (customers present at both snapshots)

Rows = segment at 2018-03-01, columns = segment at 2018-09-01, values = share of row.

| from (6 months earlier) | At Risk | Hibernating | Loyal Customers |
|---|---|---|---|
| At Risk | 96.8% | 2.3% | 0.9% |
| Hibernating | 0.0% | 99.0% | 1.0% |
| Loyal Customers | 0.0% | 0.0% | 100.0% |
| New Customers | 38.2% | 60.5% | 1.3% |
