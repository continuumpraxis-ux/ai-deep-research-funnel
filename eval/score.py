#!/usr/bin/env python3
"""Eval scoring - builds the comparison sheet from eval/results/{baseline,deepseek}.

Computes per-variant latency, report size, detected citation count, and (when
token usage is present in the saved state) estimated cost using the rate table
below. Extracts each report's citation URLs into a checklist for the independent
Perplexity validity pass (citation-accuracy is filled there, not auto-scored).

Run after both variants' runs complete:  python3 score.py
Writes: eval/SCORING-SHEET.md  and  eval/results/costs.csv
"""
import csv, json, os, re, statistics as st

ROOT = "/mnt/c/Users/<user>/stacks/ai-ops-blueprint/eval"
RESULTS = os.path.join(ROOT, "results")

# --- Rate table ($ per 1M tokens) -------------------------------------------
# DeepSeek: VERIFIED from api-docs.deepseek.com (2026-10-19), cache-miss.
# Nemotron: TODO — confirm NVIDIA API-Catalog per-token price for
# nvidia/nemotron-3-ultra-550b-a55b before trusting baseline $ (tokens are still
# measured; only the $ needs this rate). Leave None until confirmed.
RATES = {
    "deepseek-flash":              {"in": 0.15, "out": 0.60, "note": "verified off-peak cache-miss; peak $0.30/$1.20"},
    "nvidia/nemotron-3-super-120b-a12b:free": {"in": 0.0, "out": 0.0, "note": "OpenRouter free tier — zero price"},
    "nvidia/nemotron-3-ultra-550b-a55b": {"in": None, "out": None, "note": "TODO: confirm NVIDIA API-Catalog rate"},
}

# label -> researcher model used for that run's cost attribution
LABEL_MODEL = {
    "baseline": "nvidia/nemotron-3-ultra-550b-a55b",
    "deepseek": "deepseek-flash",
    "free-researcher": "nvidia/nemotron-3-super-120b-a12b:free",
}

URL_RE = re.compile(r"https?://[^\s)\]]+")

def load_summary(label):
    p = os.path.join(RESULTS, label, "_summary.csv")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return list(csv.DictReader(f))

def deep_find_usage(obj, acc):
    """Recursively sum any prompt/completion token counts found in a JSON blob."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = k.lower()
            if lk in ("prompt_tokens", "input_tokens") and isinstance(v, (int, float)):
                acc["in"] += v
            elif lk in ("completion_tokens", "output_tokens") and isinstance(v, (int, float)):
                acc["out"] += v
            else:
                deep_find_usage(v, acc)
    elif isinstance(obj, list):
        for x in obj:
            deep_find_usage(x, acc)
    return acc

def q_tokens(label, qid):
    acc = {"in": 0, "out": 0}
    for suffix in (".state.json", ".report.json"):
        p = os.path.join(RESULTS, label, qid + suffix)
        if os.path.exists(p):
            try:
                deep_find_usage(json.load(open(p, encoding="utf-8")), acc)
            except Exception:
                pass
    return acc

def citations(label, qid):
    p = os.path.join(RESULTS, label, qid + ".report.md")
    if not os.path.exists(p):
        return []
    txt = open(p, encoding="utf-8").read()
    return sorted(set(URL_RE.findall(txt)))

def section(label):
    rows = load_summary(label)
    if not rows:
        return f"### {label}\n\n_No results yet (run `run_eval.sh {label}` after the gate clears)._\n", None
    lat = [float(r["latency_s"]) for r in rows if r.get("latency_s")]
    csum = sum(int(r["citations_detected"] or 0) for r in rows)
    out = [f"### {label}", "",
           f"- questions run: {len(rows)}",
           f"- success: {sum(1 for r in rows if r['status']=='success')}/{len(rows)}",
           f"- latency (s): median {st.median(lat):.0f} / min {min(lat):.0f} / max {max(lat):.0f}" if lat else "- latency: n/a",
           f"- citation markers detected (sum): {csum}", ""]
    out.append("| qid | status | latency_s | report_chars | cites | in_tok | out_tok | est_$ |")
    out.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        tk = q_tokens(label, r["qid"])
        model = LABEL_MODEL.get(label, "nvidia/nemotron-3-ultra-550b-a55b")
        rate = RATES.get(model, {})
        est = ""
        if rate.get("in") is not None and (tk["in"] or tk["out"]):
            est = f"{(tk['in']/1e6*rate['in'] + tk['out']/1e6*rate['out']):.4f}"
        out.append(f"| {r['qid']} | {r['status']} | {r['latency_s']} | {r['report_chars']} | "
                   f"{r['citations_detected']} | {tk['in'] or ''} | {tk['out'] or ''} | {est} |")
    out.append("")
    return "\n".join(out), rows

def main():
    parts = ["# Eval Scoring Sheet - DeepSeek-flash researchers vs Nemotron default", "",
             "Latency and report/citation counts are auto-filled from the runs. **Citation accuracy**",
             "(fraction of citations that actually support the claim) is scored in the independent",
             "**Perplexity pass** using the per-question citation lists at the bottom — fill the",
             "`citation_accuracy` column there, then summarize here.", "",
             "## Rate table ($/1M tokens)",
             "- deepseek-flash: $0.15 in / $0.60 out (verified, off-peak cache-miss; peak $0.30/$1.20)",
             "- nvidia/nemotron-3-ultra-550b-a55b: **TODO confirm NVIDIA rate** (tokens measured; $ pending)",
             "", "## Results", ""]
    for label in ("baseline", "deepseek", "free-researcher"):
        sec, _ = section(label)
        parts.append(sec)
    parts += ["## Citation validity worklist (Perplexity pass)", "",
              "For each URL: mark SUPPORTS / PARTIAL / DOES-NOT-SUPPORT the cited claim.", ""]
    for label in ("baseline", "deepseek", "free-researcher"):
        if not load_summary(label):
            continue
        parts.append(f"### {label}")
        for r in load_summary(label):
            urls = citations(label, r["qid"])
            parts.append(f"- **{r['qid']}** ({len(urls)} urls)")
            parts += [f"  - [ ] {u}" for u in urls] or ["  - (no urls detected)"]
        parts.append("")
    open(os.path.join(ROOT, "SCORING-SHEET.md"), "w", encoding="utf-8").write("\n".join(parts))
    print("wrote SCORING-SHEET.md")

if __name__ == "__main__":
    main()
