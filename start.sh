#!/usr/bin/env bash
set -euo pipefail

# ── eLibrary Manager — single entry point ──────────────────────────────
# Loads .env, finds an available port, starts the server, opens browser.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colors ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

# ── Load .env (handles spaces / quotes / comments) ─────────────────────
if [ -f .env ]; then
    while IFS='=' read -r key value; do
        key=$(echo "$key" | xargs)
        # Skip empty lines, comments, and invalid identifiers (no spaces/colons)
        [[ -z "$key" || "$key" == \#* ]] && continue
        [[ "$key" =~ [^a-zA-Z0-9_] ]] && continue
        # Strip surrounding quotes from value
        value="${value%\"}" value="${value#\"}"
        value="${value%\'}" value="${value#\'}"
        export "$key=$value"
    done < .env
fi

# ── Resolve host ───────────────────────────────────────────────────────
HOST="${APP_HOST:-0.0.0.0}"

# ── Find an available port ─────────────────────────────────────────────
find_free_port() {
    local start="${1:-8000}"
    local max_end=$((start + 100))
    for port in $(seq "$start" "$max_end"); do
        if ! ss -tlnp 2>/dev/null | grep -q ":${port} " \
           && ! lsof -i ":${port}" >/dev/null 2>&1; then
            echo "$port"
            return 0
        fi
    done
    return 1
}

PREFERRED_PORT="${APP_PORT:-8000}"

if PORT=$(find_free_port "$PREFERRED_PORT"); then
    if [ "$PORT" -ne "$PREFERRED_PORT" ]; then
        echo -e "${YELLOW}Port ${PREFERRED_PORT} is in use — using ${PORT} instead${RESET}"
    fi
else
    echo -e "${RED}ERROR: No available port found in range ${PREFERRED_PORT}-$((PREFERRED_PORT + 100))${RESET}"
    exit 1
fi

# Export so the app sees the chosen port
export APP_PORT="$PORT"

# ── Ensure required directories exist ──────────────────────────────────
mkdir -p dawnstar_data static_covers static_book_images library

# ── Trap cleanup ───────────────────────────────────────────────────────
cleanup() {
    echo ""
    echo -e "${CYAN}Shutting down eLibrary Manager...${RESET}"
    if [ -n "${SERVER_PID:-}" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    echo -e "${GREEN}Goodbye!${RESET}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# ── Start server ───────────────────────────────────────────────────────
echo -e "${BOLD}${GREEN}Starting eLibrary Manager${RESET}"
echo -e "  ${CYAN}Local:${RESET}   http://localhost:${PORT}"
echo -e "  ${CYAN}Network:${RESET} http://${HOST}:${PORT}"
echo -e "  ${CYAN}Press Ctrl+C to stop${RESET}"
echo ""

uv run python -m uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --app-dir backend \
    &

SERVER_PID=$!

# ── Wait for server to be ready, then open browser ─────────────────────
HEALTH_URL="http://localhost:${PORT}/api/health"
MAX_WAIT=15
for i in $(seq 1 "$MAX_WAIT"); do
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
        echo -e "${GREEN}Server is ready!${RESET}"
        # Open in default browser (works on Linux, macOS, WSL)
        if command -v xdg-open >/dev/null 2>&1; then
            xdg-open "http://localhost:${PORT}" 2>/dev/null || true
        elif command -v open >/dev/null 2>&1; then
            open "http://localhost:${PORT}" 2>/dev/null || true
        elif command -v wslview >/dev/null 2>&1; then
            wslview "http://localhost:${PORT}" 2>/dev/null || true
        fi
        break
    fi
    sleep 1
done

# ── Wait for server process ────────────────────────────────────────────
wait "$SERVER_PID"
