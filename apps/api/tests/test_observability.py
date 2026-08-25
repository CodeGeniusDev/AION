"""Focused tests for observability primitives (observability/*.py), written
before wiring them into main.py/workflow_runner.py. Integration-level tests
(bus retention, async offloading, end-to-end request tracing) live in
test_hardening_integration.py.
"""

import logging
import time

from observability.context import bind_request_context, get_correlation_id, get_request_id, reset_request_context
from observability.logging_config import configure_logging, get_logger
from observability.rate_limiter import InMemoryRateLimiter


def teardown_function() -> None:
    reset_request_context()


# ---------------------------------------------------------------------------
# Context propagation
# ---------------------------------------------------------------------------


def test_bind_request_context_generates_ids_when_none_given() -> None:
    request_id, correlation_id = bind_request_context()
    assert request_id
    assert correlation_id
    assert get_request_id() == request_id
    assert get_correlation_id() == correlation_id


def test_bind_request_context_defaults_correlation_to_request_id() -> None:
    request_id, correlation_id = bind_request_context()
    assert correlation_id == request_id


def test_bind_request_context_uses_supplied_correlation_id() -> None:
    _, correlation_id = bind_request_context(correlation_id="external-trace-123")
    assert correlation_id == "external-trace-123"
    assert get_correlation_id() == "external-trace-123"


def test_bind_request_context_uses_supplied_request_id() -> None:
    request_id, _ = bind_request_context(request_id="fixed-id")
    assert request_id == "fixed-id"


def test_reset_request_context_clears_bound_values() -> None:
    bind_request_context()
    reset_request_context()
    assert get_request_id() is None
    assert get_correlation_id() is None


def test_each_bind_call_produces_a_distinct_request_id() -> None:
    first, _ = bind_request_context()
    second, _ = bind_request_context()
    assert first != second


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------


def test_configure_logging_is_idempotent() -> None:
    configure_logging()
    handlers_after_first = len(logging.getLogger("aion").handlers)
    configure_logging()
    handlers_after_second = len(logging.getLogger("aion").handlers)
    assert handlers_after_first == handlers_after_second


def test_get_logger_returns_child_of_aion_namespace() -> None:
    logger = get_logger("test_module")
    assert logger.name == "aion.test_module"


def test_log_record_carries_bound_request_and_correlation_ids(caplog) -> None:
    configure_logging()
    bind_request_context(request_id="req-abc", correlation_id="corr-xyz")
    logger = get_logger("test_module")

    with caplog.at_level(logging.INFO, logger="aion.test_module"):
        logger.info("test message")

    assert any(getattr(record, "request_id", None) == "req-abc" for record in caplog.records)
    assert any(getattr(record, "correlation_id", None) == "corr-xyz" for record in caplog.records)


def test_log_record_without_bound_context_uses_placeholder(caplog) -> None:
    configure_logging()
    reset_request_context()
    logger = get_logger("test_module")

    with caplog.at_level(logging.INFO, logger="aion.test_module"):
        logger.info("unbound message")

    assert any(getattr(record, "request_id", None) == "-" for record in caplog.records)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_rate_limiter_allows_requests_under_the_limit() -> None:
    limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is True


def test_rate_limiter_blocks_requests_over_the_limit() -> None:
    limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is False


def test_rate_limiter_tracks_keys_independently() -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-b") is True  # different key, independent budget
    assert limiter.allow("client-a") is False


def test_rate_limiter_window_expires_old_hits() -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=0.05)
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is False
    time.sleep(0.07)
    assert limiter.allow("client-a") is True  # window has rolled forward


def test_rate_limiter_reset_clears_all_state() -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
    limiter.allow("client-a")
    assert limiter.allow("client-a") is False
    limiter.reset()
    assert limiter.allow("client-a") is True
