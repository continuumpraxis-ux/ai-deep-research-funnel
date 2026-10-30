#!/usr/bin/env bash
# Safely stop anything on :8000 and report remaining nat/serve procs (no pattern-kill self-match).
fuser -k 8000/tcp 2>/dev/null || true
sleep 2
fuser -k 8000/tcp 2>/dev/null || true
sleep 1
echo "port 8000:"; ss -ltn 2>/dev/null | grep ':8000' || echo "  free"
echo "nat serve procs:"; ps -eo pid,args 2>/dev/null | grep '[n]at serve' || echo "  none"
echo "serve-openrouter procs:"; ps -eo pid,args 2>/dev/null | grep '[s]erve-openrouter' || echo "  none"
echo "serve-deepseek procs:"; ps -eo pid,args 2>/dev/null | grep '[s]erve-deepseek' || echo "  none"
echo "DONE"
