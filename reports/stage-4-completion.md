# Stage 4 completion report

Verification date: 20 October 2026 (Europe/London). All customer data are synthetic and all
economics illustrative. No real retention improvement, profit or deployment is claimed.

**Delivery status:** implementation and local tests are verified; the full evidence-bound live
benchmark remains incomplete because of resource pressure.

## A. Implementation summary

Added `assistant/contracts.py`, `evidence.py`, `claims.py`, `engine.py`, `ollama.py`, `api.py`,
`cli.py`, `evaluate.py` and a small local HTML interface. Added 44 fixed evaluation cases,
99 assistant tests, pinned API dependencies, the `retention-assistant` entry point,
setup/governance documentation, interview material and CV wording. Package version is 0.4.0.
The branch starts from merged Stage 3 commit `33f5177`. The Stage 1–3 numerical engine, original
test files and saved results remain unchanged.

## B. LLM runtime

Real local inference was executed with **Ollama 0.40.6 / qwen2.5:3b**, model ID prefix
`357c53fb659c`, 3.1B parameters, Q4_K_M, approximately 1.9 GB installed / 2.2 GB loaded,
100% CPU at the observed runtime snapshot. No model was downloaded. The tested Windows machine
has approximately 8 GB RAM; an in-run snapshot showed about 0.67 GiB free. This is an environmental
observation, not proof that RAM alone caused latency. The full native model context is 32768;
this application uses 4096, temperature 0, seed 20261020, prediction cap 256 and two threads.
The local smoke test succeeded after two attempts in 34.180 seconds. It is separate from the
benchmark. Later free memory fell to about 0.29 GiB; the bound run was stopped and Ollama unloaded.
Model license and actual package versions are recorded in [runtime.json](stage4/runtime.json).

## C. Evidence preparation and provenance

The service validates the saved Stage 3 schema and projects only approved aggregate fields.
Each fact carries artifact ID, SHA-256, exact field path, scenario, value, units and evidence class.
Artifact SHA-256: `a20186b0c8974ef525dc76f8ba73792a8f049a802bf07b6f92300214503c033e`.
Campaign retrieval includes recommendation, selected count, spend/budget, predicted net and the
observed-outcome estimate/interval. Sensitivity includes both scenario assumptions and results.
Pilot retrieval includes counts, baseline, MDE, alpha, power, allocation ratio and an estimand caveat.
Oracle diagnostics, latent effects, customer-level rows, local file paths and generation metadata
are withheld. No vector database is used. The hash provides traceability, not signed authenticity.

## D. Response validation

Pydantic enforces request, report, fact, claim-plan and response contracts. Ollama selects/orders
approved IDs; all required IDs must be present and unique. An optional review reminder can be
selected. Application code renders the authoritative values and mandatory caveats, then verifies
the answer, scenario, source values and recommendation-bearing text. A failed plan gets one retry;
a second failure produces a typed error. Transport errors do not trigger a silent fallback.

This is constrained claim composition, not free-form model-authored financial analysis. It protects
approved rendered numbers and text; it does not establish arbitrary semantic correctness, prove the
underlying analysis, or validate every imaginable hallucination. Catalogue wording remains reviewed
application logic. Scope-guard refusals never call the model and carry no invented numbers.

## E. Evaluation results

The fixed development suite has **44 cases: 28 supported and 16 unsupported/adversarial**.
It was defined before engine implementation. One initial routing defect (`high_cost` being treated
as a cost keyword) was corrected before the final run, without changing expectations. An interrupted
early evaluation was retained locally but excluded from these results. Both strategies used the same planned cases/model/settings. Neither prompt was tuned to the
final-run failures. **The bound benchmark is incomplete:** only five case outcomes were recorded
before severe memory pressure and a 247.81-second failure led to stopping. The remaining 39 outcomes
(including 23 supported questions) are uncompleted and may include an interrupted in-flight request.
On the five common cases, both basic and bound passed 2/5; no strategy winner is established.
Additional scope spelling/mutation edge tests and recovery logic were added separately; saved
successful responses were replayed against the final renderer to verify they still validate.

| Mode / prompt | Supported passes / completed supported cases | First-attempt live passes | Correct scope refusals | Median seconds | p95 seconds | Retries |
|---|---:|---:|---:|---:|---:|---:|
| deterministic | 28/28 | N/A | 16/16 | 0.001 | 0.003 | 0 |
| basic | 11/28 | 8 | 16/16 | 39.775 | 94.745 | 13 |
| bound | 2/5 | 0 | not run | 65.753 | 247.811 | 3 |


**basic:** 11/28 actual generation requests produced passing responses; 33/41 generation attempts returned a schema-valid plan. Terminal errors: `{'invalid_model_plan': 9, 'model_timeout': 8}`. Failed cases: `case-03, case-04, case-05, case-06, case-07, case-08, case-09, case-11, case-12, case-13, case-14, case-15, case-16, case-17, case-18, case-19, case-23`. The 11 delivered model responses contained 64 approved claims and 54 validated field references.


**bound:** 2/5 actual generation requests produced passing responses; 5/8 generation attempts returned a schema-valid plan. Terminal errors: `{'model_timeout': 3}`. Failed cases: `case-03, case-04, case-05`. The 2 delivered model responses contained 14 approved claims and 14 validated field references.


Structured final responses, evidence-value validity, approved rendered-claim accuracy and required
uncertainty preservation passed on every delivered supported answer. That denominator excludes
controlled failures: see supported success rates above. No unsupported financial claim was delivered
by a passing response; this is a catalogue/rendering invariant, not a measured free-form hallucination
rate. Refusal and tested injection resistance are system-level scope-guard results, **not LLM
successes**. All nine labelled injection cases were refused in deterministic and basic runs;
they were not reached in the partial bound run. There are zero deterministic fallback answers
counted as real-model successes.

The basic prompt asks for relevant IDs; the bound prompt additionally states required coverage and
trust rules. Both share the structured-output schema and post-validator. The comparison is not a
raw chatbot versus a governed model. Basic and bound overall denominators differ and must not be
compared as though both ran the full set. Strategies ran sequentially on one machine, not counterbalanced;
warmth, load and timeout effects confound timing comparisons. Latencies include inventory checks,
generation and retries for supported requests with actual model attempts; p95 uses nearest rank.
The 60-second HTTP timeout is per I/O phase rather than a hard wall-clock deadline;
the observed severe latency spike is a limitation, not a successful timeout guarantee.

This development suite does not establish generalization across paraphrases, models or adversarial
attacks. Rejected incomplete plans and timeouts show why deterministic demonstration remains the
default and why the LLM option should not be advertised as a reliable production assistant.

Evidence: [summary](stage4/evaluation-summary.json), [plan audit](stage4/plan-audit.json),
[deterministic cases](stage4/deterministic-cases.jsonl), [basic cases](stage4/basic-cases.jsonl),
[bound cases](stage4/bound-cases.jsonl). Per-case files preserve actual raw model plans and errors.
Case-set SHA-256: `287aaec6f98dd104316f3d639b5af0df189a9b44cd10e5e5ae021b90a1d97d44`.

## F. API and demonstrations

`GET /health`, `/report-summary`, `/evidence/{reference}`, `/evaluation-summary` and
`POST /explain` expose typed, read-only evidence; `/` serves the local UI and `/docs` OpenAPI.
Startup does not import Spark or train/generate data. Health explicitly does not probe Ollama.
Real HTTP demos A/C/D/E returned 200 for factual explanation, safe refusal, high-cost comparison
and pilot design. [Recorded demo responses](stage4/http-demos.json) preserve the actual output.
Demo B's real Ollama smoke response is [saved separately](stage4/live-smoke.json).
The UI was inspected in a browser, submitted a deterministic question and exposed the source paths.
CLI and installed entry-point help, editable installation, and dependency checks were also executed.

Exact Windows commands and expected shapes are in [the assistant guide](../docs/assistant.md).

## G. Governance and security boundaries

Questions are untrusted data, never authority to edit decisions. The model has no shell, file,
allocation or arbitrary network tools. The adapter only calls fixed loopback Ollama endpoints and
rejects remote-only model entries. HTTP clients cannot choose artifact paths or model hosts.
The API enforces an 8 KiB actual body limit, 1,000-character question limit, scenario allowlists,
host checks, one inference request per process and sanitized errors. The UI uses safe text rendering.
Synthetic/illustrative warnings and human review survive every supported response.

The lexical guard is finite and imperfect; passing the tested injections is not universal resistance.
The output allowlist is the stronger boundary. Trusted local operators can alter source/report files.
No authentication, TLS, tenant isolation, comprehensive throttling or production monitoring is claimed.

## H. Automated testing

**Full local regression: 185 passed, 0 failed,
0 skipped in 376.36 seconds.** A subsequent assistant-only run after
adding interrupted-evaluation recovery passed 99 tests in
8.21 seconds, with zero failures/skips. Together these cover
187 distinct tests; the final PR CI runs the combined suite again.
All **88 original tests** remain present and unchanged; 99 new assistant tests cover
raw-artifact traceability, missing/corrupt/schema-incompatible reports, numeric/recommendation tampering,
invalid plans, retry limits, runtime failures, prompt injection, API contracts, genuine multi-chunk
body limits, read-only report behaviour and startup without Spark. Ollama is mocked in CI.

```bat
python -m pip install -e ".[dev]"
python -m ruff check .
python -m ruff format --check .
python -m pytest -q --basetemp=data/test-stage4-full
python -m pytest tests/test_assistant.py -q --basetemp=data/test-stage4-final-assistant
python -m pip check
git diff --check
```

Lint, format, dependency and whitespace checks passed. The full run includes real Spark/Parquet
integration. A TestClient/HTTPX deprecation warning remains visible; it is maintenance work, not a
test failure. During development, an oversized pytest parameter needed a short Windows-safe test
ID; this was fixed and verified. See [test-summary.json](stage4/test-summary.json).

## I. Repository presentation

The README now gives the problem, a Mermaid architecture, measured scale, the cautious base
conclusion and a short local-demo path. Detailed prior pipeline instructions moved to
[pipeline reproduction](../docs/pipeline-reproduction.md). Methodology and Stage 1–3 completion
reports remain available. No customer rows, model binaries, credentials or private local paths
were added to the portfolio evidence. Runtime/setup limits and failures are visible, not hidden.

## J. Interview material

[Interview guide](../docs/interview-summary.md) covers each stage, leakage controls, validation
selection, IPW/paired bootstrap, uncertainty, constrained explanation and next steps with real data.
[CV wording](../docs/cv-summary.md) provides a title, stack, two bullets and an optional LLM bullet.
It describes 25,000 synthetic customers / 1.28 million transactions, causal modelling, fresh-cohort
financial evaluation and governed API integration without claiming realised revenue or foundation
model training.

## K. Remaining limitations

Synthetic mechanism and illustrative contribution/costs cannot establish commercial transfer.
Intervals are pointwise, unadjusted and conditional on fitted policies; they omit training/selection
and shift uncertainty. The pilot targets offer effects within a frozen population, not policy-wide
superiority or financial-estimand power. The local model is slow and can fail the contract or timeout.
The suite is development evidence from one model/machine with finite English routing and no
independent linguistic evaluation. Editable checkout is required to find the saved report.
The service is local-only demonstration software with trusted operators and no production controls.

## L. GitHub delivery

Branch: `feature/stage-4-governed-ai-assistant`, based on merged Stage 3. `main` is untouched.
The final delivery record and pull request provide the exact commit, CI outcome and open/unmerged
status. No merge is authorized or performed by this stage.

## M. Final project readiness

Stages 1–4 form a coherent graduate portfolio: data engineering, causal modelling, accountable
financial decisions and a deliberately constrained AI interface are supported by executable evidence.
It is suitable for presentation as a **local synthetic research/engineering prototype**, with the
recorded model failures prominently disclosed. It is not production-ready or evidence of business
ROI. Completing the bound benchmark under suitable resources, reliable interactive LLM operation,
independent language/adversarial evaluation, real randomized
business evidence and operational/privacy controls remain prerequisites for stronger claims or use.
User review and approval are required before merging the Stage 4 pull request.
