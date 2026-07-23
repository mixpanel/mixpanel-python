from __future__ import annotations

import logging
import re
from concurrent.futures import Future, ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from .utils import (
    _log_tracker_future_exception,
    dispatch_exposure,
    generate_traceparent,
    normalized_hash,
)


class TestUtils:
    def test_traceparent_format_is_correct(self):
        traceparent = generate_traceparent()

        # W3C traceparent format: 00-{32 hex chars}-{16 hex chars}-{2 hex chars}
        # https://www.w3.org/TR/trace-context/#traceparent-header
        pattern = r"^00-[0-9a-f]{32}-[0-9a-f]{16}-01$"

        assert re.match(pattern, traceparent), (
            f"Traceparent '{traceparent}' does not match W3C format"
        )

    @pytest.mark.parametrize(
        ("key", "salt", "expected_hash"),
        [
            ("abc", "variant", 0.72),
            ("def", "variant", 0.21),
        ],
    )
    def test_normalized_hash_for_known_inputs(self, key, salt, expected_hash):
        result = normalized_hash(key, salt)
        assert result == expected_hash, (
            f"Expected hash of {expected_hash} for '{key}' with salt '{salt}', got {result}"
        )

    def test_dispatch_exposure_runs_inline_when_no_executor(self):
        tracker = MagicMock()

        dispatch_exposure(tracker, None, "user-1", {"prop": "value"})

        tracker.assert_called_once_with(
            "user-1", "$experiment_started", {"prop": "value"}
        )

    def test_dispatch_exposure_logs_executor_thread_exceptions(self, caplog):
        # Without the done-callback the future.exception() would be silently
        # discarded — this test would fail (no log record captured).
        def boom(*_args, **_kwargs):
            raise RuntimeError("tracker exploded")

        with ThreadPoolExecutor(max_workers=1) as executor:
            with caplog.at_level(logging.ERROR, logger="mixpanel.flags.utils"):
                dispatch_exposure(boom, executor, "user-1", {})
            # Drain the executor so the done-callback has a chance to fire.
            executor.shutdown(wait=True)

        assert any(
            "Exposure event failed on executor thread" in rec.message
            and "tracker exploded" in rec.message
            for rec in caplog.records
        ), f"expected error log, got {[r.message for r in caplog.records]}"

    def test_log_tracker_future_exception_ignores_cancelled_future(self, caplog):
        # future.exception() on a cancelled future raises CancelledError
        # (a BaseException, not Exception) — without the guard, that
        # would escape Future._invoke_callbacks and propagate into e.g.
        # executor.shutdown(cancel_futures=True).
        future: Future = Future()
        assert future.cancel(), "fresh Future should be cancellable"

        with caplog.at_level(logging.ERROR, logger="mixpanel.flags.utils"):
            _log_tracker_future_exception(future)  # must not raise

        assert not any(
            "Exposure event failed" in rec.message for rec in caplog.records
        ), "cancelled futures must not produce an error log"
