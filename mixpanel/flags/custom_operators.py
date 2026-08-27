from __future__ import annotations

import datetime
import math
import re
from typing import Any, Callable

import json_logic

_OPERAND_COUNT = 3
# Epoch milliseconds are compared as int64 elsewhere, so anything at or beyond this is out of range.
_MAX_EPOCH_MS = 2**63
# SemVer 2.0.0 requires major.minor.patch; partial versions are zero-padded to this.
_SEMVER_PARTS = 3
# Longest operand the semver regex is allowed to see. A real version never approaches this; the
# bound matches MAX_LENGTH in node-semver, and keeps an arbitrarily long property value off the
# regex regardless of how the engine schedules backtracking.
_MAX_SEMVER_LENGTH = 256
# RFC 3339 section 5.6: hours run 00 through 23 and minutes 00 through 59. These bound the UTC
# offset, whose fields no date type validates for us.
_MAX_HOUR = 23
_MAX_MINUTE = 59
# Instants are reported as whole seconds east of this.
_EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

# Using the official semantic versioning 2.0.0 regular expression to handle cross-platform validation
# differences on other SDK's. For example, some platforms allow leading zeros even though it is not valid
# as part of the Semver 2.0.0 spec. See https://semver.org/
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

# Strict RFC3339 guard for datetime strings. Every field the instant is built from is captured; the
# pattern only constrains their shape, so each one is range-checked before use. The fraction is not
# captured because whole-second semantics discard it.
_RFC3339_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
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
    if len(actual) > _MAX_SEMVER_LENGTH or len(target) > _MAX_SEMVER_LENGTH:
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


# Returns the offset in seconds east of UTC, or None when it is not a real clock offset. The pattern
# only guarantees two digits either side of the colon.
def _utc_offset_seconds(offset: str) -> int | None:
    if offset == "Z":
        return 0
    hours, minutes = int(offset[1:3]), int(offset[4:6])
    if hours > _MAX_HOUR or minutes > _MAX_MINUTE:
        return None
    seconds = hours * 3600 + minutes * 60
    return -seconds if offset[0] == "-" else seconds


def _convert_rfc3339_to_unix_seconds(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    fields = _RFC3339_RE.match(normalized)
    if not fields:
        return None
    year, month, day, hour, minute, second = (int(fields.group(i)) for i in range(1, 7))
    offset_seconds = _utc_offset_seconds(fields.group(7))
    if offset_seconds is None:
        return None
    # The pattern constrains each field to two digits, which still admits values that cannot exist,
    # such as 2026-02-30, 29 February in a common year, an hour of 24 or a minute of 99. Building a
    # datetime range-checks every one of them, leap years included, and raises rather than
    # normalizing the way a plain seconds calculation would. Note this also rejects year 0000, which
    # datetime cannot represent at all and the other SDKs accept; failing closed on it is the
    # narrowest behaviour available here.
    try:
        moment = datetime.datetime(
            year, month, day, hour, minute, second, tzinfo=datetime.timezone.utc
        )
    except ValueError:
        return None
    # The fraction is dropped rather than rounded: in an RFC 3339 string the seconds field is already
    # the floor of the instant, which is the whole-second value both sides of a comparison resolve to.
    return int((moment - _EPOCH).total_seconds()) - offset_seconds


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
