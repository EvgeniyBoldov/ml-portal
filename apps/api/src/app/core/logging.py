from __future__ import annotations
import logging, sys, os

def _configure_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, level, logging.INFO),
        format="%(message)s",
    )

_configured = False

def get_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        _configure_logging()
        _configured = True
    return logging.getLogger(name)
