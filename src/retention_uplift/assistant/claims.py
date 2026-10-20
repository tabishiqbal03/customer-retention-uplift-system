"""Explicit finite query scope and approved claim composition, not unrestricted chat."""

import re
from dataclasses import dataclass

from .contracts import Claim

WARNING = (
    "All customers are synthetic and all economics are illustrative. "
    "No real campaign or profit has been demonstrated."
)
UNCERTAINTY = (
    "Intervals are pointwise and unadjusted; they condition on the "
    "fitted rules and assumed economics and exclude training and "
    "population-shift uncertainty."
)
METHOD = (
    "Churn estimates untreated departure risk; uplift estimates "
    "response to an offer. Positive uplift must cover cost. All "
    "comparator policies share a positive-net screen and common "
    "maximum constraints."
)
DEPLOYMENT = (
    "Real deployment needs domain-validated contribution values and "
    "offer costs, privacy assessment, guardrails and genuine "
    "randomized evidence. This local demonstration is not a production "
    "rollout decision."
)
PILOT = (
    "Randomize offers within the frozen targeted population and "
    "analyze intention-to-treat retention. This estimates the offer "
    "effect within that group, not whole-policy superiority or "
    "financial-estimand power. Additional eligible recruitment is "
    "needed; agree guardrails and analysis before launch."
)
TARGETING = (
    "Uniform-cost optimisation ranks strictly positive predicted net "
    "values within the maximum budget and contact capacity. It may "
    "leave budget unspent. The chat interface cannot alter "
    "allocations."
)


def category_for(request):
    q = request.question.casefold()
    for name in ("low_value", "high_value", "low_cost", "high_cost"):
        q = re.sub(r"\b" + name.replace("_", "[ _-]") + r"\b", name, q)
    blocked = (
        r"ignore|pretend|replace|override|reveal|secret|environment|execute|shell|"
        r"python|local files|"
        r"without mentioning|as if|guarantee|certain profit|actual bank|real .*customers?|"
        r"real .*profit|customer account|individual customer|revolut|visa|roc.?auc|"
        r"change .*customers|increase .*budget|remove .*caveat|system prompt|api.?key"
    )
    mutation = (
        r"\b(set|change|increase|decrease|modify|allocate)\b.*"
        r"\b(budget|customers|allocation|capacity|assumptions)\b"
    )
    if re.search(blocked, q) or re.search(mutation, q):
        return "unsupported"
    mentioned = {
        s
        for s in (
            "base",
            "low_value",
            "high_value",
            "low_cost",
            "high_cost",
            "unfavourable",
            "heterogeneous",
        )
        if re.search(r"\b" + s + r"\b", q)
    }
    allowed = {request.scenario, request.compare_scenario}
    if mentioned - allowed:
        return (
            "unsupported"  # explicit scenario fields, never covertly promote a favourable scenario
        )
    for name in mentioned:
        q = q.replace(name, "")
    if any(w in q for w in ("experiment", "pilot", "sample size", "alpha", "power")):
        return "pilot"
    if any(
        w in q
        for w in (
            "compare",
            "scenarios",
            "cost increases",
            "cost increase",
            "no outreach",
            "sensitivity",
        )
    ):
        return "sensitivity"
    if any(w in q for w in ("certain", "confidence", "interval", "demonstrate", "rollout")):
        return "uncertainty"
    if any(w in q for w in ("deployment", "limitation", "real deployment")):
        return "deployment"
    if any(w in q for w in ("churn", "uplift", "outperform")):
        return "method"
    if any(w in q for w in ("count", "selected", "how many", "budget", "capacity")):
        return "targeting"
    if any(w in q for w in ("financial", "net value", "benefit", "assumption", "cost", "profit")):
        return "financial"
    if any(w in q for w in ("campaign", "recommend")):
        return "campaign"
    return "unsupported"


@dataclass
class Context:
    category: str
    claims: dict[str, Claim]
    required: list[str]
    facts: dict
    scenario: str


def prepare(store, request):
    category = category_for(request)
    claims, facts, required = {}, {}, []

    def claim(id, text, paths=(), mandatory=True):
        for path in paths:
            facts[path] = store.fact(path)
        claims[id] = Claim(id=id, text=text, references=list(paths))
        if mandatory:
            required.append(id)

    def fact_claim(id, path):
        f = store.fact(path)
        value = f.value
        if isinstance(value, list):
            rendered = "[" + ", ".join(f"{v:,.2f}" for v in value) + "]"
        elif isinstance(value, str):
            rendered = value.replace("_", " ")
        elif f.units in ("customers",):
            rendered = f"{value:,}"
        elif f.units == "probability":
            rendered = f"{100 * value:.2f}%"
        else:
            rendered = f"{value:,.2f}"
        unit = {
            "GBP": " GBP",
            "customers": " customers",
            "incremental_customers": " incremental customers",
            "percentage_points": " percentage points",
            "probability": "",
            "ratio": " treatment/control",
            "recommendation": "",
        }[f.units]
        claim(id, f"{f.scenario or 'design'} — {f.label}: {rendered}{unit}.", [path])

    def scenario_claims(name, prefix):
        s = f"scenarios.{name}"
        # Bundle related values into short approved statements; every numeral has an exact source.
        for suffix, path in [
            ("decision", f"{s}.recommendation"),
            ("count", f"{s}.planning.profit.selected"),
            ("spend", f"{s}.planning.profit.spend_gbp"),
            ("predicted", f"{s}.planning.profit.predicted_net_gbp"),
        ]:
            fact_claim(prefix + suffix, path)
        a = f"{s}.observed.policies.profit.net_gbp"
        estimate, ci = store.fact(a + ".estimate"), store.fact(a + ".ci95")
        claim(
            prefix + "observed",
            (
                f"{name} — observed-outcome estimated incremental net: "
                f"{estimate.value:,.2f} GBP; pointwise 95% CI [{ci.value[0]:,.2f}, "
                f"{ci.value[1]:,.2f}] GBP. This is not realized cash."
            ),
            [a + ".estimate", a + ".ci95"],
        )
        if category == "sensitivity":
            paths = [f"{s}.assumptions.{f}" for f in ("value", "offer_cost", "contact_cost")]
            vals = [store.fact(p).value for p in paths]
            claim(
                prefix + "assumptions",
                (
                    f"{name} assumptions: contribution {vals[0]:,.2f} GBP, offer cost "
                    f"{vals[1]:,.2f} GBP and contact cost {vals[2]:,.2f} GBP per "
                    "customer. Usage-based value, where selected, varies by the "
                    "documented multiplier."
                ),
                paths,
            )
        label = store.report.scenarios[name].recommendation
        interpretations = {
            "inconclusive_no_rollout": (
                "The interval spans negative and "
                "positive values; a positive point estimate does not establish "
                "positive net value. Do not roll out on this evidence."
            ),
            "controlled_pilot": (
                "The pointwise interval supports further "
                "controlled testing under these assumptions, not full rollout or "
                "real profit. This sensitivity scenario does not replace the "
                "primary base result."
            ),
            "no_offer": (
                "No customers meet the configured positive-net "
                "opportunity rule; no outreach is planned."
            ),
            "no_rollout_negative_evidence": (
                "The interval is below zero; this evidence does not support rollout."
            ),
        }
        claim(
            prefix + "interpretation",
            f"{name}: " + interpretations[label],
            [f"{s}.recommendation", a + ".ci95"],
        )

    s = f"scenarios.{request.scenario}"
    if category in ("campaign", "financial", "uncertainty", "sensitivity"):
        if category == "sensitivity" and "no outreach" in request.question.casefold():
            for name in store.report.scenarios:
                fact_claim(name + "_decision", f"scenarios.{name}.recommendation")
                fact_claim(name + "_count", f"scenarios.{name}.planning.profit.selected")
        else:
            scenario_claims(request.scenario, "primary_")
            if category == "sensitivity":
                other = request.compare_scenario or "high_cost"
                if other != request.scenario:
                    scenario_claims(other, "comparison_")
        if category == "financial":
            for field in ("value", "offer_cost", "contact_cost"):
                fact_claim(field, f"{s}.assumptions.{field}")
            claim(
                "value_definition",
                (
                    "Value is illustrative contribution per extra retained customer "
                    "over the outcome horizon, not customer spending or measured "
                    "lifetime value. The usage scenario applies the documented bounded "
                    "historical-usage multiplier."
                ),
            )
        if category == "campaign":
            fact_claim("budget", "protocol.economics.budget")
    elif category == "targeting":
        for field in ("selected", "spend_gbp", "unspent_gbp"):
            fact_claim(field, f"{s}.planning.profit.{field}")
        fact_claim("budget", "protocol.economics.budget")
        fact_claim("capacity", "protocol.economics.maximum_contacts")
        claim("rule", TARGETING)
    elif category == "pilot":
        for field in (
            "control",
            "treatment",
            "total",
            "p0",
            "mde_pp",
            "alpha",
            "target_power",
            "treatment_control_ratio",
        ):
            fact_claim(field, f"pilot.{field}")
        claim("pilot_scope", PILOT)
    elif category == "method":
        claim("method", METHOD)
        path = f"{s}.observed.paired_net_gbp.profit - churn"
        fact_claim("difference", path + ".estimate")
        fact_claim("difference_ci", path + ".ci95")
        ci = store.fact(path + ".ci95").value
        claim(
            "comparison_scope",
            "The paired interval includes zero; superiority over screened churn is not established."
            if ci[0] <= 0 <= ci[1]
            else (
                "This is a pointwise comparison under the selected synthetic "
                "assumptions, not universal superiority."
            ),
            [path + ".ci95"],
        )
    elif category == "deployment":
        claim("deployment", DEPLOYMENT)
    if category != "unsupported":
        claim(
            "review_reminder",
            "A human must review the saved evidence and assumptions before acting.",
            mandatory=False,
        )
    context = Context(category, claims, required, facts, request.scenario)
    claims.update(optional_catalogue(context))
    return context


def optional_catalogue(context):
    """Two distinct explanatory lenses, additional to the mandatory saved facts."""
    lenses = {
        "campaign": (
            (
                "Treat the recommendation as an evidence gate: review uncertainty before "
                "committing campaign resources."
            ),
            (
                "A planned campaign describes who could be contacted; it does not establish "
                "that contacting them creates value."
            ),
        ),
        "financial": (
            (
                "Planning estimates help compare allocations; observed-outcome estimates "
                "evaluate the frozen rule using different evidence."
            ),
            (
                "Economic assumptions translate retention into money, so changing those "
                "assumptions can change the decision even when retention estimates stay "
                "fixed."
            ),
        ),
        "uncertainty": (
            (
                "A confidence interval describes estimation uncertainty under the stated "
                "design; it is not a promise about the next campaign."
            ),
            (
                "Decision confidence depends on the range of plausible effects, not merely "
                "the sign of the point estimate."
            ),
        ),
        "sensitivity": (
            (
                "Sensitivity comparisons test dependence on assumptions; they do not select a "
                "new primary analysis after seeing favourable results."
            ),
            (
                "Different costs can change both who qualifies and how many contacts fit the "
                "constraints, so scenario differences need not scale proportionally."
            ),
        ),
        "targeting": (
            (
                "A maximum is a ceiling, not a spending target: the positive-net screen can "
                "bind before budget or capacity."
            ),
            (
                "The selected count describes the frozen policy; identifying individual "
                "recipients requires a separate approved operational process."
            ),
        ),
        "pilot": (
            (
                "Precommitting the analysis prevents favourable outcomes from redefining what "
                "the experiment was intended to test."
            ),
            (
                "Power concerns the specified retention effect; it cannot be transferred "
                "directly to a financial outcome with different variability."
            ),
        ),
        "method": (
            (
                "Risk prediction and treatment response answer different questions: a "
                "high-risk customer may still be unresponsive to an offer."
            ),
            (
                "A fair policy comparison uses the same population and constraints, so "
                "differences reflect the decision rule rather than unequal resources."
            ),
        ),
        "deployment": (
            (
                "A demonstration validates software behaviour; operational adoption also "
                "needs evidence that the assumptions transfer to the intended population."
            ),
            (
                "Human review should connect the saved evidence to operational constraints "
                "before any deployment decision."
            ),
        ),
    }
    return {
        f"explain_{i}": Claim(id=f"explain_{i}", text=text, references=[])
        for i, text in enumerate(lenses.get(context.category, ()), 1)
    }
