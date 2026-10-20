# Stage 2: modelling and evaluation protocol

## Research question and scope

Which offers change retention? Untreated churn risk is `1-E[Y(0)|X]`; uplift is
`E[Y(1)-Y(0)|X]`. High risk does not imply a positive response. All data, randomization
and response mechanisms here are synthetic. No actual retention improvement, financial
ROI, profitable campaign or production deployment has been achieved. Real experiments,
privacy controls and domain validation would be required before use.

Stage 2 retains Stage 1 unchanged. Spark reads only the features, assignments and outcomes
for modelling, validates customer coverage/uniqueness, joins them, and selects Stage 1's
22-column allowlist. It refuses more than 120,000 customers before collection. The customer
matrix is bounded; historical transactions are never collected into Python. Stage 1 `_SUCCESS`
is required. ID is used only for joining, deterministic splitting and tie-breaking; it is not
a predictor. Dates, treatment, outcomes, latent variables and oracle values are excluded from X.
Finite numeric predictors are required; missing data are rejected rather than imputed.

## Splits and selection — specified before test analysis

Sort SHA256(seed|split|customer_id) within each original randomized arm. Assign floor(60%)
to training, the next floor(80%)-floor(60%) to validation and the remainder to test. This
preserves arm coverage with deterministic near-60/20/20 counts, independent of outcomes
and original row order. A CSV records every membership. No temporal-generalization claim
is made: this is one campaign with a shared historical cutoff. Outcomes are not stratification
variables. Counts and event rates are recorded per arm/split. No observations are rerandomized.

Seeds: simulation 20261019, split 20261020, estimator 20261021, policy 20261022,
bootstrap 20261023. No seed search is performed. Medium scale is an engineering verification;
the same predeclared configuration is used at standard scale, without revising models from
medium test results. Because Stage 1 hashes the same customer IDs, scales contain overlapping
customers and are not independent replication studies.

* Churn: StandardScaler + logistic regression on training **controls only**, predicting
  `1-retained`. Choose C in {0.1,1} by control-validation Brier score. Scaling is fitted only on
  training controls. Report control-test ROC-AUC, average precision (not trapezoidal PR-AUC),
  Brier, calibration and confusion matrix at an a priori 0.5 threshold.
* Constant effect: training mean of `Z = T*Y/e - (1-T)*Y/(1-e)`, where e is recorded propensity.
  This Horvitz–Thompson ATE estimate allows unequal propensities. It is not an individualized
  score. Like other unbiased IPW estimates, it can exceed probability bounds in small samples.
* T-learner: two HistGradientBoostingClassifier models, each fitted on its training arm.
  Compute retention probabilities `m1(X)-m0(X)`, preserving negative estimates.
* S-learner: one equivalent outcome model on `[X,T]`; evaluate at T=1 and T=0. Treatment is
  legitimate only in this explicit outcome-model interface, never a churn predictor.

Trees use learning_rate=.05, max_iter=100, min_samples_leaf=40, l2_regularization=10,
early_stopping=False; max_leaf_nodes in {7,15}. No scaling is needed for trees. Early stopping
is disabled to avoid an implicit changing split with sample size. Numerical threads are limited
to two. Validation criterion for each uplift candidate is mean(prediction² - 2*prediction*Z).
This differs from transformed-outcome MSE only by the common Z² term. Under randomized
assignment, E[Z|X]=E[tau|X], so the population minimizer is observable-feature CATE. It is
noisy; a winning validation score is not proof of policy superiority. Choose each family's
candidate, then choose among constant/T/S by this same criterion. Deterministic ties use
leaf count within family and family name overall. No refitting on validation is performed.

The orchestration writes selection.json and fitted models before test prediction. It then
freezes test scores and policy decisions in test-predictions.npz before test evaluation.
Only after observed evaluation does it load the test customers' oracle table. Training and
policy construction functions cannot accept oracle columns. This is an interface boundary,
not a security boundary. The saved models.joblib is local, ignored and version-dependent;
only load artifacts you trust. Resolved settings, package versions and aggregate metrics
are saved. Models are not production scoring services.

## Causal evaluation definitions

The test observed effect signal is `Z_i = T_i Y_i/e_i - (1-T_i)Y_i/(1-e_i)`.
For fixed binary policy pi, incremental retention versus no offer is
`mean(pi_i * Z_i)` over **all test customers**, not the selected subset. This is a
Horvitz–Thompson estimate of `E[pi(X)*(Y(1)-Y(0))]`. It uses known randomized propensities,
not observed arm proportions or raw selected-customer retention rates. No fitted nuisance
models or doubly robust claims are involved. Consistency, positivity, no interference and
randomization are assumptions built into this simulation.

Ranked gain: `G(q)=sum(Z_i for top floor(q*N))/N`, with G(0)=0. Its endpoint is the test
IPW ATE. Qini area is the trapezoidal integral of `G(q)-q*G(1)` over q in [0,1], computed
at all customer ranks (101 points retained for plots). This is an unnormalized gain-area
measure in probability units; it is neither individual causal accuracy nor a standardized
commercial Qini score. Constant predictions use hashed ties, so their finite-sample Qini
need not be exactly zero. Curves for all models are descriptive, never a new selection rule.

Oracle MAE/RMSE compare predictions with full-state tau on test customers only. Report mean
predicted/true effect, Spearman correlation and ten ranked calibration groups. Correlation
is undefined (JSON null) for constant scores. Oracle tau depends on inaccessible latent
state: the learnable target is E[tau|22 observed features], not full-state tau itself. Error
combines model error and irreducible latent variation; this study does not estimate an oracle
irreducible-error floor. Group averages and policy ranking offer complementary evidence.
Oracle expectations are simulation diagnostics unavailable in real deployments, never used
to select models, hyperparameters, budgets or customers.

## Fair policies and uncertainty

Predeclared requested outreach fractions: 5%,10%,20%,30%,50%. The selected uplift rule ranks
descending estimated effect and sends only to positive-scoring customers. Actual k is
min(floor(q*N), number of positive selected-model scores). Random and churn policies receive
**exactly this same k**. Report achieved k and actual fraction; a saturated cap may repeat
allocations across requested budgets. This prevents comparisons that silently use unequal
outreach. An all-negative model yields zero outreach for all comparators. Churn prioritizes
highest untreated churn risk. Random uses a seeded customer hash; tied scores use a separate
hash domain, not outcome-dependent order. Constant-effect policies are equivalent to a
random ranking in expectation, so their relevant comparator is random targeting.

These are proposed counterfactual allocations, not historical assignments. The operational
rules use only scores and IDs, with no access to test treatment, outcomes or oracle. The
positive-count cap depends only on test covariates/scores, never outcomes. Report oracle
increment `mean(pi*tau)` and expected absolute retention `mean(p0+pi*tau)` as diagnostics.
Oracle expectations condition on this finite synthetic test cohort and have no outcome-sampling
error; they are not claimed to be known for a future population.

For observed ATE, policy increments and uplift-minus-random/churn differences, resample whole
test customers with replacement 1,000 times. Use identical resample indices for all policies,
then percentile 95% intervals. Models, membership and individual policy decisions stay fixed:
no fitting, oracle use, reranking or budget optimization inside bootstrap. These intervals
condition on fitted rules and realized allocation boundaries, omit training/selection and
future threshold uncertainty, and do not maintain an exact budget within each resample.
They are an approximate conditional customer-bootstrap analysis, not exact finite-population
randomization intervals. Pairwise intervals preserve covariance; overlapping marginal intervals
are not a test. Intervals are pointwise and unadjusted for multiple models/budgets, so isolated
positive findings warrant caution rather than a blanket superiority claim.

## Reproduction

The pinned Stage 2 NumPy release requires Python >=3.12; local execution uses Python 3.14.3.
The package requirement reflects this rather than promising unsupported Python 3.11 installs.

```bat
python -m pip install -e ".[dev]"
python -m retention_uplift.cli generate --config configs/medium.toml --output data/medium
python -m retention_uplift.cli run-stage2 --input data/medium --output data/stage2-medium
python -m retention_uplift.cli generate --config configs/evaluation.toml --output data/evaluation
python -m retention_uplift.cli run-stage2 --input data/evaluation --output data/stage2-evaluation
python -m retention_uplift.cli generate --config configs/standard.toml --output data/standard
python -m retention_uplift.cli run-stage2 --input data/standard --output data/stage2-standard
python -m ruff check .
python -m ruff format --check .
python -m pytest -q --basetemp=data/test-stage2-tmp
```

Use a new output directory for repeats; never overwrite evidence. CI's integration run uses
160 customers and five boosting iterations; it verifies mechanics, not model quality. Test
outputs and model binaries remain under ignored data/. Aggregate results and four scientific
plots can be copied to reports/. The full historical generator still uses Spark and the
tested bounded Windows portable sink. Local scale is not a distributed throughput benchmark.
The 25,000-customer evaluation profile is an intermediate resource option. The attempted
100,000-customer run exhausted the default Java heap during readback validation on an 8 GB
Windows machine; its partial files have no success manifest and are not modelling inputs.
A minimal Stage 1 cache-lifetime correction releases generated tables before disk readback;
an integration regression assertion checks that release. This does not establish that the
100,000 profile now fits: the completion report records only successfully executed scales.

Stage 2 alone does not implement financial optimization or an explanation service. The merged
[Stage 3](financial-decisions.md) adds explicit illustrative cost/value assumptions and pilot
planning; [Stage 4](assistant.md) adds the local explanation API/UI. These extensions do not
establish commercial value or production readiness.

References: [scikit-learn leakage guidance](https://scikit-learn.org/stable/common_pitfalls),
[HistGradientBoostingClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html).
