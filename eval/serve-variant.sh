#!/usr/bin/env bash
# Serve an AI-Q config variant on a chosen port, without touching the primary
# server on :8000 or the pacing proxy on :18123.
#   usage: serve-variant.sh <config-filename> <port> [with-tavily|no-tavily]
# Keys are pulled via op read into the PROCESS ENV only; never written to disk/log.
# no-tavily (default) deliberately omits TAVILY_API_KEY so that even an accidental
# Tavily call fails closed instead of spending from the frozen pool.
set -uo pipefail
CFG="${1:?config filename required}"
PORT="${2:?port required}"
TAVILY_MODE="${3:-no-tavily}"
SRC=/root/aiq-gate
REPO="/mnt/c/Users/<user>/stacks/ai-ops-blueprint"

cp "$REPO/aiq/configs/$CFG" "$SRC/configs/$CFG"
cd "$SRC"

cat > deploy/.env <<'EOF'
APP_ENV=development
LOG_LEVEL=INFO
PYTHONWARNINGS=ignore
DEEP_RESEARCHER_CHROMA_DIR=/tmp/chroma_data
EOF

export NVIDIA_API_KEY="$(op.exe read 'op://TEAM VAULT/<item-name>/credential' | tr -d '\r\n')"
export INFERENCE_NVIDIA_API_KEY="$NVIDIA_API_KEY"
export DEEPSEEK_API_KEY="$(op.exe read 'op://TEAM VAULT/<item-name>/credential' | tr -d '\r\n')"
if [ "$TAVILY_MODE" = "with-tavily" ]; then
  export TAVILY_API_KEY="$(op.exe read 'op://TEAM VAULT/<item-name>/credential' | tr -d '\r\n')"
  echo "TAVILY key: present (len ${#TAVILY_API_KEY})"
else
  unset TAVILY_API_KEY || true
  echo "TAVILY key: DELIBERATELY ABSENT (fail-closed; pool stays frozen)"
fi
if [ -z "${NVIDIA_API_KEY:-}" ] || [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  echo "KEY_MISSING (NVIDIA=${#NVIDIA_API_KEY} DEEPSEEK=${#DEEPSEEK_API_KEY})"; exit 1
fi
echo "keys in env only — NVIDIA ${#NVIDIA_API_KEY}, DEEPSEEK ${#DEEPSEEK_API_KEY}"
echo "serving $CFG on :$PORT (Nemotron routed via the pacing proxy per the config)"
exec "$SRC/.venv/bin/nat" serve --config_file "configs/$CFG" --host 0.0.0.0 --port "$PORT"
