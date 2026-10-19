# Customer retention decision brief

**Synthetic customers; illustrative GBP economics; no real campaign or profit.**

**Decision question.** Which offers are worth funding? Churn risk alone measures who may leave; it does not measure who changes behaviour because of an offer. Positive uplift must also cover cost.

**Current decision: inconclusive no rollout.** The frozen T-learner ranks customers by predicted incremental contribution less cost, excluding nonpositive opportunities. A prediction is a planning estimate, not a guaranteed customer or financial return.

**Plan.** Across 10,000 fresh synthetic customers, select 1,500; spend £3,000.00 of the £3,000.00 maximum, with a 2,500-contact ceiling. Predicted incremental retained customers: 204.68; gross value £8,187.17; net value £5,187.17. Unspent budget £0.00.

**Evidence.** Randomized-outcome estimated net value: £3,800.00 [-698.15, 8,308.20]; incremental retained customers: 170.00 [58.00, 284.00]. Brackets are pointwise 95% intervals. They condition on the model and assumed economics. They do not validate real profit.

**Assumptions.** Each extra retained customer contributes £40.00 over 30 days. Each selected customer costs £1.50 plus £0.50 contact cost, even if they leave. These are examples, not measured lifetime values or industry costs. Customer spending is not company revenue.

**Sensitivity.** Prespecified scenarios give the following decisions:

| Assumption | Contacts | Spend GBP | Estimated net GBP [95% CI] | Decision |
|---|---:|---:|---|---|
| base | 1500 | 3000.00 | 3,800.00 [-698.15, 8,308.20] | inconclusive no rollout |
| low_value | 1495 | 2990.00 | 490.00 [-1,784.10, 2,740.65] | inconclusive no rollout |
| high_value | 1500 | 3000.00 | 10,600.00 [1,637.85, 19,670.20] | controlled pilot |
| low_cost | 2500 | 2500.00 | 4,700.00 [-1,480.40, 10,599.10] | inconclusive no rollout |
| high_cost | 84 | 672.00 | 688.00 [-304.60, 1,736.20] | inconclusive no rollout |
| unfavourable | 0 | 0.00 | 0.00 [0.00, 0.00] | no offer |
| heterogeneous | 1500 | 3000.00 | 6,950.00 [797.72, 13,090.77] | controlled pilot |

**Next evidence, not rollout.** If business assumptions and guardrails are validated, randomize offers within the frozen targeted population: 4,129 controls and 4,129 treated customers for an assumed 60% baseline, +3.0 percentage-point effect, 80% power and two-sided 5% significance. This tests the offer within that population, not whole-policy superiority or profit. Review complaints, opt-outs and delivery quality; avoid repeated interim testing.

**Limits.** Designed simulation, uncertain effects, hypothetical economics and unadjusted scenario comparisons. Stage 2 results were already examined; this final cohort has a different seed and disjoint IDs. No real retention or profitability gain has been demonstrated. Real deployment requires privacy assessment, domain validation and genuine randomized evidence.
