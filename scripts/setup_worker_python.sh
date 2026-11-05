#!/usr/bin/env bash
# The host runner shares the project's exact Python; the stdlib proxy uses Ubuntu Python.
set -euo pipefail
if [[ $EUID -ne 0 ]] || [[ $(hostname -s) != latch-worker ]]; then
  printf '%s\n' 'Root on the dedicated latch-worker is required.' >&2
  exit 1
fi
if [[ $(/opt/latch/uv --version) != 'uv 0.13.7'* ]]; then
  printf '%s\n' 'The verified project uv 0.13.7 binary is required.' >&2
  exit 1
fi
export UV_PYTHON_INSTALL_DIR=/opt/latch/python
/opt/latch/uv python install --no-bin 3.13.18
/opt/latch/uv venv --python 3.13.18 /opt/latch/host-venv
/opt/latch/uv pip install --python /opt/latch/host-venv/bin/python \
  --require-hashes --only-binary :all: -r /opt/latch/infra/worker/requirements.lock
/opt/latch/host-venv/bin/python --version
sha256sum /opt/latch/uv > /var/lib/latch/provenance/uv-sha256.txt
