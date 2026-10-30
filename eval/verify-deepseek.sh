#!/usr/bin/env bash
# Credential-gate check - "does the DeepSeek pull work?" (NOT the eval).
# Pulls the key from TEAM VAULT via op read (env only), lists models, confirms
# the deepseek-flash id resolves. Spends no inference tokens.
set -uo pipefail
DEEPSEEK_OP_REF='__DEEPSEEK_OP_REF__'   # <-- same op reference as serve-deepseek.sh
[ "$DEEPSEEK_OP_REF" = '__DEEPSEEK_OP_REF__' ] && { echo "GATE: DeepSeek op reference not set."; exit 3; }
KEY="$(op.exe read "$DEEPSEEK_OP_REF" | tr -d '\r\n')"
[ -n "$KEY" ] || { echo "NO_DEEPSEEK_KEY (item/field not found)"; exit 1; }
echo "key pulled from TEAM VAULT, len ${#KEY} (not printed)"
code=$(curl -s -o /tmp/ds_models.json -w '%{http_code}' --max-time 20 https://api.deepseek.com/v1/models -H "Authorization: Bearer $KEY")
echo "GET https://api.deepseek.com/v1/models -> HTTP $code"
python3 -c "import json
try:
    d=json.load(open('/tmp/ds_models.json')); ids=[m.get('id') for m in d.get('data',[])]
    print('models:', ids); print('deepseek-flash present:', 'deepseek-flash' in ids)
except Exception as e:
    print('parse_err', e)"
rm -f /tmp/ds_models.json
echo "VERIFY_DONE"
