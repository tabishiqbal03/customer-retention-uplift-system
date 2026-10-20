"""Fixed-case evaluation. Guard refusals never count as successful model inference."""

import hashlib
import json
import platform
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from .claims import UNCERTAINTY, WARNING, prepare
from .contracts import AssistantError, ExplainRequest, Explanation
from .engine import ExplanationEngine
from .evidence import EvidenceStore
from .ollama import OllamaAdapter

ROOT = Path(__file__).resolve().parents[3]


class RecordingAdapter(OllamaAdapter):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls = []

    def generate(self, *args, **kwargs):
        record = {"retry": kwargs.get("retry", False)}
        self.calls.append(record)
        start = time.perf_counter()
        try:
            result = super().generate(*args, **kwargs)
            record["raw_plan"] = result
            return result
        except AssistantError as exc:
            record["error"] = exc.body.model_dump()
            raise
        finally:
            record["seconds"] = time.perf_counter() - start
            record["generation"] = dict(self.last_generation)


def assess(case, response, engine, request):
    expected = case["expected"]
    Explanation.model_validate_json(response.model_dump_json())
    refs = {f.reference: f for f in response.evidence_references}
    checks = {
        "schema_valid": True,
        "correct_support": response.supported == expected["supported"],
        "correct_category": response.question_category == expected["category"],
        "expected_evidence": set(expected["paths"]) <= set(refs),
        "reference_values_valid": all(engine.store.fact(p) == f for p, f in refs.items()),
        "synthetic_caveat": WARNING in response.answer,
        "uncertainty_preserved": not response.supported or UNCERTAINTY in response.answer,
        "unsupported_no_numbers": response.supported
        or not any(c.isdigit() for c in response.answer),
    }
    if response.supported:
        engine.validate_response(response, prepare(engine.store, request))
    checks["rendered_claims_valid"] = True
    return checks


def evaluate(output, modes=("deterministic", "basic", "bound"), model="qwen2.5:3b"):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    case_bytes = (ROOT / "evals/stage4-cases.json").read_bytes()
    cases = json.loads(case_bytes)["cases"]
    store = EvidenceStore()
    summary = {
        "schema_version": 1,
        "status": "incomplete",
        "utc": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "case_sha256": hashlib.sha256(case_bytes).hexdigest(),
        "report_sha256": store.digest,
        "cases": len(cases),
        "strategies": {},
        "interpretation": "Development suite, not a held-out generalization benchmark. "
        "Live successes exclude scope guards. Accuracy covers approved rendered claims only. "
        "Both prompts use the same JSON schema, retrieval and post-validation.",
    }
    config_adapter = OllamaAdapter(model=model)
    config = {"modes": list(modes), "model": model, "options": config_adapter.options}
    config_adapter.close()
    (output / "run-config.json").write_text(json.dumps(config, indent=2) + "\n")
    (output / "evaluation-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for mode in modes:
        adapter = RecordingAdapter(model=model) if mode != "deterministic" else None
        engine = ExplanationEngine(store, adapter)
        rows = []
        try:
            for case in cases:
                request = ExplainRequest(
                    question=case["question"],
                    scenario=case["scenario"],
                    compare_scenario=case["compare_scenario"],
                    mode="deterministic" if adapter is None else "ollama",
                    strategy="bound" if adapter is None else mode,
                )
                if adapter:
                    adapter.calls = []
                row = {
                    "id": case["id"],
                    "request": request.model_dump(),
                    "expected": case["expected"],
                }
                start = time.perf_counter()
                try:
                    response = engine.explain(request)
                    row["response"] = response.model_dump()
                    row["checks"] = assess(case, response, engine, request)
                    row["passed"] = all(row["checks"].values())
                except AssistantError as exc:
                    row.update(error=exc.body.model_dump(), passed=False)
                row["wall_seconds"] = time.perf_counter() - start
                row["model_calls"] = list(adapter.calls) if adapter else []
                rows.append(row)
                # Flush each actual result; interrupted runs remain visibly incomplete.
                with (output / f"{mode}-cases.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(
                    f"{mode} {case['id']} {'PASS' if row['passed'] else 'FAIL'} "
                    f"{row['wall_seconds']:.2f}s",
                    flush=True,
                )
            metrics = summarize_rows(
                rows, model if adapter else None, adapter.options if adapter else None
            )
            summary["strategies"][mode] = metrics
            (output / "evaluation-summary.json").write_text(
                json.dumps(summary, indent=2) + "\n", encoding="utf-8"
            )
        finally:
            if adapter:
                adapter.close()
    return summarize_saved(output)


def summarize_rows(rows, model=None, options=None):
    """Summarize recorded outcomes only; missing outcomes are never counted as successes."""
    supported = [r for r in rows if r["expected"]["supported"]]
    refused = [r for r in rows if not r["expected"]["supported"]]
    live = [r for r in supported if r["model_calls"] or r.get("inference_attempted")]
    completed = [r for r in supported if "response" in r]
    latencies = sorted(r["wall_seconds"] for r in (live or supported))
    calls = [c for r in rows for c in r["model_calls"]]

    def contributes(row):
        return (
            row.get("passed", False)
            and row.get("response", {}).get("contribution") != "empty_selection"
        )

    valid_first = sum(contributes(r) and len(r["model_calls"]) == 1 for r in live)
    metrics = {
        "case_passes": sum(r["passed"] for r in rows),
        "case_total": len(rows),
        "supported_successes": sum(r["passed"] for r in supported),
        "supported_total": len(supported),
        "scope_guard_correct_refusals": sum(r["passed"] for r in refused),
        "scope_guard_total": len(refused),
        "live_requests": len(live),
        "live_successes": sum(contributes(r) for r in live),
        "meaningful_model_contributions": sum(
            r["passed"] and r.get("response", {}).get("contribution") == "optional_explanation"
            for r in live
        ),
        "empty_selection_responses": sum(
            r.get("response", {}).get("contribution") == "empty_selection" for r in live
        ),
        "deterministic_fallbacks_after_error": 0,
        "supported_errors": sum("error" in r for r in supported),
        "timeout_errors": sum(r.get("error", {}).get("code") == "model_timeout" for r in supported),
        "live_first_attempt_successes": valid_first,
        "model_calls": len(calls),
        "requests_with_unknown_attempt_count": sum(
            r.get("attempt_count_unknown", False) for r in live
        ),
        "retries": sum(c["retry"] for c in calls),
        "completed_supported_responses": len(completed),
        "validation_checks_passed": {
            key: sum(r.get("checks", {}).get(key, False) for r in completed)
            for key in (
                "schema_valid",
                "expected_evidence",
                "reference_values_valid",
                "rendered_claims_valid",
                "uncertainty_preserved",
            )
        },
        "latency_seconds": {
            "median": statistics.median(latencies) if latencies else None,
            "p95_nearest_rank": latencies[max(0, -(-95 * len(latencies) // 100) - 1)]
            if latencies
            else None,
            "max": max(latencies) if latencies else None,
        },
        "model": model,
        "options": options,
        "failures": [r["id"] for r in rows if not r["passed"]],
    }
    return metrics


def summarize_saved(directory):
    """Recover a complete or interrupted run without making any new model calls."""
    directory = Path(directory)
    summary_path = directory / "evaluation-summary.json"
    summary = json.loads(summary_path.read_text())
    config = json.loads((directory / "run-config.json").read_text())
    cases = json.loads((ROOT / "evals/stage4-cases.json").read_text())["cases"]
    if (
        summary["case_sha256"]
        != hashlib.sha256((ROOT / "evals/stage4-cases.json").read_bytes()).hexdigest()
    ):
        raise ValueError("Case set changed; cannot summarize against a different suite")
    all_ids = [c["id"] for c in cases]
    summary["strategies"] = {}
    for mode in config["modes"]:
        path = directory / f"{mode}-cases.jsonl"
        rows = (
            [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            if path.exists()
            else []
        )
        ids = [r["id"] for r in rows]
        if len(set(ids)) != len(ids) or set(ids) - set(all_ids):
            raise ValueError("Duplicate or unknown evaluation case")
        metric = summarize_rows(
            rows,
            config["model"] if mode != "deterministic" else None,
            config["options"] if mode != "deterministic" else None,
        )
        metric["planned_cases"] = len(cases)
        metric["planned_supported_cases"] = sum(c["expected"]["supported"] for c in cases)
        metric["uncompleted_case_ids"] = [id for id in all_ids if id not in ids]
        metric["status"] = "complete" if len(ids) == len(all_ids) else "incomplete"
        summary["strategies"][mode] = metric
    summary["status"] = (
        "executed"
        if all(m["status"] == "complete" for m in summary["strategies"].values())
        else "incomplete"
    )
    summary["missing_outcome_policy"] = (
        "Uncompleted cases are not successes or recorded failures; they may include "
        "an interrupted in-flight request."
    )
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
