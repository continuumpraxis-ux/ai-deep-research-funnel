# Recorded Run: Q01, 2026-10-26

On 2026-10-26, question Q01 was run end to end on the build machine with the evaluation configuration. Everything below comes from that run's own records: the launcher, driver and watchdog logs, the run summary, the balance snapshots, and a NIM probe taken minutes before the run. The four record files that ship are in [`eval/evidence/recorded-run/`](../eval/evidence/recorded-run/).

This is a demonstration run, not an evaluation run. It is separate from the Q01 row in the evaluation table (job `08d94b22`, 2026-10-20).

## What was run

- Question Q01: "What are the credible, evidence-backed revenue opportunities for solo AI-agent operators in the next 12 months?"
- Configuration: the evaluation configuration (`config_web_deepseek_search.yml`). The launcher verified the staged config's SHA-256 prefix at serve time: `ede84b57`, as expected.
- Path: the pacing proxy was up before the server started, and the Nemotron roles route through it.
- Server: the funnel server answered on port 8002, because the staged NIM services hold ports 8000 and 8001.
- Driver: the evaluation driver in single-question mode (`ONLY=Q01`).
- Job: `c65ea76d-6ea9-4a6c-8944-8a88ba88a296`.

## Timeline (local time)

| Time | Event |
|---|---|
| about 17:53 | Pre-run NIM probe: both staged services answer (see below) |
| 17:57:35 | Pacing proxy up |
| 17:57:48 | Server answering on 8002; staged config SHA-256 prefix `ede84b57` verified |
| 17:57:49 | Spend watchdog up, trip set at $0.45 spend |
| 17:57:51 | Balance pre-flight: $2.52; Q01 submitted |
| 18:14:42 | Q01 status `success`, latency 1,011 s |
| 18:14:45 | Balance post-flight: $2.08; driver exit 0 |
| 18:14:48 | Server and proxy stopped |

## Result

| Measure | Value |
|---|---|
| Status | success |
| Latency | 1,011 s |
| Committed report | 41,579 characters |
| Distinct citation markers | 59 |

The report text itself is not included in this package.

## Spend: this run's own observation

The DeepSeek balance went from $2.52 before the run to $2.08 after it, so the metered spend for this run was **$0.44**. This is this run's own observation, recorded by its watchdog and balance snapshots. **It is not an evaluation figure.** In particular, the $2.08 here is the account balance at the end of this run; it is unrelated to the $2.08 total spend of the evaluation set, and the two coincide only by chance.

The spend watchdog was armed to trip at $0.45. The highest spend it recorded was $0.44, so it never tripped.

## Staged NIM services, before the run

A probe at about 17:53 local time, minutes before the run was submitted, found both staged NIM services answering on localhost:

- port 8000, `GET /v1/models`: `nvidia/Nemotron-3.5-Embed-1B-BF16` (the staged embedder)
- port 8001, `GET /v1/models`: `nvidia/llama-nemotron-rerank-vl-1b-v2` (the staged reranker)

The precision leg is staged. It was not part of this run's evaluation, and this run makes no claim about citation precision.

## Record files

| File | What it shows |
|---|---|
| `eval/evidence/recorded-run/_summary.csv` | status, latency, report characters, citation markers |
| `eval/evidence/recorded-run/spend-watchdog.log` | balance and spend each minute, trip level |
| `eval/evidence/recorded-run/balance-start.json` | balance before the run |
| `eval/evidence/recorded-run/balance-end.json` | balance after the run |

The launcher log, driver log and NIM probe note are part of the run record but are not shipped; the timeline above is taken from them.
