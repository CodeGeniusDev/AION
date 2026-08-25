"""Structured logging configuration.

Every log record automatically carries request_id/correlation_id from the
current context (observability/context.py) via a logging.Filter — callers
never need to pass these explicitly. Log lines are structured
(key=value pairs), not free text, so they're greppable/parseable without
adding a JSON logging dependency this project doesn't otherwise need.

configure_logging() is idempotent — safe to call multiple times (e.g. once
in main.py at import time, and again in tests) without duplicating handlers.
"""

import logging

from observability.context import get_correlation_id, get_request_id

_CONFIGURED = False


class _RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        record.correlation_id = get_correlation_id() or "-"
        return True


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    root_logger = logging.getLogger("aion")
    root_logger.setLevel(level.upper())

    if _CONFIGURED:
        return

    handler = logging.StreamHandler()
    handler.addFilter(_RequestContextFilter())
    handler.setFormatter(logging.Formatter(
        "%(asctime)s level=%(levelname)s logger=%(name)s "
        "request_id=%(request_id)s correlation_id=%(correlation_id)s msg=%(message)s"
    ))
    root_logger.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Convenience accessor — always returns a child of the 'aion' logger
    so configure_logging()'s handler/level applies."""
    return logging.getLogger(f"aion.{name}")
