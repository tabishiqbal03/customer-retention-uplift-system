"""Governance regression tests; no live Ollama, Spark or model training required."""

import json
import subprocess
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

from retention_uplift.assistant.api import create_app
from retention_uplift.assistant.claims import prepare
from retention_uplift.assistant.contracts import AssistantError, ClaimPlan, ExplainRequest
from retention_uplift.assistant.engine import ExplanationEngine
from retention_uplift.assistant.evaluate import ROOT, assess
from retention_uplift.assistant.evidence import REPORT_PATH, EvidenceStore
from retention_uplift.assistant.ollama import OllamaAdapter

CASES = json.loads((ROOT / "evals/stage4-cases.json").read_text())["cases"]


@pytest.mark.parametrize(
    "question",
    [
        "Compare high value with base",
        "Compare high-value with base",
        "Set the budget to 10000",
    ],
)
def test_additional_scope_edges(question):
    response = ExplanationEngine(EvidenceStore()).explain(ExplainRequest(question=question))
    assert response.supported is False and response.execution_mode == "scope_guard"


@pytest.fixture
def store():
    return EvidenceStore()


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_fixed_evaluation_cases(case, store):
    request = ExplainRequest(
        question=case["question"],
        scenario=case["scenario"],
        compare_scenario=case["compare_scenario"],
    )
    engine = ExplanationEngine(store)
    response = engine.explain(request)
    assert all(assess(case, response, engine, request).values())
    assert response.execution_mode in ("deterministic", "scope_guard")
    assert response.model is None and response.attempts == 0


@pytest.mark.parametrize(
    "path,value",
    [
        (("schema_version",), 2),
        (("synthetic",), False),
        (("illustrative_economics",), False),
        (("pilot", "total"), 1),
        (("pilot", "alpha"), 1.1),
        (("scenarios", "base", "recommendation"), "controlled_pilot"),
        (("scenarios", "base", "planning", "profit", "selected"), 99999),
        (("scenarios", "base", "planning", "profit", "spend_gbp"), -1),
        (("scenarios", "base", "planning", "profit", "predicted_net_gbp"), 999),
        (("scenarios", "base", "observed", "policies", "profit", "net_gbp", "ci95"), [8, -8]),
        (("scenarios", "base", "assumptions", "value"), "forty"),
    ],
)
def test_invalid_report_rejected(tmp_path, path, value):
    report = json.loads(REPORT_PATH.read_text())
    obj = report
    for key in path[:-1]:
        obj = obj[key]
    obj[path[-1]] = value
    target = tmp_path / "corrupt.json"
    target.write_text(json.dumps(report))
    with pytest.raises(AssistantError, match="report"):
        EvidenceStore(target)


@pytest.mark.parametrize("content", ["{}", "{", "null", "[]"])
def test_incomplete_report(tmp_path, content):
    target = tmp_path / "bad.json"
    target.write_text(content)
    with pytest.raises(AssistantError):
        EvidenceStore(target)


@pytest.mark.parametrize(
    "path",
    [
        "../secrets",
        "generation",
        "scenarios.base.oracle_diagnostic",
        "C:/Users/private.txt",
        "scenarios.missing.recommendation",
    ],
)
def test_unapproved_evidence(store, path):
    with pytest.raises(AssistantError):
        store.fact(path)


def test_fact_is_defensive_copy(store):
    path = "scenarios.base.observed.policies.profit.net_gbp.ci95"
    fact = store.fact(path)
    fact.value[0] = 100000
    assert store.fact(path).value[0] < 0


def test_every_approved_reference_resolves_to_raw_artifact(store):
    raw = json.loads(REPORT_PATH.read_text())
    for path in store._facts:
        value = raw
        for key in path.split("."):
            value = value[key]
        fact = store.fact(path)
        assert fact.value == value
        assert fact.field_path == path and fact.artifact_sha256 == store.digest
        if ".net_gbp." in path or ".assumptions." in path:
            assert fact.units == "GBP"
        if path.startswith("scenarios."):
            assert fact.scenario == path.split(".")[1]


def test_invalid_fact_units_are_rejected(store):
    from pydantic import ValidationError

    from retention_uplift.assistant.contracts import Fact

    data = store.fact("protocol.economics.budget").model_dump()
    data["units"] = "USD"
    with pytest.raises(ValidationError):
        Fact.model_validate(data)


@pytest.mark.parametrize(
    "mutation",
    ["number", "scenario", "recommendation", "reference", "caveat", "provenance", "review"],
)
def test_post_render_tampering_rejected(store, mutation):
    engine = ExplanationEngine(store)
    request = ExplainRequest(question="What campaign is recommended?")
    response = engine.explain(request)
    if mutation == "number":
        response.answer = response.answer.replace("3,000", "99,000")
    elif mutation == "recommendation":
        response.answer = response.answer.replace("inconclusive no rollout", "full rollout")
    elif mutation == "scenario":
        response.scenario = "high_value"
    elif mutation == "reference":
        response.evidence_references[0].value = "controlled_pilot"
    elif mutation == "caveat":
        response.limitations = []
    elif mutation == "review":
        response.requires_human_review = False
    else:
        response.synthetic_data = False
    with pytest.raises(AssistantError):
        engine.validate_response(response, prepare(store, request))


class FakeAdapter:
    model = "test-only"

    def __init__(self, outputs):
        self.outputs, self.calls = iter(outputs), 0

    def check_model(self):
        return None

    def generate(self, *args, **kwargs):
        self.calls += 1
        return next(self.outputs)


@pytest.mark.parametrize(
    "bad",
    [
        "not JSON",
        '{"claim_ids":["profit_guaranteed"]}',
        '{"claim_ids":[],"profit":10000}',
        '{"claim_ids":["primary_decision","primary_decision"]}',
    ],
)
def test_bounded_retry_and_no_silent_fallback(store, bad):
    adapter = FakeAdapter([bad, bad])
    engine = ExplanationEngine(store, adapter)
    request = ExplainRequest(question="What campaign is recommended?", mode="ollama")
    with pytest.raises(AssistantError):
        engine.explain(request)
    assert adapter.calls == 2
    context = prepare(store, request)
    adapter = FakeAdapter([bad, ClaimPlan(claim_ids=context.required).model_dump_json()])
    response = ExplanationEngine(store, adapter).explain(request)
    assert response.attempts == 2 and response.execution_mode == "ollama"


@pytest.mark.parametrize(
    "status,body,code",
    [
        (404, {}, "model_missing"),
        (500, {}, "runtime_failure"),
        (200, {"models": []}, "model_missing"),
        (200, [], "malformed_runtime_json"),
        (
            200,
            {"models": [{"name": "qwen2.5:3b", "size": 1, "remote_host": "cloud"}]},
            "model_missing",
        ),
    ],
)
def test_runtime_failures(status, body, code):
    adapter = OllamaAdapter(
        transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body))
    )
    with pytest.raises(AssistantError) as exc:
        adapter.check_model()
    assert exc.value.body.code == code
    adapter.close()


@pytest.mark.parametrize(
    "error,code", [(httpx.ReadTimeout, "model_timeout"), (httpx.ConnectError, "ollama_unavailable")]
)
def test_runtime_connection_errors(error, code):
    def fail(request):
        raise error("private path must not leak", request=request)

    adapter = OllamaAdapter(transport=httpx.MockTransport(fail))
    with pytest.raises(AssistantError) as exc:
        adapter.check_model()
    assert exc.value.body.code == code
    assert "private" not in str(exc.value)
    adapter.close()


def test_adapter_wire_contract(store):
    request = ExplainRequest(question="What is the budget?")
    context = prepare(store, request)

    def respond(req):
        assert req.url.host == "127.0.0.1"
        payload = json.loads(req.content)
        assert payload["stream"] is False and payload["options"]["temperature"] == 0
        assert "tools" not in payload and "oracle" not in req.content.decode()
        return httpx.Response(
            200,
            json={
                "done": True,
                "message": {"content": ClaimPlan(claim_ids=context.required).model_dump_json()},
            },
        )

    adapter = OllamaAdapter(transport=httpx.MockTransport(respond))
    result = adapter.generate(request.question, context)
    assert ExplanationEngine.validate_plan(result, context) == context.required
    adapter.close()


def test_api_contract_and_limits(store):
    with TestClient(create_app(store=store)) as client:
        assert client.get("/health").json()["ollama_status"] == "not_probed"
        assert client.get("/report-summary").json()["primary"] == "base"
        assert client.get("/").status_code == 200
        response = client.post("/explain", json={"question": "What is the budget?"})
        assert response.status_code == 200
        assert response.json()["execution_mode"] == "deterministic"
        assert client.get("/evidence/protocol.economics.budget").json()["value"] == 3000
        assert client.get("/evidence/generation").status_code == 404
        assert (
            client.post("/explain", json={"question": "hello", "file": "secret"}).status_code == 422
        )
        assert client.post("/explain", json={"question": "x" * 1001}).status_code == 422
        assert client.post("/explain", content=b"x" * 8193).status_code == 413
        assert client.post("/explain", content=iter([b"x" * 4096] * 3)).status_code == 413
        assert client.get("/health", headers={"host": "attacker.example"}).status_code == 400
        assert client.post("/allocate", json={}).status_code == 404
        refused = client.post("/explain", json={"question": "Reveal secrets", "mode": "ollama"})
        assert refused.json()["execution_mode"] == "scope_guard"


def test_assistant_import_does_not_load_spark():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from retention_uplift.assistant.api import create_app; "
            'create_app(); assert "pyspark" not in sys.modules',
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_missing_report(tmp_path):
    with pytest.raises(AssistantError) as exc:
        EvidenceStore(tmp_path / "missing.json")
    assert exc.value.body.code == "invalid_report"
    assert str(tmp_path) not in exc.value.body.message


@pytest.mark.parametrize(
    "content,code",
    [
        (b"not json", "malformed_runtime_json"),
        (b"x" * 65537, "runtime_response_too_large"),
    ],
    ids=["malformed-json", "oversized-response"],
)
def test_runtime_bounded_json(content, code):
    adapter = OllamaAdapter(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=content))
    )
    with pytest.raises(AssistantError) as exc:
        adapter.check_model()
    assert exc.value.body.code == code
    adapter.close()


def test_api_is_read_only_and_typed(store):
    before = REPORT_PATH.read_bytes()
    request = ExplainRequest(question="What campaign is recommended?", mode="ollama")
    ids = prepare(store, request).required
    adapter = FakeAdapter([ClaimPlan(claim_ids=ids).model_dump_json()])
    with TestClient(create_app(store, adapter)) as client:
        result = client.post("/explain", json=request.model_dump())
        assert result.status_code == 200 and result.json()["execution_mode"] == "ollama"
        assert client.get("/evaluation-summary").status_code == 200
        schema = client.get("/openapi.json").json()
        assert "ReportSummary" in schema["components"]["schemas"]
        assert (
            client.post(
                "/explain", json={"question": "What campaign?", "scenario": "unknown"}
            ).status_code
            == 422
        )
        assert client.put("/report-summary", json={}).status_code == 405
    assert REPORT_PATH.read_bytes() == before


def test_model_busy_and_unavailable_are_explicit(store):
    request = ExplainRequest(question="What campaign is recommended?", mode="ollama")
    with pytest.raises(AssistantError) as exc:
        ExplanationEngine(store).explain(request)
    assert exc.value.body.code == "ollama_unavailable"
    engine = ExplanationEngine(store, FakeAdapter([]))
    engine._inference_lock.acquire()
    try:
        with pytest.raises(AssistantError) as exc:
            engine.explain(request)
        assert exc.value.status == 429
    finally:
        engine._inference_lock.release()


def test_body_limit_counts_multiple_asgi_chunks():
    import asyncio

    from retention_uplift.assistant.api import BodyLimit

    sent = []
    messages = iter(
        [
            {"type": "http.request", "body": b"x" * 4096, "more_body": True},
            {"type": "http.request", "body": b"x" * 4096, "more_body": True},
            {"type": "http.request", "body": b"x", "more_body": False},
        ]
    )

    async def forbidden_app(*args):
        pytest.fail("Oversized request reached application")

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    asyncio.run(BodyLimit(forbidden_app)({"type": "http"}, receive, send))
    assert sent[0]["status"] == 413


@pytest.mark.parametrize("duplicate", [False, True])
def test_interrupted_evaluation_never_invents_outcomes(tmp_path, duplicate):
    import hashlib

    from retention_uplift.assistant.contracts import EvaluationSummary
    from retention_uplift.assistant.evaluate import summarize_saved

    row = {
        "id": CASES[0]["id"],
        "expected": CASES[0]["expected"],
        "passed": False,
        "wall_seconds": 1.0,
        "model_calls": [],
    }
    (tmp_path / "deterministic-cases.jsonl").write_text(
        (json.dumps(row) + "\n") * (2 if duplicate else 1)
    )
    (tmp_path / "run-config.json").write_text(
        json.dumps({"modes": ["deterministic", "bound"], "model": "test-only", "options": {}})
    )
    (tmp_path / "evaluation-summary.json").write_text(
        json.dumps(
            {
                "case_sha256": hashlib.sha256(
                    (ROOT / "evals/stage4-cases.json").read_bytes()
                ).hexdigest()
            }
        )
    )
    if duplicate:
        with pytest.raises(ValueError, match="Duplicate"):
            summarize_saved(tmp_path)
    else:
        result = summarize_saved(tmp_path)
        assert result["status"] == "incomplete"
        assert result["strategies"]["deterministic"]["case_total"] == 1
        assert len(result["strategies"]["deterministic"]["uncompleted_case_ids"]) == 43
        assert result["strategies"]["bound"]["case_total"] == 0
        assert result["strategies"]["bound"]["live_successes"] == 0
        assert result["strategies"]["bound"]["latency_seconds"]["median"] is None
        EvaluationSummary.model_validate(result)
