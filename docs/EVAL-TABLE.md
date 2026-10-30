# Evaluation Results

Final evaluation set, run 2026-10-20 on the build machine (Windows on ARM laptop, NVIDIA RTX Spark). Every figure below comes from the run record (`eval/evidence/metrics.csv` and `eval/evidence/EVAL10-RESULT.md`). None of it is estimated or reconstructed.

## Outcome summary

| Metric | Result |
|---|---|
| Research questions run | 10 |
| Completed with committed, cited reports | **8 of 10** |
| Failed on citation integrity gate | 1 (Q06) |
| Failed on execution timeout | 1 (Q08) |
| Total DeepSeek spend, all ten questions | **$2.08** |
| DeepSeek spend, Q02 to Q10 | $1.89 |
| Mean cost per question | about $0.21 ($0.208) |
| Tavily calls and spend, final configuration | 0 |
| Mean latency, all ten | 1,324 s |
| Mean latency, the eight successes | 1,053 s |

## Per-question rows

| Q | Status | Latency (s) | Report chars | Citation markers | Body citations | Cost | Error / fingerprint |
|---|---|---:|---:|---:|---:|---:|---|
| Q01 | success | 1,419 | 39,467 | 64 | 41 | $0.19 | job 08d94b22 (see note) |
| Q02 | success | 1,002 | 16,206 | 8 | 8 | $0.16 | |
| Q03 | success | 916 | 40,308 | 91 | 68 | $0.19 | |
| Q04 | success | 1,096 | 32,630 | 61 | 40 | $0.16 | |
| Q05 | success | 824 | 31,016 | 30 | 19 | $0.19 | |
| Q06 | failure | 854 | 0 | 0 | 0 | $0.20 | CitationIntegrityError / b9793675134d |
| Q07 | success | 1,117 | 30,600 | 64 | 47 | $0.19 | |
| Q08 | failure | 3,958 | 0 | 0 | 0 | $0.18 | DeepResearchExecutionTimeout / fdb89121e2c4 |
| Q09 | success | 1,098 | 14,990 | 16 | 14 | $0.30 | |
| Q10 | success | 951 | 23,554 | 41 | 25 | $0.32 | |

Note: Q01 is the earlier proof job `08d94b22` on the same configuration and was not rerun in the evaluation pass; Q02 to Q10 ran fresh, one at a time. Full rows with Nemotron, proxy and search counts: [eval/results.md](../eval/results.md). Question texts: [eval/questions.md](../eval/questions.md).

## Cost

The cost column reconciles exactly: the ten rows sum to $2.08, Q02 to Q10 sum to $1.89, and the mean is $0.208 per question, about $0.21. Cost per question is the DeepSeek balance delta at $0.01 resolution.

## Failures, itemised

| Question | Failure mode | What happened |
|---|---|---|
| Q06 | Citation integrity gate | The report matched zero sources in the run's source registry. The harness refused to publish it and nothing was persisted. The gate stopped a bad report from shipping. Run cost ($0.20) was still spent. See [GATE.md](GATE.md). |
| Q08 | Execution timeout | The writer got stuck in a research loop and never committed a report. The server-side 3,600 s graph budget raised `DeepResearchExecutionTimeout`. The eval driver's 5,400 s cancel deadline did not fire. The 3,958 s latency is submit-to-terminal wall time for the whole job, a different span from the graph budget. See [PASS-RULES.md](PASS-RULES.md). |

## Citation quality (spot check)

Claims were checked against the live cited pages on three questions (Q01, Q05, Q10), 10 sources in all, 9 of them content-checkable (the tenth was a dead link).

| Check | Result |
|---|---|
| Sources fully supporting the claim | 4 of 9 checked |
| Sources with a precision defect | 5 of 9 checked |
| Dead links | 1 of 10 total |
| Fabricated URLs | 0 |
| Headline numbers not found in a cited source | 0 |

The five defects are precision errors: a wrong year, one misattributed sub-claim, one interpolated pair of percentiles, one unsupported median, and one off-by-one citation key.

## Against the baseline

The baseline is an earlier configuration with Nemotron researchers and Tavily search. It produced one Q01 report; the other nine questions were never run on it.

| | Baseline (Q01 only) | This build |
|---|---|---|
| Citation form | Titles only, no URLs | URL citations |
| Traceable | No | Yes, on every successful report |

## Notable individual results

| Item | Result |
|---|---|
| Q01, after the writer-client fix | Passed, 41 body citations, $0.19 |
| Free-tier route (OpenRouter free variant) | 0 of 10 completed under 429 saturation (16,414 requests), measured at $0 |
| Unpaced NVIDIA calls, two earlier Q01 attempts | Failed with 46 and 90 HTTP 429 responses |
| Paced through the proxy, final run | 545 Nemotron calls, 125 upstream 429s absorbed as latency, none reached the funnel as a failure |

## Source of record

`metrics.csv` as produced by the run has SHA-256 `cba381d93e8d84d8e712984475192e454c2a1cc1f01cd2a118906a4c17ad5e67`. The copy in `eval/evidence/` has the same content with LF line endings in place of the original CRLF, so its hash differs.

See [KNOWN-LIMITS.md](KNOWN-LIMITS.md) for what these results do not show.
