# Stakeholder Requirements

| Stakeholder | Needs | Delivered as |
|---|---|---|
| Business Analyst | explore behaviour and performance, reproduce numbers | data mart in PostgreSQL (`mart`, `pbi` schemas), notebooks, KPI dictionary |
| Marketing Team | who to target with what message | segment profiles + strategy, Power BI page 6 (opportunity matrix, recommended campaigns) |
| CRM Team | retention, loyalty, win-back | retention/churn/cohort analysis, high-value-at-risk list, reactivation KPI |
| Management | customer contribution and revenue at a glance | Power BI page 1 (executive overview), executive summary |
| Data Analyst | clean, documented data + methods | data dictionary, data-quality report, experiment tracking workbook |
| Operations (added) | the experience drivers found in the data | late-delivery share and review score as driver KPIs |

**Non-functional (PRD 12):** reproducible (`python -m custseg.pipeline`, fixed seeds, dataset SHA-256 version),
SQL-side aggregation, pre-aggregated tables for Power BI, no PII in the dashboard (customers appear as `C000123`;
`customer_unique_id`, zip codes and coordinates of individuals are never exposed), documented transformations.
