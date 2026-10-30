#!/usr/bin/env python3
"""Phase 1 premise probe — no DeepSeek spend, no Tavily.

One ~170k-char call and one ~20k-char control call to nvidia/nemotron-3-ultra-550b-a55b through the
local pacing proxy (127.0.0.1:18123), shaped like job decdbac1's fatal orchestrator turn: the
orchestrator system prompt, the Q01 user request, then assistant `task` tool calls each followed by a
tool result carrying one stored ResearchNotes payload from jobs.db, then the writer's return.
Same request parameters as nemotron_ultra_llm. The client read timeout is 600 s, deliberately longer
than ChatNVIDIA's 60 s default, so the probe observes NVIDIA's real behaviour.
Logs status, elapsed time and the response body. The API key is never written anywhere.
"""
import json, os, pathlib, sqlite3, sys, time
import httpx

JOB = "decdbac1-ff6f-4c55-9063-b8a0acff1ceb"
PROXY = "http://127.0.0.1:18123/v1/chat/completions"
MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
NOTE_EVENT_IDS = [9780, 9808, 9810, 9812, 9815]   # researcher workflow.end payloads containing narrative_notes
ORCH_PROMPT = "/root/aiq-gate/src/deep_researcher_agent/agents/deep_researcher/prompts/orchestrator.j2"
Q01 = "What are the credible, evidence-backed revenue opportunities for solo AI-agent operators in the next 12 months?"
OUT = pathlib.Path("/mnt/c/Users/<user>/stacks/ai-ops-blueprint/eval/results/deepseek-search/probe")
OUT.mkdir(parents=True, exist_ok=True)

TOOLS = [
    {"type": "function", "function": {"name": "task", "description": "Delegate work to a subagent.",
     "parameters": {"type": "object", "properties": {
         "subagent_type": {"type": "string"}, "description": {"type": "string"}},
         "required": ["subagent_type", "description"]}}},
    {"type": "function", "function": {"name": "write_todos", "description": "Replace the todo list.",
     "parameters": {"type": "object", "properties": {"todos": {"type": "array", "items": {"type": "string"}}},
                    "required": ["todos"]}}},
]


def note_text(event_data: str) -> str:
    """Return the stored ResearchNotes payload (the longest string/dict containing narrative_notes)."""
    try:
        doc = json.loads(event_data)
    except Exception:
        return event_data
    best = ""

    def walk(x):
        nonlocal best
        if isinstance(x, str):
            if "narrative_notes" in x and len(x) > len(best):
                best = x
        elif isinstance(x, dict):
            if "narrative_notes" in x:
                s = json.dumps(x, ensure_ascii=False)
                if len(s) > len(best):
                    best = s
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(doc)
    return best or event_data


def load_notes():
    con = sqlite3.connect("file:/root/aiq-gate/jobs.db?mode=ro", uri=True)
    notes = []
    for eid in NOTE_EVENT_IDS:
        row = con.execute("select event_data from job_events where id=? and job_id=?", (eid, JOB)).fetchone()
        if row and row[0]:
            notes.append(note_text(row[0]))
    return notes


def build(notes, target_chars, system_text):
    """Orchestrator-shaped conversation, trimmed so total content chars land at target_chars."""
    msgs = [{"role": "system", "content": system_text}, {"role": "user", "content": Q01}]
    used = len(system_text) + len(Q01)
    writer_return = ("writer-agent did not commit /shared/output.md. The final report could not be produced "
                     "within the model-call budget; the source notes are available under /shared/. ") * 3
    reserve = len(writer_return) + 200
    for i, note in enumerate(notes):
        room = target_chars - used - reserve
        if room <= 0:
            break
        chunk = note if len(note) <= room else note[:room]
        args = json.dumps({"subagent_type": "researcher-agent", "description": f"Research batch {i + 1}"})
        msgs.append({"role": "assistant", "content": "",
                     "tool_calls": [{"id": f"call_{i}", "type": "function",
                                     "function": {"name": "task", "arguments": args}}]})
        msgs.append({"role": "tool", "tool_call_id": f"call_{i}", "content": chunk})
        used += len(chunk) + len(args)
    args = json.dumps({"subagent_type": "writer-agent", "description": "Write the final report"})
    msgs.append({"role": "assistant", "content": "",
                 "tool_calls": [{"id": "call_w", "type": "function", "function": {"name": "task", "arguments": args}}]})
    msgs.append({"role": "tool", "tool_call_id": "call_w", "content": writer_return})
    used += len(writer_return) + len(args)
    return msgs, used


def call(label, msgs, content_chars, key):
    body = {"model": MODEL, "messages": msgs, "tools": TOOLS, "tool_choice": "auto",
            "temperature": 0.2, "top_p": 0.7, "max_tokens": 16384, "stream": False,
            "chat_template_kwargs": {"enable_thinking": False}}
    payload = json.dumps(body, ensure_ascii=False)
    print(f"\n=== {label}: content_chars={content_chars:,}  request_json_bytes={len(payload.encode()):,}  "
          f"messages={len(msgs)} ===", flush=True)
    t0 = time.monotonic()
    status, text, err = None, "", ""
    try:
        r = httpx.post(PROXY, content=payload.encode(), headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=httpx.Timeout(connect=30, read=600, write=120, pool=30))
        status, text = r.status_code, r.text
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    elapsed = time.monotonic() - t0
    rec = {"label": label, "content_chars": content_chars, "request_json_bytes": len(payload.encode()),
           "status": status, "elapsed_s": round(elapsed, 1), "client_error": err}
    try:
        d = json.loads(text) if text else {}
        rec["usage"] = d.get("usage")
        ch = (d.get("choices") or [{}])[0]
        rec["finish_reason"] = ch.get("finish_reason")
        m = ch.get("message") or {}
        rec["content_preview"] = (m.get("content") or "")[:400]
        rec["tool_calls_preview"] = json.dumps(m.get("tool_calls"))[:400] if m.get("tool_calls") else None
        if d.get("error") or (status and status >= 400):
            rec["error_body"] = text[:4000]
    except Exception:
        rec["raw_body_preview"] = text[:4000]
    (OUT / f"{label}.response.txt").write_text(text or err, encoding="utf-8")
    (OUT / f"{label}.meta.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(rec, indent=2, ensure_ascii=False), flush=True)
    return rec


def main():
    key = os.environ.get("NVIDIA_API_KEY", "")
    if not key:
        sys.exit("NO_NVIDIA_KEY")
    notes = load_notes()
    print("stored ResearchNotes payloads loaded:", [len(n) for n in notes], "total", sum(map(len, notes)))
    system_text = pathlib.Path(ORCH_PROMPT).read_text(encoding="utf-8")
    print("orchestrator system prompt chars:", len(system_text))

    big_msgs, big_chars = build(notes, 170_000, system_text)
    ctl_msgs, ctl_chars = build(notes, 20_000, system_text)

    big = call("probe_170k", big_msgs, big_chars, key)
    ctl = call("control_20k", ctl_msgs, ctl_chars, key)

    def verdict(r):
        if r["client_error"]:
            return f"CLIENT ERROR after {r['elapsed_s']} s ({r['client_error']})"
        if r["status"] == 200:
            return f"SUCCEEDS — HTTP 200 in {r['elapsed_s']} s"
        if r["status"] in (400, 413, 422):
            return f"REJECTED — HTTP {r['status']} in {r['elapsed_s']} s"
        if r["status"] in (408, 504, 524):
            return f"TIMES OUT (server/gateway) — HTTP {r['status']} in {r['elapsed_s']} s"
        return f"HTTP {r['status']} in {r['elapsed_s']} s"

    print("\n########## READOUT ##########")
    print("probe_170k :", verdict(big))
    print("control_20k:", verdict(ctl))
    print("ChatNVIDIA (nim client) read timeout: 60 s (sock_read=timeout, default 60)")


main()
