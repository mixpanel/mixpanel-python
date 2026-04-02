from __future__ import annotations

import uuid

EXPOSURE_EVENT = "$experiment_started"

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


def prepare_common_query_params(token: str, sdk_version: str) -> dict[str, str]:
    """Prepare common query string parameters for feature flag evaluation.

    :param token: The project token
    :param sdk_version: The SDK version
    :return: Dictionary of common query parameters
    """
    return {"mp_lib": "python", "lib_version": sdk_version, "token": token}


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
