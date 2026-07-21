from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)

# Retains a hard reference to fire-and-forget aclose() tasks scheduled
# from close_async_client_from_sync when a loop is already running, so
# they can't be gc'd before completing. Removed via done_callback.
_pending_aclose_tasks: set[asyncio.Task] = set()

EXPOSURE_EVENT = "$experiment_started"


def close_async_client_from_sync(client: httpx.AsyncClient) -> None:
    """SDK-85: close an ``httpx.AsyncClient`` from sync code.

    If no event loop is running on the current thread, bridges to sync
    via ``asgiref.async_to_sync`` and blocks until close completes.

    If a loop is already running on this thread (e.g. ``shutdown()`` was
    called from inside an async function), schedules a background
    ``aclose`` task without blocking — ``async_to_sync`` would raise
    ``RuntimeError`` in that scenario. Callers running under an event
    loop should prefer ``__aexit__`` / awaiting ``aclose`` directly.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        async_to_sync(client.aclose)()
        return

    task = loop.create_task(client.aclose())
    _pending_aclose_tasks.add(task)
    task.add_done_callback(_pending_aclose_tasks.discard)
    logger.warning(
        "close_async_client_from_sync scheduled aclose() on a running "
        "event loop and did not wait for it. Prefer awaiting aclose() "
        "or using __aexit__ from async code."
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
