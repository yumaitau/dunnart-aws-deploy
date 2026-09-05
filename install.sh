#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .tools/python
.tools/python/bin/pip install --quiet --disable-pip-version-check -r requirements.txt
if [[ "${1:-}" == "--automated" ]]; then
  exec .tools/python/bin/python scripts/launch-job.py "$@"
fi
exec .tools/python/bin/python scripts/install.py "$@"
