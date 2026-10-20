# Stage 4 reliability improvement — engineering complete, live validation blocked

## A. Root-cause analysis

The historical basic run delivered 11/28 supported responses. Of 41 generation attempts,
33 returned plans; all 33 passed the old typed JSON schema. **22/33 omitted mandatory IDs**;
none contained unknown or duplicate IDs. Eight attempts ended in transport timeouts. Nine
requests ultimately failed plan validation and eight ended in timeout. The five-case bound
run returned five schema-valid plans from eight attempts; three omitted mandatory IDs and
three attempts timed out. See [the recorded audit](stage4-reliability-v2/diagnosis.json).

For case-03, “How many customers are selected?”, the model first returned `selected` alone;
the repair returned `selected`, `budget`, `capacity`, still omitting three required claims.
Case-04 repeated the same two-ID incomplete answer on both attempts. The model answered the
narrow question but failed the application's broader completeness obligation. Retrying that
obligation added work without reliably correcting it.

Catalogues required 1–14 mandatory IDs (median 7), alongside full rendered financial prose.
They were not proven to exceed context limits. The saved logs lack token counts and stop
reasons, so truncation, context overflow and a model/runtime defect cannot be established.
There were no recorded routing mismatches in the fixed deterministic cases. Historical
memory pressure and long wall times are measured facts, but do not prove every timeout was
memory-caused. The improvement targets the demonstrated omission failure directly.

## B. Changes implemented

Old local contract: `{"claim_ids":[...]}` requiring the model to repeat every mandatory ID.
New local contract: `{"optional_claim_ids":[...]}` with zero to two unique IDs from a two-item,
category-specific allowlist. The application includes all mandatory facts before considering
model output. The model chooses additional conceptual explanations, for example the distinction
between a budget ceiling and a spending target, or between retention power and financial power.
These are curated explanations, not model-authored metrics or new evidence.

Ollama's `format` receives a typed JSON schema with an enum of allowed IDs. Pydantic and
application checks still reject extras, unknown IDs, duplicates and oversized selections.
Every final sentence and numeric source is rendered and validated deterministically.
This follows [Ollama's structured-output documentation](https://docs.ollama.com/capabilities/structured-outputs).

Additive response fields are `model_selected_claim_ids` and `contribution`. Nonempty valid
selection is `optional_explanation`; empty selection is `empty_selection` and earns no
meaningful-contribution credit. Deterministic and scope-guard results say `none`. The old
plan validator remains for final completeness and custom-adapter compatibility (`legacy_plan`);
the actual Ollama adapter does not silently accept the old contract. Strict response clients
must allow the added fields. The UI displays the contribution classification.

## C. Resource efficiency

Across the unchanged 28 supported questions, bound-prompt message length fell from median
1,538.5 to 713.5 characters (**53.6% reduction**). Median serialized request size fell from
2,115.5 to 1,270.5 bytes (**39.9% reduction**); maxima fell from 3,554 to 1,314 bytes.
These are measured payload sizes, not tokenizer counts or demonstrated inference speedups.

The installed model remains `qwen2.5:3b`, Q4_K_M, approximately 1.9 GB on disk, Ollama 0.40.6.
It was the only listed model; none was loaded at the initial check. No downloads or system
configuration changes occurred. New options: temperature 0, seed 20261020, context 2048
(previously 4096), output cap 64 (previously 256), two CPU threads, keep_alive 30 seconds
(previously two minutes). Successful local inventory checks are cached for 60 seconds.
Generation telemetry now records token counts, stop reasons and runtime durations when returned.

The machine reports 8,148,984 KiB physical RAM. Free memory was initially 789,152 KiB with
no model loaded. The benchmark gate measured 842.85 MiB, then 794.48 MiB after the full test
process and Spark exited. Both were below the prespecified 1,024 MiB start threshold.
No new inference latency, model-memory footprint or speedup was measured. See the append-only
[resource observations](stage4-reliability-v2/resources.jsonl).

## D. New live-model results

The [frozen protocol](../evals/stage4-reliability-protocol.md) predates new benchmark execution.
The [saved summary](stage4-reliability-v2/summary.json) is explicitly incomplete:

| Metric | Result |
|---|---|
| Supported live cases completed | 0/28 planned |
| Valid live responses | 0/0 attempted; rate undefined |
| Meaningful model contributions | 0/0 attempted; rate undefined |
| Empty-selection responses | 0 |
| Error-triggered deterministic fallbacks | 0; unsupported by design |
| Live timeout/error rate | Undefined; no inference attempted |
| Returned-plan schema validity | 0/0; undefined |
| Live median/p95 latency | Not available |
| Scope-guard refusals | 16/16; zero model calls |
| Separate deterministic evaluation | 28/28 supported + 16/16 guards |

All supported cases 01–28 remain uncompleted. They are neither successes nor failures.
No real-model contribution has been established for the new contract. Mocked contract tests
and deterministic evaluation are never presented as live-model results.

## E. Historical comparison

Historical basic: **11/28**, median 39.78 seconds, nearest-rank p95 94.75 seconds. Historical
bound: **2/5 completed**, not a full 28-case benchmark. Original JSONL and summaries under
`reports/stage4` are unchanged. New v2 evidence has its own directory. The new responsibility
is narrower, and machine load differs; even a future completed run would be an engineering
comparison rather than a controlled model-capability experiment. No live improvement is claimed.

## F. Factual validation

All mandatory claims, exact source references, financial numbers, interval interpretations,
recommendations, synthetic/illustrative caveats and human-review metadata remain application
controlled. The full matrix of 28 supported cases with empty, either single, and both optional
selections verifies the same mandatory evidence as deterministic mode. Additional explanations
contain no financial numbers and do not claim new evidence. Stage 3 bytes and all prior tests
are unchanged. The base result remains inconclusive: no rollout; sensitivities cannot replace it.

## G. Safety and reliability

The unchanged 16 adversarial/unsupported cases, including nine injection cases, are refused
before inference. No tools, arbitrary URLs, shell actions, customer selection or report writes
are available to the model. API defaults remain loopback and read-only. Invalid plans allow one
repair attempt; transport errors return explicit errors without retries or silent fallback.

The incremental Windows runner checks memory, records each row immediately and verifies frozen
case/report/protocol hashes and inference options on resumption. It skips completed IDs and
rejects duplicate/unknown cases. Expansion beyond five supported cases requires at least four
meaningful contributions and the resource limits. Two consecutive errors, excessive latency
or severe free-memory pressure stop the run. Its subprocess watchdog ends the benchmark client
at 100 seconds and requests model unload; this is not a guarantee of immediate server-side
cancellation. Unknown attempt counts after watchdog termination are explicitly marked unknown.
The ordinary API retains per-I/O timeouts, not a hard wall-clock deadline.

## H. Automated verification

Full local regression: **311 passed, zero failed/skipped**, 359.52 seconds (console time).
After two additional resource/attribution tests, the final assistant suite passed **225 tests**
in 27.60 seconds. The combined suite contains **313 tests**, including all **187 unchanged
pre-existing tests**. [Machine-readable local results](stage4-reliability-v2/tests.json) use JUnit
suite timing, which excludes a small amount of command overhead. Ruff lint/format, `pip check`
and `git diff --check` pass. One existing Starlette/httpx deprecation warning remains non-fatal.
CI for the delivered commit is linked in the PR and delivery record.

The first sandbox test attempt hit temporary-directory restrictions and was interrupted;
verification used explicit repository-local temporary directories and normal local permissions.
No test assertions were removed or weakened. CI runs the complete final suite independently.

## I. Local demonstration — Windows CMD

From the repository checkout:

```bat
.venv\Scripts\activate
python -m retention_uplift.assistant.cli serve
```

Open `http://127.0.0.1:8000`. In another activated CMD window:

```bat
python -m retention_uplift.assistant.cli explain "What campaign is recommended?"
ollama list
python -m retention_uplift.assistant.cli explain "What campaign is recommended?" --mode ollama
```

The last command makes a real model request, requires adequate available memory, and can fail
explicitly. It is an invocation example, not a claim of successful v2 execution on this machine.
For guarded incremental benchmarking, use a new directory:

```bat
python -m retention_uplift.assistant.reliability --output data/eval-live-v2
REM Repeat to resume; expand only after the initial prefix passes its gates:
python -m retention_uplift.assistant.reliability --output data/eval-live-v2 --expand
python -m pytest -q --basetemp=data/test-full-tmp
```

Use deterministic mode when resource-constrained. The UI's historical evaluation link and
`/evaluation-summary` deliberately retain the old v1 summary; current evidence is in the v2 files.

## J. Outstanding limitations

Live v2 success, selection diversity, empty-selection frequency, latency and memory improvements
remain unverified. The 1 GiB gate is a conservative operating threshold, not a guarantee that a
3B model fits without paging. Finite keyword routing and curated English explanations limit
coverage. A valid nonempty selection is a prespecified proxy for useful contribution, not a
human utility study. Lower output/context limits require live confirmation. No new prompt-tuning
loop or unapproved model download was used to chase a headline percentage.

## K. PR delivery

Continue [PR #4](https://github.com/tabishiqbal03/customer-retention-uplift-system/pull/4) on
`feature/stage-4-governed-ai-assistant`. It remains open and unmerged. The final commit SHA and
CI URL are recorded in the delivered completion report and PR checks after push. No customer-level
data, credentials, local personal paths or model binaries are included in this improvement.

## L. Merge recommendation

The deterministic governed system is suitable for a clearly labelled portfolio demonstration,
subject to passing final CI and owner review. The new optional contract removes the mandatory-ID
failure mode by construction, but **actual model reliability is not established**. Do not merge
on the premise that local LLM performance has improved. If live reliability is a merge condition,
keep PR #4 open until a resource-adequate run completes. This is not production-ready and is not
suitable for real-world deployment without separate evidence and operational governance.
