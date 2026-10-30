# Per-Question Results

Final evaluation arm, run 2026-10-20: deepseek-flash researchers (thinking disabled), DeepSeek Search as the source supply, and Nemotron planner, writer and orchestrator on the OpenAI-compatible client (`request_timeout: 600`) behind the pacing proxy. Served config `config_web_deepseek_search.yml`, SHA-256 `ede84b573fae70839ae3e3ff69d732992e607f814e2189bfe123e4f502480e8d` as served, unchanged at start, at serve time and after the set.

Every cell comes from [`evidence/metrics.csv`](evidence/metrics.csv). No cell is estimated or reconstructed. Q01 is the earlier proof job `08d94b22` on the same configuration and was not rerun; Q02 to Q10 ran fresh, one at a time.

| Q | Status | Latency (s) | Report chars | Citation markers | Body citations | URL sources | Cost | Nemotron calls | Nemotron LLM errors | Calls over 60 s | Proxy 429 pauses | Searches | Researcher truncations at 8,192 | Error / fingerprint |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Q01 | success | 1,419 | 39,467 | 64 | 41 | 64 | $0.19 | 55 | 0 | 12 | 11 | 87 | 4 | proof job 08d94b22 |
| Q02 | success | 1,002 | 16,206 | 8 | 8 | 8 | $0.16 | 40 | 0 | 10 | 10 | 94 | 5 | |
| Q03 | success | 916 | 40,308 | 91 | 68 | 91 | $0.19 | 36 | 0 | 8 | 8 | 98 | 1 | |
| Q04 | success | 1,096 | 32,630 | 61 | 40 | 61 | $0.16 | 47 | 0 | 10 | 10 | 88 | 3 | |
| Q05 | success | 824 | 31,016 | 30 | 19 | 30 | $0.19 | 31 | 0 | 7 | 6 | 97 | 4 | |
| Q06 | failure | 854 | 0 | 0 | 0 | 0 | $0.20 | 34 | 0 | 6 | 5 | 98 | 6 | CitationIntegrityError / b9793675134d |
| Q07 | success | 1,117 | 30,600 | 64 | 47 | 64 | $0.19 | 38 | 0 | 9 | 9 | 90 | 2 | |
| Q08 | failure | 3,958 | 0 | 0 | 0 | 0 | $0.18 | 186 | 1 | 47 | 47 | 98 | 5 | DeepResearchExecutionTimeout / fdb89121e2c4 |
| Q09 | success | 1,098 | 14,990 | 16 | 14 | 16 | $0.30 | 42 | 0 | 11 | 11 | 97 | 5 | |
| Q10 | success | 951 | 23,554 | 41 | 25 | 41 | $0.32 | 36 | 0 | 9 | 8 | 92 | 4 | |

"Citation markers" counts distinct `[n]` across the whole report, including the Sources list. "Body citations" counts distinct `[n]` used in the text. Cost is the DeepSeek balance delta at $0.01 resolution.

## Totals

- **Cost:** $2.08 for all ten questions; $1.89 for Q02 to Q10. Both sums reproduce exactly from the rows. The mean is $0.208 per question, about $0.21.
- **Latency:** 13,235 s in total; mean 1,324 s across all ten; mean 1,053 s across the eight successes.
- **Citations:** 375 markers, 262 body citations, 375 URL sources across the set.
- **Nemotron:** 545 calls; 1 LLM error (Q08's in-flight call, cancelled by the execution timeout); 129 calls over 60 s, all successful; 125 upstream 429s absorbed by the proxy as pauses.
- **DeepSeek:** 939 searches, 0 fetches, 39 researcher truncations at exactly 8,192 tokens.
- **Tavily:** 0 calls, 0 spend.

## Failures

- **Q06:** the citation integrity gate refused the report (`CitationIntegrityError`); nothing was published. See [docs/GATE.md](../docs/GATE.md).
- **Q08:** the server-side 3,600 s graph budget raised `DeepResearchExecutionTimeout`; the 5,400 s driver cancel did not fire. See [docs/PASS-RULES.md](../docs/PASS-RULES.md).

## Evidence in this folder

| File | Contents |
|---|---|
| `evidence/EVAL10-RESULT.md` | the evaluation's own result write-up |
| `evidence/metrics.csv` | per-question metrics (LF line endings; content identical to the CRLF original) |
| `evidence/Q06.job.json`, `evidence/Q06.report.json` | the Q06 job record and the empty report response |
| `evidence/server-log-extract.txt` | the CitationIntegrity and ExecutionTimeout server log lines |
| `evidence/Q02.report.md`, `evidence/Q07.report.md`, `evidence/Q10.report.md` | sample committed reports |
| `evidence/deepseek-search/` | the DeepSeek Search provider leg: result and balance records |
| `evidence/deepseek/` | the first DeepSeek researcher leg: diagnosis and balance records |
| `evidence/free-researcher/RESULT.md` | the free-route verdict |
| `evidence/recorded-run/` | the 2026-10-26 recorded run: summary, watchdog log, balances. See [docs/recorded-run.md](../docs/recorded-run.md) |
