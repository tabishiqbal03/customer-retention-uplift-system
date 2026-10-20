# Governed local explanation assistant

The Stage 1–3 decision engine remains authoritative. The assistant reads the committed
`reports/stage3/metrics.json`; it never invokes Spark, fits a model, selects customers or changes
assumptions. Use a repository checkout and an editable install, as shown in the README.

## Evidence and response contracts

`contracts.py` validates schema version 1, provenance, scenario/policy coverage, ordered intervals,
planning constraints, totals and recommendation consistency. Unknown technical report fields are
ignored by an explicit projection, not forwarded. The artifact's SHA-256 accompanies every fact.
This digest provides traceability, not a cryptographic signature or protection against a malicious
operator replacing the report and application together. Byte hashes describe the exact local
checkout, including line endings; changing that format requires a new evaluation directory.

Approved fields include budget/capacity, scenario assumptions, planning counts/spend/predicted net,
observed IPW estimates and pointwise intervals, paired comparisons, recommendation labels and pilot
design. Oracle diagnostics, latent effects, customer records, generation metadata, local paths and
model files are withheld. Prediction, observed estimate, interval, assumption, recommendation and
pilot design have separate categories and units. No embeddings or vector database are needed.

Routing selects a small claim catalogue for a supported topic. Explicit `scenario` and
`compare_scenario` fields control retrieval; a conflicting scenario name is refused. English keyword
routing is intentionally limited and may over-refuse or misunderstand unfamiliar wording. Use the
UI examples and explicit selectors. It is not a general natural-language understanding benchmark.

Ollama returns only `{"claim_ids":[...]}`. IDs must exist in that question's catalogue, be unique and
include every required claim. It can reorder claims and select an optional human-review reminder.
The renderer copies approved statements and formats numbers directly from validated facts, adds
mandatory caveats, and checks the final response and references again. There is no free-form
model-written numerical or recommendation text to leak through a regular-expression checker.
This deliberately limits expressive flexibility: the model is a constrained composer, not an analyst.
Catalogue wording and scientific interpretations still require human review.

Responses contain `answer`, `question_category`, `scenario`, `evidence_references`, `claim_ids`,
`limitations`, `confidence_or_evidence_status`, `requires_human_review`, `supported`,
`synthetic_data`, `illustrative_economics`, `execution_mode`, `model`, `attempts` and latency.
Each evidence entry supplies artifact ID/hash, exact field path, scenario, value, units and category.
An unsupported answer has no numeric claims or evidence references and uses `scope_guard`, even
if Ollama was requested. That outcome is never attributed to model performance.

## Windows setup and five demonstrations

Tested: Python 3.14.3, FastAPI 0.150.0, Pydantic 2.14.1, Uvicorn 0.54.0 and HTTPX 0.28.1.
Java 25.0.2 / PySpark 4.2.0 are needed for pipeline integration tests, not assistant startup.

```bat
.venv\Scripts\activate
python -m pip install -e ".[dev]"
python -m retention_uplift.assistant.cli serve
```

Open `http://127.0.0.1:8000` (UI) or `/docs` (OpenAPI). Binding is fixed to loopback; only the port
is configurable. In another activated CMD window:

```bat
REM Demo A: factual explanation without Ollama
python -m retention_uplift.assistant.cli explain "What campaign is recommended?"

REM Check existing runtime and installed model before Demo B
ollama --version
ollama list
ollama show qwen2.5:3b
REM If the service is stopped, run ollama serve in a separate window.
python -m retention_uplift.assistant.cli explain "What campaign is recommended?" --mode ollama

REM Demo C: unsupported real-world claim; no model call and no invented count
python -m retention_uplift.assistant.cli explain "How many real Revolut customers benefited?"

REM Demo D: compare approved cost scenarios
python -m retention_uplift.assistant.cli explain "What happens if offer cost increases?" --scenario base --compare-scenario high_cost

REM Demo E: pilot design and estimand caveat
python -m retention_uplift.assistant.cli explain "What experiment should run next?"
```

For the same request over HTTP in Windows CMD:

```bat
curl.exe -s http://127.0.0.1:8000/health
curl.exe -s http://127.0.0.1:8000/report-summary
curl.exe -s -X POST http://127.0.0.1:8000/explain -H "Content-Type: application/json" -d "{\"question\":\"What campaign is recommended?\",\"scenario\":\"base\",\"mode\":\"deterministic\"}"
curl.exe -s http://127.0.0.1:8000/evidence/scenarios.base.observed.policies.profit.net_gbp.ci95
curl.exe -s http://127.0.0.1:8000/evaluation-summary
```

Expected A/B shape: `supported: true`, `question_category: "campaign"`, valid evidence, mandatory
warnings, and `execution_mode` matching the selected mode. Expected C: `supported: false`,
`execution_mode: "scope_guard"`, `model: null`, `attempts: 0`, empty evidence. Expected D includes
base and high-cost fields; E includes `pilot.total=8258`, 4,129 per arm, alpha 5%, target power 80%,
baseline retention 60%, MDE 3 percentage points and the targeted-offer-effect caveat.

The available model was `qwen2.5:3b`, Ollama 0.40.6, Q4_K_M, approximately 1.9 GB on disk.
No model was installed or downloaded for this stage. If missing, install Ollama from its official
distribution, review the model's license and download size, and make an explicit operator decision
before using `ollama pull qwen2.5:3b`. This repository never pulls a model. The model binary is not
redistributed; the installed model reports the Qwen research license.

Runtime: loopback `/api/tags` and `/api/chat`, no tools or remote-model support; temperature 0,
seed 20261020, context 4096, prediction cap 256, two inference threads, keep-alive two minutes,
60-second HTTP timeout per request, at most two generation attempts. A validation failure permits
one retry; transport failures do not. HTTPX timeouts are per I/O phase, not a hard whole-process
deadline. One inference request runs per application process; use a single server worker on 8 GB.
Do not run Spark and LLM benchmarks simultaneously on this machine. Runtime caching and hardware
affect timings; fixed seeds do not guarantee bitwise inference reproducibility.

The adapter follows [Ollama's API](https://github.com/ollama/ollama/blob/main/docs/api.md) and
[structured-output interface](https://ollama.com/blog/structured-outputs). Pydantic v2 is used for
[Python 3.14 compatibility](https://github.com/fastapi/fastapi/blob/master/docs/en/docs/how-to/migrate-from-pydantic-v1-to-pydantic-v2.md).

## Evaluation and trust boundaries

```bat
python -m pytest tests/test_assistant.py -q --basetemp=data/test-assistant-tmp
python -m retention_uplift.assistant.cli evaluate --output data/eval-deterministic --modes deterministic
python -m retention_uplift.assistant.cli evaluate --output data/eval-live
```

Output directories must be new. The fixed 44-case development suite was defined before the engine;
it has 28 supported questions and 16 unsupported/adversarial requests. Expected support, category,
source fields and caveats are machine checked. It is not a held-out linguistic generalization set.
Both live strategies use the same model, evidence, JSON schema, validation and retry bound. `basic`
asks for relevant IDs; `bound` additionally directs inclusion, scope and trust handling. Thus this
compares prompt instructions inside a governed pipeline, not a raw chatbot against a governed one.

The recorded run completed deterministic and basic strategies, but only five bound cases completed
before severe memory pressure (about 0.29 GiB free) and a 247.81-second failure led to stopping it.
Basic passed 11/28 supported questions; bound passed 2/5 completed questions. These unequal totals
are not a fair headline comparison. On their five common cases, both passed 2/5. This small,
sequential, resource-confounded comparison establishes no prompt-strategy winner. The remaining
39 bound case outcomes are uncompleted, not successes or recorded failures; an in-flight request
may have been interrupted. Deterministic mode passed 44/44 and is the recommended demonstration.

An interrupted run can be summarized without invoking Ollama:

```bat
python -m retention_uplift.assistant.cli summarize --input data/eval-live
```

This rebuilds only the derived summary from saved JSONL rows and run configuration. It does not
resume inference or invent missing outcomes. Status stays `incomplete` until every planned case
has a recorded outcome. Keep raw rows and configuration together for audit.

Per-case JSONL records include requests, expected properties, actual raw model plans, errors,
validated responses, attempts and elapsed times. Summary denominators distinguish supported
model requests, completed responses, first-attempt success and deterministic scope refusals.
The quantitative accuracy check compares approved rendered claims/references with authoritative
values. It does not measure unconstrained factuality. No model success is credited for a guard
refusal; passing adversarial cases demonstrates system behaviour only on this tested set.

Questions are untrusted data. Prompt wording is not the security boundary: the model has no file,
shell, allocation or external-service tools, output is an allowlisted plan, and rendered facts cannot
be overwritten by model text. API clients cannot set a report path, model host or runtime options.
JSON requests have an 8 KiB actual-body limit and questions a 1,000-character limit. Host checks,
no CORS enablement and safe DOM `textContent` reduce accidental exposure. This is still a local
demo without authentication, TLS, audit persistence, comprehensive rate limiting or multiuser
isolation; do not expose it to a network. A trusted operator controls local files and the runtime.

## Failures and troubleshooting

Errors have shape `{"error":{"code":"...","message":"...","retryable":false}}`.

| Condition | Result / action |
|---|---|
| Missing or corrupted aggregate report | Startup fails with `invalid_report`; restore the reviewed artifact |
| Invalid request/scenario/extra path field | 422 `invalid_request`; use the documented contract |
| Oversized body | 413 `request_too_large` |
| Unknown/restricted source | 404 `unknown_evidence` |
| Ollama stopped or unreachable | 503 `ollama_unavailable`; start local service or explicitly select deterministic mode |
| Model missing/remote-only | 503 `model_missing`; inspect `ollama list`; no automatic download |
| Runtime loading/server failure | 503 `runtime_failure`; inspect Ollama locally |
| Timeout | 504 `model_timeout`; avoid other heavy workloads and retry explicitly |
| Another inference in progress | 429 `model_busy`; retry after completion |
| Invalid JSON/plan after bounded retry | 502; no unverified answer or automatic fallback |

The health endpoint validates report readiness, **not** Ollama readiness. It explicitly says
`not_probed`. Deterministic mode remains useful when the model fails, but must be chosen and is
labelled separately. The tested FastAPI/Starlette combination emits a TestClient HTTPX deprecation
warning; it does not affect test success, and dependency migration remains maintenance work.
