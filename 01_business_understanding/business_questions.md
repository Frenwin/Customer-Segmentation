# Business Questions — Answers (PRD 2.1)

Window Jan 2017 – Aug 2018, snapshot 2018-09-01, delivered orders only, revenue = items + freight (R$).
Every number is produced by the pipeline; the source file is given for each answer.

## A. Customer Overview
| Question | Answer | Source |
|---|---|---|
| Total registered customers? | **96,096** persons placed an order (any status); 93,104 have ≥ 1 delivered order | `09_kpi_framework/business_metrics.md` |
| Active customers? | **58,267** (62.6 %) purchased within the last 278 days (inactivity threshold T) | Power BI p1, `mart.customer_segmentation` |
| Customer acquisition trend? | new customers per month grew from 718 (Jan 2017) to 6,000–7,000 per month in 2018; peak 7,061 in Nov 2017 (Black Friday); Jan–Aug revenue +143 % YoY | `08_.../purchase_behavior/monthly_kpi.csv` |
| % returning customers? | **3.0 %** of customers have ≥ 2 orders; returning customers are 1–3 % of each month's buyers | `ANALYTICS_REPORT.md` §6.3 |
| Distribution by location? | Sudeste 68.6 % of customers / 64.6 % of revenue (SP alone: 42 % of customers, 37 % of revenue); remote regions spend more per customer (Norte R$ 230 vs Sudeste R$ 156) but wait longer | `08_.../geographic_analysis/` |

## B. Customer Value
| Question | Answer | Source |
|---|---|---|
| Highest-revenue customers? | ranked list (pseudonymous codes) on Power BI p3 "Top 10" and p6 "High-value at-risk" | Power BI |
| Segment with largest revenue? | **At Risk** — 33.9 % of customers, **61.2 % of revenue** (high-ticket one-time buyers) | `10_business_insights/segment_profiles.md` |
| Average spending per customer? | **R$ 165.12** (median R$ 107.78); AOV R$ 159.79 | KPI dictionary |
| CLV distribution? | historical CLV right-skewed, median R$ 108; predicted 12-month repeat value only R$ 2.47 per customer (BG/NBD × Gamma-Gamma, holdout-validated) | `ANALYTICS_REPORT.md` §6.2 |
| Do few customers generate most revenue? | moderately: top 10 % → 38.3 %, top 20 % → 53.5 % of revenue | revenue Pareto |

## C. Customer Behaviour
| Question | Answer | Source |
|---|---|---|
| How often do customers buy? | 1.03 orders per customer; 97 % buy once | KPI dictionary |
| Average transaction value? | AOV R$ 159.79; 1.14 items per order; 2.9 installments on average | §6.8 |
| Most purchased categories? | Home & Furniture (24.7 % of revenue), Electronics & Tech (14.1 %), Gifts & Lifestyle (13.0 %), Health & Beauty (12.0 %) | `08_.../purchase_behavior/category_group.csv` |
| Behaviour per segment? | At Risk: high ticket (AOV R$ 298, 4 installments); Hibernating: low ticket (R$ 68), freight 26 % of value; New: recent, AOV R$ 133, best reviews; Loyal: 2.1 orders, the only repeaters | segment profiles |
| Change over time? | volume grew strongly, behaviour did not: 6-month repeat rate 2.7–3.6 % in every acquisition quarter, no improving trend; weekday-heavy buying (Mon–Tue peak) | §6.3, §6.8 |

## D. Customer Retention
| Question | Answer | Source |
|---|---|---|
| Retention rate? | **0.92 %** (3-month periods, pooled: customers of the previous period who buy again) | `mart.period_retention` |
| Churn rate? | 99.1 % on the same 3-month base; **37.4 %** of customers are inactive > 278 days; **96.2 %** of customers with a full observation window never returned | §6.3, §6.5 |
| Highest churn-risk segment? | **Hibernating** (48.2 % already inactive), then At Risk (43.7 %) | segment profiles |
| How many never buy again? | 90,315 customers (97 %) have exactly one delivered order | §6.3 |
| Repeat behaviour over time? | flat: no acquisition quarter exceeds 3.6 % second purchase within 6 months; month-1 cohort retention ~0.5 % | §6.4 |

## E. Customer Segmentation
| Question | Answer | Source |
|---|---|---|
| Optimal number of segments? | **4** (RFM log-standardised K-Means), selected from 127 runs on a composite of separation, stability, balance and interpretability; the behavioural K = 6 model is a close second and is kept as a secondary lens | `07_.../results/EXPERIMENT_RESULTS.md` |
| Characteristics of each segment? | At Risk · Hibernating · New Customers · Loyal Customers — see profiles | `10_business_insights/segment_profiles.md` |
| Most profitable segment? | cost data is not available, so profitability cannot be measured; **highest revenue** = At Risk (61 %), **highest value per customer** = Loyal (R$ 309 historical, R$ 8.8 predicted 12-month) | segment profiles |
| Growth potential? | New Customers (17k, still inside the 90-day second-purchase window) and Loyal Customers (2–5× the predicted 12-month CLV of the other segments) | marketing recommendations |
| Strategy per segment? | see `10_business_insights/marketing_recommendations.md` | |
