# Customer Insights

Each insight answers PRD 11: *What happened? Why? Which segment? Business impact? What to do?* All numbers come from the pipeline outputs of this run.

## 1. Almost every customer buys once

**Finding.** 97.0% of 93,104 customers placed exactly one delivered order; 3-month retention is 0.92% and 96.2% of customers with a full 278-day window never returned.

**Why.** Olist is a marketplace: customers search a product, buy from a seller, and have no relationship with the platform brand. Second-order drivers measured on the first order (review, delivery, category, payment) all have small effects (Cramér's V < 0.1).

**Segment affected.** All segments; the loyal segment is Loyal Customers (3.0%)

**Business impact.** Expected repeat revenue from today's base in the next 12 months is only R$ 230,277 (1.50% of historical revenue): growth depends on paid acquisition.

**Recommendation.**
- Make the **second purchase** the north-star CRM metric (6-month repeat rate, baseline 3.13%, best cohort 3.56%).
- Trigger a post-delivery journey inside the 0–90 day window (median gap between purchases 71 days).
- Test every incentive against a hold-out control group.

## 2. 61.2% of revenue sits in 'At Risk'

**Finding.** 'At Risk' holds 33.9% of customers but 61.2% of revenue (AOV R$ 297.68 vs R$ 159.79 overall); 43.7% of them (13,802) are already inactive for more than 278 days. Overall the top 10 % of customers generate 38.3% of revenue and the top 20 % 53.5%.

**Why.** High-ticket single purchases (average 4.0 installments, top category Home & Furniture) drive the upper tail; there is no loyalty-driven concentration because repeat buyers are rare.

**Segment affected.** At Risk

**Business impact.** Revenue is concentrated in customers who do not come back on their own: the platform re-buys this revenue with acquisition spend every period.

**Recommendation.**
- Win-back for 'At Risk' in the original category, incentive capped by the expected value; start with the high-value-at-risk list (top-20 % spenders, inactive 167-278 days).
- Installment-friendly premium offers (interest-free plans with card issuers) for the next high-ticket purchase.
- Measure reactivation rate against a randomised hold-out.

## 3. Late delivery is the strongest controllable driver of dissatisfaction

**Finding.** Late orders average 2.27★ vs 4.29★ on time; 6.8% of delivered orders arrived late (top-quartile month 3.0%). Customers whose first order was late returned less often (2.60% vs 3.91%, p = 0.006).

**Why.** Delivery takes longer in remote states and state-level reviews fall as delivery time rises (ρ(delivery days, review) = -0.48).

**Segment affected.** all segments - 6,495 customers (7.0%) had at least one late order; highest late share in 'At Risk' (8.4%)

**Business impact.** Every late order costs ~2 review stars, depresses marketplace ratings and lowers the already small chance of a second purchase.

**Recommendation.**
- Service recovery for the 6,495 customers with a late order before any promotion (apology + voucher, carrier escalation); flag them with `late_delivery_share` in `dim_customer`.
- Operations KPI: late-delivery share with the best observed month as target; buffer delivery estimates for remote states.
- Exclude unresolved unhappy customers from promotional blasts.

## 4. Freight is a hidden price for small baskets

**Finding.** Freight is a median ~34 % of the order value in the lowest value quintile vs ~8 % in the highest.

**Why.** Shipping cost is largely fixed per parcel, so it weighs on cheap items.

**Segment affected.** Hibernating (freight = 26.4% of order value on average vs 13.0% in At Risk)

**Business impact.** Price-sensitive small-basket buyers are the least likely to come back at full freight.

**Recommendation.**
- Free-shipping threshold set just above the typical small basket to lift AOV.
- Add-on recommendations at checkout; regional fulfilment for the most frequent low-ticket categories.

## 5. Cross-selling signal is weak in this data

**Finding.** Only 0.81% of orders contain more than one category; 6 association rules pass support ≥ 10 and lift > 1.

**Why.** Single-product purchase missions and one-time buyers leave little co-purchase history.

**Segment affected.** All segments

**Business impact.** Bundles built from historical rules would rest on a few dozen baskets.

**Recommendation.**
- Run bundling / 'frequently bought together' as an A/B test (home: bed_bath_table + home_comfort is the most consistent pair) rather than a roll-out.

## 6. Segments are lifecycle stages: 'New' customers lapse within months

**Finding.** Of customers who were 'New Customers' on 2018-03-01, 60.5% are now 'Hibernating', 38.2% are now 'At Risk', 1.3% are now 'Loyal Customers' six months later. Segment sizes changed by At Risk +108%, Hibernating +112%, New Customers -10%, Loyal Customers +73%.

**Why.** With almost no second purchases, a customer's segment is driven by the time since the only order: every cohort flows from New into At Risk (high spend) or Hibernating (low spend).

**Segment affected.** Hibernating, At Risk, Loyal Customers

**Business impact.** The lapsing segments grow every month by construction; the window to act on a new customer is short (median gap between purchases 71 days, P90 278 days).

**Recommendation.**
- Act while customers are 'New': onboarding and second-purchase offer in the first 90 days.
- Track monthly segment migration - success = more customers moving New -> Loyal.
