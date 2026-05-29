"""Application configuration loaded from environment.

This module reads configuration from environment variables. During local
development a root-level ``.env`` file is loaded (via python-dotenv) so that
values can be kept out of source control while maintaining sensible defaults.

The expected environment variables are documented in the repository-level
``.env`` file.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional


def load_environment_file() -> None:
    """Load a .env file from the current working directory or a parent.

    When the app is installed as a wheel, __file__ points inside site-packages,
    so searching from the process working directory is the most reliable way to
    find the deployment .env file.
    """

    candidates = [Path.cwd() / ".env"]
    candidates.extend(parent / ".env" for parent in Path.cwd().parents)

    for candidate in candidates:
        if candidate.exists():
            load_dotenv(candidate)
            return


load_environment_file()


def require_env(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise EnvironmentError(f"Missing required environment variable: {name}")
    return value


def parse_env_bool(name: str, default: str = "false") -> bool:
    value = require_env(name, default).strip().lower()
    return value in {"1", "true", "yes", "on"}


def parse_env_csv(name: str, default: str = "") -> list[str]:
    value = require_env(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


# Database config
DB: dict[str, Optional[str]] = {
    "USERNAME": require_env("DB_USERNAME"),
    "PASSWORD": require_env("DB_PASSWORD"),
    "HOST": require_env("DB_HOST"),
    "PORT": require_env("DB_PORT"),
    "DATABASE": require_env("DB_DATABASE"),
}

# Prefer an explicit DATABASE_URL when one is provided, otherwise use the
# PostgreSQL DSN expected by the current deployment.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg://{DB['USERNAME']}:{DB['PASSWORD']}@{DB['HOST']}:{DB['PORT']}/{DB['DATABASE']}",
)

# Server exposure config
HOST: str = require_env("HOST")
PORT: int = int(require_env("PORT"))
WORKERS: int = int(require_env("WORKERS"))


def get_host() -> str:
    """Return the `HOST` value from the environment at call time.

    This is a lazy getter so callers can re-read the environment when they
    need the current runtime value rather than the value captured at module
    import time.
    """
    return require_env("HOST")


def get_port() -> int:
    """Return the `PORT` value from the environment at call time as an int."""
    return int(require_env("PORT"))


def get_workers() -> int:
    """Return the `WORKERS` value from the environment at call time as an int."""
    return int(require_env("WORKERS"))


# Auth / JWT settings
SECURE_COOKIES: bool = parse_env_bool("SECURE_COOKIES", "false")
CORS_ORIGINS: list[str] = parse_env_csv("CORS_ORIGINS")

SECRET_KEY: str = require_env("SECRET_KEY")
ALGORITHM: str = require_env("ALGORITHM")
MIN_PASSWORD_ZXCVBN_SCORE: int = int(require_env("MIN_PASSWORD_ZXCVBN_SCORE", "3"))

_access_default: str = require_env("ACCESS_TOKEN_EXPIRE_SECONDS", "900")
ACCESS_TOKEN_EXPIRE_SECONDS: int = int(_access_default)

_refresh_default: str = require_env("REFRESH_TOKEN_EXPIRE_SECONDS", "2592000")
REFRESH_TOKEN_EXPIRE_SECONDS = int(_refresh_default)

GOOGLE_OAUTH2_SECRET: str = require_env("GOOGLE_OAUTH2_SECRET")
WEB_CLIENT_ID: str = require_env("WEB_CLIENT_ID")
