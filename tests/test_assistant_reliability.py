"""Optional composition never controls mandatory evidence or claimed success."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from retention_uplift.assistant.api import create_app
from retention_uplift.assistant.claims import UNCERTAINTY, WARNING, prepare
from retention_uplift.assistant.contracts import AssistantError, ExplainRequest
from retention_uplift.assistant.engine import ExplanationEngine
from retention_uplift.assistant.evaluate import ROOT, assess, summarize_rows
from retention_uplift.assistant.evidence import REPORT_PATH, EvidenceStore
from retention_uplift.assistant.ollama import OllamaAdapter
from retention_uplift.assistant.reliability import recover, run_case

CASES = json.loads((ROOT / "evals/stage4-cases.json").read_text())["cases"]


class OptionalAdapter:
    model = "test-only"
    plan_contract = "optional_v2"

    def __init__(self, raw):
        self.raw = raw
        self.calls = 0

    def check_model(self):
        pass

    def generate(self, *args, **kwargs):
        self.calls += 1
        if isinstance(self.raw, Exception):
            raise self.raw
        return self.raw


@pytest.mark.parametrize("case", CASES[:28], ids=lambda c: c["id"])
@pytest.mark.parametrize("selected", [[], ["explain_1"], ["explain_2"], ["explain_1", "explain_2"]])
def test_mandatory_evidence_independent_of_model(case, selected):
    store = EvidenceStore()
    engine = ExplanationEngine(store, OptionalAdapter(json.dumps({"optional_claim_ids": selected})))
    req = ExplainRequest(
        question=case["question"],
        scenario=case["scenario"],
        compare_scenario=case["compare_scenario"],
        mode="ollama",
    )
    result = engine.explain(req)
    assert all(assess(case, result, engine, req).values())
    assert result.claim_ids == prepare(store, req).required + selected
    assert result.contribution == ("optional_explanation" if selected else "empty_selection")
    assert result.model_selected_claim_ids == selected
    assert WARNING in result.answer and UNCERTAINTY in result.answer
    deterministic = ExplanationEngine(store).explain(
        req.model_copy(update={"mode": "deterministic"})
    )
    assert result.evidence_references == deterministic.evidence_references
    assert deterministic.contribution == "none"


@pytest.mark.parametrize(
    "raw",
    [
        '{"optional_claim_ids":["unknown"]}',
        '{"optional_claim_ids":["explain_1","explain_1"]}',
        '{"optional_claim_ids":["explain_1","explain_2","explain_1"]}',
        '{"optional_claim_ids":["primary_decision"]}',
        '{"optional_claim_ids":[],"profit":100}',
        '{"claim_ids":["primary_decision"]}',
        "null",
    ],
)
def test_invalid_selection_fails_closed(raw):
    adapter = OptionalAdapter(raw)
    with pytest.raises(AssistantError):
        ExplanationEngine(EvidenceStore(), adapter).explain(
            ExplainRequest(question="What campaign?", mode="ollama")
        )
    assert adapter.calls == 2


@pytest.mark.parametrize("code", ["model_timeout", "ollama_unavailable"])
def test_no_retry_or_fallback_after_transport_error(code):
    adapter = OptionalAdapter(AssistantError(code, "Controlled failure", 503))
    with pytest.raises(AssistantError) as exc:
        ExplanationEngine(EvidenceStore(), adapter).explain(
            ExplainRequest(question="What campaign?", mode="ollama")
        )
    assert exc.value.body.code == code and adapter.calls == 1


def test_schema_enum_and_cached_inventory():
    calls = []

    def respond(req):
        calls.append(req.url.path)
        if req.method == "GET":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:3b", "size": 1}]})
        payload = json.loads(req.content)
        schema = payload["format"]["properties"]["optional_claim_ids"]
        assert schema["items"]["enum"] == ["explain_1", "explain_2"]
        assert schema["maxItems"] == 2
        assert "required_ids" not in req.content.decode()
        assert payload["options"]["num_ctx"] == 2048
        return httpx.Response(
            200, json={"done": True, "message": {"content": '{"optional_claim_ids":["explain_2"]}'}}
        )

    with TestClient(
        create_app(adapter=OllamaAdapter(transport=httpx.MockTransport(respond)))
    ) as client:
        before = REPORT_PATH.read_bytes()
        for _ in range(2):
            r = client.post("/explain", json={"question": "What campaign?", "mode": "ollama"})
            assert r.status_code == 200 and r.json()["contribution"] == "optional_explanation"
        assert before == REPORT_PATH.read_bytes()
    assert calls.count("/api/tags") == 1


def test_metrics_do_not_credit_empty_selection_or_guards():
    rows = []
    for contribution in ("optional_explanation", "empty_selection"):
        rows.append(
            {
                "id": contribution,
                "expected": {"supported": True},
                "passed": True,
                "model_calls": [{"retry": False}],
                "wall_seconds": 1,
                "response": {"contribution": contribution},
            }
        )
    rows.append(
        {
            "id": "guard",
            "expected": {"supported": False},
            "passed": True,
            "model_calls": [],
            "wall_seconds": 0.01,
            "response": {"contribution": "none"},
        }
    )
    result = summarize_rows(rows)
    assert result["supported_successes"] == 2
    assert result["meaningful_model_contributions"] == 1
    assert result["live_successes"] == 1
    assert result["empty_selection_responses"] == 1
    assert result["scope_guard_correct_refusals"] == 1


def test_partial_recovery_and_duplicate_rejection(tmp_path):
    row = run_case(CASES[28], True)
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(row) + "\n")
    _, summary = recover(tmp_path, CASES, {"model": "test", "options": {}})
    assert summary["meaningful_model_contributions"] == 0
    assert len(summary["uncompleted_case_ids"]) == 43
    assert summary["status"] == "incomplete"
    path.write_text((json.dumps(row) + "\n") * 2)
    with pytest.raises(ValueError, match="Duplicate"):
        recover(tmp_path, CASES, {"model": "test", "options": {}})


def test_resource_abort_and_resume_preserve_rows(tmp_path, monkeypatch):
    from retention_uplift.assistant import reliability

    monkeypatch.setattr(reliability, "free_mib", lambda: 800)
    monkeypatch.setattr(
        reliability.subprocess, "run", lambda *a, **k: pytest.fail("Unsafe inference")
    )
    result = reliability.benchmark(tmp_path)
    before = (tmp_path / "cases.jsonl").read_bytes()
    assert result["supported_total"] == 0 and result["scope_guard_total"] == 16
    assert reliability.benchmark(tmp_path)["status"] == "incomplete"
    assert (tmp_path / "cases.jsonl").read_bytes() == before
    config = json.loads((tmp_path / "config.json").read_text())
    config["model"] = "changed"
    (tmp_path / "config.json").write_text(json.dumps(config))
    with pytest.raises(ValueError, match="Frozen"):
        reliability.benchmark(tmp_path)


def test_contribution_tampering_rejected():
    engine = ExplanationEngine(EvidenceStore(), OptionalAdapter('{"optional_claim_ids":[]}'))
    request = ExplainRequest(question="What campaign?", mode="ollama")
    response = engine.explain(request)
    response.contribution = "optional_explanation"
    with pytest.raises(AssistantError):
        engine.validate_response(response, prepare(engine.store, request))
