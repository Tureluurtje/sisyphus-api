import os
import sys

# Ensure project root is on sys.path so absolute imports like `api.*` resolve
project_root = os.path.dirname(p=os.path.abspath(path=__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Export the FastAPI app object for ASGI servers/CLIs (uvicorn/fastapi)
from api.main import app  # noqa: E402, F401

__all__ = ["app"]
