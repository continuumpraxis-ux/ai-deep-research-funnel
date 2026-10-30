# DeepSeek leg — Q01 GAP failure diagnosis (2026-10-20)

Pass halted by request: Q01 failure, Q02 failure, Q03 cancelled (`POST …/cancel` → interrupted),
harness stopped before Q04. No reruns performed.

## 1. Researcher calls + errors (job b57f9bec-86e5-46cd-9eae-6c9db268d102 and the shared server run)
- **52 DeepSeek `/v1/chat/completions` requests — ALL `HTTP/1.1 400 Bad Request`. Zero succeeded.**
- Cascade in the server log: `Researcher worker failed (error_type=RuntimeError)` →
  `[LLM Error] deepseek-flash` (many) → `[Tool Error] run_research_batch` →
  `[Chain Error] researcher-agent` → `[Chain Error] deep_research_agent`.
- `researcher-agent` chain starts: 116; `writer-agent`: 4. No `model=deepseek-flash` agent/token
  lines (calls 400'd before producing a token record).
- **The 400 response BODY is not printed** (httpx logs only the status line; the openai client's
  BadRequestError body is not surfaced to the log). So the exact rejected field is not in the logs —
  see the code-level cause below. `tool_choice` / `reasoning_content` literals: 0 occurrences in log.

## 2. Root cause: deepseek-flash is a THINKING model; the researcher forces tool/structured calls
- The pre-flight smoke (plain chat, no tools, no `response_format`) returned **HTTP 200 + usage** — so
  the key, model id, and endpoint are fine. Only the researcher's request *shape* fails.
- The researcher issues **structured-output-via-tool** calls: `response_format=ToolStrategy(ResearchNotes)`
  (`custom_middleware.py:219`, also the finalization turn) plus the Tavily function-calling tools.
  deepseek-flash (DeepSeek-V4.1-Flash, a reasoning/thinking model) **rejects tool / forced-structured
  requests in thinking mode → 400** — exactly the class flagged before the run (tool_choice / function
  calling in thinking mode). Every researcher turn uses this shape, so all 52 calls 400'd.
- The middleware has a tools-disabled JSON *correction* path (`custom_middleware.py:148-154`), but it
  only triggers when a call *returns* unstructured text; a 400 raises before that, so the fallback
  never engages. Result: researcher workers raise RuntimeError, return no notes.

## 3. Where researcher writes vs where writer reads (both paths)
- **Researcher → `/shared/`.** The researcher worker returns a structured `ResearchNotes`;
  `run_research_batch` **persists it under `/shared/`** after the worker returns
  (`tools/research.py:87-89`). Control files in the same shared store: `/shared/plan.json`
  (planner), `/shared/source_routing.json`.
- **Writer ← `/shared/`.** The writer reads the persisted ResearchNotes/sources from `/shared/` and
  must commit the final report to **`/shared/output.md`** (`custom_middleware.py:62` `FINAL_REPORT_PATH`;
  the run "cannot finish until writer commits /shared/output.md", line 757).
- `/shared/` is the **host-side StateBackend** ("durable job text"), not an on-disk path, when no
  sandbox provider is configured (this config has none) — `sandbox/README.md:26,31`.
- **Because all 52 researcher calls 400'd, nothing was persisted to `/shared/`** → the writer found no
  ResearchNotes / verified sources at synthesis → **GAP report, 0 citations, status failure** (Q01
  latency 1,158 s was retries/backoff against the 400s).

## 4. Filesystem search for Q01 ResearchNotes
- `find /root/aiq-gate /tmp` for `*researchnote*`/`*research_note*`/`*notes*` modified after 06:00
  today → **none**. Expected: `/shared/` is the StateBackend (job state), and nothing was written
  because the researcher never produced notes. Job records (incl. the GAP report) live in
  `/root/aiq-gate/jobs.db`. No `/shared` or sandbox dirs on disk.

## 5. Balance
- Start $5.00 (`balance-start.json`) → now **$4.99** (`balance-mid.json`); ~$0.01 spent on the failed
  calls. is_available=True.

## 6. Harness bug found (fix before any rerun)
- The cancel-on-timeout I added used `DELETE /…/job/{id}` → **HTTP 405**. The correct cancel route is
  **`POST /v1/jobs/async/job/{id}/cancel`** (verified: returns `interrupted`, `task_cancelled:true`).
  `run_eval.sh` must use POST …/cancel, or timeouts won't actually free the slot.

## 7. Proposed fix (awaiting go — nothing rerun)
The researcher model must accept function-calling + structured output. deepseek-flash (thinking) does
not, in this request shape. In order:
1. **One controlled diagnostic probe** (~$0.001) to capture the exact 400 body: plain vs +tools vs
   `+response_format=ToolStrategy` against deepseek-flash — pins the precise rejected field.
2. **If deepseek-flash can disable thinking** (a DeepSeek request param / `extra_body`), set it in the
   `openai` llm block so tool/structured calls are accepted, then retry.
3. **Else point the researcher LLM at a non-reasoning DeepSeek model that supports function calling +
   structured output** (e.g. `deepseek-chat`), keeping orchestrator/planner/writer on Nemotron so the
   researcher stays the only changed variable. (deepseek-flash is thinking-only; a tool-using
   sub-agent needs a function-calling model.)
4. **Fix the harness cancel route** (POST …/cancel) and keep the 90-min deadline, before any rerun.

Server stopped after this diagnosis; no leftover jobs (Q03 cancelled). Awaiting the go.

## FIX APPLIED + Q01-alone smoke (2026-10-20) — researcher fix PROVEN; NEW bottleneck = NVIDIA 429
Applied the probe-confirmed fix: `reasoning_effort: none` on the `deepseek_flash_researcher_llm`
block only (disables thinking so the forced tool_choice is accepted); researcher stays deepseek-flash
(single-variable design intact); orchestrator/planner/writer unchanged on Nemotron. Also fixed the
harness cancel route (POST …/cancel, not DELETE). Server reloaded; config loaded cleanly.

**Probe (pre-fix, direct to DeepSeek):** researcher shape `tools + tool_choice:"required"` → **HTTP 400
"Thinking mode does not support this tool_choice"** (invalid_request_error); same with a named tool.
`reasoning_effort:"none"` (and `thinking:{type:disabled}`) → **200 with 0 reasoning tokens**.
`chat_template_kwargs:{thinking:false}` → still 400 (ignored). So the rejected field is `tool_choice`
in thinking mode; `reasoning_effort:none` is the fix.

**Q01-alone smoke result (job aa1d42b2…):**
- ✅ **Researcher FIXED:** DeepSeek calls **36 × HTTP 200, 0 × 400** ("Thinking mode…" = 0). The
  researcher ran, gathered **dozens of real Tavily sources**, and ResearchNotes were produced
  (11 persist log mentions). The `reasoning_effort:none` fix is proven.
- ❌ **Job still FAILED (status=failure, 1,828 s) — new cause: NVIDIA Nemotron-3-ultra 429s.** The
  orchestrator/planner/writer (NVIDIA API-Catalog) hit **46 × `429 Too Many Requests`** —
  ~18 `[LLM Error] nvidia/nemotron-3-ultra-550b-a55b` with NAT retries — exhausting retries →
  `Deep Research Subagent failed (RuntimeError)` **before the writer committed `/shared/output.md`** →
  report_chars 0, 0 citations. No NVIDIA 400/403/413 — purely rate-limiting.
- **Balance:** $4.99 → **$4.95** (~$0.04 DeepSeek; the 429s are NVIDIA-side, no DeepSeek cost).
  `balance-start.json` / `balance-end.json` saved.

**So:** the writer-produces-citations half did NOT complete — not because of the researcher (now
working) but because the **NVIDIA Nemotron key is being 429-rate-limited** on the non-researcher roles.
In the earlier baseline run the same Nemotron config completed the Q1 report, so this is a fresh NVIDIA quota/rate
condition (possibly the faster non-thinking researcher drives Nemotron calls faster into a per-minute
cap, or the API-Catalog trial quota is depleting). This is independent of the single-variable design.

**Decision needed (awaiting go — nothing rerun):**
1. The researcher fix is confirmed; to finish Q01 the **NVIDIA Nemotron 429s** must clear — options:
   wait for the NVIDIA quota/rate to reset and rerun; check the NVIDIA API-Catalog plan/limits for
   `nemotron-3-ultra-550b`; or add pacing/backoff so Nemotron calls stay under the per-minute cap.
2. Then re-run Q01-alone to confirm the writer produces a cited report, before the full ten.
Server stopped; no leftover jobs.

## Q01 re-run after the rate reset (2026-10-20) — waiting is NOT sufficient; 429 reproduces
Per the chosen option ("wait for the NVIDIA rate/quota to reset, then re-run Q01-alone"):

**The 429 is a short per-minute/burst cap, not a depleted quota.** A single probe returned 429; the
polling check (`wait-nvidia.sh`) returned **HTTP 200 on its very first attempt ~1-2 min later**
(`NVIDIA_CLEARED after 1 attempts`). So the limit resets in about a minute.

**Process-hygiene note (first re-run discarded).** The first re-run was served by an **orphaned**
`nat` server (PID 975) that my earlier stop had not cleared; my new server failed to bind
(`[Errno 98] address already in use`) and shut down, so that run's log was unattributable. Result
(failure, 0 citations, $0.17) is therefore **not counted as evidence**. All nat processes were then
killed by PID (`kill-all-nat.sh`) and a single server verified: exactly one PID on :8000, zero bind
errors — then Q01 was re-run cleanly.

**Clean Q01 re-run (job c9fa4b17…, 07:50:59→08:19:38, latency 1,719 s):**
- ✅ **Researcher still perfect:** DeepSeek **38 × HTTP 200, 0 × 400, 0 DeepSeek LLM errors.**
- ❌ **Same failure, reproduced:** NVIDIA **90 × 429**, **24 × `[LLM Error] nemotron-3-ultra`** →
  `Deep Research Subagent failed (RuntimeError)` with the **identical fingerprint
  `ref=sha256:d65561eca6f5`** as the earlier run. `output.md` mentions: **0** — the writer never
  committed the report → **report_chars 0, citations 0**.
- Balance $4.78 → **$4.71** ($0.07 this run).

**Conclusion:** the deepseek-flash researcher fix is confirmed twice over (38/38 and 36/36 calls at
200). The blocker is entirely the **NVIDIA API-Catalog per-minute rate cap on
`nemotron-3-ultra-550b`**, which the deep-research orchestration bursts past within minutes.
Because the cap resets in ~1 minute, **waiting before a run cannot fix it** — the run re-saturates
the cap. Two independent clean runs produced the same error fingerprint.

**Decision needed (awaiting go — the full ten NOT started):**
1. **Pace/backoff the Nemotron calls** so orchestrator/planner/writer stay under the per-minute cap
   (the previously-offered option 2), or
2. **Raise the NVIDIA limit** (API-Catalog plan/credits for `nemotron-3-ultra-550b`), or
3. **Reduce Nemotron call pressure** (e.g. a lighter model for orchestrator/source-router, keeping
   writer on Nemotron) — note this touches roles that were frozen, so it needs explicit approval.
Server stopped, all nat processes killed, no leftovers.
