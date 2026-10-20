"""Incremental Windows live benchmark with durable rows and a subprocess watchdog.

Run: python -m retention_uplift.assistant.reliability --output NEW_DIRECTORY
Resume the same frozen run by repeating the command; --expand enables cases 06–28.
"""

import argparse
import ctypes
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

from .contracts import AssistantError, ExplainRequest, OptionalPlan
from .engine import ExplanationEngine
from .evaluate import ROOT, RecordingAdapter, assess, summarize_rows
from .evidence import EvidenceStore


def free_mib():
    class Memory(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong)
            for name in (
                "total",
                "available",
                "page",
                "free_page",
                "virtual",
                "free_virtual",
                "extended",
            )
        ]

    memory = Memory()
    memory.length = ctypes.sizeof(memory)
    if sys.platform != "win32" or not ctypes.windll.kernel32.GlobalMemoryStatusEx(
        ctypes.byref(memory)
    ):
        raise RuntimeError("Live benchmark requires a verified Windows memory reading")
    return memory.available / 1024**2


def run_case(case, live):
    adapter = RecordingAdapter() if live else None
    engine = ExplanationEngine(EvidenceStore(), adapter)
    request = ExplainRequest(
        question=case["question"],
        scenario=case["scenario"],
        compare_scenario=case["compare_scenario"],
        mode="ollama" if live else "deterministic",
    )
    row = {"id": case["id"], "request": request.model_dump(), "expected": case["expected"]}
    start = time.perf_counter()
    try:
        response = engine.explain(request)
        row.update(response=response.model_dump(), checks=assess(case, response, engine, request))
        row["passed"] = all(row["checks"].values())
    except AssistantError as exc:
        row.update(error=exc.body.model_dump(), passed=False)
    finally:
        row["wall_seconds"] = time.perf_counter() - start
        row["model_calls"] = adapter.calls if adapter else []
        if adapter:
            adapter.close()
    return row


def recover(directory, cases, config):
    rows = []
    path = directory / "cases.jsonl"
    if path.exists():
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)) or set(ids) - {c["id"] for c in cases}:
        raise ValueError("Duplicate or unknown recorded case")
    expected = {c["id"]: c["expected"] for c in cases}
    if any(r["expected"] != expected[r["id"]] for r in rows):
        raise ValueError("Recorded expectations changed")
    summary = summarize_rows(rows, config["model"], config["options"])
    summary["uncompleted_case_ids"] = [c["id"] for c in cases if c["id"] not in ids]
    summary["planned_supported"] = 28
    summary["planned_guards"] = 16
    summary["status"] = "complete" if len(ids) == len(cases) else "incomplete"
    if summary["supported_total"] < 20:
        summary["latency_seconds"]["p95_nearest_rank"] = None
    returned = [call for row in rows for call in row["model_calls"] if "raw_plan" in call]
    schema_valid = 0
    for call in returned:
        try:
            OptionalPlan.model_validate_json(call["raw_plan"])
            schema_valid += 1
        except ValueError:
            pass
    summary["raw_schema_valid"] = schema_valid
    summary["raw_plans_returned"] = len(returned)
    summary["selection_distribution"] = {}
    for row in rows:
        for id in row.get("response", {}).get("model_selected_claim_ids", []):
            summary["selection_distribution"][id] = summary["selection_distribution"].get(id, 0) + 1
    (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return rows, summary


def benchmark(directory, expand=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    raw = (ROOT / "evals/stage4-cases.json").read_bytes()
    cases = json.loads(raw)["cases"]
    adapter = RecordingAdapter()
    config = {
        "contract": "optional_v2",
        "model": adapter.model,
        "options": adapter.options,
        "case_sha256": hashlib.sha256(raw).hexdigest(),
        "report_sha256": EvidenceStore().digest,
        "protocol_sha256": hashlib.sha256(
            (ROOT / "evals/stage4-reliability-protocol.md").read_bytes()
        ).hexdigest(),
    }
    adapter.close()
    path = directory / "config.json"
    if path.exists() and json.loads(path.read_text()) != config:
        raise ValueError("Frozen configuration changed; use a new output directory")
    path.write_text(json.dumps(config, indent=2) + "\n")
    rows, summary = recover(directory, cases, config)
    for case in cases[28:] + cases[:28]:
        if case["id"] in {r["id"] for r in rows}:
            continue
        live = case["expected"]["supported"]
        if live:
            supported = [r for r in rows if r["expected"]["supported"]]
            if any(r["wall_seconds"] > 90 for r in supported):
                summary["stop_reason"] = "prior_request_exceeded_latency_limit"
                break
            if len(supported) >= 5 and (
                not expand
                or sum(
                    r.get("response", {}).get("contribution") == "optional_explanation"
                    and r["passed"]
                    for r in supported[:5]
                )
                < 4
            ):
                break
            memory = free_mib()
            with (directory / "resources.jsonl").open("a") as handle:
                handle.write(
                    json.dumps(
                        {"before_case": case["id"], "free_mib": memory, "unix_time": time.time()}
                    )
                    + "\n"
                )
            if memory < 1024:
                summary["stop_reason"] = "free_memory_below_1024_MiB_before_inference"
                break
            if len(supported) >= 2 and all("error" in r for r in supported[-2:]):
                summary["stop_reason"] = "two_consecutive_errors"
                break
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "retention_uplift.assistant.reliability",
                        "--worker",
                        case["id"],
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=100,
                    check=True,
                )
                row = json.loads(result.stdout)
            except subprocess.TimeoutExpired:
                row = {
                    "id": case["id"],
                    "expected": case["expected"],
                    "passed": False,
                    "error": {"code": "watchdog_timeout"},
                    "wall_seconds": 100,
                    "model_calls": [],
                    "inference_attempted": True,
                    "attempt_count_unknown": True,
                }
                try:
                    with httpx.Client(timeout=5, trust_env=False) as client:
                        client.post(
                            "http://127.0.0.1:11434/api/generate",
                            json={"model": config["model"], "keep_alive": 0},
                        )
                except httpx.HTTPError:
                    pass
        else:
            row = run_case(case, True)  # scope guard must never invoke the adapter
        with (directory / "cases.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        rows, summary = recover(directory, cases, config)
        print(case["id"], row["passed"], row["wall_seconds"], flush=True)
        after_memory = free_mib() if live else None
        if live:
            with (directory / "resources.jsonl").open("a") as handle:
                handle.write(
                    json.dumps(
                        {
                            "after_case": case["id"],
                            "free_mib": after_memory,
                            "unix_time": time.time(),
                        }
                    )
                    + "\n"
                )
        if live and (row["wall_seconds"] > 90 or after_memory < 512):
            summary["stop_reason"] = "post_request_resource_or_latency_limit"
            break
    (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--expand", action="store_true")
    parser.add_argument("--worker")
    args = parser.parse_args()
    if args.worker:
        cases = json.loads((ROOT / "evals/stage4-cases.json").read_text())["cases"]
        print(json.dumps(run_case(next(c for c in cases if c["id"] == args.worker), True)))
    elif args.output:
        print(json.dumps(benchmark(args.output, args.expand), indent=2))
    else:
        parser.error("--output is required")
