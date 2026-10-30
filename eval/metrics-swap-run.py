#!/usr/bin/env python3
"""Metrics for the Q01 swap run: per-call Nemotron timings, errors, 429s, DeepSeek calls, search/fetch.
Usage: metrics-swap-run.py <server.log> <usage.jsonl> <usage_baseline_lines>
"""
import json, re, sys
from collections import Counter, defaultdict
from datetime import datetime

log_path, usage_path, base = sys.argv[1], sys.argv[2], int(sys.argv[3])
ANSI = re.compile(r"\x1b\[[0-9;]*m")
TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
lines = [ANSI.sub("", l.rstrip("\n")) for l in open(log_path, encoding="utf-8", errors="replace")]


def ts(l):
    m = TS.match(l)
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S") if m else None


open_calls = defaultdict(list)     # model -> [(start_ts, input_chars, line_no)]
calls, errors = [], []
for i, l in enumerate(lines):
    if "[AGENT] " in l:
        model = l.split("[AGENT] ", 1)[1].strip()
        chars = None
        if i + 1 < len(lines) and "Agent input: chars=" in lines[i + 1]:
            chars = int(re.search(r"chars=(\d+)", lines[i + 1]).group(1))
        open_calls[model].append((ts(l), chars, i + 1))
    elif "[Tokens]" in l:
        m = re.search(r"prompt=(\d+), completion=(\d+), model=(\S+)", l)
        if m and open_calls[m.group(3)]:
            st, chars, ln = open_calls[m.group(3)].pop(0)
            calls.append({"model": m.group(3), "start": st, "end": ts(l), "secs": (ts(l) - st).total_seconds(),
                          "input_chars": chars, "prompt": int(m.group(1)), "completion": int(m.group(2)), "line": ln})
    if re.search(r"LLM Error|APITimeoutError|ReadTimeout|TimeoutError|Request timed out|APIConnectionError", l):
        errors.append((i + 1, l[:260]))

nem = [c for c in calls if "nemotron" in c["model"]]
ds = [c for c in calls if "deepseek" in c["model"]]
print(f"== completed LLM calls: nemotron={len(nem)} deepseek={len(ds)} (unclosed nemotron starts: "
      f"{sum(len(v) for k, v in open_calls.items() if 'nemotron' in k)})")
print("== Nemotron calls (start, secs, input_chars, prompt_tok, completion_tok):")
for c in nem:
    flag = "  <-- >60s" if c["secs"] > 60 else ""
    print(f"   {c['start']:%H:%M:%S}  {c['secs']:6.0f}s  in={c['input_chars']}  p={c['prompt']}  c={c['completion']}{flag}")
over = [c for c in nem if c["secs"] > 60]
print(f"== Nemotron calls over 60 s that SUCCEEDED (would have hit the nim 60 s read timeout): {len(over)}")
print(f"== max Nemotron input chars: {max((c['input_chars'] or 0) for c in nem) if nem else 0}")
print(f"== error lines (LLM Error / timeouts): {len(errors)}")
for ln, l in errors[:30]:
    print(f"   L{ln}: {l}")

http = Counter(re.findall(r'POST (http\S+) "HTTP/1\.1 (\d+)', "\n".join(lines)))
print("== HTTP responses by endpoint/status:")
for (u, s), n in sorted(http.items()):
    print(f"   {n:4d}  {s}  {u}")
print(f"== 429 occurrences: {sum(1 for l in lines if ' 429' in l or '[429]' in l or 'Too Many Requests' in l)}")
print(f"== DeepSeek tokens: prompt={sum(c['prompt'] for c in ds)} completion={sum(c['completion'] for c in ds)}")

rows = [json.loads(l) for l in open(usage_path, encoding="utf-8").read().splitlines()[base:] if l.strip()]
k = Counter((r.get("kind"), r.get("billed")) for r in rows)
print(f"== DeepSeek Search/Fetch this run (usage.jsonl lines {base + 1}..{base + len(rows)}): {dict(k)}")
billed = sum(1 for r in rows if r.get("billed"))
print(f"   billed requests={billed} -> ${billed * 0.00075:.4f} at $0.75/1k")
print("== writer / output.md lines:")
for i, l in enumerate(lines):
    if re.search(r"writer-agent|output\.md", l):
        print(f"   L{i + 1}: {l[:200]}")
