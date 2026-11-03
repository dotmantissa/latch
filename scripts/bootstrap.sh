#!/usr/bin/env bash
set -euo pipefail
LATCH_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$LATCH_ROOT"
if [[ ! -x .tools/uv/bin/uv ]] || [[ "$(.tools/uv/bin/uv --version)" != 'uv 0.13.7'* ]]; then
  python3 -m pip install --upgrade --target .tools/uv uv==0.13.7
fi
export UV_PYTHON_INSTALL_DIR="$LATCH_ROOT/.tools/python"
.tools/uv/bin/uv python install --no-bin 3.13.18
.tools/uv/bin/uv sync --locked
npm install --prefix .tools/node --save-exact node@24.22.2 npm@10.8.2 --no-audit --no-fund
export PATH="$LATCH_ROOT/.tools/node/node_modules/node/bin:$PATH"
.tools/node/node_modules/node/bin/node .tools/node/node_modules/npm/bin/npm-cli.js ci --ignore-scripts --no-audit --no-fund
.tools/node/node_modules/node/bin/node .tools/node/node_modules/npm/bin/npm-cli.js run check:runtime
.venv/bin/python -m services.common.preflight runtime
