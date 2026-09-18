import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Keep test collection independent from the production environment. These
# values are loaded before any api module imports api.config.
os.environ.update(
    {
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "DB_USERNAME": "test",
        "DB_PASSWORD": "test",
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_DATABASE": "test",
        "HOST": "127.0.0.1",
        "PORT": "8000",
        "WORKERS": "1",
        "SECRET_KEY": "test-secret-key-with-at-least-32-bytes",
        "ALGORITHM": "HS256",
        "GOOGLE_OAUTH2_SECRET": "test-google-secret",
        "WEB_CLIENT_ID": "test-web-client",
        "RESEND_API_KEY": "test-resend-key",
    }
)
