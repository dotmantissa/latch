#!/usr/bin/env bash
set -euo pipefail
LATCH_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$LATCH_ROOT"
if [[ ! -x .venv/bin/python ]]; then
  printf '%s\n' 'Run scripts/bootstrap.sh first.' >&2
  exit 1
fi
exec .venv/bin/python -m services.common.preflight "$@"
