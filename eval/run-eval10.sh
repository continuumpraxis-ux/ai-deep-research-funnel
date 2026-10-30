#!/usr/bin/env bash
# =============================================================================
# Eval, DeepSeek-search arm: Q02..Q10 on the swapped config (Q01 = job 08d94b22, not rerun).
# Same submit / poll / 90-min cancel / persist logic as run_eval.sh, plus:
#   - results in eval/results/deepseek-search-eval10/ (proof artifacts untouched)
#   - per-question DeepSeek balance snapshots (cost per question, $0.01 resolution)
#   - a set-wide spend watchdog (spend-watchdog-set.py) that writes STOP and cancels the running job
#     at the trip level; the loop checks STOP before every submit
#   - hard-fail fingerprint (sha256 of the normalized job error); 3 consecutive identical -> stop
# DeepSeek key in process env only (balance reads); never written to disk or logs.
#   usage: run-eval10.sh <base_url> <trip_usd>
# =============================================================================
set -uo pipefail
BASE="${1:-http://localhost:8001}"
TRIP="${2:-2.45}"
ROOT="/mnt/c/Users/<user>/stacks/ai-ops-blueprint"
EV=$ROOT/eval
QFILE="$EV/questions.json"
OUT="$EV/results/deepseek-search-eval10"
IDS=(Q02 Q03 Q04 Q05 Q06 Q07 Q08 Q09 Q10)
mkdir -p "$OUT"
ls "$OUT"/Q*.job_id >/dev/null 2>&1 && { echo "stale job_id files in $OUT - refusing"; exit 2; }
rm -f "$OUT/STOP" "$OUT/DONE"
log(){ echo "[eval10 $(date +%H:%M:%S)] $*"; }

export DEEPSEEK_API_KEY="$(op.exe read 'op://TEAM VAULT/<item-name>/credential' | tr -d '\r\n')"
[ -n "${DEEPSEEK_API_KEY:-}" ] || { echo NO_DEEPSEEK_KEY; exit 1; }
balance(){ curl -s --max-time 20 https://api.deepseek.com/user/balance -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print((d.get('balance_infos') or [{}])[0].get('total_balance',''))" 2>/dev/null; }

B0=$(balance); log "start balance \$$B0, watchdog trip at spend >= \$$TRIP"
[ -n "$B0" ] || { echo "BALANCE_UNAVAILABLE"; exit 5; }
/root/aiq-gate/.venv/bin/python "$EV/spend-watchdog-set.py" "$OUT" "$BASE" "$TRIP" &
WD=$!

SUMMARY="$OUT/_summary.csv"
echo "qid,status,latency_s,report_chars,citation_markers,body_citations,cost_usd,start,end,fingerprint,error" > "$SUMMARY"
prev_fp=""; streak=0

for QID in "${IDS[@]}"; do
  [ -e "$OUT/STOP" ] && { log "STOP file present (spend cap) - not submitting $QID"; break; }
  Q=$(python3 -c "import json;print(next(q['text'] for q in json.load(open('$QFILE'))['questions'] if q['id']=='$QID'))")
  bq0=$(balance)
  body=$(python3 -c "import json,sys;print(json.dumps({'agent_type':'deep_researcher','input':sys.argv[1]}))" "$Q")
  t0=$(date +%s); ts0=$(date '+%Y-%m-%d %H:%M:%S')
  log "submit $QID (balance \$$bq0)"
  resp=$(curl -s --max-time 30 -X POST "$BASE/v1/jobs/async/submit" -H 'content-type: application/json' -d "$body")
  jid=$(printf '%s' "$resp" | python3 -c "import sys,json;
try: print(json.load(sys.stdin).get('job_id',''))
except Exception: print('')")
  if [ -z "$jid" ]; then
    log "SUBMIT_FAIL $QID: $resp"; echo "$QID,submit_fail,,,,,,$ts0,,submit_fail,\"$resp\"" >> "$SUMMARY"; continue
  fi
  echo "$jid" > "$OUT/$QID.job_id"
  deadline=$(( $(date +%s) + 5400 )); status=""
  while [ "$(date +%s)" -lt "$deadline" ]; do
    status=$(curl -s --max-time 10 "$BASE/v1/jobs/async/job/$jid" | python3 -c "import sys,json;
try: print(json.load(sys.stdin).get('status',''))
except Exception: print('')")
    case "$status" in success|failure|interrupted|not_found) break;; esac
    sleep 15
  done
  t1=$(date +%s); ts1=$(date '+%Y-%m-%d %H:%M:%S'); lat=$(( t1 - t0 ))
  case "$status" in
    success|failure|interrupted|not_found) ;;
    *) log "$QID TIMEOUT after ${lat}s - cancelling $jid"
       curl -s --max-time 20 -X POST "$BASE/v1/jobs/async/job/$jid/cancel" -o /dev/null -w 'cancel HTTP %{http_code}\n' || true
       status="timeout_cancelled";;
  esac
  curl -s --max-time 30 "$BASE/v1/jobs/async/job/$jid" > "$OUT/$QID.job.json" 2>&1 || true
  curl -s --max-time 60 "$BASE/v1/jobs/async/job/$jid/report" > "$OUT/$QID.report.json" 2>&1 || true
  curl -s --max-time 60 "$BASE/v1/jobs/async/job/$jid/state"  > "$OUT/$QID.state.json"  2>&1 || true
  bq1=$(balance)
  row=$(python3 - "$OUT/$QID.report.json" "$OUT/$QID.report.md" "$OUT/$QID.job.json" "$status" "$bq0" "$bq1" <<'PY'
import hashlib, json, re, sys
rj, rmd, jj, status, b0, b1 = sys.argv[1:7]
txt = ""
try:
    rep = json.load(open(rj)).get("report")
    txt = rep if isinstance(rep, str) else (json.dumps(rep, ensure_ascii=False) if rep else "")
except Exception:
    pass
open(rmd, "w", encoding="utf-8").write(txt)
markers = len(set(re.findall(r"\[(\d{1,3})\]", txt)))
body = re.split(r"\n#+\s*(Sources|References)\b", txt)[0]
body_c = len(set(re.findall(r"\[(\d{1,3})\]", body)))
err = ""
try:
    err = json.load(open(jj)).get("error") or ""
except Exception:
    pass
fp = ""
if status != "success":
    norm = re.sub(r"[0-9a-f]{8}-[0-9a-f-]{27,}|0x[0-9a-f]+|\d+", "#", (err or status).lower())
    fp = hashlib.sha256(norm.encode()).hexdigest()[:12]
try:
    cost = f"{float(b0) - float(b1):.2f}"
except Exception:
    cost = ""
e = err.replace('"', "'").replace("\n", " ")[:300]
print(f'{len(txt)},{markers},{body_c},{cost},{fp},"{e}"')
PY
)
  IFS=, read -r chars markers bodyc cost fp _ <<< "$row"
  err_field="${row#*,*,*,*,*,}"
  echo "$QID,$status,$lat,$chars,$markers,$bodyc,$cost,$ts0,$ts1,$fp,$err_field" >> "$SUMMARY"
  log "$QID status=$status latency=${lat}s chars=$chars markers=$markers body=$bodyc cost=\$$cost fp=${fp:--}"
  if [ "$status" = "success" ]; then prev_fp=""; streak=0
  else
    if [ -n "$fp" ] && [ "$fp" = "$prev_fp" ]; then streak=$((streak+1)); else streak=1; prev_fp="$fp"; fi
    [ "$streak" -ge 3 ] && { log "3 consecutive hard-fails with fingerprint $fp - stopping pass"; break; }
  fi
done

touch "$OUT/DONE"
wait "$WD" 2>/dev/null || true
B1=$(balance)
SPENT=$(python3 -c "import sys;print(f'{float(sys.argv[1])-float(sys.argv[2]):.2f}')" "$B0" "$B1" 2>/dev/null)
log "end balance \$$B1, set spend \$$SPENT"
unset DEEPSEEK_API_KEY
log "DONE -> $SUMMARY"
