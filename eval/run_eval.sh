#!/usr/bin/env bash
# =============================================================================
# EVAL HARNESS (STAGED) - 10-question deep-research comparison.
# Runs ONE variant at a time against an already-running AI-Q server, submitting
# the 10 fixed questions SEQUENTIALLY (one heavy run at a time), polling each to
# a terminal state, and persisting report + state + per-question timing.
#
#   Usage:  EVAL_CONFIRMED=1 bash run_eval.sh <label> [base_url]
#     <label>    baseline | deepseek   (names the results subfolder)
#     [base_url] default http://localhost:8000
#
# HARD GATE: refuses to run unless EVAL_CONFIRMED=1.
# Per-question deadline is 90 min; on timeout the job is CANCELLED (DELETE) so only
# ONE job is ever active at a time (strictly sequential).
# Optional: set BALANCE_OP_REF=op://TEAM VAULT/<item-name>/credential to record DeepSeek
#   /user/balance before (balance-start.json) and after (balance-end.json) the run;
#   the run stops at pre-flight if the balance is not available.
# Machine rule: never launch two labels at once; only one AI-Q server up at a time.
# =============================================================================
set -uo pipefail

LABEL="${1:-}"
BASE="${2:-http://localhost:8000}"
ROOT="/mnt/c/Users/<user>/stacks/ai-ops-blueprint"
QFILE="$ROOT/eval/questions.json"
OUT="$ROOT/eval/results/$LABEL"

case "$LABEL" in baseline|deepseek|deepseek-search|free-researcher) ;; *) echo "ERR: label must be baseline | deepseek | free-researcher"; exit 2;; esac
[ "${EVAL_CONFIRMED:-}" = "1" ] || { echo "GATE: set EVAL_CONFIRMED=1 to run (staged — blocked by default)."; exit 3; }
PACE_SECONDS="${PACE_SECONDS:-0}"   # delay between questions (free-tier pacing); 0 = none
mkdir -p "$OUT"
log(){ echo "[eval:$LABEL $(date +%H:%M:%S)] $*"; }

# Server reachable?
curl -s --max-time 10 "$BASE/v1/jobs/async/submit" -o /dev/null -X OPTIONS 2>/dev/null
command -v python3 >/dev/null || { echo "ERR: python3 required"; exit 4; }

mapfile -t IDS < <(python3 -c "import json;print('\n'.join(q['id'] for q in json.load(open('$QFILE'))['questions']))")
[ -n "${ONLY:-}" ] && { IDS=("$ONLY"); log "ONLY=$ONLY (single-question smoke)"; }
SUMMARY="$OUT/_summary.csv"
echo "qid,status,latency_s,report_chars,citations_detected" > "$SUMMARY"

# Optional provider balance pre-flight (DeepSeek): records starting balance; stops if unavailable.
balance_snapshot(){ # $1=outfile
  [ -n "${BALANCE_OP_REF:-}" ] || return 0
  local bkey; bkey="$(op.exe read "$BALANCE_OP_REF" | tr -d '\r\n')"
  curl -s --max-time 20 https://api.deepseek.com/user/balance -H "Authorization: Bearer $bkey" > "$1" 2>/dev/null || true
  unset bkey
}
if [ -n "${BALANCE_OP_REF:-}" ]; then
  balance_snapshot "$OUT/balance-start.json"
  avail=$(python3 -c "import json;print(json.load(open('$OUT/balance-start.json')).get('is_available'))" 2>/dev/null || echo "")
  bal=$(python3 -c "import json;print((json.load(open('$OUT/balance-start.json')).get('balance_infos') or [{}])[0].get('total_balance'))" 2>/dev/null || echo "")
  log "balance pre-flight: is_available=$avail total_balance=$bal"
  [ "$avail" = "True" ] || { echo "BALANCE_NOT_AVAILABLE (is_available=$avail) — stopping before any question"; exit 5; }
fi

for QID in "${IDS[@]}"; do
  Q=$(python3 -c "import json;print(next(q['text'] for q in json.load(open('$QFILE'))['questions'] if q['id']=='$QID'))")
  log "submit $QID"
  body=$(python3 -c "import json,sys;print(json.dumps({'agent_type':'deep_researcher','input':sys.argv[1]}))" "$Q")
  t0=$(date +%s)
  resp=$(curl -s --max-time 30 -X POST "$BASE/v1/jobs/async/submit" -H 'content-type: application/json' -d "$body")
  jid=$(printf '%s' "$resp" | python3 -c "import sys,json;
try: print(json.load(sys.stdin).get('job_id',''))
except Exception: print('')")
  [ -n "$jid" ] || { log "SUBMIT_FAIL $QID: $resp"; echo "$QID,submit_fail,,," >> "$SUMMARY"; continue; }
  echo "$jid" > "$OUT/$QID.job_id"

  # Poll to terminal; CANCEL (DELETE) on timeout so only ONE job is ever active.
  deadline=$(( $(date +%s) + 5400 )); status=""   # 90-min per-question ceiling
  while [ "$(date +%s)" -lt "$deadline" ]; do
    status=$(curl -s --max-time 10 "$BASE/v1/jobs/async/job/$jid" | python3 -c "import sys,json;
try: print(json.load(sys.stdin).get('status',''))
except Exception: print('')")
    case "$status" in success|failure|interrupted|not_found) break;; esac
    sleep 15
  done
  t1=$(date +%s); lat=$(( t1 - t0 ))
  case "$status" in
    success|failure|interrupted|not_found) ;;
    *) log "$QID TIMEOUT after ${lat}s — cancelling job $jid (POST .../cancel)"
       curl -s --max-time 20 -X POST "$BASE/v1/jobs/async/job/$jid/cancel" -o /dev/null -w 'cancel HTTP %{http_code}\n' || true
       status="timeout_cancelled";;
  esac
  log "$QID status=$status latency=${lat}s"

  curl -s --max-time 60 "$BASE/v1/jobs/async/job/$jid/report" > "$OUT/$QID.report.json" 2>&1 || true
  curl -s --max-time 60 "$BASE/v1/jobs/async/job/$jid/state"  > "$OUT/$QID.state.json"  2>&1 || true

  read -r chars cites < <(python3 - "$OUT/$QID.report.json" "$OUT/$QID.report.md" <<'PY'
import json,sys,re
try:
    d=json.load(open(sys.argv[1]))
    rep=d.get("report")
    txt=rep if isinstance(rep,str) else (json.dumps(rep,ensure_ascii=False) if rep else "")
    open(sys.argv[2],"w",encoding="utf-8").write(txt)
    cites=len(set(re.findall(r"\[(\d{1,3})\]", txt)))   # distinct [n] citation markers
    print(len(txt), cites)
except Exception:
    print(0,0)
PY
)
  echo "$QID,$status,$lat,$chars,$cites" >> "$SUMMARY"
  # Free-tier pacing between questions (bounded; on upstream 429 the server's
  # num_retries backs off and the harness continues to the next question).
  [ "$PACE_SECONDS" -gt 0 ] && { log "pacing ${PACE_SECONDS}s before next"; sleep "$PACE_SECONDS"; }
done

if [ -n "${BALANCE_OP_REF:-}" ]; then
  balance_snapshot "$OUT/balance-end.json"
  endbal=$(python3 -c "import json;print((json.load(open('$OUT/balance-end.json')).get('balance_infos') or [{}])[0].get('total_balance'))" 2>/dev/null || echo "")
  log "balance post-flight: total_balance=$endbal"
fi
log "DONE -> $SUMMARY"
