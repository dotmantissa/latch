#!/usr/bin/env bash
set -euo pipefail
LATCH_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$LATCH_ROOT"
export PATH="$LATCH_ROOT/.tools/node/node_modules/node/bin:$PATH"
node .tools/node/node_modules/npm/bin/npm-cli.js run build
mkdir -p private
chmod 700 private
if [[ ! -f private/local.key || ! -f private/local.crt ]]; then
  umask 077
  openssl req -x509 -newkey rsa:2048 -nodes -keyout private/local.key -out private/local.crt \
    -days 30 -subj '/CN=localhost' -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1' 2>/dev/null
fi
printf '%s\n' 'Local workspace: https://localhost:8443 (local development certificate)'
exec .venv/bin/python -m uvicorn services.api.app:create_app --factory --host 127.0.0.1 \
  --port 8443 --ssl-keyfile private/local.key --ssl-certfile private/local.crt --no-access-log
