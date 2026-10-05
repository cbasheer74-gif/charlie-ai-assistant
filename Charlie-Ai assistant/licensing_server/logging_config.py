"""
licensing_server/logging_config.py — Centralized log rotation and structured logging setup.

Configures:
  1. Console stdout stream handler.
  2. RotatingFileHandler writing to logs/charlie_server.log (10MB max, 5 rotated archives).
  3. Structured JSON formatter for security and access loggers.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
LOGS_DIR = SERVER_DIR / "logs"
LOG_FILE_PATH = LOGS_DIR / "charlie_server.log"

MAX_BYTES = 10 * 1024 * 1024  # 10 MB per log file
BACKUP_COUNT = 5               # Retain 5 rotated backups


def setup_logging() -> None:
    """Initialize rotated file logging and stdout handlers across application loggers."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Base formatter for standard log messages
    standard_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Raw formatter for loggers that emit pre-formatted JSON (e.g. access & security)
    raw_formatter = logging.Formatter("%(message)s")

    # Rotating file handler
    file_handler = RotatingFileHandler(
        filename=str(LOG_FILE_PATH),
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(standard_formatter)

    # Dedicated file handler for JSON audit logs
    audit_file_path = LOGS_DIR / "charlie_audit.log"
    audit_file_handler = RotatingFileHandler(
        filename=str(audit_file_path),
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    audit_file_handler.setLevel(logging.INFO)
    audit_file_handler.setFormatter(raw_formatter)

    # Console stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(standard_formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(stdout_handler)
        root_logger.addHandler(file_handler)

    # Configure specialized security and access loggers
    for logger_name in ("licensing_server.access", "licensing_server.security", "licensing_server.payment"):
        sub_logger = logging.getLogger(logger_name)
        sub_logger.setLevel(logging.INFO)
        sub_logger.propagate = False
        # Avoid duplicate handlers if setup_logging() is called multiple times
        if not sub_logger.handlers:
            sub_logger.addHandler(stdout_handler)
            sub_logger.addHandler(audit_file_handler)
