#!/bin/bash
set -euo pipefail

# Change to project root directory
cd "$(dirname "$0")"

# Running locally without SSL (no certificate/key required)

# ...existing code...
# Make common bin paths visible in Localports
export PATH="$PWD/venv/bin:$PWD/.venv/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# Ensure pyenv is available in non-interactive shells (Localports)
export PYENV_ROOT="${PYENV_ROOT:-$HOME/.pyenv}"
if [ -d "$PYENV_ROOT/bin" ]; then
  export PATH="$PYENV_ROOT/bin:$PYENV_ROOT/shims:$PATH"
fi
# ...existing code...

# 1) Prefer project virtualenv Python
if [ -x "venv/bin/python" ]; then
  exec venv/bin/python -m uvicorn asgi_app:app --host 0.0.0.0 --port 8000
elif [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python -m uvicorn asgi_app:app --host 0.0.0.0 --port 8000
fi

# 2) Fallback to uvicorn executable on PATH
if command -v uvicorn >/dev/null 2>&1; then
  exec uvicorn asgi_app:app --host 0.0.0.0 --port 8000
fi

# 3) Fallback to pyenv-managed python with uvicorn module
# pyenv-managed python with uvicorn module
if command -v pyenv >/dev/null 2>&1 && pyenv exec python -c "import uvicorn" >/dev/null 2>&1; then
  exec pyenv exec python -m uvicorn asgi_app:app --host 0.0.0.0 --port 8000
fi

# 4) Fallback to system python with uvicorn module
if command -v python3 >/dev/null 2>&1 && python3 -c "import uvicorn" >/dev/null 2>&1; then
  exec python3 -m uvicorn asgi_app:app --host 0.0.0.0 --port 8000
fi

echo "No runnable uvicorn found."
echo "Expected one of:"
echo "  - ./venv/bin/python with uvicorn installed"
echo "  - ./.venv/bin/python with uvicorn installed"
echo "  - 'uvicorn' on PATH"
echo "  - pyenv python with uvicorn installed"
echo "  - 'python3 -m uvicorn' available"
exit 1
