#!/usr/bin/env bash
# Launch eLibrary Manager on the configured port.
#
# ELIBRARY_PORT (and all other config) is injected by systemd from
# /etc/elibrary-manager/config.env via EnvironmentFile=, so we do NOT re-read
# the file here — that way config.env ownership/permissions can never break
# startup. Defaults to 8000 if unset.
set -euo pipefail

cd /opt/elibrary-manager
exec /opt/elibrary-manager/.venv/bin/python -m uvicorn app.main:app \
    --host 0.0.0.0 --port "${ELIBRARY_PORT:-8000}" --no-access-log
