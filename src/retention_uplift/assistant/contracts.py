"""Public contracts and a strict projection of the approved Stage 3 schema."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ScenarioId = Literal[
    "base", "low_value", "high_value", "low_cost", "high_cost", "unfavourable", "heterogeneous"
]
Category = Literal[
    "campaign",
    "financial",
    "uncertainty",
    "sensitivity",
    "targeting",
    "pilot",
    "method",
    "deployment",
    "unsupported",
]
Recommendation = Literal[
    "inconclusive_no_rollout", "no_rollout_negative_evidence", "controlled_pilot", "no_offer"
]
Nonnegative = Annotated[float, Field(ge=0)]
Probability = Annotated[float, Field(gt=0, lt=1)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Projection(Contract):
    # Only this explicitly declared projection is ever exposed. Oracle/technical extras
    # are withheld.
    model_config = ConfigDict(extra="ignore", strict=True, allow_inf_nan=False)


class Interval(Contract):
    estimate: float
    ci95: list[float] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def ordered(self):
        if self.ci95[0] > self.ci95[1]:
            raise ValueError("Reversed confidence interval")
        return self


class Plan(Projection):
    selected: int = Field(ge=0)
    predicted_incremental_retained: float
    predicted_gross_gbp: float
    spend_gbp: Nonnegative
    predicted_net_gbp: float
    unspent_gbp: Nonnegative


class Assumptions(Contract):
    name: ScenarioId
    value: Nonnegative
    offer_cost: Nonnegative
    contact_cost: Nonnegative
    value_mode: Literal["fixed", "usage"]


class PolicyEstimate(Contract):
    incremental_retained: Interval
    net_gbp: Interval
    net_per_eligible_gbp: Interval


class Observed(Contract):
    policies: dict[str, PolicyEstimate]
    paired_net_gbp: dict[str, Interval]
    bootstrap: int = Field(ge=1000)


class Scenario(Projection):
    assumptions: Assumptions
    planning: dict[str, Plan]
    observed: Observed
    recommendation: Recommendation


class Economics(Projection):
    primary: ScenarioId
    budget: Nonnegative
    maximum_contacts: int = Field(ge=0)


class Protocol(Projection):
    economics: Economics


class Pilot(Projection):
    control: int = Field(gt=0)
    treatment: int = Field(gt=0)
    total: int = Field(gt=0)
    p0: Probability
    p1: Probability
    mde_pp: float = Field(gt=0, lt=100)
    alpha: Probability
    target_power: Probability
    treatment_control_ratio: float = Field(gt=0)


class Report(Projection):
    schema_version: Literal[1]
    synthetic: Literal[True]
    illustrative_economics: Literal[True]
    n_customers: int = Field(gt=0)
    protocol: Protocol
    scenarios: dict[ScenarioId, Scenario]
    pilot: Pilot

    @model_validator(mode="after")
    def integrity(self):
        import math

        policies = {"no_offer", "random", "churn", "uplift", "profit"}
        if (
            set(self.scenarios) != set(ScenarioId.__args__)
            or self.protocol.economics.primary != "base"
        ):
            raise ValueError("Unsupported scenario set or changed primary protocol")
        for name, scenario in self.scenarios.items():
            if (
                name != scenario.assumptions.name
                or set(scenario.planning) != policies
                or set(scenario.observed.policies) != policies
            ):
                raise ValueError("Scenario or policy coverage mismatch")
            if set(scenario.observed.paired_net_gbp) != {
                f"profit - {k}" for k in policies - {"profit"}
            }:
                raise ValueError("Missing paired comparisons")
            for p in scenario.planning.values():
                if (
                    p.selected > min(self.n_customers, self.protocol.economics.maximum_contacts)
                    or p.spend_gbp > self.protocol.economics.budget
                ):
                    raise ValueError("Invalid planning constraints")
                if not math.isclose(
                    p.predicted_gross_gbp - p.spend_gbp, p.predicted_net_gbp, abs_tol=1e-7
                ):
                    raise ValueError("Inconsistent planning totals")
            ci = scenario.observed.policies["profit"].net_gbp.ci95
            expected = (
                "no_offer"
                if scenario.planning["profit"].selected == 0
                else "no_rollout_negative_evidence"
                if ci[1] < 0
                else "controlled_pilot"
                if ci[0] > 0
                else "inconclusive_no_rollout"
            )
            if scenario.recommendation != expected:
                raise ValueError("Recommendation disagrees with saved evidence")
        if self.pilot.total != self.pilot.control + self.pilot.treatment:
            raise ValueError("Inconsistent pilot total")
        return self


class ExplainRequest(Contract):
    question: str = Field(min_length=3, max_length=1000)
    scenario: ScenarioId = "base"
    compare_scenario: ScenarioId | None = None
    mode: Literal["deterministic", "ollama"] = "deterministic"
    strategy: Literal["basic", "bound"] = "bound"


class Fact(Contract):
    reference: str
    artifact: str
    artifact_sha256: str
    field_path: str
    scenario: ScenarioId | None = None
    value: float | int | str | list[float]
    units: Literal[
        "GBP",
        "customers",
        "incremental_customers",
        "probability",
        "percentage_points",
        "ratio",
        "recommendation",
    ]
    category: Literal[
        "assumption",
        "prediction",
        "observed_estimate",
        "interval",
        "recommendation",
        "pilot_design",
    ]
    label: str


class Claim(Contract):
    id: str
    text: str
    references: list[str]


class ClaimPlan(Contract):
    claim_ids: list[str] = Field(min_length=1, max_length=16)


class OptionalPlan(Contract):
    optional_claim_ids: list[str] = Field(max_length=2)


class Explanation(Contract):
    schema_version: Literal[1] = 1
    answer: str
    question_category: Category
    scenario: ScenarioId
    evidence_references: list[Fact]
    claim_ids: list[str]
    limitations: list[str]
    confidence_or_evidence_status: str
    requires_human_review: bool
    supported: bool
    synthetic_data: Literal[True] = True
    illustrative_economics: Literal[True] = True
    execution_mode: Literal["deterministic", "ollama", "scope_guard"]
    model: str | None = None
    attempts: int = Field(ge=0, le=2)
    latency_seconds: float = Field(ge=0)
    model_selected_claim_ids: list[str] = Field(default_factory=list)
    contribution: Literal["none", "optional_explanation", "empty_selection", "legacy_plan"] = "none"


class ErrorBody(Contract):
    code: str
    message: str
    retryable: bool = False


class Health(Contract):
    status: Literal["ok"]
    report_validated: Literal[True]
    ollama_status: Literal["not_probed"]
    local_only: Literal[True]


class ReportSummary(Contract):
    schema_version: Literal[1]
    synthetic_data: Literal[True]
    illustrative_economics: Literal[True]
    primary: Literal["base"]
    recommendation: Recommendation
    scenarios: list[ScenarioId]
    artifact: Literal["stage3-metrics-v1"]
    artifact_sha256: str


class EvaluationCounts(Projection):
    case_passes: int = Field(ge=0)
    case_total: int = Field(ge=0)
    supported_successes: int = Field(ge=0)
    supported_total: int = Field(ge=0)
    scope_guard_correct_refusals: int = Field(ge=0)
    scope_guard_total: int = Field(ge=0)
    live_requests: int = Field(ge=0)
    live_successes: int = Field(ge=0)
    live_first_attempt_successes: int = Field(ge=0)
    model_calls: int = Field(ge=0)
    retries: int = Field(ge=0)
    latency_seconds: dict[Literal["median", "p95_nearest_rank", "max"], Nonnegative | None]


class EvaluationSummary(Projection):
    status: Literal["executed", "not_executed", "incomplete"]
    strategies: dict[Literal["deterministic", "basic", "bound"], EvaluationCounts] = Field(
        default_factory=dict
    )


class AssistantError(Exception):
    def __init__(self, code, message, status=422, retryable=False):
        self.body = ErrorBody(code=code, message=message, retryable=retryable)
        self.status = status
        super().__init__(message)
