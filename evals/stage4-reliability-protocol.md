# Frozen reliability protocol (20 October 2026; before live v2 execution)

Reuse all 44 existing cases and expectations unchanged. Run deterministic cases
and scope guards separately; neither is an LLM success. Preserve reports/stage4.
New evidence lives in reports/stage4-reliability-v2.

The real adapter uses optional_v2: zero to two unique allowlisted explanatory IDs.
The application includes every mandatory claim, warning and exact source value.
A safe response passes the original assess checks and exact rendering validation.
A meaningful model contribution additionally requires a nonempty validated
selection from the category-specific explanatory catalogue. Each choice adds a
distinct conceptual explanation absent from the mandatory facts; this measures
bounded selection, not novel reasoning or demonstrated user benefit. Record IDs
and their distribution. No automatic deterministic fallback after model errors.
An empty selection is a safe mandatory-only response, not an LLM contribution.

Report valid supported responses and meaningful contributions over completed
supported requests, alongside the planned denominator of 28 and all missing IDs.
Report 16 scope guards separately. Schema validity uses raw returned plans as
denominator; also report all attempts including transport errors. Numeric,
reference, uncertainty and recommendation correctness use delivered responses,
not failed requests. Latency includes errors; median, maximum and nearest-rank
p95 are descriptive only (p95 omitted for fewer than 20 requests).

Use installed qwen2.5:3b, temperature 0, seed 20261020, context 2048, output 64,
two CPU threads, keep_alive 30s, per-I/O timeout 60s, at most one repair attempt
only for invalid plans. Both basic and bound now use the same optional contract;
benchmark bound against historical basic 11/28. This is a sequential engineering
comparison with different load and responsibility, not a randomized model study.

Check free physical memory before every live case. Do not start below 1024 MiB;
stop after a request if below 512 MiB, after two consecutive errors, or after a
request exceeds 90s. A subprocess watchdog stops an in-flight benchmark request
at 100s, records an error, and unloads the task's model before another attempt.
Start with cases 01–05 in original order; expand only if at least four provide
meaningful contributions, none exceeds 90s and memory permits. Preserve every
completed row immediately. Resume skips completed IDs and checks case/report
hashes and inference configuration. Never overwrite a historical row. Resource
blocked cases are uncompleted, not failures or successes. No downloads, training,
Spark benchmark process or system configuration changes.
