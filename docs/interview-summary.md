# Interview engineering summary

I built a synthetic decision-support system to answer a more useful question than who might churn:
whose response to a retention offer could justify its cost, and what evidence should a business
require before acting? It is a graduate portfolio experiment, not a commercial deployment.

## The four stages

1. **Data foundation:** PySpark generates historical transactions, customers, randomized offers
   and observed outcomes, then validates schemas and Parquet readback. The executed Stage 2
   population has 25,000 customers and 1,280,055 transactions. A configured 100,000-customer
   profile is not an executed performance claim.
2. **Causal modelling:** a control-only logistic churn model estimates untreated departure risk;
   constant, T- and S-learner uplift estimators predict offer response. Validation selected the
   T-learner. Test diagnostics did not trigger reselection, even when S looked better on some
   metrics. This protects against presenting test-driven model choice as independent evidence.
3. **Decisions:** frozen rules face a budget, capacity and strictly positive predicted-net screen.
   A fresh 10,000-customer simulated cohort provides randomized observed-outcome policy values,
   paired bootstrap intervals, seven prespecified economic scenarios and pilot planning.
4. **AI engineering:** FastAPI retrieves typed aggregate facts, sends only a small approved claim
   catalogue to local Ollama, validates the returned IDs, and renders values and caveats from the
   report. A deterministic demonstration uses the same facts and is labelled separately.

## Decisions I would defend

**Why uplift?** Churn risk is not treatment response. An offer may be wasted on someone who would
stay anyway, fail to help someone likely to leave, or harm a message-averse customer. Uplift estimates
conditional offer effects, though the synthetic mechanism cannot establish real-world transfer.

**Leakage prevention:** features use pre-offer history only. IDs, assignment, outcomes and oracle
truth are excluded from the predictor allowlist. Customer-level train/validation/test splitting is
independent of outcomes, and model selection uses validation. Stage 3 freezes the selected model
before generating disjoint customer IDs with a new seed. Oracle diagnostics remain separate from
operational inputs and are never sent to the explanation model.

**Policy evaluation:** inverse-propensity weighting uses the known randomized assignment probability.
Paired customer bootstrap resamples preserve covariance between policies. Comparators share the
positive-net screen and maximum constraints, so claims are about these specific policies. Pointwise
intervals do not correct for multiple comparisons or cover retraining and distribution shift.

**Uncertainty changes the decision:** base planning predicts £5,187.17 net after £3,000 cost for
1,500 contacts. The observed-outcome estimate is £3,800, with a 95% interval of [−£698.15, £8,308.20].
That does not demonstrate positive profit. The recommendation stays inconclusive/no rollout.
Favourable sensitivity scenarios do not replace the prespecified primary result.

**Next experiment:** the saved design needs 4,129 customers per arm, 8,258 total, for a 3-percentage-point
retention effect under a 60% baseline, 5% alpha and 80% target power. It estimates an offer effect
within the frozen target population, not whole-policy superiority or financial-estimand power.
Additional recruitment and prespecified guardrails would be needed.

**Why constrain the LLM?** Financial arithmetic and recommendations should not depend on plausible
prose. Claim IDs plus authoritative rendering give a small, testable trust boundary. The model has
no shell, file or targeting tools. The trade-off is limited language flexibility: it selects zero to two optional
conceptual explanations. Application code supplies mandatory facts and review language. Empty
selection is safe but contributes no additional model explanation; errors require the user to
choose deterministic mode explicitly.

**How I evaluated it:** 44 fixed development cases cover supported facts, scenario comparisons,
uncertainty, pilot design and 16 unsupported/adversarial inputs. The historical qwen2.5:3b basic prompt passed 11/28 supported questions; the bound prompt passed
2/5 completed questions before stopping, so the 44-case comparison was not completed. The current
optional-only contract has no supported live measurements because the memory gate stopped it. Per-case raw plans, retries, failures and timings
are saved. Refusals by the deterministic scope guard are excluded from LLM success denominators.
See the [completion report](../reports/stage-4-completion.md) for measured results; this is not a
held-out benchmark of free-form hallucination or a claim of universal prompt-injection resistance.

## With real business data

First agree consent/privacy boundaries, retention definition, contribution horizon, actual offer
costs, interference assumptions and adverse-outcome guardrails. Validate targeting on genuinely
randomized and temporally distinct data; assess subgroup performance, calibration and uncertainty
from model selection/retraining. Compare policies prospectively rather than treating synthetic oracle
performance as commercial evidence. Production would also need authentication, audit trails,
monitoring, access controls, incident handling and broader independently reviewed language evals.

I did not train a foundation model, demonstrate realised revenue, or deploy a production bank service.
