#!/usr/bin/env python3
"""Per-question metrics for the eval10 set (+ the Q01 row from the swap run).

Slices server logs, the pacing-proxy log and usage.jsonl by each question's [start, end] window
(questions ran strictly one at a time). Writes metrics.csv and prints a table.
"""
import csv, json, re
from datetime import datetime, timedelta
from pathlib import Path

EV = Path("/mnt/c/Users/<user>/stacks/ai-ops-blueprint/eval")
if not EV.exists():
    EV = Path("C:/Users/<user>/stacks/ai-ops-blueprint/eval")
OUT = EV / "results/deepseek-search-eval10"
PROXY_LOG = EV.parents[2] / "diag-stage" / "nv-proxy.log"   # .../<user>/diag-stage/nv-proxy.log
USAGE = EV / "results/deepseek-search/usage.jsonl"
ANSI = re.compile(r"\x1b\[[0-9;]*m")
F = "%Y-%m-%d %H:%M:%S"


def load(path):
    rows = []
    for l in open(path, encoding="utf-8", errors="replace"):
        l = ANSI.sub("", l.rstrip("\n"))
        m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", l)
        rows.append((datetime.strptime(m.group(1), F) if m else None, l))
    # carry timestamps forward to continuation lines
    last = None
    out = []
    for t, l in rows:
        last = t or last
        out.append((last, l))
    return out


def window_metrics(lines, start, end):
    w = [l for t, l in lines if t and start <= t <= end]
    open_calls, nem, ds = {}, [], []
    cur_t = None
    for t, l in [(t, l) for t, l in lines if t and start <= t <= end]:
        if "[AGENT] " in l:
            open_calls.setdefault(l.split("[AGENT] ", 1)[1].strip(), []).append(t)
        m = re.search(r"\[Tokens\] prompt=(\d+), completion=(\d+), model=(\S+)", l)
        if m and open_calls.get(m.group(3)):
            st = open_calls[m.group(3)].pop(0)
            rec = {"secs": (t - st).total_seconds(), "completion": int(m.group(2)), "prompt": int(m.group(1))}
            (nem if "nemotron" in m.group(3) else ds).append(rec)
    text = "\n".join(w)
    http = re.findall(r'POST (http\S+) "HTTP/1\.1 (\d+)', text)
    nem_http = [s for u, s in http if "18123" in u]
    return {
        "nemotron_calls": len(nem),
        "nemotron_non200": sum(1 for s in nem_http if s != "200"),
        "nemotron_llm_errors": len(re.findall(r"LLM Error.*nemotron|nemotron.*(APITimeoutError|ReadTimeout|Request timed out)", text)),
        "nemotron_over_60s": sum(1 for c in nem if c["secs"] > 60),
        "nemotron_max_secs": max((c["secs"] for c in nem), default=0),
        "deepseek_chat_calls": sum(1 for u, s in http if "deepseek.com/v1/chat" in u),
        "deepseek_chat_non200": sum(1 for u, s in http if "deepseek.com/v1/chat" in u and s != "200"),
        "researcher_truncations_8192": sum(1 for c in ds if c["completion"] == 8192),
        "researcher_chain_errors": text.count("[Chain Error] researcher-agent"),
        "batch_tool_errors": text.count("[Tool Error] run_research_batch"),
        "researcher_completed": text.count("[Chain End] researcher-agent"),
        "writer_started": text.count("[Chain Start] writer-agent"),
        "writer_ended": text.count("[Chain End] writer-agent"),
        "ds_prompt_tok": sum(c["prompt"] for c in ds),
        "ds_completion_tok": sum(c["completion"] for c in ds),
    }


def proxy_429s(start, end):
    n = 0
    if not PROXY_LOG.exists():
        return None
    day = start.strftime("%Y-%m-%d")
    for l in open(PROXY_LOG, encoding="utf-8", errors="replace"):
        m = re.match(r"^\[(\d{2}:\d{2}:\d{2})\] 429", l)
        if m:
            t = datetime.strptime(f"{day} {m.group(1)}", F)
            if start <= t <= end:
                n += 1
    return n


def usage_counts(start, end):
    s = f = 0
    for l in open(USAGE, encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l)
        t = datetime.strptime(r["ts"][:19], "%Y-%m-%dT%H:%M:%S")
        if start <= t <= end:
            if r.get("kind") == "search":
                s += 1
            elif r.get("kind") == "fetch":
                f += 1
    return s, f


def cites(md):
    t = md.read_text(encoding="utf-8") if md.exists() else ""
    body = re.split(r"\n#+\s*(Sources|References)\b", t)[0]
    srcs = re.findall(r"^\[\d+\] .*?(https?://\S+)\s*$", t, re.M)
    return len(t), len(set(re.findall(r"\[(\d{1,3})\]", t))), len(set(re.findall(r"\[(\d{1,3})\]", body))), len(srcs)


rows = []
# Q01 from the swap run
q01_log = load(EV / "results/deepseek-search/swap/server.log")
s, e = datetime(2026, 10, 20, 15, 10, 54), datetime(2026, 10, 20, 15, 34, 33)
ch, mk, bc, ns = cites(EV / "results/deepseek-search/Q01.report.md")
rows.append({"qid": "Q01", "status": "success", "latency_s": 1419, "report_chars": ch, "citation_markers": mk,
             "body_citations": bc, "url_sources": ns, "cost_usd": "0.19", **window_metrics(q01_log, s, e),
             "proxy_429": proxy_429s(s, e), "searches": usage_counts(s, e)[0], "fetches": usage_counts(s, e)[1]})

log = load(OUT / "server.log")
for r in csv.DictReader(open(OUT / "_summary.csv", encoding="utf-8")):
    if not r.get("start") or not r.get("end"):
        rows.append({"qid": r["qid"], "status": r["status"]})
        continue
    s, e = datetime.strptime(r["start"], F), datetime.strptime(r["end"], F)
    ch, mk, bc, ns = cites(OUT / f"{r['qid']}.report.md")
    sc, fc = usage_counts(s, e)
    rows.append({"qid": r["qid"], "status": r["status"], "latency_s": int(r["latency_s"]), "report_chars": ch,
                 "citation_markers": mk, "body_citations": bc, "url_sources": ns, "cost_usd": r["cost_usd"],
                 **window_metrics(log, s, e), "proxy_429": proxy_429s(s, e), "searches": sc, "fetches": fc,
                 "fingerprint": r.get("fingerprint", ""), "error": r.get("error", "")})

keys = []
for r in rows:
    for k in r:
        if k not in keys:
            keys.append(k)
with open(OUT / "metrics.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=keys)
    w.writeheader()
    w.writerows(rows)
for r in rows:
    print(json.dumps(r))
