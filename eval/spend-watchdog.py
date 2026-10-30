#!/usr/bin/env python3
"""DeepSeek spend watchdog for a single eval job.

Polls GET /user/balance every 60 s. If spend since start reaches the trip level (default $0.45, so the
$0.50 cap holds even with a one-poll lag), it cancels the running job (POST .../cancel) and exits.
Also exits when the job reaches a terminal state. DEEPSEEK_API_KEY from process env only.
Usage: spend-watchdog.py <job_id_file> <base_url> [trip_usd]
"""
import json, os, pathlib, sys, time
import httpx

jid_file, base = pathlib.Path(sys.argv[1]), sys.argv[2]
trip = float(sys.argv[3]) if len(sys.argv) > 3 else 0.45
key = os.environ["DEEPSEEK_API_KEY"]
LOG = pathlib.Path("/mnt/c/Users/<user>/stacks/ai-ops-blueprint/eval/results/deepseek-search/spend-watchdog.log")


def bal():
    d = httpx.get("https://api.deepseek.com/user/balance", headers={"Authorization": f"Bearer {key}"}, timeout=20).json()
    return float((d.get("balance_infos") or [{}])[0].get("total_balance"))


def log(m):
    line = f"[watchdog {time.strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


start = bal()
log(f"start balance ${start:.2f}, trip at spend >= ${trip:.2f}")
jid = ""
while True:
    time.sleep(60)
    if not jid and jid_file.exists():
        jid = jid_file.read_text().strip()
        log(f"watching job {jid}")
    try:
        now = bal()
    except Exception as e:  # noqa: BLE001
        log(f"balance read failed: {e}")
        continue
    spent = round(start - now, 4)
    status = ""
    if jid:
        try:
            status = httpx.get(f"{base}/v1/jobs/async/job/{jid}", timeout=10).json().get("status", "")
        except Exception:
            pass
    log(f"balance ${now:.2f} spent ${spent:.2f} job={status or '-'}")
    if spent >= trip and jid:
        r = httpx.post(f"{base}/v1/jobs/async/job/{jid}/cancel", timeout=20)
        log(f"TRIP: spend ${spent:.2f} >= ${trip:.2f} -> cancel HTTP {r.status_code}")
        break
    if status in ("success", "failure", "interrupted", "not_found"):
        log(f"job terminal ({status}); final spend ${spent:.2f}")
        break
