# Evaluation Framework

The best model is **not** chosen on silhouette alone (PRD 5.4). Two stages:

**Stage 1 — best K per family** (family = feature space × algorithm, K restricted to 3–8: K = 2 is not an actionable
segmentation, K > 8 is not manageable for campaign teams). Composite score min-max normalised within the family.
Any K that produces a cluster below 1% of customers is reviewed: kept only if that cluster is a
*niche high-value* group (median spend ≥ 3 × the population median), otherwise treated as over-segmentation /
anomaly and skipped.

**Stage 2 — compare the family winners and E1 on equal terms.** Internal metrics depend on the feature space, so
every finalist is scored in **all 7 candidate feature spaces** and the metrics are averaged. *Design note:* the
first version of this stage scored all finalists in the E2 log-RFM space (→ the E2 model won); scoring in the
8-feature profile space instead made the E3 model that uses exactly those features win. Both are home-advantage
artefacts; the cross-space average gives each finalist its own space once and removes the bias evenly. Result
of this run: **E2-rfm-log-standard-kmeans-k4** (composite 0.852) ahead of
E3-beh-value-lifecycle-kmeans-k6 (0.837) — a narrow margin, reported as such.

| Criterion | Metric | Weight |
|---|---|---:|
| Cohesion / separation | silhouette (on a fixed 20,000-customer sample) | 15% |
| Separation | Davies-Bouldin (lower better) | 10% |
| Separation | Calinski-Harabasz (log) | 5% |
| Stability | bootstrap ARI (5 × 80 % refits) | 25% |
| Cluster size balance | normalised size entropy | 15% |
| Business interpretability | mean of (share of clusters with a ≥ 0.8 SD distinguishing feature, share of clusters with a unique ±0.5 SD signature) in the common 8-feature business profile | 30% |

Interpretability gets the largest weight because PRD 7 requires every final segment to have a business identity;
stability is second because a segmentation that reshuffles customers on new data cannot drive campaigns.
