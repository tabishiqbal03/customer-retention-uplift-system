"""Validate model claim plans, then render authoritative facts and mandatory caveats."""

import time
from threading import Lock

from pydantic import ValidationError

from .claims import DEPLOYMENT, UNCERTAINTY, WARNING, prepare
from .contracts import AssistantError, ClaimPlan, Explanation


class ExplanationEngine:
    def __init__(self, store, adapter=None):
        self.store, self.adapter = store, adapter
        self._inference_lock = Lock()

    @staticmethod
    def validate_plan(raw, context):
        try:
            plan = ClaimPlan.model_validate_json(raw)
        except (ValidationError, ValueError) as exc:
            raise AssistantError(
                "invalid_model_plan", "Model output failed its typed claim contract.", 502
            ) from exc
        ids = plan.claim_ids
        if (
            len(set(ids)) != len(ids)
            or set(ids) - set(context.claims)
            or set(context.required) - set(ids)
        ):
            raise AssistantError(
                "invalid_model_plan",
                "Model selected fabricated, duplicate or incomplete claims.",
                502,
            )
        return ids

    def explain(self, request):
        start = time.perf_counter()
        context = prepare(self.store, request)
        if context.category == "unsupported":
            return Explanation(
                answer=(
                    "This question is outside the approved aggregate-report scope. No "
                    "verified answer is available. "
                )
                + DEPLOYMENT
                + " "
                + WARNING,
                question_category="unsupported",
                scenario=request.scenario,
                evidence_references=[],
                claim_ids=[],
                limitations=[
                    WARNING,
                    (
                        "No private customer data, unavailable metrics, arbitrary files or "
                        "decision changes are exposed."
                    ),
                ],
                confidence_or_evidence_status="unsupported_insufficient_evidence",
                requires_human_review=True,
                supported=False,
                execution_mode="scope_guard",
                attempts=0,
                latency_seconds=time.perf_counter() - start,
            )
        attempts = 0
        if request.mode == "deterministic":
            ids = list(context.required)
        else:
            if self.adapter is None:
                raise AssistantError(
                    "ollama_unavailable",
                    "Local LLM mode is not configured; choose deterministic mode explicitly.",
                    503,
                )
            if not self._inference_lock.acquire(blocking=False):
                raise AssistantError(
                    "model_busy",
                    "A local inference request is already running. Retry after it completes.",
                    429,
                    True,
                )
            try:
                self.adapter.check_model()
                for attempts in (1, 2):
                    raw = self.adapter.generate(
                        request.question, context, request.strategy, retry=attempts == 2
                    )
                    try:
                        ids = self.validate_plan(raw, context)
                        break
                    except AssistantError:
                        if attempts == 2:
                            raise
            finally:
                self._inference_lock.release()
        paths = list(dict.fromkeys(path for id in ids for path in context.claims[id].references))
        response = Explanation(
            answer="\n\n".join([context.claims[id].text for id in ids] + [WARNING, UNCERTAINTY]),
            question_category=context.category,
            scenario=request.scenario,
            evidence_references=[self.store.fact(p) for p in paths],
            claim_ids=ids,
            limitations=[
                WARNING,
                UNCERTAINTY,
                "This is constrained claim composition, not unrestricted model-authored analysis.",
            ],
            confidence_or_evidence_status="validated_saved_evidence",
            requires_human_review=True,
            supported=True,
            execution_mode=request.mode,
            model=self.adapter.model if request.mode == "ollama" else None,
            attempts=attempts,
            latency_seconds=time.perf_counter() - start,
        )
        self.validate_response(response, context)
        return response

    def validate_response(self, response, context):
        ids = self.validate_plan(ClaimPlan(claim_ids=response.claim_ids).model_dump_json(), context)
        expected = "\n\n".join([context.claims[id].text for id in ids] + [WARNING, UNCERTAINTY])
        paths = list(dict.fromkeys(p for id in ids for p in context.claims[id].references))
        if response.answer != expected or response.evidence_references != [
            self.store.fact(p) for p in paths
        ]:
            raise AssistantError(
                "invalid_response",
                "Response text or evidence differs from authoritative rendering.",
                502,
            )
        if (
            response.scenario != context.scenario
            or response.synthetic_data is not True
            or response.illustrative_economics is not True
            or response.confidence_or_evidence_status != "validated_saved_evidence"
            or response.question_category != context.category
            or not response.supported
            or not response.requires_human_review
            or response.limitations[:2] != [WARNING, UNCERTAINTY]
        ):
            raise AssistantError(
                "invalid_response", "Response metadata or mandatory caveats changed.", 502
            )
        return response
