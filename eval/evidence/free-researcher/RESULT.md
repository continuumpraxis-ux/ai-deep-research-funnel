# Free-researcher run — RESULT (2026-10-19 → 2026-10-20)

**Researcher for this pass = Nemotron 3 Super (free, via OpenRouter)**, substituting the deferred
DeepSeek-flash leg (DeepSeek variant stays parked). Run spanned ~20:48 Oct 19 → 03:34 Oct 20.

## Outcome: the free route is NOT viable for AI-Q deep research — 0/10 completed
| metric | value |
|---|---|
| questions submitted | 10 (Q01–Q10) |
| terminal success | **0 / 10** |
| per-question latency | ~2407–2411 s — i.e. the harness's **2400 s poll ceiling**, not true completion |
| reports captured | 0 (all jobs still `running` when polling gave up) |
| citations captured | 0 |
| est. cost | **$0** (free tier) |

See `SCORING-SHEET.md` and `_summary.csv`.

## Why (evidenced from the server log, 36,993 lines)
- **The researcher swap worked:** `model=nvidia/nemotron-3-super-120b-a12b:free` logged **61×**
  (orchestrator/planner/writer stayed on `nemotron-3-ultra-550b` 134×). The free model answered the
  smoke call (HTTP 200 + usage) after the account's model-training policy was enabled.
- **Free-tier rate limiting throttled it into the ground:** 16,414 OpenRouter request lines, saturated
  with **`HTTP 429 Too Many Requests`** and openai-client exponential-backoff retries. The deep-research
  loop makes many researcher calls per job (researcher-agent chains: 338), so the free quota was
  exhausted continuously.
- **No convergence in time:** the writer stage was reached only 8×; **zero** jobs reached a terminal
  `success/failure`. Q01 reached the writer with 55 sources found but `cited: 0` and an empty report.

## Harness note (for a future paced re-run)
The harness times out polling at 2400 s but **does not cancel** the non-terminal job before moving to
the next. So all 10 jobs kept running server-side concurrently overnight, competing for the same free
quota and compounding the 429s. A future run against a rate-limited route should **cancel on timeout**
(DELETE the job) so only one job is active at a time, and/or raise the per-question deadline well above
40 min. The config already uses bounded `num_retries: 3`; the 429 storm came from 10 concurrent jobs,
not from a retry-storm within one call.

## Bottom line / recommendation
- **Free OpenRouter route: functional but unusable for deep research** — the free quota cannot sustain
  a multi-loop deep-research job to completion. It would only suit a single, light, shallow-research
  query at a time, not the 10-question deep pass.
- **The default Nemotron researcher route is the viable one** (it produced the full baseline Q1 report,
  ~25.8K chars, cited). For a real researcher-swap comparison, use a **paid** route: either the parked
  **DeepSeek-flash** leg (pending top-up) or the **paid** OpenRouter model
  `nvidia/nemotron-3-super-120b-a12b` (no `:free`) — the OpenRouter account has credits. Both are
  decisions for the project owner; neither was run here.
- Server stopped; stuck jobs killed; no leftovers. The DeepSeek variant remains parked and untouched.
