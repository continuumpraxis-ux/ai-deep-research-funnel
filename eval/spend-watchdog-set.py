#!/usr/bin/env python3
"""Set-wide DeepSeek spend watchdog for run-eval10.sh.

Polls GET /user/balance every 60 s. When spend since start reaches the trip level, it writes <out>/STOP
(the driver submits nothing more), cancels whichever job in <out>/*.job_id is still running, and exits.
Exits on its own when the driver writes <out>/DONE. DEEPSEEK_API_KEY from process env only.
Usage: spend-watchdog-set.py <out_dir> <base_url> <trip_usd>
"""
import os, pathlib, sys, time
import httpx

out, base, trip = pathlib.Path(sys.argv[1]), sys.argv[2], float(sys.argv[3])
key = os.environ["DEEPSEEK_API_KEY"]
LOG = out / "spend-watchdog.log"


def bal():
    d = httpx.get("https://api.deepseek.com/user/balance", headers={"Authorization": f"Bearer {key}"}, timeout=20).json()
    return float((d.get("balance_infos") or [{}])[0].get("total_balance"))


def log(m):
    line = f"[watchdog {time.strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def running_jobs():
    for p in sorted(out.glob("Q*.job_id")):
        jid = p.read_text().strip()
        try:
            s = httpx.get(f"{base}/v1/jobs/async/job/{jid}", timeout=10).json().get("status", "")
        except Exception:
            s = ""
        if s not in ("success", "failure", "interrupted", "not_found"):
            yield p.stem.split(".")[0], jid, s


start = bal()
log(f"start balance ${start:.2f}, trip at set spend >= ${trip:.2f}")
while not (out / "DONE").exists():
    time.sleep(60)
    try:
        now = bal()
    except Exception as e:  # noqa: BLE001
        log(f"balance read failed: {e}")
        continue
    spent = round(start - now, 4)
    log(f"balance ${now:.2f} set spend ${spent:.2f}")
    if spent >= trip:
        (out / "STOP").write_text(f"spend {spent:.2f} >= trip {trip:.2f}\n")
        for qid, jid, s in running_jobs():
            r = httpx.post(f"{base}/v1/jobs/async/job/{jid}/cancel", timeout=20)
            log(f"TRIP: cancelled {qid} job {jid} (was {s or '?'}) -> HTTP {r.status_code}")
        log(f"TRIP: set spend ${spent:.2f} >= ${trip:.2f}; STOP written")
        break
log("watchdog exit")
