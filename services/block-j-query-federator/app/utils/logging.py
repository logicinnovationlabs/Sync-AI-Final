"""Structured logging setup."""

from __future__ import annotations

import logging
import sys

from app.config import settings


def setup_logging(level: str | None = None) -> None:
    """Configure root logger with a structured console format."""
    log_level = (level or settings.log_level).upper()
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(log_level)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(log_level)
