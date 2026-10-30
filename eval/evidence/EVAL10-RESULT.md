# Eval: DeepSeek-search arm, 10 questions (2026-10-20)

**Config:** `config_web_deepseek_search.yml`, exactly as it stood after the swap (sha256 `ede84b57…80e8d`
at start, at serve time and after the set; unchanged). Researchers are deepseek-flash
(`reasoning_effort: none`), web search is DeepSeek Search (count 3), and Nemotron 3 Ultra handles
orchestrator, planner and writer through the `openai` client (600 s timeout) via the pacing proxy.
There was no Tavily key, and **Tavily calls were zero**.

**Scope:** Q02–Q10 ran fresh, one at a time, on :8001 (driver `eval/run-eval10.sh`). The Q01 row is
job `08d94b22` from `../deepseek-search/SWAP-RESULT.md` (not rerun).

**Spend:** the Q02–Q10 set cost **$1.89** (balance $4.41 → $2.52). Including Q01 the total is
**$2.08**. The set-wide watchdog was armed at $2.45 (cap $2.50) and never tripped. Nothing was
touched on the primary server (PID 999) or its config, the pacing proxy (1095), or the plan document.
The swap was not applied anywhere else, and the 8,192 cap was not touched. The :8001 server was
stopped after the set.

## Per-question results

| Q | status | latency | report chars | citation markers | body citations | URL sources | DeepSeek cost |
|---|---|---|---|---|---|---|---|
| Q01* | success | 1,419 s | 39,467 | 64 | 41 | 64 | $0.19 |
| Q02 | success | 1,002 s | 16,206 | 8 | 8 | 8 | $0.16 |
| Q03 | success | 916 s | 40,308 | 91 | 68 | 91 | $0.19 |
| Q04 | success | 1,096 s | 32,630 | 61 | 40 | 61 | $0.16 |
| Q05 | success | 824 s | 31,016 | 30 | 19 | 30 | $0.19 |
| Q06 | **failure**: `CitationIntegrityError` | 854 s | 0 | 0 | 0 | 0 | $0.20 |
| Q07 | success | 1,117 s | 30,600 | 64 | 47 | 64 | $0.19 |
| Q08 | **failure**: `DeepResearchExecutionTimeout` | 3,958 s | 0 | 0 | 0 | 0 | $0.18 |
| Q09 | success | 1,098 s | 14,990 | 16 | 14 | 16 | $0.30 |
| Q10 | success | 951 s | 23,554 | 41 | 25 | 41 | $0.32 |

\* Q01 = job 08d94b22 (swap run). "Citation markers" counts distinct `[n]` across the whole report
(the harness metric, which includes the Sources list). "Body citations" counts distinct `[n]` used
in the text. Cost per question is the balance delta at $0.01 resolution.

### Named causes of the two hard-fails

- **Q06: `CitationIntegrityError` (`citation_integrity_lost`).** The writer finished (writer-agent
  chain end logged), but the final verification found **zero** citations in the report that
  matched the run's source registry, so the harness refused to publish (`agent.py:421`,
  `verify_citations` → `valid_citations` empty). This is the integrity gate working. Fingerprint
  `b9793675134d`.
- **Q08: `DeepResearchExecutionTimeout`.** The writer started at 17:37. It then ran about 52 minutes
  of `grep` (55) and `think` (50) tool calls plus 15 `read_file` calls, its context growing about
  1k chars per call up to roughly 191k, and **never wrote `output.md`**. The harness's research
  wall-clock limit ended the job at 18:29:11. Q08 accounts for 186 of the set's 545 Nemotron calls
  and 47 of its 125 proxy 429 pauses. Fingerprint `fdb89121e2c4`.

The two fingerprints differ, and Q07 succeeded between them, so the three-consecutive stop rule
never came close.

## Aggregate

| | |
|---|---|
| **Completions** | **8 / 10** (including Q01) |
| Mean latency, all 10 | 1,324 s (22.1 min) |
| Mean latency, the 8 successes | 1,053 s (17.5 min) |
| **Total DeepSeek cost** | **$2.08** ($0.208/question; $1.89 for this pass) |
| DeepSeek Search requests | 939 (all 200; ≈ $0.70 of the total at $0.75/1k) |
| DeepSeek Fetch requests | 0 |
| Tavily calls | 0 |

### Nemotron across the set

- **545 calls, 0 non-200 responses, 1 LLM-error line.** That one line is Q08's in-flight call being
  cancelled by `DeepResearchExecutionTimeout` at 18:29:11. It is a local cancellation, not an
  NVIDIA failure.
- **129 calls ran longer than 60 s and all succeeded.** Every one would have been killed by the old
  nim client's 60 s read timeout. 125 of them line up with **125 upstream 429s absorbed by the
  proxy** (60 s pause, then retry). The rest are long generations; the longest was 217 s, Q01's
  writer.

### Researcher truncation (deepseek-flash 8,192-token stop): counted, not fixed

- **39 researcher ResearchNotes responses stopped at exactly 8,192 completion tokens**, in every
  question (1–6 per question).
- 40 researcher-agent chain errors: 39 truncations plus 1 other, in Q07.
- **15 `run_research_batch` tool errors** (failed batches), every one re-dispatched by the
  orchestrator.
- 88 researcher runs completed. Q02 (5 truncations, only 5 researchers completed) produced the
  thinnest successful report (8 sources).

## Citation spot-checks (claims checked against live pages)

Details are in `spotcheck-Q05.md` and `spotcheck-Q10.md`, and Q01's are in `../deepseek-search/SWAP-RESULT.md` §4.

| question | fully supported | defects found | unverifiable |
|---|---|---|---|
| Q01 | 2 / 3 ([52], [62]+[23]) | [4]: right figures, wrong year (2025 should be 2026) | n/a |
| Q05 | 2 / 3 ([7] verbatim quote, [13]) | [6]: right figures; one sub-claim ("observability existed") attributed to a source that says monitoring was absent | n/a |
| Q10 | 0 / 3 | [2]: 11 figures verbatim, but "top 5% $15–30K / top 2% $50K+" is not on the page. [18]: distribution exact, "$4,200 median" absent. HeadshotPro "$300K MRR" is true but cited as [9] when it is [10] | [12]: dead link (redirects to the site homepage) |

**Across 10 checked sources:** 4 fully supported, 5 with a defect, 1 dead link. **No fabricated
URLs.** Every headline number checked was found in a cited source. The defects are precision
errors: a wrong year, one misattributed sub-claim, one interpolated pair of percentiles, one
unsupported median, and one off-by-one citation key. All 64 Q01 source URLs trace to that run's
DeepSeek Search results.

## §7 comparison: this arm vs the earlier Nemotron baseline

**Where baseline data exists (Q01 only).** The baseline run used Nemotron researchers with Tavily, job
`bf99f419`, output `runs/Q1-report.md`.

| | Nemotron baseline (Q01) | this arm (Q01) | this arm (8 successes) |
|---|---|---|---|
| report chars | 25,839 | 39,467 | 14,990 – 40,308 |
| citation markers | 8 | 64 | 8 – 91 (median 51) |
| **sources carry URLs** | **No. 8 grouped source sets, titles only, 0 URLs** | Yes, 64 URLs, all traceable to this run's searches | Yes, every listed source has a URL |
| spot-check accuracy | **No data.** No URLs to check; no spot-check was ever run on it | 2 / 3 fully supported, 1 year error | 4 / 9 fully supported, 5 defects, 1 dead link (Q01, Q05, Q10) |

- **Citation presence:** this arm is clearly ahead of the one baseline report. The baseline's
  "sources" are bundles of publication titles with no links, some generic (e.g. "State of AI
  Consulting 2024 - Solo Operator Benchmarks"). They can't be resolved to pages, so their
  accuracy can't be measured. This arm's citations are individually numbered and URL-bearing.
- **Spot-check accuracy: no baseline comparison is possible.** The baseline report has no URLs and
  no recorded spot-check, so there is no accuracy figure to set against this arm's 4 / 9.
- **Q02–Q10: no baseline data exists at all.** The Nemotron-researcher arm of the 10-question eval
  was never run, so completion rate, latency, cost and citations for those nine questions have no
  comparison point. Cost is also not comparable: the baseline ran on free-tier NVIDIA plus
  Tavily, and its Tavily spend per question was not recorded.

## Files

- Driver, run log and per-question summary: `run.log`, `_summary.csv`
- Per question: `Q0x.job_id`, `Q0x.job.json`, `Q0x.report.json`, `Q0x.report.md`, `Q0x.state.json`
- Metrics: `metrics.csv` and `metrics.jsonl` (from `eval/metrics-eval10.py`)
- Server log: `server.log`; watchdog log: `spend-watchdog.log`; preflight hash: `preflight.txt`
- Spot-checks: `spotcheck-Q05.md`, `spotcheck-Q10.md`
