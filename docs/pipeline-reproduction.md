# Customer Retention Uplift & Decision Intelligence System

**Full pipeline reproduction for the four merged stages.**

Which fintech customers should receive a retention offer so that it changes behaviour?
A churn score estimates risk; uplift estimates the change caused by an intervention.
A high-risk customer may ignore an offer, while a moderately at-risk customer may respond.
Stage 2 investigates this distinction with this reproducible randomized dataset.

Stage 1 generates customers, historical transactions, randomized assignments, observed outcomes
and hidden expected effects. It builds pre-offer features and validates their integrity.
Stage 2 adds control-only churn prediction, constant/T/S uplift estimators and equal-outreach
policy evaluation. Stage 3 adds financial decisions and pilot planning; Stage 4 adds governed explanations.

All customer and transaction data are synthetic. Behaviour and offer responsiveness are designed
assumptions, the experiment is simulated, and known treatment effects are synthetic ground truth.
No real-world retention improvement, financial return, commercial ROI or fintech deployment has
been demonstrated. Real-world generalisation remains unverified.

## Quick start — Windows CMD

The tested stack is Python 3.14.3, Java 25.0.2 and PySpark 4.2.0. Set `JAVA_HOME` to your actual JDK
directory if Java is not already configured. No unofficial Hadoop binaries are required.

```bat
git clone https://github.com/tabishiqbal03/customer-retention-uplift-system.git
cd customer-retention-uplift-system
git checkout main
py -3.14 -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
python -m ruff check .
python -m ruff format --check .
python -m pytest -q -m "not integration" --basetemp=data/test-unit-tmp
python -m pytest -q -m integration --basetemp=data/test-spark-tmp
python -m retention_uplift.cli generate --config configs/smoke.toml --output data/smoke
python -m retention_uplift.cli validate --input data/smoke
```

With an existing environment, activate it and start at installation. On POSIX use `python3 -m venv .venv` and `source .venv/bin/activate`;
the Python commands are identical. `retention-data` is an equivalent installed CLI entry point.

Optional, unverified scale profile (100,000 customers): this exhausted Java heap on the tested
8 GB machine. It is not required for reproduction; use the verified 25,000-customer workflow below.

```bat
python -m retention_uplift.cli generate --config configs/standard.toml --output data/standard
python -m retention_uplift.cli validate --input data/standard
```

The `generate` command creates all six tables and validates Parquet readback; `validate` checks
an existing saved dataset. `validation.json` records
counts, experiment diagnostics, versions, schemas, configuration and measured run information.
`_SUCCESS` appears only after checks pass. Existing output directories are never overwritten;
use `data/smoke-repeat` for a new run. Failed runs can leave partial output without `_SUCCESS`.
Pytest cleans its own `--basetemp`: never point that flag at data you want to preserve.

See [execution evidence](../reports/stage-1-completion.md), [scientific design](simulation.md),
[data dictionary](data-dictionary.md) and [operations](operations.md).

## Timeline and experiment

| Stage | Default dates |
|---|---|
| Historical observation | 1 January–31 December 2025, inclusive |
| Feature cutoff | End of 31 December 2025 |
| Randomized offer | 1 January 2026 |
| Outcome window | 2–31 January 2026, inclusive |

The daily-resolution design excludes assignment-day activity to avoid intraday ambiguity.
History is exactly 12 calendar months; dates, outcome length, size, seed and propensity are
configurable. Each customer gets one Bernoulli(0.5) assignment using a separate random stream.

The simulator defines `p0`, `p1` and `tau = p1 - p0`. Only the assigned arm's observed retention
is sampled. Retained means at least one qualifying activity day in the outcome window; a hurdle
simulation generates occurrence and a positive day count. Both binary counterfactuals are never
presented as observed labels. Oracle probabilities and effects live only in `evaluation_only/`.

Six overlapping latent archetypes generate stable, drifting, low-engagement, multi-product,
price-sensitive and message-averse behaviour. They influence noisy historical usage and response,
producing positive, near-zero and negative effects. No archetype label enters model features.
Latent variation means later models target effects conditional on observable history, not exact
recovery of each full-state oracle effect.

## Architecture

```text
configs/                       smoke and standard TOML profiles
src/retention_uplift/
  config.py                    validated experiment and mechanism settings
  randomness.py                seed/domain/stable-ID draws
  simulator.py                 latent population, transactions, experiment and truth
  features.py                  historical-only features and predictor allowlist
  validation.py                integrity and randomized-experiment diagnostics
  storage.py                   Parquet persistence and schema readback
  pipeline.py / cli.py         reproducible orchestration
tests/                         unit, leakage and real Spark integration checks
docs/                          assumptions, data dictionary and operations
reports/                       measured evidence; no bulk datasets
```

Spark creates a distributed customer range, expands customer-month counts into transactions,
and performs temporal filters, joins, aggregations, uniqueness checks and experiment diagnostics.
No pandas, Python UDF, driver-sized transaction list or `toPandas()` is used. The Windows portable
sink streams bounded batches from Spark to PyArrow Parquet; Spark reads them back. This avoids
the Hadoop permission operation that fails without `winutils` on the tested machine. Elsewhere
`--writer auto` uses Spark's distributed writer. Both writers can be explicitly selected.

`build_features(customers, transactions, config)` accepts historical sources only, selects allowed
columns, enforces both date boundaries and validates customer uniqueness/snapshot dates. A left
join retains zero-transaction customers. `model_inputs(features)` returns 22 numeric predictors,
excluding ID, cutoff metadata, treatment, outcomes and oracle truth. Tests inject future events
and forbidden columns and assert unchanged features. Raw validation separately rejects future
events. Physical separation is an interface convention, not a security access-control boundary.

Validation checks keys, coverage, foreign keys, nulls/nonfinite values, dates, binary outcomes,
propensities and probabilities. Allocation/covariate balance, true ATE, effect-sign shares,
observed arm rates and a descriptive 95% interval are reported. Sampling variation is expected;
observed effects need not exactly equal oracle effects. Statistical warnings remain visible and
do not cause rerandomization or seed selection.

## Stage 2 workflow

```bat
python -m retention_uplift.cli generate --config configs/medium.toml --output data/medium
python -m retention_uplift.cli run-stage2 --input data/medium --output data/stage2-medium
```

Use `configs/evaluation.toml` for 25,000 customers, or `configs/standard.toml` for the
100,000-customer profile, with new output paths. The 100,000 attempt exhausted the Java heap
on this machine and is not a verified modelling benchmark. The workflow creates
60/20/20 customer splits, validates seven modest candidates, freezes model/policy selection,
then evaluates untouched customers. Training never reads oracle truth. Positive uplift targeting,
random selection and highest untreated churn risk receive identical actual outreach counts.
Observed incremental retention uses known-propensity weighting with paired bootstrap intervals.
No model is assumed to win. Oracle diagnostics include inaccessible latent variation and are
not real-world causal validation. See [the full protocol](modelling.md) and the
[Stage 2 completion report](../reports/stage-2-completion.md) for measured findings and limitations.

New modules: `modelling_data.py` (bounded Spark bridge/splits), `models.py` (training/selection),
`policy.py` (allocation/IPW/bootstrap), `evaluation.py` (final diagnostics), and
`stage2.py` / `stage2_reporting.py` (artifacts/figures). Local models, manifests and per-customer
scores live under ignored `data/`; only aggregate evidence is committed. Stage 3 extends these interfaces as described below.

## Stage 3 workflow

```bat
python -m retention_uplift.cli generate --config configs/evaluation.toml --output data/evaluation
python -m retention_uplift.cli run-stage2 --input data/evaluation --output data/stage2-evaluation
python -m retention_uplift.cli run-stage3 --models data/stage2-evaluation --training-source data/evaluation --output data/stage3-final
```

Reuse existing successful Stage 1/2 outputs instead of overwriting them. Stage 3 freezes the selected
T-learner and seven explicit economic scenarios before generating 10,000 new customers with a
different seed and disjoint IDs. If a reproduced Stage 2 selects a different learner, the Stage 3
protocol rejects it rather than silently reselecting. Use trusted local model files only.

The base scenario assumes GBP40 contribution per incremental retained customer over 30 days,
GBP2 cost per selected customer, GBP3000 maximum spend and 2500 maximum contacts. These are
illustrative assumptions, not industry measurements. Profit selection maximizes predicted net
value under uniform costs. All comparators share a positive-net screen and common maximum limits.
Uplift and profit rankings coincide at fixed value; heterogeneous values can separate them.

Outputs: protocol/model hashes, frozen local policy decisions, aggregate predicted and randomized
observed monetary estimates, paired bootstrap intervals, sensitivity, four figures and a business
brief. No real CLV, offer cost, campaign, retention gain or profitability improvement is established.
Previously examined Stage 2 results are not fresh confirmation. The fresh cohort is a new simulated
sample from the same mechanism, not real or temporal validation. A hypothetical targeted pilot
estimates an offer effect within that population, not whole-policy superiority or profit.

Read [financial methodology and pilot design](financial-decisions.md),
[completion evidence](../reports/stage-3-completion.md) and the
[business brief](../reports/stage3/business-summary.md). See [the assistant guide](assistant.md) for Stage 4.
