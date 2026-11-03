#!/usr/bin/env bash
set -euo pipefail
LATCH_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$LATCH_ROOT"
python3 -m pip install --target .tools/uv uv==0.13.7
export UV_PYTHON_INSTALL_DIR="$LATCH_ROOT/.tools/python"
.tools/uv/bin/uv python install --no-bin 3.13.18
.tools/uv/bin/uv sync --locked
npm install --prefix .tools/node --save-exact node@24.22.2
export PATH="$LATCH_ROOT/.tools/node/node_modules/node/bin:$PATH"
npm ci --ignore-scripts --no-audit --no-fund
npm run check:runtime
.venv/bin/python -m services.common.preflight runtime
