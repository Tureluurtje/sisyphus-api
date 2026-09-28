#!/bin/bash
set -euo pipefail

# Change to project root directory
cd "$(dirname "$0")"

# Load variables from .env and export them to child processes
if [ -f ".env" ]; then
    set -a
    source ".env"
    set +a
else
    echo "Error: .env file not found in $PWD" >&2
    exit 1
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-1}"
SSL_CERTFILE="${SSL_CERTFILE:-}"
SSL_KEYFILE="${SSL_KEYFILE:-}"

SSH_HOST="${SSH_HOST:-vps-db}"
DB_TUNNEL_PORT="${DB_PORT:-5433}"

# Make common bin paths visible
export PATH="$PWD/venv/bin:$PWD/.venv/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# Ensure pyenv is available in non-interactive shells
export PYENV_ROOT="${PYENV_ROOT:-$HOME/.pyenv}"

if [ -d "$PYENV_ROOT/bin" ]; then
    export PATH="$PYENV_ROOT/bin:$PYENV_ROOT/shims:$PATH"
fi

SSH_PID=""
APP_PID=""

cleanup() {
    local exit_code=$?

    # Prevent the trap from running recursively
    trap - EXIT INT TERM

    echo
    echo "Stopping development server..."

    if [ -n "${APP_PID:-}" ] && kill -0 "$APP_PID" 2>/dev/null; then
        echo "Stopping Uvicorn..."
        kill "$APP_PID" 2>/dev/null || true
        wait "$APP_PID" 2>/dev/null || true
    fi

    if [ -n "${SSH_PID:-}" ] && kill -0 "$SSH_PID" 2>/dev/null; then
        echo "Stopping SSH tunnel..."
        kill "$SSH_PID" 2>/dev/null || true
        wait "$SSH_PID" 2>/dev/null || true
    fi

    exit "$exit_code"
}

trap cleanup EXIT INT TERM

echo "Starting SSH tunnel through '$SSH_HOST'..."

# Do not use -f here. Bash backgrounds the process with &, allowing us
# to capture and later stop the exact SSH process.
ssh \
    -N \
    -o ExitOnForwardFailure=yes \
    "$SSH_HOST" &

SSH_PID=$!

# Give SSH a moment to either establish the forward or fail.
sleep 1

if ! kill -0 "$SSH_PID" 2>/dev/null; then
    echo "Error: SSH tunnel failed to start." >&2
    wait "$SSH_PID"
    exit 1
fi

# Optional verification that the local forwarded port is available
if command -v nc >/dev/null 2>&1; then
    if ! nc -z 127.0.0.1 "$DB_TUNNEL_PORT" >/dev/null 2>&1; then
        echo "Error: SSH is running, but local port $DB_TUNNEL_PORT is unavailable." >&2
        exit 1
    fi
fi

echo "SSH tunnel started with PID $SSH_PID."
echo "Starting Uvicorn..."

UVICORN_COMMAND=()

# 1) Prefer project virtualenv Python
if [ -x "venv/bin/python" ]; then
    UVICORN_COMMAND=(
        venv/bin/python -m uvicorn
        asgi_app:app
        --host "$HOST"
        --port "$PORT"
        --workers "$WORKERS"
    )
elif [ -x ".venv/bin/python" ]; then
    UVICORN_COMMAND=(
        .venv/bin/python -m uvicorn
        asgi_app:app
        --host "$HOST"
        --port "$PORT"
        --workers "$WORKERS"
    )

# 2) Fallback to uvicorn executable on PATH
elif command -v uvicorn >/dev/null 2>&1; then
    UVICORN_COMMAND=(
        uvicorn
        asgi_app:app
        --host "$HOST"
        --port "$PORT"
        --workers "$WORKERS"
    )

# 3) Fallback to pyenv-managed Python
elif command -v pyenv >/dev/null 2>&1 \
    && pyenv exec python -c "import uvicorn" >/dev/null 2>&1; then
    UVICORN_COMMAND=(
        pyenv exec python -m uvicorn
        asgi_app:app
        --host "$HOST"
        --port "$PORT"
        --workers "$WORKERS"
    )

# 4) Fallback to system Python
elif command -v python3 >/dev/null 2>&1 \
    && python3 -c "import uvicorn" >/dev/null 2>&1; then
    UVICORN_COMMAND=(
        python3 -m uvicorn
        asgi_app:app
        --host "$HOST"
        --port "$PORT"
        --workers "$WORKERS"
    )
else
    echo "No runnable Uvicorn found." >&2
    exit 1
fi

if [ -n "$SSL_CERTFILE" ] && [ -n "$SSL_KEYFILE" ]; then
    UVICORN_COMMAND+=(
        --ssl-certfile "$SSL_CERTFILE"
        --ssl-keyfile "$SSL_KEYFILE"
    )
fi

"${UVICORN_COMMAND[@]}" &
APP_PID=$!

# Wait until Uvicorn exits or Ctrl+C triggers cleanup
wait "$APP_PID"
