# AI Deep Research Funnel with a Citation Integrity Gate

An AI deep research funnel built on the NVIDIA AI-Q blueprint pattern. DeepSeek flash models act as researcher agents, with DeepSeek Search as the source provider. A Nemotron planner, writer and orchestrator are reached through a pacing proxy. At the end of the funnel, a **citation integrity gate** refuses to publish any report whose citations do not match the run's source registry.

## Results (final evaluation, 2026-10-20)

- **8 of 10** research questions completed with committed, cited reports.
- **Q06** was stopped by the citation integrity gate. The report matched zero sources in the run registry, so the harness refused to publish it and nothing was persisted. The gate caught a bad report instead of shipping it. Full write-up: [docs/GATE.md](docs/GATE.md).
- **Q08** failed on execution timeout. The writer got stuck in a research loop and never committed a report. The server-side 3,600 s graph budget raised `DeepResearchExecutionTimeout`; the eval driver's 5,400 s cancel deadline did not fire.
- **$2.08** total DeepSeek spend across all ten questions: $1.89 for Q02 to Q10, plus $0.19 for Q01. The mean is about $0.21 per question. Tavily spend in the final configuration was zero.
- **Zero fabricated URLs** in a spot check of 10 cited sources across three questions (Q01, Q05, Q10). Of the 10 sources, 9 could be content-checked: 4 fully supported the claim and 5 had a precision defect. The remaining source was a dead link. Every headline number checked was found in a cited source.
- Every successful report carries traceable URL citations. The earlier baseline configuration (Nemotron researchers with Tavily search) produced a Q01 report whose sources were titles only, with no URLs, so they could not be traced.

Full table: [docs/EVAL-TABLE.md](docs/EVAL-TABLE.md). Per-question rows: [eval/results.md](eval/results.md).

A note on the spot-check counts: earlier drafts of this evaluation counted only the 9 sources whose content could be checked, while the summary table counted all 10 spot-checked sources, including the dead link. This package reports both denominators explicitly: support and defect rates are shares of the 9 checked sources, and the dead link is 1 of the 10 spot-checked sources.

## Architecture

```
research question
      |
      v
Nemotron planner / orchestrator ----+
      |                             |
      v                             |   all Nemotron calls go through the
DeepSeek flash researchers          +-- pacing proxy (token bucket per model,
      |    ^                        |   429 pause and requeue) to the hosted
      v    |                        |   NVIDIA endpoint
DeepSeek Search (tool results)      |
      |                             |
      +--> run source registry      |
      |    (URLs and citation keys  |
      |     captured from tool      |
      |     results)                |
      v                             |
researcher notes --> Nemotron writer
                          |
                          v
              citation integrity gate  <-- run source registry
               |                    |
     citations match         no valid citations
               |                    |
   committed, cited report   refused: CitationIntegrityError,
                             nothing persisted
```

Mermaid diagram, model IDs and component walk-through: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Problems solved on evidence

- **The free route is not viable.** The OpenRouter free-tier variant completed 0 of 10 questions under 429 saturation (16,414 requests). It was measured at $0, so the ceiling is empirical, not assumed.
- **Rate cap.** Two earlier unpaced Q01 attempts failed with 46 and 90 HTTP 429 responses from NVIDIA's per-minute burst cap. The pacing proxy keeps a token bucket for each model and requeues 429s, so rejections become latency. In the final run, 125 upstream 429s were absorbed by the proxy and none reached the funnel as a failure.
- **The two-day blocker.** The old nim client's 60-second read limit collided with the proxy's 60-second 429 pauses and with long non-streamed generations. It was root-caused by elimination. A 170k-character call returned in 5.3 seconds, which ruled out payload size, and a larger 175,916-character call succeeded on retry. The fix was swapping the writer client and setting `request_timeout` to 600. Q01 then passed with 41 body citations at $0.19.
- **Verified negatives.** These were ruled out on vendor evidence, not preference:
  - NemoClaw: NVIDIA's own matrix lists DGX OS hardware only, with no Windows or WSL2 path.
  - OpenShell and Milvus: excluded in this build.
  - Several container candidates: their registry manifests are amd64-only. The manifest takes precedence over NGC metadata, per the download compatibility gate.

Details: [docs/SOLVED-PROBLEMS.md](docs/SOLVED-PROBLEMS.md)

## Citation-precision leg (staged)

Citation precision is the weak metric. To work on it, two NIM services are staged on the build machine:
- **Embedder:** `nvidia/Nemotron-3.5-Embed-1B-BF16` (BF16 names the weights artifact; the engine serves at fp16).
- **Reranker:** `nvidia/llama-nemotron-rerank-vl-1b-v2` (FP16, GB10-optimized NIM).

Both answered locally before the recorded run. The evaluation results above come from before this leg existed and do not include it. No precision improvement is claimed.

## Known limits

Short version:
- Citation precision is not clean yet. Fabrication is zero.
- The 8,192-token researcher note cap can starve a question's source pool. This happened on Q02.
- The gate prevents bad output, but not the spend on a run that fails it.
- The only loop guard on the writer is the server-side execution budget.
- The architecture is hybrid by necessity, because of the Windows on ARM platform.

Full list: [docs/KNOWN-LIMITS.md](docs/KNOWN-LIMITS.md). Pass rules and the two timeout layers: [docs/PASS-RULES.md](docs/PASS-RULES.md).

## Platform

The build runs on a Windows on ARM laptop (Lenovo Yoga, NVIDIA RTX Spark). It uses hosted APIs (DeepSeek, NVIDIA) together with NIM containers staged on the laptop. Components that needed DGX OS or x86 Linux were excluded on evidence.

## Recorded run

On 2026-10-26, Q01 was run end to end on the build machine with the evaluation configuration, the pacing proxy in the path, and a spend watchdog armed. It succeeded in 1,011 s and committed a 41,579-character report with 59 distinct citation markers. The full account, including what that run's own spend figure does and does not mean: [docs/recorded-run.md](docs/recorded-run.md).

## Setup and usage

This section carries only what the pulled scripts and configs show. A from-scratch install guide for a fresh machine is not part of this package.

**What is in this repository.** `aiq/` holds the files changed or added in the NVIDIA AI-Q deep researcher checkout (served configs, the example environment file, the DeepSeek Search plugin, the citation verification module, the deep researcher agent, its resource limits, and the job runner). It is not the full upstream tree. `eval/` holds the evaluation harness, the pacing proxy, and the evidence.

| Component | Location |
|---|---|
| Pacing proxy | `eval/nv-pacing-proxy.py` |
| DeepSeek Search plugin | `aiq/sources/deepseek_web_search/` |
| Citation gate | `aiq/src/deep_researcher_agent/common/citation_verification.py`, invoked from `aiq/src/deep_researcher_agent/agents/deep_researcher/agent.py` |
| Execution limits | `aiq/src/deep_researcher_agent/agents/deep_researcher/resource_limits.py` |
| Job runner (server side submit, poll, cancel) | `aiq/frontends/deep_researcher_api/src/deep_researcher_api/jobs/runner.py` |
| Eval harness | `eval/` (`run_eval.sh`, `run-eval10.sh`, `metrics-eval10.py`, `score.py`, `SCORING-SHEET.md`, `spend-watchdog.py`, `spend-watchdog-set.py`, `questions.json`) |
| Served configs | `aiq/configs/` |
| Example environment | `aiq/deploy/.env.example` |

**Requirements visible in the scripts.** bash, curl and python3 for the drivers; python3 with aiohttp for the pacing proxy.

**Serve.** The serve scripts stage a config variant into the served source tree and run the NeMo Agent Toolkit server from the runtime virtualenv, in this form (from `eval/serve-variant.sh`):

```
nat serve --config_file configs/<config>.yml --host 0.0.0.0 --port <port>
```

**Job endpoints used by the eval drivers.**

| Method | Path |
|---|---|
| POST | `/v1/jobs/async/submit` |
| GET | `/v1/jobs/async/job/<id>` |
| POST | `/v1/jobs/async/job/<id>/cancel` |

**Pacing proxy environment variables and defaults** (`eval/nv-pacing-proxy.py`). Nemotron roles in the served config route through the proxy at `http://localhost:18123/v1`.

| Variable | Default | Meaning |
|---|---|---|
| `NV_PROXY_RATE_PER_MIN` | 24 | per-model sustained rate |
| `NV_PROXY_GLOBAL_PER_MIN` | 48 | global sustained rate |
| `NV_PROXY_PAUSE_S` | 60 | bucket pause after an upstream 429 |
| `NV_PROXY_MAX_ATTEMPTS` | 12 | upstream attempts per request |
| `NV_PROXY_PORT` | 18123 | listen port |

**Served configuration.** The evaluation config is `aiq/configs/config_web_deepseek_search.yml`. As served for the evaluation, its SHA-256 was `ede84b573fae70839ae3e3ff69d732992e607f814e2189bfe123e4f502480e8d`. The copy in this repository differs only in its header comments, which were edited to remove internal labels, so its hash does not match that value. The Nemotron role blocks use the OpenAI-compatible client with `request_timeout: 600`.

**Credentials.** No key values are in this repository. Config `api_key` fields carry environment references. The serve scripts read keys at runtime with `op read` into the process environment only; every vault reference is the placeholder `op://TEAM VAULT/<item-name>/credential`, to be replaced with your own item. The DeepSeek Search plugin reads `DEEPSEEK_API_KEY` from the process environment.

**Paths.** Scripts carry the absolute paths of the build machine, with the user segment replaced by `<user>`. Set them for your machine before running.

## License

MIT. See [LICENSE](LICENSE). Files that carry their own SPDX license headers keep them: the NVIDIA AI-Q files under `aiq/` are marked Apache-2.0, and the DeepSeek Search plugin is marked Apache-2.0.
