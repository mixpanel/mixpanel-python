from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync

if TYPE_CHECKING:
    import httpx

EXPOSURE_EVENT = "$experiment_started"


def close_async_client_from_sync(client: httpx.AsyncClient) -> None:
    """SDK-85: close an ``httpx.AsyncClient`` from sync code.

    Bridges to sync via ``asgiref.async_to_sync`` and blocks until the
    close completes. If a loop is already running on the current thread
    (e.g. ``shutdown()`` was called from inside an ``async def``), raises
    ``RuntimeError`` — scheduling a background ``aclose`` on the running
    loop is unsafe because loop teardown can cancel the task before it
    finishes, defeating the fix. Async callers should use ``__aexit__``
    or await ``aclose()`` directly.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        async_to_sync(client.aclose)()
        return

    raise RuntimeError(
        "close_async_client_from_sync() cannot be called from a running "
        "event loop. Use 'async with provider:' or await the provider's "
        "__aexit__ from async code."
    )


REQUEST_HEADERS: dict[str, str] = {
    "X-Scheme": "https",
    "X-Forwarded-Proto": "https",
    "Content-Type": "application/json",
}


def normalized_hash(key: str, salt: str) -> float:
    """Compute a normalized hash using FNV-1a algorithm.

    :param key: The key to hash
    :param salt: Salt to add to the hash
    :return: Normalized hash value between 0.0 and 1.0
    """
    hash_value = _fnv1a64(key.encode("utf-8") + salt.encode("utf-8"))
    return (hash_value % 100) / 100.0


def _fnv1a64(data: bytes) -> int:
    """FNV-1a 64-bit hash function.

    :param data: Bytes to hash
    :return: 64-bit hash value
    """
    fnv_prime = 0x100000001B3
    hash_value = 0xCBF29CE484222325

    for _byte in data:
        hash_value ^= _byte
        hash_value *= fnv_prime
        hash_value &= 0xFFFFFFFFFFFFFFFF  # Keep it 64-bit

    return hash_value


def prepare_common_query_params(
    token: str, sdk_version: str, project_id: str | None = None
) -> dict[str, str]:
    """Prepare common query string parameters for feature flag evaluation.

    :param token: The project token
    :param sdk_version: The SDK version
    :param project_id: Optional project ID for service account authentication
    :return: Dictionary of common query parameters
    """
    params = {
        "mp_lib": "python",
        "lib_version": sdk_version,
        "token": token,
    }

    if project_id is not None:
        params["project_id"] = project_id

    return params


def generate_traceparent() -> str:
    """Generate a W3C traceparent header for distributed tracing interop.

    https://www.w3.org/TR/trace-context/#traceparent-header
    :return: A traceparent string
    """
    trace_id = uuid.uuid4().hex
    span_id = uuid.uuid4().hex[:16]

    # Trace flags: '01' for sampled
    trace_flags = "01"

    return f"00-{trace_id}-{span_id}-{trace_flags}"
