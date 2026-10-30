# Search optimization — RESULT (2026-10-20)

Two new config variants built. **No existing config, the pacing proxy, or the plan document was
modified.** The primary server on :8000 and the pacing proxy on :18123 were left running throughout;
my variants ran on :8002 (load smoke) and :8001 (proof) and are now stopped.

---

## CHANGE 1 — Capped Tavily variant → `aiq/configs/config_web_tavily_capped.yml`

### Current served values (recorded, resolved against the real schema)
| tool | max_results | advanced_search → search_depth | include_answer | max_content_length | max_retries |
|---|---|---|---|---|---|
| `web_search_tool` | **5** | False → **basic** | `'advanced'` | 1000 | 3 |
| `advanced_web_search_tool` | **2** | True → **advanced** | `'advanced'` | None (no truncation) | 3 |

### Capped values (both tools)
`max_results = 3` · `advanced_search = false → search_depth = basic` · `include_answer = ''` ·
`max_content_length = 1000`

### Knob mapping — two requested knobs DO NOT EXIST (not invented)
`TavilyWebSearchToolConfig` fields are exactly:
`advanced_search, api_base_url, api_key, include_answer, max_content_length, max_results, max_retries`.
- **`max_results`** — exists. Capped to 3.
- **`search_depth`** — **NO SUCH CONFIG KEY** (`'search_depth' in schema: False`). The plugin derives it:
  `search_depth = "advanced" if advanced_search else "basic"`, so basic depth is set via
  `advanced_search: false`.
- **`include_answer`** — exists, but typed **`str`** (default `"advanced"`); there is **no boolean off**.
  `''` is the only schema-permitted falsy value. **Whether Tavily honours `''` as "off" is UNVERIFIED —
  confirming it would need a Tavily call, which was forbidden this pass.**
- **`chunks_per_source`** — **NO SUCH CONFIG KEY** (`False`) and never passed to the provider.
  `max_content_length` is the nearest cost lever and is pinned at 1000.

### Smoke (config-level only)
Server loaded the capped config on :8002 → `Application startup complete`, `/health` healthy.
Run with **TAVILY_API_KEY deliberately absent**, so both tools registered fail-closed
(`Tool web_search_tool is unavailable: missing TAVILY_API_KEY`). **Tavily calls this pass: ZERO** — by
construction, not just by intent. Pool remains frozen at 773/1,000 (untouched).

### Side effect worth noting
Capping `advanced_web_search_tool` to basic depth collapses its distinction from the shallow tool, and
raises its result count 2 → 3. Net Tavily credit cost still falls, because basic depth costs less per
call than advanced; but the deep agent (which uses the advanced tool) now gets 3 basic results instead
of 2 advanced ones.

---

## CHANGE 2 — DeepSeek Search provider → `aiq/sources/deepseek_web_search/` + `aiq/configs/config_web_deepseek_search.yml`

### Feasibility verdict: **MATCHED — no harness fork required**
AI-Q exposes providers through `[project.entry-points."nat.plugins"]`, and a search tool is just
`async (question: str) -> str` yielded via `FunctionInfo.from_fn`. That is the same path all eight
shipped providers use (tavily, exa, nimble, duckduckgo, you_com, …). I added a **new package**, changed
**no core code**, and swapped only `_type` while keeping the tool **names** — so `data_sources`, every
agent's `exclude_tools`, the planner, the writer and the eval harness run unchanged.

### Implementation
- `deepseek_web_search`: `POST /v1/tools/search`, `count=3`, query truncated to **128 chars** (DeepSeek's
  hard limit — Tavily's plugin allows 400, so this had to be handled or every call would 400).
  Emits the same `<Document href=…>` envelope, with `provenance="deepseek-search"`, `rerank_score`
  (0–3) and `authority` (0–4) on every source.
- `deepseek_web_fetch`: `POST /v1/tools/fetch` → page as Markdown.
- Content precedence `summary → content → snippet`: `need_content` defaults false (DeepSeek returns an
  empty `content` then), and `summary` is the 600–800-char model-oriented field — cheaper payload.
- Billing-accurate usage log (`usage.jsonl`): a record is marked `billed` only on HTTP 200 **with** a
  result, matching DeepSeek's rule that empty/failed/timeout requests are not billed.
- Key from TEAM VAULT (item reference redacted) into the **process env only**; never written to a
  file or a log. Fetch is registered but deliberately **not** added to the agent tool set, so the
  agent surface stays provider-only.

### Exact-shape smoke — **PASS**
- **1 Search**: 3,703 chars, 3 results, correct envelope, e.g. `rerank_score="1.8426"` `authority="3"`.
- **1 Fetch**: first attempt **HTTP 500** on the top result (a Chinese crypto-news aggregator) —
  unbilled. One labelled diagnostic fetch against a stable page returned **8,938 chars of Markdown**,
  proving the Fetch path works and the 500 was page-specific.

---

## PROOF RUN — ONE Q01 on the DeepSeek-search variant (job `decdbac1`)

| metric | value |
|---|---|
| status | **failure** (named below) — writer did **not** commit |
| latency | 1,571 s |
| report_chars / citations | **0 / 0** |
| searches consumed | **52 billed** (all HTTP 200 with results) |
| fetches consumed | **1 billed**, 3 failed/unbilled |
| distinct source URLs returned | **144** |
| search+fetch cost (usage log) | 53 billable × $0.00075 = **$0.03975** |
| DeepSeek balance | **$4.71 → $4.60 = $0.11 total** (≈$0.04 search/fetch + ≈$0.07 deepseek-flash inference) |
| budget | **$0.11 of the $1.00 cap** |
| Tavily calls | **ZERO** |

### Named failure: the final large-context Nemotron synthesis call
- **The pacing proxy worked.** `429 occurrences: 0` this run, against **46** and **90** in the two
  earlier unpaced Q01 attempts. Rate-limiting is no longer the blocker.
- **DeepSeek researcher: clean.** 29 × HTTP 200, **0** DeepSeek LLM errors, 0 "Thinking mode" 400s.
- **All 18 `[LLM Error]` lines were `nvidia/nemotron-3-ultra-550b-a55b`.** The first 17 follow a
  recoverable pattern: `[AGENT] nemotron` → `Agent input: chars=19678` → error → **immediate retry with
  the identical input succeeds**.
- **The fatal one is different in exactly one way: its input was `chars=173649`** (vs ~19.7k for every
  recoverable error). That call errored and did not recover →
  `Deep Research Subagent failed (error_type=RuntimeError detail_chars=27 ref=sha256:d65561eca6f5)`.
- **Inference, stated as such:** the ~174k-char input points at a **context/payload ceiling at the
  synthesis step**, inflated by 144 accumulated sources. The log does **not** print the upstream error
  body, so this is read from input size + the retry pattern, not a quoted error. The only 20–34 char
  RuntimeError in the deep-researcher tree is `RuntimeError("researcher worker failed")`
  (`tools/research.py:145`), which is consistent with `detail_chars=27` but not proven.
- The failure fingerprint `d65561eca6f5` is **identical across all three Q01 attempts** — the
  429-saturated ones and this 429-free one. That is the strongest single finding here: **the Q01
  blocker was never purely the rate cap.**

### Citation quality vs the earlier Tavily-based Q01 attempts
| run | provider | sources found | report committed | citations |
|---|---|---|---|---|
| Baseline (Nemotron researchers) | Tavily | — | **YES** — `runs/Q1-report.md`, 25,839 chars | **8** distinct `[n]` markers |
| Q01 attempt, deepseek-flash researchers | Tavily | ~55 | no | 0 |
| Q01 attempt, deepseek-flash researchers (clean, paced) | Tavily | — | no | 0 |
| **Q01 this run** | **DeepSeek Search** | **144** | no | 0 |

- **On committed citations no comparison is possible**: every deepseek-researcher attempt is 0, with or
  without DeepSeek Search. Only the original Nemotron-researcher + Tavily run has ever committed a
  cited report (8 citations, 25.8K chars).
- **On source supply, DeepSeek Search is strong**: 144 distinct URLs from 52 searches, with rerank and
  authority scores Tavily does not provide — useful for a citation-quality rubric.
- **Language/quality concern:** for an English query, DeepSeek's top-ranked result was a
  **Chinese-language crypto-news aggregator** (`rerank_score 1.84`, `authority 3`). The provider
  surfaces Chinese-language sources prominently, which is a real risk for an English cited report and
  should weigh in the next provider bake-off.
- **Counter-effect to flag:** more sources made the synthesis input bigger (174k chars), so DeepSeek
  Search plausibly *contributed* to the context overflow that killed this run. Capping `count` below 3,
  or capping accumulated sources, is the lever to test next.

## End state
Variants on :8001 and :8002 stopped; **primary server on :8000 and pacing proxy on :18123 left running and
unmodified**; Tavily pool untouched; $0.89 of the $1.00 DeepSeek budget unspent.

### One harness change, disclosed
`eval/run_eval.sh` label whitelist gained `deepseek-search` (a one-line allow-list addition) so results
land in their own directory instead of overwriting the existing `deepseek` evidence. No other harness
behaviour was touched, and the search-tool shape was not hacked.
