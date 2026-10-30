#!/usr/bin/env python3
"""Long-output probe — no DeepSeek spend, no Tavily.

Same ~170k prompt material as probe_170k (orchestrator system prompt, Q01, the five stored decdbac1
ResearchNotes) sent to nvidia/nemotron-3-ultra-550b-a55b through the pacing proxy, with NO tools:
the model is told to write the full final report. max_tokens 16384, non-streaming, client read
timeout 600 s. Without a tools array, assistant tool_call / tool messages are not a valid chat shape,
so the notes go in a single user turn after the Q01 request. Logs status, elapsed time, completion tokens.
"""
import json, os, pathlib, sys, time
import httpx

PROXY = "http://127.0.0.1:18123/v1/chat/completions"
MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
ORCH_PROMPT = "/root/aiq-gate/src/deep_researcher_agent/agents/deep_researcher/prompts/orchestrator.j2"
Q01 = "What are the credible, evidence-backed revenue opportunities for solo AI-agent operators in the next 12 months?"
OUT = pathlib.Path("/mnt/c/Users/<user>/stacks/ai-ops-blueprint/eval/results/deepseek-search/probe")
TARGET = 170_000

INSTRUCTION = ("All research is complete and the writer subagent is unavailable. Write the FULL final report "
               "yourself now, in Markdown: title, executive summary, a detailed section per opportunity with "
               "evidence, risks and counter-evidence, a comparison table, and a numbered Sources list. Cite "
               "sources inline as [n] using the URLs found in the research notes below. Be thorough and complete.")


def main():
    key = os.environ.get("NVIDIA_API_KEY", "")
    if not key:
        sys.exit("NO_NVIDIA_KEY")
    # reuse the stored-notes loader from the first probe without executing its main()
    src = pathlib.Path(__file__).with_name("probe-nemotron.py").read_text(encoding="utf-8")
    ns = {"__name__": "pn"}
    exec(compile(src.replace("\nmain()\n", "\n"), "probe-nemotron.py", "exec"), ns)
    notes = ns["load_notes"]()
    system_text = pathlib.Path(ORCH_PROMPT).read_text(encoding="utf-8")

    head = f"{Q01}\n\n{INSTRUCTION}\n\n"
    budget = TARGET - len(system_text) - len(head)
    parts, used = [], 0
    for i, n in enumerate(notes):
        room = budget - used - 40
        if room <= 0:
            break
        chunk = n if len(n) <= room else n[:room]
        parts.append(f"=== Research note {i + 1} ===\n{chunk}")
        used += len(parts[-1]) + 2
    user = head + "\n\n".join(parts)
    msgs = [{"role": "system", "content": system_text}, {"role": "user", "content": user}]
    content_chars = len(system_text) + len(user)

    body = {"model": MODEL, "messages": msgs, "temperature": 0.2, "top_p": 0.7, "max_tokens": 16384,
            "stream": False, "chat_template_kwargs": {"enable_thinking": False}}
    payload = json.dumps(body, ensure_ascii=False).encode()
    print(f"=== probe_longout: content_chars={content_chars:,} request_json_bytes={len(payload):,} "
          f"messages={len(msgs)} tools=none ===", flush=True)
    t0 = time.monotonic()
    status, text, err = None, "", ""
    try:
        r = httpx.post(PROXY, content=payload, headers={"Authorization": f"Bearer {key}",
                       "Content-Type": "application/json"},
                       timeout=httpx.Timeout(connect=30, read=600, write=120, pool=30))
        status, text = r.status_code, r.text
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    elapsed = time.monotonic() - t0
    rec = {"label": "probe_longout", "content_chars": content_chars, "request_json_bytes": len(payload),
           "status": status, "elapsed_s": round(elapsed, 1), "client_error": err}
    try:
        d = json.loads(text) if text else {}
        rec["usage"] = d.get("usage")
        ch = (d.get("choices") or [{}])[0]
        rec["finish_reason"] = ch.get("finish_reason")
        content = (ch.get("message") or {}).get("content") or ""
        rec["output_chars"] = len(content)
        rec["content_head"] = content[:300]
        if status and status >= 400:
            rec["error_body"] = text[:4000]
        (OUT / "probe_longout.report.md").write_text(content, encoding="utf-8")
    except Exception:
        rec["raw_body_preview"] = text[:4000]
    (OUT / "probe_longout.response.txt").write_text(text or err, encoding="utf-8")
    (OUT / "probe_longout.meta.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(rec, indent=2, ensure_ascii=False), flush=True)
    ct = (rec.get("usage") or {}).get("completion_tokens")
    print("\n########## READOUT ##########")
    if status == 200:
        print(f"HTTP 200 in {rec['elapsed_s']} s, completion_tokens={ct}, finish={rec.get('finish_reason')}")
        print("OVER 60 s -> mechanism confirmed" if elapsed > 60 else "UNDER 60 s -> mechanism NOT confirmed")
    else:
        print(f"status={status} err={err} elapsed={rec['elapsed_s']} s")


main()
