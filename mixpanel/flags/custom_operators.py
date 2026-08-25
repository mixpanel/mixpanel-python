from __future__ import annotations

import math
import re
from typing import Any, Callable

import json_logic
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
    "===": lambda cmp: cmp == 0,
    "!==": lambda cmp: cmp != 0,
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
    cmp = _compare_semver(normalized_actual, normalized_target)
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


def _is_numeric_identifier(identifier: str) -> bool:
    return identifier != "" and all("0" <= char <= "9" for char in identifier)


# Numeric identifiers carry no leading zeros, so the longer run of digits is the larger number.
# Comparing them as digits rather than parsing to a fixed-width integer keeps versions that overflow
# a 64-bit integer ordered correctly.
def _compare_numeric(a: str, b: str) -> int:
    if len(a) != len(b):
        return -1 if len(a) < len(b) else 1
    return (a > b) - (a < b)


# SemVer 2.0.0 section 11.4: digits compare numerically, a numeric identifier ranks below an
# alphanumeric one, and anything else compares by ASCII order.
def _compare_prerelease_identifier(a: str, b: str) -> int:
    a_numeric, b_numeric = _is_numeric_identifier(a), _is_numeric_identifier(b)
    if a_numeric and b_numeric:
        return _compare_numeric(a, b)
    if a_numeric:
        return -1
    if b_numeric:
        return 1
    return (a > b) - (a < b)


# Ordering per SemVer 2.0.0 section 11. Both operands have already been normalized and matched
# against the official regex, so the core holds exactly three numeric identifiers and every
# prerelease field is well-formed; the split needs no error path.
def _compare_semver(a: str, b: str) -> int:
    a_core, a_prerelease = _split_semver(a)
    b_core, b_prerelease = _split_semver(b)

    for a_part, b_part in zip(a_core, b_core):
        result = _compare_numeric(a_part, b_part)
        if result:
            return result

    # A prerelease ranks below the release it belongs to (section 11.3).
    if not a_prerelease and not b_prerelease:
        return 0
    if not a_prerelease:
        return 1
    if not b_prerelease:
        return -1

    for a_field, b_field in zip(a_prerelease, b_prerelease):
        result = _compare_prerelease_identifier(a_field, b_field)
        if result:
            return result
    # Every field so far is equal, so the longer list wins (section 11.4.4).
    return (len(a_prerelease) > len(b_prerelease)) - (
        len(a_prerelease) < len(b_prerelease)
    )


# Strip optional build metadata and separate the core version from pre-release identifiers
def _split_semver(version: str) -> tuple[list[str], list[str]]:
    plus = version.find("+")
    if plus != -1:
        version = version[:plus]
    dash = version.find("-")
    if dash == -1:
        return version.split("."), []
    return version[:dash].split("."), version[dash + 1 :].split(".")


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
