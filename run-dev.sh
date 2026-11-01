#!/usr/bin/env bash
# run-dev.sh: start the eLibrary Manager dev server on an available port.
#
# Port selection: ELIBRARY_DEV_PORT env var if set, else the configured
# app port (8000), else the first free port scanning upward — so the dev
# server never fails on "address already in use" when other apps (or the
# packaged eLibrary install) own the default port.
#
# Usage: ./run-dev.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

PREFERRED_PORT="${ELIBRARY_DEV_PORT:-8000}"

find_free_port() {
    local port="$1"
    while true; do
        if ! ss -tln "sport = :${port}" 2>/dev/null | grep -q LISTEN; then
            echo "$port"
            return
        fi
        port=$((port + 1))
        if [ "$port" -gt 65535 ]; then
            echo "No free port found above ${1}" >&2
            exit 1
        fi
    done
}

# Validate the env override; if it is occupied, fall through to scanning.
if ss -tln "sport = :${PREFERRED_PORT}" 2>/dev/null | grep -q LISTEN; then
    echo "Port ${PREFERRED_PORT} is in use — scanning for a free port..."
    PREFERRED_PORT=$(find_free_port "$PREFERRED_PORT")
fi

echo "Starting eLibrary Manager dev server on http://127.0.0.1:${PREFERRED_PORT}"
echo "  (set ELIBRARY_DEV_PORT to pin a port; Ctrl+C to stop)"
exec uv run python -m uvicorn app.main:app \
    --host 127.0.0.1 \
    --port "${PREFERRED_PORT}" \
    --app-dir backend \
    --reload
