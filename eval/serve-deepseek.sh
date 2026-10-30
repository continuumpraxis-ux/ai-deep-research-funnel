#!/usr/bin/env bash
# =============================================================================
# Serve AI-Q with the DeepSeek-flash researcher variant (STAGED).
# Mirrors scripts/serve.sh, adds the DeepSeek key pull, and serves the variant
# config. Keys pulled from TEAM VAULT via `op read` into the PROCESS ENV only -
# never written to disk/log.
#
# CREDENTIAL GATE (do this before running):
#   1) Add the DeepSeek API key to TEAM VAULT.
#   2) Put its op reference below (replace __DEEPSEEK_OP_REF__), e.g.
#        op://TEAM VAULT/<item-name>/credential
#   3) Confirm the pull works (see eval/verify-deepseek.sh).
# Until then this script exits at the gate - it will NOT start a run.
# =============================================================================
set -uo pipefail
SRC=/root/aiq-gate
REPO="/mnt/c/Users/<user>/stacks/ai-ops-blueprint"
PORT="${1:-8000}"

# ---- Credential gate -------------------------------------------------------
DEEPSEEK_OP_REF='op://TEAM VAULT/<item-name>/credential'   # TEAM VAULT DeepSeek API item
if [ "$DEEPSEEK_OP_REF" = '__DEEPSEEK_OP_REF__' ]; then
  echo "GATE: DeepSeek op reference not set. Add the key to TEAM VAULT and edit DEEPSEEK_OP_REF. Not starting."
  exit 3
fi

# Stage the variant config into the served source tree (non-secret).
cp "$REPO/aiq/configs/config_web_deepseek_researchers.yml" "$SRC/configs/config_web_deepseek_researchers.yml"
cd "$SRC"

cat > deploy/.env <<'EOF'
APP_ENV=development
LOG_LEVEL=INFO
PYTHONWARNINGS=ignore
DEEP_RESEARCHER_CHROMA_DIR=/tmp/chroma_data
EOF

export NVIDIA_API_KEY="$(op.exe read 'op://TEAM VAULT/<item-name>/credential' | tr -d '\r\n')"
export INFERENCE_NVIDIA_API_KEY="$NVIDIA_API_KEY"
export TAVILY_API_KEY="$(op.exe read 'op://TEAM VAULT/<item-name>/credential' | tr -d '\r\n')"
export DEEPSEEK_API_KEY="$(op.exe read "$DEEPSEEK_OP_REF" | tr -d '\r\n')"
if [ -z "${NVIDIA_API_KEY:-}" ] || [ -z "${TAVILY_API_KEY:-}" ] || [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  echo "KEY_MISSING (NVIDIA=${#NVIDIA_API_KEY} TAVILY=${#TAVILY_API_KEY} DEEPSEEK=${#DEEPSEEK_API_KEY})"; exit 1
fi
echo "keys in env only — NVIDIA ${#NVIDIA_API_KEY}, TAVILY ${#TAVILY_API_KEY}, DEEPSEEK ${#DEEPSEEK_API_KEY}"
echo "starting nat serve on :$PORT (config_web_deepseek_researchers.yml)"
exec "$SRC/.venv/bin/nat" serve --config_file configs/config_web_deepseek_researchers.yml --host 0.0.0.0 --port "$PORT"
