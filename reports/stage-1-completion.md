# Stage 1 engineering completion report

Verification date: 19 October 2026, Europe/London. All reported customer results are synthetic.
Machine-readable evidence: [smoke-validation.json](smoke-validation.json).

## A. Implementation summary

Implemented a src-layout Python package with configurable customer/transaction simulation,
customer-level randomization, observed activity/retention outcomes, isolated oracle ground truth,
a historical-only Spark feature API, schema/data validation, Parquet persistence and a CLI.
Added smoke/standard TOML profiles, 35 tests, a lightweight GitHub Actions workflow and technical
documentation. Expanded README and preserved/extended the original Python .gitignore.

Core modules: config.py, randomness.py, simulator.py, features.py, validation.py, storage.py,
spark.py, pipeline.py and cli.py. No Stage 2 model or targeting functionality was implemented.

## B. Data-generation design

- Verified smoke: **1,000 customers and 50,524 historical transactions**.
- Configured standard: 100,000 customers; not executed or benchmarked.
- History: 2025-01-01 through 2025-12-31. Assignment: 2026-01-01.
- Outcome: 2026-01-02 through 2026-01-31 inclusive; retained means >=1 qualifying activity day.
- Seed: **20261019**. Equal-weight overlapping stable/drifting/low-engagement/multi-product/
  price-sensitive/message-averse latent archetypes, with noisy observable behaviour.
- Separate keyed SHA-256 pseudo-random streams assign treatment and simulate outcomes independently
  of historical generation. Bernoulli propensity .5 is recorded for every customer.
- Logistic baseline and shifted-logit offer response produce bounded p0/p1 and tau=p1−p0.
  Positive response depends on engagement, drift and sensitivity; aversion can make response negative.
- Only the assigned arm's binary outcome is sampled; oracle probabilities are not observed labels.
- Transaction amounts are integer GBP pence; card spending excludes savings/transfers.

Equations, parameters, fixed constants and limitations are in [simulation.md](../docs/simulation.md).

## C. Spark pipeline

Spark generates ranges/month-slot expansions, filters history, aggregates counts/amounts/recency/
variability/window trends/product shares, joins customer records, and checks keys, schemas,
foreign keys and experiment integrity. Zero-transaction customers remain through a left join.
Integer monetary moments ensure partition-stable aggregation before final numeric conversions.

Feature-table schema (22 predictors plus two audit fields):

```text
customer_id                  string
tenure_days                  int
transaction_count            bigint
monthly_frequency            double
card_spend_gbp               double
mean_transaction_gbp         double
transaction_stddev_gbp       double
active_months                bigint
recency_days                 int
transactions_30d             bigint
transactions_90d             bigint
transactions_previous_30d    bigint
activity_change_30d          bigint
card_spend_30d_gbp           double
card_spend_90d_gbp           double
card_count                   bigint
savings_count                bigint
transfer_count               bigint
products_used                int
card_share                   double
groceries_share              double
transport_share              double
leisure_share                double
feature_cutoff               date
```

Physical separation: raw/customers, raw/transactions, processed/features, experiment/assignments,
experiment/outcomes and evaluation_only/truth. Each customer-grain table had exactly 1,000 rows.
The actual Windows run used bounded portable Parquet writes and Spark Parquet reads.

## D. Verification results

Commands executed from the isolated checkout (PowerShell invocation shown; CMD equivalents use
the same executable/arguments without `&`). JAVA_HOME referenced the existing Java 25.0.2 JDK.

```powershell
uv pip install --python .venv\Scripts\python.exe --no-deps -e .
& .venv\Scripts\python.exe -m ruff check .
& .venv\Scripts\python.exe -m ruff format --check .
& .venv\Scripts\python.exe -m pytest -q -m 'not integration' --basetemp=data/test-unit-tmp
& .venv\Scripts\python.exe -m pytest -q --basetemp=data/test-final-tmp --tb=short
& .venv\Scripts\python.exe -m retention_uplift.cli generate --config configs/smoke.toml --output data/smoke
& .venv\Scripts\python.exe -m retention_uplift.cli validate --input data/smoke
git diff --check
```

| Check | Observed result |
|---|---|
| Editable package build / CLI help | Passed |
| Ruff lint | All checks passed |
| Ruff formatting | 19 files already formatted |
| Separate unit run | 21 passed, 14 integration tests deselected, 0.27 seconds |
| Final complete suite | **35 passed, zero skipped/failed, 193.21 seconds** |
| Unit/integration breakdown | 21 unit, 14 actual Spark integration tests |
| Smoke structural checks | Passed, all six tables |
| Smoke Parquet roundtrip | Passed; fingerprints matched all six tables |
| Standalone validation CLI | Passed, exit 0; saved-table fingerprints matched smoke report |
| Output completion marker | Present |
| Git whitespace checks | Passed |

The integration suite checks hand-calculated features, zero-history handling, inserted future and
pre-history events, injected treatment/outcome/latent columns, duplicate customers, future snapshots,
assignment independence/reproducibility, probability equations, extreme assigned-arm outcomes,
corrupt raw/outcome/truth records, exact six-table equality across partition counts, and end-to-end
disk execution. A 65,539-row storage test verifies row-group/file boundaries without mocking I/O.

Initial issues and resolutions:

1. Restricted sandbox temp-file/process operations blocked an early attempt. Workspace temporary
   directories and permitted local Spark execution resolved the execution-environment limitation.
2. Native Spark Parquet writing failed because Windows Hadoop support was absent. The default Windows
   portable writer avoids that operation, and its output was read and validated with Spark.
3. An initial integration run had 13 passes and one failure: floating-point standard deviation varied
   slightly across partitions. Replaced it with integer monetary moments. The final full suite passed.

Spark startup still reported missing winutils/native Hadoop and JVM module warnings. PySpark also
printed process-cleanup messages after the passing test run; the command exited zero and data checks
passed. These messages are recorded rather than interpreted as proof that native Hadoop writing works.

Smoke pipeline measured 97.716 seconds (excluding Spark startup) and 856,777 Parquet bytes. It ran
while tests were active: this is a run record, **not a performance benchmark or capacity estimate**.

## E. Statistical sanity checks

| Metric | Synthetic smoke result |
|---|---:|
| Treatment / control | 491 / 509 (49.1% / 50.9%) |
| True average expected effect | +0.02103236 (+2.103 percentage points) |
| Treated retention | 0.59877800 (59.878%) |
| Control retention | 0.54027505 (54.028%) |
| Observed treated−control difference | +0.05850295 (+5.850 percentage points) |
| Difference estimated SE | 0.03129256 |
| Approximate 95% interval | [−0.00283047, 0.11983638] |
| Effect > +.01 | 45.4% |
| Effect within ±.01 | 17.3% |
| Effect < −.01 | 37.3% |
| Min / max individual expected effect | −0.324864 / +0.392484 |

Observed difference is about 1.20 SE above the true ATE, consistent with finite-sample variation.
The interval includes zero; this run is not evidence of real-world impact or a policy advantage.
Allocation z=−0.569. Absolute covariate-balance z values were <=1.160 and absolute standardized
differences <=0.074 across tenure, transaction count, card spend and recency. No four-SE warnings.
All adversarial leakage checks passed.

## F. Reproducibility and environment

Executed locally on Windows 11 (10.0.26200), not a cloud runtime. Versions: Python 3.14.3,
Java 25.0.2, Spark 4.2.0, Py4J 0.10.9.9, PyArrow 26.0.0, pytest 9.1.1, Ruff 0.17.1.
Smoke: seed 20261019, local[2], eight partitions. Normal tests do not generate 100,000 customers.

An isolated workspace virtual environment installed test/Arrow dependencies and the package.
It referenced the user's existing PySpark installation through a local, ignored .pth file to avoid
duplicating its large distribution. The original repository/virtual environment was not modified.
Editable installation used --no-deps because these dependencies were already available. A completely
fresh dependency install and Linux execution were not established by these local checks alone.

CMD reproduction after activating an environment:

```bat
python -m pip install -e ".[dev]"
python -m pytest -q --basetemp=data/test-local-tmp
python -m retention_uplift.cli generate --config configs/smoke.toml --output data/smoke-new
python -m retention_uplift.cli validate --input data/smoke-new
python -m retention_uplift.cli generate --config configs/standard.toml --output data/standard
```

Full setup is in README. Preserve source revision, resolved config and environment versions.
Repeat runs need new output directories. Hash fingerprints are diagnostic; exact fixture equality
is tested separately. Cross-platform mathematical-library differences remain possible.

## G. Repository and GitHub status

Dedicated branch: `feature/stage-1-data-foundation`, based on initial main commit
`d8c82aa3e2866ca02cdddd6c92469b7467a27014`. The delivery message and pull request identify the
published head commit and PR URL. Main is not automatically merged. Generated data, virtual
environments, Spark artifacts, caches and binary Parquet files are excluded from Git; this report
and aggregate JSON evidence are intentionally tracked. The existing Git history is preserved.

## H. Limitations and unresolved issues

No known failing Stage 1 test remains. Native Windows Spark writing remains unavailable without
appropriate Hadoop support; the tested portable path is the default. Its serial driver sink is
not a distributed throughput claim. Full standard/500,000-customer and 10M-transaction runs were
not executed. The CI workflow was added; remote CI status must be checked independently.

Simulation assumptions are intentionally simplified, with no real customers, calibrated behaviour,
causal spillovers, noncompliance, costs or measured financial return. Oracle effects condition on
latent information unavailable to future models. Physical file separation is not security isolation.

## I. Stage 2 readiness

Ready for review and the next approved modelling stage: reproducible pre-treatment features,
randomized assignments, observed binary outcomes and isolated synthetic truth are available.
No Stage 1 data/interface blocker was found. Stage 2 still requires a split/evaluation design,
churn baselines and uplift estimators; none have been implemented. Work stops at Stage 1.
