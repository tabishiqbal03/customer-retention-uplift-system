# Data contracts and feature dictionary

Six Parquet directories have `_schema.json` files. Each run includes resolved `config.json`,
`validation.json` and a final `_SUCCESS`. Dates are Spark date values; session timezone is UTC.
Columns and types are independently enforced by validation, not just inferred on disk readback.
All fields must be non-null and all floating-point values finite.

| Directory | Grain / key | Columns and types |
|---|---|---|
| raw/customers | Customer / customer_id | customer_id string, tenure_days int, snapshot_date date |
| raw/transactions | Transaction / transaction_id | customer_id string, transaction_id string, event_date date, product string, category string, amount_pence long, currency string |
| processed/features | Customer / customer_id | customer_id string, 22 predictors below, feature_cutoff date |
| experiment/assignments | Customer / customer_id | customer_id string, treatment int, propensity double, assignment_date date |
| experiment/outcomes | Customer / customer_id | customer_id string, qualifying_activity_days int, retained int, outcome_start date, outcome_end date |
| evaluation_only/truth | Customer / customer_id | customer_id/archetype string; tenure_days/has_savings/has_transfers/inactive int; engagement/trend/sensitivity/aversion/spend_scale/residual/p0/p1/tau double |

All customer-grain tables cover the same customer keys once; transactions can be absent for a
customer. No orphans are allowed. Snapshots equal cutoff. History includes both its start and
cutoff dates. Future events fail raw validation and cannot enter feature computations.

## Predictors

30-day window: `[assignment−30, cutoff]`; 90-day: `[assignment−90, cutoff]`; previous 30-day:
`[assignment−60, assignment−31]`. All products count as activity; only card payments count as spend.
Spark long is named bigint in the schema. Customer ID and cutoff are metadata, not predictors.

| Feature | Type | Definition / rationale |
|---|---|---|
| tenure_days | int | Age at cutoff; lifecycle |
| transaction_count | long | Historical settled events; usage |
| monthly_frequency | double | transaction_count / 12, including inactive months |
| card_spend_gbp | double | Card amount_pence sum / 100 |
| mean_transaction_gbp | double | Mean amount across all products / 100 |
| transaction_stddev_gbp | double | Population stddev across all amounts / 100; variability |
| active_months | long | Distinct calendar year-months with events; continuity |
| recency_days | int | cutoff minus latest event; history_days for empty history |
| transactions_30d | long | Recent 30-day activity |
| transactions_90d | long | Recent quarter activity |
| transactions_previous_30d | long | Prior equally long comparison period |
| activity_change_30d | long | Recent minus previous 30-day count; trend |
| card_spend_30d_gbp | double | Recent 30-day card spend |
| card_spend_90d_gbp | double | Recent 90-day card spend |
| card_count | long | Card usage |
| savings_count | long | Savings movements |
| transfer_count | long | Outbound transfers |
| products_used | int | Number of products with positive usage, 0–3 |
| card_share | double | card_count / all transaction_count |
| groceries_share | double | Grocery count / all transaction_count |
| transport_share | double | Transport count / all transaction_count |
| leisure_share | double | Leisure count / all transaction_count |

Category shares sum to card_share, not necessarily one. Empty histories get zero counts, amounts,
variability and shares, with the documented recency sentinel. One transaction has zero population
standard deviation. Denominators are at least one. All predictors must be observable by cutoff.

## Future modelling interface

Use `features.model_inputs()` to select the 22-column allowlist. Join assignments and outcomes by
unique customer ID separately when constructing a modelling dataset. Treatment is not a baseline
covariate; an estimator may later consume it through a deliberate treatment interface. Keep oracle
truth unavailable to fitting code. Stage 1 contains no model fit, customer split or policy ranking.
