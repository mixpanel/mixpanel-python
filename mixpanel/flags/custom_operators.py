from __future__ import annotations

import math
import re
from typing import Any, Callable

import json_logic
import semver
from dateutil import parser as dateutil_parser

_OPERAND_COUNT = 3
# Epoch milliseconds are compared as int64 elsewhere, so anything at or beyond this is out of range.
_MAX_EPOCH_MS = 2**63
# SemVer 2.0.0 requires major.minor.patch; partial versions are zero-padded to this.
_SEMVER_PARTS = 3

# Using the official semantic versioning 2.0.0 regular expression to handle cross-platform validation
# differences on other SDK's. For example, some platforms allow leading zeros even though it is not valid
# as part of the Semver 2.0.0 spec. See https://semver.org/
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

# Strict RFC3339 guard for datetime strings.
_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)

_COMPARATORS: dict[str, Callable[[int], bool]] = {
    "=": lambda cmp: cmp == 0,
    "!=": lambda cmp: cmp != 0,
    "<": lambda cmp: cmp < 0,
    "<=": lambda cmp: cmp <= 0,
    ">": lambda cmp: cmp > 0,
    ">=": lambda cmp: cmp >= 0,
}


# Implements a custom operation for semantic versioning comparison that conforms to the semver 2.0.0 standard.
# Prior to comparison, any leading version prefix is stripped.
def semver_compare(*values: Any) -> bool:
    if len(values) != _OPERAND_COUNT:
        return False
    actual, symbol, target = values
    if not isinstance(symbol, str):
        return False
    if not isinstance(actual, str) or not isinstance(target, str):
        return False
    normalized_actual = _normalize_semver(actual)
    normalized_target = _normalize_semver(target)
    if not _SEMVER_RE.match(normalized_actual) or not _SEMVER_RE.match(
        normalized_target
    ):
        return False
    actual_version = semver.Version.parse(normalized_actual)
    target_version = semver.Version.parse(normalized_target)
    cmp = actual_version.compare(target_version)
    return _comparator_matches(cmp, symbol)


# Implements a custom operation for datetime comparison.
# The target value stored on the feature flag is the millisecond epoch, whereas the actual value
# provided at evaluation time must be RFC-3339 formatted.
def datetime_compare(*values: Any) -> bool:
    if len(values) != _OPERAND_COUNT:
        return False
    actual, symbol, target = values
    if not isinstance(symbol, str):
        return False
    actual_seconds = _convert_rfc3339_to_unix_seconds(actual)
    if actual_seconds is None:
        return False
    target_seconds = _convert_unix_milliseconds_to_seconds(target)
    if target_seconds is None:
        return False
    cmp = actual_seconds - target_seconds
    return _comparator_matches(cmp, symbol)


def _comparator_matches(cmp: int, symbol: str) -> bool:
    predicate = _COMPARATORS.get(symbol)
    return predicate(cmp) if predicate is not None else False


def _normalize_semver(value: str) -> str:
    value = value.strip()
    if value[:1] in ("v", "V"):
        value = value[1:]

    suffix_start = len(value)
    for separator in ("-", "+"):
        index = value.find(separator)
        if index != -1 and index < suffix_start:
            suffix_start = index

    core = value[:suffix_start]
    suffix = value[suffix_start:]

    parts = core.split(".")
    while len(parts) < _SEMVER_PARTS:
        parts.append("0")
    return ".".join(parts) + suffix


def _convert_rfc3339_to_unix_seconds(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    if not _RFC3339_RE.match(normalized):
        return None
    try:
        parsed = dateutil_parser.isoparse(normalized)
    except (ValueError, OverflowError):
        return None
    whole_second = parsed.replace(microsecond=0)
    return int(whole_second.timestamp())


def _convert_unix_milliseconds_to_seconds(value: Any) -> int | None:
    # bool is an int subclass, so it must be rejected explicitly.
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    milliseconds = int(value)
    # A value int64 cannot represent is not a real timestamp; treating one as a bound would let a
    # nonsense target define a rollout window.
    if abs(milliseconds) >= _MAX_EPOCH_MS:
        return None
    # Integer arithmetic, so a target too large for a float cannot raise, truncating toward zero.
    magnitude = abs(milliseconds) // 1000
    return -magnitude if milliseconds < 0 else magnitude


json_logic.operations["semver_compare"] = semver_compare
json_logic.operations["datetime_compare"] = datetime_compare
