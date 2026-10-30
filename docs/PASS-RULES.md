# Pass Rules and the Two Timeout Layers

The evaluation's pass rules, as evidenced by the harness code, the agent code and the run record. There are two distinct timeout layers, and they are not interchangeable.

## The execution timeout that fired on Q08: 3,600 s (server-side graph budget)

- `aiq/src/deep_researcher_agent/agents/deep_researcher/resource_limits.py` sets `DEFAULT_MAX_RESEARCH_EXECUTION_SECONDS = 3600.0`. `DeepResearchResourceLimits.max_execution_seconds` defaults to 3600.0 with a field constraint `le=DEFAULT_MAX_RESEARCH_EXECUTION_SECONDS`, so no served configuration can raise it above 3,600 s. No override appears in the served configs. The runner passes the function config's resource limits through (`jobs/runner.py`, `resource_limits=fn_config.resource_limits`), and the agent constructs the defaults when none are supplied.
- `aiq/src/deep_researcher_agent/agents/deep_researcher/agent.py` wraps the orchestrator invocation in `asyncio.timeout(self.resource_limits.max_execution_seconds)` and raises `DeepResearchExecutionTimeout` only when that timeout context has expired. An inner provider or tool `TimeoutError` is re-raised as itself.
- Q08 evidence: server log lines 18128 and 18132 (in `eval/evidence/server-log-extract.txt`) record the `DeepResearchExecutionTimeout` failure at 2026-10-20 18:29:11 for job `5fe6a0cf-762e-4e19-9cae-30f39f47da99`.
- Why Q08's metrics latency is 3,958 s rather than 3,600 s: the metrics latency is submit-to-terminal wall time for the whole job. The 3,600 s budget governs the graph execution context inside the agent, which starts after job setup. The two numbers measure different spans; both are reported as found.

## The outer driver deadline: 5,400 s (harness poll and cancel ceiling)

- `eval/run_eval.sh` and `eval/run-eval10.sh` both set `deadline = now + 5400` (90 minutes). On expiry the driver POSTs the job cancel route and marks the row `timeout_cancelled`.
- This ceiling did not produce Q08's failure. The server-side execution timeout ended the job first, and the driver recorded the server failure.
- 5,400 s is the driver's poll and cancel deadline. It is not the execution timeout.

## Rule 1: citation integrity gate

- `aiq/src/deep_researcher_agent/common/citation_verification.py`: a `SourceRegistry` captures URLs and citation keys from tool-call results; `verify_citations()` validates cited source identities against that registry; `CitationIntegrityError` carries the stable message `citation_integrity_lost` and is raised when a verified report would be published without any verified citations.
- `agent.py` verifies twice: once in post-processing (invalid citations are removed), then again on the final message. If the final verification has no valid citations, it raises `CitationIntegrityError` at line 421.
- Q06 evidence: server log lines 11612 and 11615 record the failure at 2026-10-20 17:04:37; `eval/evidence/Q06.job.json` (job `439044a5-9071-445d-9c5c-53da9586c311`), `eval/evidence/Q06.report.json` (no report), and fingerprint `b9793675134d`. $0.20 was spent; nothing was published. Full write-up: [GATE.md](GATE.md).

## Remaining pass rules, as evidenced by the run record

2. **One job at a time.** The eval drivers submit, poll, and persist sequentially.
3. **Cancel on outer timeout** through the POST cancel route. The earlier DELETE route returned 405 and was fixed in the driver.
4. **Spend cap.** The set ran under a $2.50 cap, with the set-wide watchdog armed at a $2.45 trip and balance snapshots before and after each question. Final spend was $2.08; the watchdog never tripped.
5. **Config invariance.** The served config's SHA-256 is verified unchanged at start, at serve time, and after the set. A mid-run change invalidates the set.
6. **Failure is terminal and recorded.** A failed job persists a 0-byte report, a job record naming the error, and a metrics row. It is not silently retried.
7. **Researcher note cap (measured config fact).** deepseek-flash non-thinking output stops at 8,192 tokens while the config asks for 32,768. The final run had 39 truncations and 15 failed batches, all recovered by the orchestrator. Changing the cap is an open decision.
8. **The locked 5-point citation decision rule is a known limit, not a pass rule that was executed.** The comparison arm was never run, and the baseline carries titles only, with no URLs and no spot check, so the rule cannot be executed as written. The evaluation closed on cost, completion, and traceability.
