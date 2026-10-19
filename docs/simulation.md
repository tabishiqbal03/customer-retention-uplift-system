# Scientific design

This is a designed simulation, not an empirically calibrated fintech population. All accounts are
established: cutoff tenure is `history_days + floor(1800 U)`. There are no real identities/accounts.

## Randomness and archetypes

Uniform draws use the first 13 hex digits of `SHA256(seed | domain | stable row keys)`, plus .5,
divided by `2^52`. This gives open-interval deterministic pseudo-random draws. Box–Muller produces
normal draws from separate domains. Assignment and outcome streams are distinct from history.
Partitioning does not affect draws; no Python hash salt or Spark partition-seeded rand is used.

Equal-weight mixtures have these means, fixed in `simulator.ARCHETYPES`:

| Archetype | Engagement e | Trend g | Sensitivity s | Aversion a |
|---|---:|---:|---:|---:|
| Stable | .80 | .03 | .15 | .05 |
| Drifting | .60 | −.55 | .85 | .05 |
| Low engagement | .18 | −.10 | .12 | .06 |
| Multi-product | .70 | .06 | .25 | .06 |
| Price-sensitive | .48 | −.15 | .95 | .08 |
| Message-averse | .55 | −.10 | .40 | .85 |

Independent normal noise has SD .22 for e/s/a and .28 for g. Clip e to [.01,.99], g to [−.95,.70],
s/a to [0,1]. The distributions overlap. Savings adoption is Bernoulli(.15+.6e), transfers
Bernoulli(.2+.5e). Multi-product membership does not guarantee adoption. An independent 4% flag
creates whole-year inactive histories; rounding below creates more zero-transaction months.

## Transactions

For months m=0,...,11:

```text
rate_im = monthly_rate * (.1 + e_i) * exp(g_i*m/11)
          * (.35 + 1.3 U_im) * seasonality(calendar_month)
n_im = floor(min(rate_im, max_monthly_transactions) + independent U_im)
```

Defaults: monthly_rate=7, cap=60, seasonality=1.15 for November/December and 1 otherwise.
Inactive histories have zero counts. This is stochastic rounding, not Poisson sampling.
Spark expands 12 month records per customer, then bounded slots; it never appends millions of
transactions to a Python list. Event days are uniform within actual calendar months. IDs combine
customer/month/slot. Historical trend and monthly noise generate recency/frequency variation.

Product is savings if adopted and product draw <.15, transfer if adopted and draw >.8, otherwise
card. Card categories are uniformly groceries/transport/leisure. All transactions are positive
settled GBP outflows. Savings movements and outbound transfers are not card spending. No refunds,
FX, failures or account-balance accounting are modelled.

Customer amount scale is `mean_spend_gbp*exp(.5 Z_i)`. Transaction amounts multiply this by
`exp(spend_log_sigma Z_event)` and an 8x multiplier for an independent 1% of events. Clip amounts
to £.01–£10,000 and round to integer pence. Defaults: £35 scale, .85 log sigma. £35 is a scale,
not the arithmetic mean. Integer-pence sums and squared sums make feature aggregation associative
before final double-precision divisions/square roots. Per-customer generator bounds keep these
integer moments below `2^53`, avoiding precision loss when converting the sums to double.

## Probability mechanism

With savings adoption v and independent normal residual z, default equations are:

```text
sigmoid(t) = 1/(1+exp(-t))
L = -.8 + 2.3e + 1.0g + .25v + .6z
D = 1.8 * 4e(1-e) * sigmoid(-3g) * s - 1.4a
p0 = sigmoid(L)
p1 = sigmoid(L+D)
tau = p1-p0
```

Engaged-but-drifting sensitive customers tend to benefit. Low sensitivity and baseline ceiling
effects limit benefit for many stable customers; aversion can create negative effects. Archetypes
do not guarantee effect signs. Diagnostics define near zero as `abs(tau)<=.01`.

All configurable coefficients and noise/transaction scales are `Mechanism` fields in `config.py`;
override with TOML `[mechanism]`. Mixture means, 4/−3 shape constants, product thresholds, 4%
inactivity, seasonality and amount tails are explicit fixed design constants in `simulator.py`,
documented here. Preserve the code revision as well as the fully resolved saved configuration.

Assign `T=1[U_assignment<propensity]` once per customer. Propensity defaults to .5 and is stored
on every assignment. No baseline feature enters this draw. Balance diagnostics can detect major
errors but cannot prove independence; domain separation and the randomization design establish
the intended independence.

Draw `B=1[U_outcome<p_T]`. If B=1, qualifying_activity_days is uniform in 1,...,outcome_days;
otherwise zero. Retained is exactly `1[qualifying_activity_days>0]`. A qualifying day has at least
one settled payment, savings movement or outbound transfer. This window-level hurdle summary
avoids redundant raw future transactions while ensuring `P(retained=1|state,T)=p_T`.
No binary outcome under the other treatment is sampled or stored. The offer is illustrative;
costs, redemption, delivery failure, noncompliance and spillovers are not simulated.

Oracle probabilities condition on full latent state, not solely observable features. Later models
target `E[tau(full state)|observed features]`; unobserved residuals and noisy history prevent exact
individual oracle recovery. Ground truth is privileged offline evaluation data, never a feature.

## Diagnostics and limitations

Allocation z uses `sqrt(p(1-p)/N)`. Four baseline covariates get standardized mean differences and
differences divided by their estimated SE. Four-SE warnings are conservative routine diagnostics;
they are not a guarantee of perfect balance or grounds for selecting a favourable seed.

Observed ATE is the treated-minus-control retention rate. Its estimated SE is
`sqrt(s1^2/n1+s0^2/n0)` using sample variances; report a normal-approximation 95% interval.
Compare with realized population mean tau, allowing sampling error. Four-SE discrepancies are
warnings. Small-sample intervals can be unstable; exact equality/coverage is not required.
These are sanity checks, not power analysis or model-performance scores.

No calibrated balance dynamics, macroeconomic shocks, missingness or measurement attrition.
Historical and future activity share latent state but have independent draws; historical inactivity
does not force future nonretention. Known expected effects are special to this simulation. No real
customer impact or financial return has been measured; real-world generalisation is unverified.
