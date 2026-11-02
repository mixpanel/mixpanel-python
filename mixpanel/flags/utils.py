from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any, Callable

from asgiref.sync import async_to_sync

from mixpanel.identity import MixpanelIdentity

if TYPE_CHECKING:
    from concurrent.futures import Executor, Future

    import httpx

logger = logging.getLogger(__name__)

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


def _present(value: Any) -> str | None:
    """Return ``value`` as a string, or None if it is None or empty."""
    if value is None or str(value) == "":
        return None
    return str(value)


def exposure_identity(
    context: dict[str, Any], hierarchical_groups: bool
) -> str | MixpanelIdentity | None:
    """Return who an exposure event for ``context`` is attributed to.

    Without hierarchical groups this is the context's ``distinct_id``, passed
    to the tracker as a plain string exactly as before. With hierarchical
    groups it is a :class:`~mixpanel.identity.MixpanelIdentity` carrying
    whichever of ``distinct_id``, ``$user_id`` and ``$company_id`` the context
    has, attributable by ``$company_id`` or ``distinct_id``. Returns None if the
    exposure cannot be attributed.
    """
    distinct_id = context.get("distinct_id")
    if not hierarchical_groups:
        return distinct_id or None

    company_id = _present(context.get("$company_id"))
    if company_id is None and not distinct_id:
        return None
    return MixpanelIdentity(
        distinct_id=str(distinct_id) if distinct_id else None,
        # A $user_id without its company names a separate user, which the
        # client's track() rejects, so it is sent only alongside one.
        user_id=_present(context.get("$user_id")) if company_id else None,
        company_id=company_id,
    )


def missing_exposure_identity_message(hierarchical_groups: bool) -> str:
    """The warning logged when an exposure cannot be attributed."""
    key = "$company_id" if hierarchical_groups else "distinct_id"
    return f"Cannot track exposure event without a {key} in the context"


def dispatch_exposure(
    tracker: Callable,
    executor: Executor | None,
    distinct_id: str | MixpanelIdentity,
    properties: dict[str, Any],
) -> None:
    """Invoke the tracker inline or via the configured executor.

    Shared between local and remote flag providers so a change to the
    dispatch policy only needs to happen in one place.
    """
    if executor is None:
        tracker(distinct_id, EXPOSURE_EVENT, properties)
        return

    try:
        future = executor.submit(tracker, distinct_id, EXPOSURE_EVENT, properties)
    except RuntimeError:
        logger.exception("Exposure event dropped — executor refused to accept task")
        return

    # Retrieve exceptions raised on the executor thread; otherwise a
    # tracker raising on the background thread is swallowed by the Future.
    future.add_done_callback(_log_tracker_future_exception)


def _log_tracker_future_exception(future: Future) -> None:
    # future.exception() raises CancelledError on a cancelled future,
    # and CancelledError is a BaseException (not Exception) — it would
    # escape Future._invoke_callbacks' `except Exception` and propagate
    # into e.g. executor.shutdown(cancel_futures=True).
    if future.cancelled():
        return
    exc = future.exception()
    if exc is not None:
        logger.error(
            "Exposure event failed on executor thread: %s: %s",
            type(exc).__name__,
            exc,
        )


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
