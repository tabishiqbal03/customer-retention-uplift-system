# Stage 3: illustrative financial decisions and experimental design

All customers and transactions are synthetic. All values, offer costs and campaign limits
are illustrative; no company customer lifetime values or actual offer costs have been measured.
No real marketing campaign ran, and no real retention or profitability improvement was demonstrated.
Estimated monetary results are conditional on the assumed economics. Real deployment needs domain
validation, privacy assessment and genuine randomized experimental evidence.

## Protocol and independence

Stage 2's test findings were already examined. They are not untouched confirmation for Stage 3.
The frozen T-learner remains selected by Stage 2 validation, despite some better S-learner test
metrics. No retraining or model reselection uses the new cohort. The CLI loads trusted local
Stage 2 artifacts (joblib is executable serialization; do not load untrusted files).

`run-stage3` writes protocol.json with model SHA256, full selection/training configuration,
economics, seeds and metrics before generating any new cohort. The generation seed is 20261103
and ID prefix FINAL rather than the original seed 20261019/prefix C. Prefixes enter all hashed
random streams at generation, not after generation. All old split-manifest IDs are checked for
intersection with new IDs. This is a distinct pseudorandom sample from the same designed population,
not evidence of temporal or real-world generalization. No seed search or rerandomization occurs.

Stage 1 generation/validation necessarily accesses outcomes and truth to create and validate all
six tables. This infrastructure validation is not financial policy selection. After generation,
the operational loader opens only the pre-treatment feature table and its 22-column allowlist.
It freezes scores, all scenario policy masks, planning.json and decision hashes before the financial
workflow loads assignments/outcomes. Observed estimates are saved before the oracle loader runs.
Physical separation is a code contract, not an operating-system security boundary. Tests guard
this read order. The 100,000-customer failed Stage 2 dataset is never used.

## Economic assumptions

`configs/economics.toml` is the complete prespecified grid. Monetary value means assumed net
contribution associated with an extra customer retained over the 30-day outcome horizon.
It is not measured lifetime value. Transaction count and spend are usage; spend is neither company
revenue nor company profit. The fixed-value baseline is GBP40, with GBP1.50 offer and GBP0.50
contact cost. Each selected customer incurs both costs regardless of historical assignment or
subsequent retention. No redemption model is assumed.

| Scenario | Value GBP | Offer GBP | Contact GBP | Total cost GBP |
|---|---:|---:|---:|---:|
| base | 40 | 1.50 | .50 | 2 |
| low_value | 20 | 1.50 | .50 | 2 |
| high_value | 80 | 1.50 | .50 | 2 |
| low_cost | 40 | .50 | .50 | 1 |
| high_cost | 40 | 7.50 | .50 | 8 |
| unfavourable | 10 | 11.50 | .50 | 12 |
| heterogeneous | 20–60 | 1.50 | .50 | 2 |

The grid is pedagogical, not industry-calibrated. It was written before fresh data generation.
The deliberately unfavourable offer exceeds even the maximum incremental contribution of an
extra retained customer; no outreach must be allowed. The heterogeneous mapping is precisely
`40*(.5 + .5*active_months/12 + .5*products_used/3)`, using historical active months (0–12) and
historically used products (0–3). It illustrates value-ranking changes without equating spend
with value. There is no post-treatment, latent or oracle input. Configurable base value rescales
this multiplier. Values and costs must be finite and nonnegative.

## Allocation and comparison

For each customer, predicted net GBP is `uplift*value-cost`. Negative effects remain negative.
A binary mask maximizes summed predicted net subject to spend <=GBP3000 and contacts <=2500.
Uniform cost is enforced; heterogeneous cost vectors are rejected. At uniform cost, feasible
cardinality is min(capacity,floor(budget/cost)); choose that many largest strictly positive net
values, or fewer when they run out. An exchange argument proves optimality: replacing a selected
smaller score by a larger unselected score never reduces the objective or changes cost. For free
offers the budget does not bind; the contact ceiling still does. This is optimal for the predicted
objective, not guaranteed optimal for unknown true effects. Unspent money is allowed.

No-offer, random, churn, uplift and profit share the same cohort, positive-net eligibility screen,
maximum budget, capacity and cost within a scenario. Thus comparators mean financially screened
random/churn/uplift strategies, not their unrestricted versions. Stable SHA256 ties/random order
are independent of outcomes. We impose common maxima, not identical spend; actual counts/spend are
reported. With the shared screen and uniform cost, nonempty comparator counts happen to coincide.
For fixed value, uplift and profit rankings are mathematically identical; any claimed improvement
between those policies would be misleading. Heterogeneous values can change their ranking.
Planning outputs include retained-customer expectation, gross value, spend, net, unused budget,
capacity use and counts excluded for nonpositive net or limits/no-offer. Local NPZ holds masks
and scores, from which per-customer exclusion categories can be reconstructed; it is never committed.

## Randomized financial evaluation

For recorded propensity e and randomized observed (T,Y), use
`Z=T*Y/e-(1-T)*Y/(1-e)`. For fixed mask pi, incremental retained total is `sum(pi*Z)`;
net GBP total is `sum(pi*(V*Z-C))`. Per-eligible net is total/N. The cost applies to the
proposed campaign mask, never only to customers historically assigned treatment. Under randomized
assignment, consistency and no interference, E[Z|X]=tau(X), so this targets incremental value
relative to no offer. It estimates effects, not realized cash or individual counterfactual outcomes.

1,000 paired customer resamples jointly resample all policies' retention and monetary contributions.
Masks are frozen and never reranked/refitted. Totals are resampled means times original N;
95% percentile intervals use 2.5/97.5 percentiles. Net pair differences use the SAME resamples,
retaining covariance. Cost is deterministic within each contribution, although resampling the
customer population changes selected proportions; this is a superpopulation customer-bootstrap
interpretation, not conditional finite-cohort randomization inference with exactly fixed spend
in every bootstrap draw. No-offer and identical-policy differences have exact zero intervals.

Intervals condition on fitted rules and assumed economics. They exclude model training/selection,
unknown real customer economics, population shift and scenario-selection uncertainty. Scenario
and budget comparisons are pointwise and unadjusted, not proof from a winning comparison.
Oracle tau is used afterward for separate expected-effect/net diagnostics only.

Prespecified recommendations: zero recipients => no offer; upper net CI below zero => no rollout
(negative evidence); lower CI above zero => controlled pilot; otherwise inconclusive/no rollout.
These labels describe evidence under assumptions, never automatic production decisions. Sensitivity
shows all seven scenarios; it does not select and promote the most favourable one. Predicted budget
curves use GBP0,500,1000,2000,3000,5000,10000 at fixed capacity. Break-even uplift C/V is reported for
positive fixed values; at V=0 the threshold is undefined and no strictly profitable offer exists,
even at zero cost. Heterogeneous values have customer-specific thresholds.

## Hypothetical pilot

Primary hypothesis: an offer changes 30-day retention among customers selected by the frozen base
policy. Primary outcome: >=1 qualifying activity day on days 1–30 after assignment (assignment day
excluded). Unit: unique customer, once. Prespecify consent/contact eligibility and legal exclusions,
freeze history cutoff, features, model and financial configuration before randomization. Within this
targeted population, assign 1:1 to the stated offer versus no offer, analyzing intention-to-treat.
No observed response is used to define eligibility. Baseline 60% is an illustrative planning input,
not an industry rate. Target improvement +3 percentage points, two-sided alpha .05, power .80.

The normal approximation uses r=n_treatment/n_control, pbar=(p0+r*p1)/(1+r),
A=pbar*(1-pbar)*(1+1/r), B=p0*(1-p0)+p1*(1-p1)/r, and
`n_control=ceil((z_(1-alpha/2)*sqrt(A)+z_power*sqrt(B))^2/(p1-p0)^2)`;
`n_treatment=ceil(r*n_control)`. It neglects the far tail of the two-sided alternative power,
uses a pooled null variance and separate alternative variance, and has no continuity correction.
The approach follows the [statsmodels two-proportion approximation documentation](https://www.statsmodels.org/stable/generated/statsmodels.stats.proportion.samplesize_proportions_2indep_onetail.html)
and [normal sample size documentation](https://www.statsmodels.org/stable/generated/statsmodels.stats.power.normal_sample_size_one_tail.html).
Our ratio is treatment/control; check the library's sample-1/sample-2 convention before comparing.
SciPy supplies quantiles, avoiding an extra statsmodels dependency. Inputs reject impossible
probabilities, nonpositive MDE/ratio and invalid alpha/power. Rare outcomes or small cells need a
more suitable method. A reproducible 20,000-trial binomial Monte Carlo checks the two-sided pooled
z test without continuity correction under both the alternative and null; Monte Carlo SE is saved.

Guardrails: complaints, opt-outs, adverse customer experience, offer-delivery failure, intervention
cost and retention measurement missingness. Agree quantitative stopping margins with domain owners
before a real pilot; no invented safety margin is presented as validated. Verify unique identity,
assignment logs, propensity, delivery, outcome coverage, arm balance, no post-offer features and no
cross-arm contact. Do not repeatedly test efficacy or stop at a favourable p-value. Prespecify any
safety monitoring separately. At the fixed end, consider further testing only if the two-sided
retention interval supports improvement, guardrails pass, and independently validated economics
justify it; otherwise reject or redesign. The 3pp MDE is a power input, not a guarantee or proof
that the true effect exceeds 3pp. The fresh demonstration may contain too few target-eligible
customers for the planned pilot; recruitment would require additional eligible customers.

This trial estimates offer ATE WITHIN the selected population, not superiority of entire policies.
For whole-policy comparison, randomize the broader eligible population to independent policy regimes
with equal per-person maximum budgets and contact ceilings, apply each frozen rule using only its
assigned group, and compare regime intention-to-treat retention/value across ALL assigned customers.
Account for within-regime quota dependence and avoid interference/shared offers; cluster/regime
replication may be needed. An observational historical-campaign comparison does not supply randomized
evidence. Retention two-proportion power is NOT power for a monetary policy-value estimand, which
requires its own variance/design calculation and validated costs/values.

## Reproduction and artifacts

After reproducing Stage 1 evaluation and Stage 2 artifacts as documented in README:

```bat
python -m retention_uplift.cli run-stage3 --models data/stage2-evaluation --training-source data/evaluation --output data/stage3-final
python -m pytest -q --basetemp=data/stage3-tests
python -m ruff check .
python -m ruff format --check .
```

Optional --cohort and --economics point to TOML files. Use fresh output paths; existing ones are
never overwritten. Defaults produce 10,000 fresh customers on the 8GB machine with the portable
Parquet writer. No full transaction history is collected to Python. Only aggregate reports/figures
are committed; the generated cohort, models, customer masks and scores stay ignored. The report
contains exact protocol, generation validation, versions, timing, scenarios, paired estimates,
planning and pilot simulation. A future governed LLM may explain these stable schema-versioned
fields with their caveats; it must not recalculate money, choose customers or invent evidence.
No LLM service, dashboard, API or deployment is implemented in Stage 3.
