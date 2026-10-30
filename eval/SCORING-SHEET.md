# Eval Scoring Sheet - DeepSeek-flash researchers vs Nemotron default

Latency and report/citation counts are auto-filled from the runs. **Citation accuracy**
(fraction of citations that actually support the claim) is scored in the independent
**Perplexity pass** using the per-question citation lists at the bottom — fill the
`citation_accuracy` column there, then summarize here.

## Rate table ($/1M tokens)
- deepseek-flash: $0.15 in / $0.60 out (verified, off-peak cache-miss; peak $0.30/$1.20)
- nvidia/nemotron-3-ultra-550b-a55b: **TODO confirm NVIDIA rate** (tokens measured; $ pending)

## Results

### baseline

_No results yet (run `run_eval.sh baseline` after the gate clears)._

### deepseek

_No results yet (run `run_eval.sh deepseek` after the gate clears)._

### free-researcher

- questions run: 10
- success: 0/10
- latency (s): median 2410 / min 2407 / max 2411
- citation markers detected (sum): 0

| qid | status | latency_s | report_chars | cites | in_tok | out_tok | est_$ |
|---|---|---|---|---|---|---|---|
| Q01 | running | 2410 | 0 | 0 |  |  |  |
| Q02 | running | 2407 | 0 | 0 |  |  |  |
| Q03 | running | 2410 | 0 | 0 |  |  |  |
| Q04 | running | 2410 | 0 | 0 |  |  |  |
| Q05 | running | 2410 | 0 | 0 |  |  |  |
| Q06 | running | 2407 | 0 | 0 |  |  |  |
| Q07 | running | 2410 | 0 | 0 |  |  |  |
| Q08 | running | 2411 | 0 | 0 |  |  |  |
| Q09 | running | 2408 | 0 | 0 |  |  |  |
| Q10 | running | 2407 | 0 | 0 |  |  |  |

## Citation validity worklist (Perplexity pass)

For each URL: mark SUPPORTS / PARTIAL / DOES-NOT-SUPPORT the cited claim.

### free-researcher
- **Q01** (0 urls)
  - (no urls detected)
- **Q02** (0 urls)
  - (no urls detected)
- **Q03** (0 urls)
  - (no urls detected)
- **Q04** (0 urls)
  - (no urls detected)
- **Q05** (0 urls)
  - (no urls detected)
- **Q06** (0 urls)
  - (no urls detected)
- **Q07** (0 urls)
  - (no urls detected)
- **Q08** (0 urls)
  - (no urls detected)
- **Q09** (0 urls)
  - (no urls detected)
- **Q10** (0 urls)
  - (no urls detected)
