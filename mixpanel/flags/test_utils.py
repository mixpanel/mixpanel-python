from __future__ import annotations

import logging
import re
from concurrent.futures import Future, ThreadPoolExecutor
from unittest.mock import MagicMock

import httpx
import pytest

from .utils import (
    _log_tracker_future_exception,
    build_base_url,
    close_async_client_from_sync,
    dispatch_exposure,
    generate_traceparent,
    normalized_hash,
)


class TestBuildBaseUrl:
    @pytest.mark.parametrize("verify_cert", [True, False])
    def test_bare_host_defaults_to_https(self, verify_cert):
        # verify_cert relaxes verification only; it never downgrades the scheme.
        assert build_base_url("api.mixpanel.com", verify_cert) == (
            "https://api.mixpanel.com"
        )

    @pytest.mark.parametrize("verify_cert", [True, False])
    def test_explicit_https_is_preserved(self, verify_cert):
        assert build_base_url("https://api.mixpanel.com", verify_cert) == (
            "https://api.mixpanel.com"
        )

    def test_http_allowed_when_not_verifying(self):
        assert build_base_url("http://host.minikube.internal/tproxy", False) == (
            "http://host.minikube.internal/tproxy"
        )

    def test_http_rejected_when_verifying(self):
        with pytest.raises(ValueError, match="verify_cert=False"):
            build_base_url("http://host.minikube.internal/tproxy", True)

    def test_scheme_match_is_case_insensitive(self):
        assert build_base_url("HTTP://host.internal", False) == "HTTP://host.internal"

    @pytest.mark.parametrize("api_host", ["ftp://host.internal", "ws://host.internal"])
    def test_other_schemes_rejected(self, api_host):
        with pytest.raises(ValueError, match="Unsupported scheme"):
            build_base_url(api_host, False)

    def test_host_with_path_and_port_is_untouched(self):
        # A bare host may carry a port and path prefix (a dev proxy mount).
        assert build_base_url("host.internal:8000/tproxy", True) == (
            "https://host.internal:8000/tproxy"
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


class TestCloseAsyncClientFromSync:
    # SDK-85: shutdown() and __exit__ need to close the AsyncClient
    # from sync context. Callers already inside a running event loop
    # must use __aexit__ — see the raises test below.

    def test_closes_client_when_no_loop_running(self):
        client = httpx.AsyncClient()
        assert not client.is_closed

        close_async_client_from_sync(client)

        assert client.is_closed

    @pytest.mark.asyncio
    async def test_raises_when_called_from_running_loop(self):
        # Fire-and-forget scheduling on the running loop can be cancelled
        # by loop teardown before aclose finishes, so the helper refuses
        # the call and points async callers at __aexit__.
        client = httpx.AsyncClient()
        try:
            with pytest.raises(RuntimeError, match="running event loop"):
                close_async_client_from_sync(client)
            assert not client.is_closed
        finally:
            await client.aclose()
