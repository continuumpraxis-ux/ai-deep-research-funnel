#!/usr/bin/env bash
# =============================================================================
# Serve AI-Q with the FREE OpenRouter researcher variant (Nemotron 3 Super).
# Mirrors scripts/serve.sh; adds the OpenRouter key pull and serves the free-route
# config. Keys pulled from vaults via `op read` into the PROCESS ENV only — never
# written to disk/log.
#
# GATE: do NOT run until eval/smoke-openrouter.sh returns HTTP 200 + a usage block.
# As of 2026-10-19 the free model is blocked by OpenRouter account data policy
# ("free-model-training-violation-by-account") — enable it at
# https://openrouter.ai/settings/privacy first.
#
#   Usage: bash serve-openrouter.sh [port]   (default 8000)
# =============================================================================
set -uo pipefail
SRC=/root/aiq-gate
REPO="/mnt/c/Users/<user>/stacks/ai-ops-blueprint"
PORT="${1:-8000}"

cp "$REPO/aiq/configs/config_web_openrouter_free_researchers.yml" "$SRC/configs/config_web_openrouter_free_researchers.yml"
cd "$SRC"

cat > deploy/.env <<'EOF'
APP_ENV=development
LOG_LEVEL=INFO
PYTHONWARNINGS=ignore
DEEP_RESEARCHER_CHROMA_DIR=/tmp/chroma_data
EOF

# Non-researcher roles still run on NVIDIA API-Catalog Nemotron; researcher = OpenRouter free.
export NVIDIA_API_KEY="$(op.exe read 'op://TEAM VAULT/<item-name>/credential' | tr -d '\r\n')"
export INFERENCE_NVIDIA_API_KEY="$NVIDIA_API_KEY"
export TAVILY_API_KEY="$(op.exe read 'op://TEAM VAULT/<item-name>/credential' | tr -d '\r\n')"
# The valid OpenRouter vault item (a same-titled stale item returned 401).
export OPENROUTER_API_KEY="$(op.exe read 'op://TEAM VAULT/<item-name>/credential' | tr -d '\r\n')"
if [ -z "${NVIDIA_API_KEY:-}" ] || [ -z "${TAVILY_API_KEY:-}" ] || [ -z "${OPENROUTER_API_KEY:-}" ]; then
  echo "KEY_MISSING (NVIDIA=${#NVIDIA_API_KEY} TAVILY=${#TAVILY_API_KEY} OPENROUTER=${#OPENROUTER_API_KEY})"; exit 1
fi
echo "keys in env only — NVIDIA ${#NVIDIA_API_KEY}, TAVILY ${#TAVILY_API_KEY}, OPENROUTER ${#OPENROUTER_API_KEY}"
echo "starting nat serve on :$PORT (config_web_openrouter_free_researchers.yml)"
exec "$SRC/.venv/bin/nat" serve --config_file configs/config_web_openrouter_free_researchers.yml --host 0.0.0.0 --port "$PORT"
