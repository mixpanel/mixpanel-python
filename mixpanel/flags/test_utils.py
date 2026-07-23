from __future__ import annotations

import re

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
