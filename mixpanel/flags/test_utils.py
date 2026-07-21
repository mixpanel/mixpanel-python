from __future__ import annotations

import asyncio
import logging
import re
from unittest.mock import Mock

import httpx
import pytest

from .utils import (
    close_async_client_from_sync,
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


class TestCloseAsyncClientFromSync:
    # SDK-85: shutdown() and __exit__ need to close the AsyncClient
    # from sync context without breaking callers that happen to be
    # inside a running event loop.

    def test_closes_client_when_no_loop_running(self):
        client = httpx.AsyncClient()
        assert not client.is_closed

        close_async_client_from_sync(client)

        assert client.is_closed

    @pytest.mark.asyncio
    async def test_schedules_close_and_warns_when_loop_running(self, caplog):
        # Inside an async test we already have a running loop — the
        # helper must not raise (as async_to_sync would) and must
        # schedule the aclose task for later.
        client = httpx.AsyncClient()
        assert not client.is_closed

        with caplog.at_level("WARNING", logger="mixpanel.flags.utils"):
            close_async_client_from_sync(client)

        # Give the event loop a chance to execute the scheduled task.
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert client.is_closed
        assert any("scheduled aclose" in rec.message for rec in caplog.records)

    @pytest.mark.asyncio
    async def test_logs_error_when_scheduled_aclose_raises(self, caplog):
        # If the scheduled aclose() task raises, the done_callback must
        # retrieve and log the exception. Otherwise the caller sees a
        # successful shutdown() return and the failure only surfaces as
        # an anonymous "Task exception was never retrieved" at gc time.
        client = Mock(spec=httpx.AsyncClient)

        async def _boom():
            raise RuntimeError("aclose blew up")

        client.aclose.side_effect = _boom

        with caplog.at_level(logging.ERROR, logger="mixpanel.flags.utils"):
            close_async_client_from_sync(client)
            # Let the task run + done_callback fire.
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        assert any(
            "Async HTTP client close failed" in rec.message
            and "aclose blew up" in rec.message
            for rec in caplog.records
        ), f"expected error log, got {[r.message for r in caplog.records]}"
