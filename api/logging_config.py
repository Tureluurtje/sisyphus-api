import logging
from logging.handlers import RotatingFileHandler
import os
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "api", "logs")

os.makedirs(f"{LOG_DIR}/requests", exist_ok=True)
os.makedirs(f"{LOG_DIR}/errors", exist_ok=True)
os.makedirs(f"{LOG_DIR}/app", exist_ok=True)

# ANSI color codes (console only)
RESET = "\033[0m"
LEVEL_COLORS = {
    "DEBUG":    "\033[36m",   # Cyan
    "INFO":     "\033[32m",   # Green
    "WARNING":  "\033[33m",   # Yellow
    "ERROR":    "\033[31m",   # Red
    "CRITICAL": "\033[1;31m", # Bold red
}

LINE_FMT  = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FMT  = "%Y-%m-%d %H:%M:%S"


class PlainLineFormatter(logging.Formatter):
    """Single-line plain-text formatter for .log files."""
    def format(self, record: Any):
        base = super().format(record)
        return base


class ColorLineFormatter(logging.Formatter):
    """Same single-line format but with per-level ANSI colors for console."""
    def format(self, record: Any):
        color = LEVEL_COLORS.get(record.levelname, RESET)
        msg = super().format(record)
        return f"{color}{msg}{RESET}"


def get_logger(name: str, log_file: str, console: bool = False) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        # File handler — plain, no ANSI
        fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
        fh.setFormatter(PlainLineFormatter(LINE_FMT, datefmt=DATE_FMT))
        logger.addHandler(fh)

        # Optional console handler — colored
        if console:
            ch = logging.StreamHandler()
            ch.setFormatter(ColorLineFormatter(LINE_FMT, datefmt=DATE_FMT))
            logger.addHandler(ch)

    logger.propagate = False
    return logger


app_logger     = get_logger("app",      f"{LOG_DIR}/app/app.log",           console=True)
error_logger   = get_logger("errors",   f"{LOG_DIR}/errors/error.log",      console=True)
request_logger = get_logger("requests", f"{LOG_DIR}/requests/request.log",  console=False)
