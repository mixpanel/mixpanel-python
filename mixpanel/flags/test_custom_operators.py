import json_logic
import pytest

import mixpanel.flags.custom_operators  # noqa: F401  (registers the operators)
from mixpanel.flags.custom_operators import datetime_compare, semver_compare


def var_node(key):
    return {"var": key}


def semver_rule(key, sym, target):
    return {"semver_compare": [var_node(key), sym, target]}


def datetime_rule(key, sym, target):
    return {"datetime_compare": [var_node(key), sym, target]}


def custom_between(op, key, lo, hi):
    return {
        "and": [
            {op: [var_node(key), ">=", lo]},
            {op: [var_node(key), "<=", hi]},
        ]
    }


def datetime_between(key, lo, hi):
    return {
        "and": [
            {"datetime_compare": [var_node(key), ">=", lo]},
            {"datetime_compare": [var_node(key), "<=", hi]},
        ]
    }


SEMVER_CASES = [
    (
        "is, equal",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "1.2.3"},
        True,
    ),
    (
        "is, not equal",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "1.2.4"},
        False,
    ),
    (
        "is not",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "1.2.4"},
        True,
    ),
    (
        "less than, patch",
        semver_rule("app_version", "<", "1.2.3"),
        {"app_version": "1.2.2"},
        True,
    ),
    (
        "less than, false",
        semver_rule("app_version", "<", "1.2.3"),
        {"app_version": "1.2.3"},
        False,
    ),
    (
        "less or equal, boundary",
        semver_rule("app_version", "<=", "1.2.3"),
        {"app_version": "1.2.3"},
        True,
    ),
    (
        "greater than, minor",
        semver_rule("app_version", ">", "1.2.3"),
        {"app_version": "1.3.0"},
        True,
    ),
    (
        "greater or equal, boundary",
        semver_rule("app_version", ">=", "1.2.3"),
        {"app_version": "1.2.3"},
        True,
    ),
    (
        "double-digit ordering (not lexical)",
        semver_rule("app_version", ">", "1.9.0"),
        {"app_version": "1.10.0"},
        True,
    ),
    (
        "prerelease precedes release",
        semver_rule("app_version", "<", "1.0.0"),
        {"app_version": "1.0.0-alpha"},
        True,
    ),
    (
        "lenient v-prefix",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "v1.2.3"},
        True,
    ),
    (
        "lenient uppercase V-prefix",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "V1.2.3"},
        True,
    ),
    (
        "v-prefix keeps prerelease",
        semver_rule("app_version", "<", "1.0.0"),
        {"app_version": "v1.0.0-alpha"},
        True,
    ),
    (
        "v-prefix, not equal",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "v1.2.4"},
        True,
    ),
    (
        "v-prefix, at or below",
        semver_rule("app_version", "<=", "1.2.3"),
        {"app_version": "v1.2.3"},
        True,
    ),
    (
        "v-prefix, greater",
        semver_rule("app_version", ">", "1.2.3"),
        {"app_version": "v1.2.4"},
        True,
    ),
    (
        "v-prefix, at or above",
        semver_rule("app_version", ">=", "1.2.3"),
        {"app_version": "v1.2.3"},
        True,
    ),
    (
        "lenient minor-only target",
        semver_rule("app_version", "=", "1.2"),
        {"app_version": "1.2.0"},
        True,
    ),
    # Every symbol is asserted in both directions.
    (
        "is not, equal",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "1.2.3"},
        False,
    ),
    (
        "less or equal, above",
        semver_rule("app_version", "<=", "1.2.3"),
        {"app_version": "1.2.4"},
        False,
    ),
    (
        "greater than, below",
        semver_rule("app_version", ">", "1.2.3"),
        {"app_version": "1.2.2"},
        False,
    ),
    (
        "greater or equal, below",
        semver_rule("app_version", ">=", "1.2.3"),
        {"app_version": "1.2.2"},
        False,
    ),
    # Prerelease precedence, SemVer 2.0.0 section 11.
    (
        "prerelease alpha before beta",
        semver_rule("app_version", "<", "1.0.0-beta"),
        {"app_version": "1.0.0-alpha"},
        True,
    ),
    (
        "prerelease beta before rc1",
        semver_rule("app_version", "<", "1.0.0-rc1"),
        {"app_version": "1.0.0-beta"},
        True,
    ),
    (
        "prerelease rc1 before rc2",
        semver_rule("app_version", "<", "1.0.0-rc2"),
        {"app_version": "1.0.0-rc1"},
        True,
    ),
    (
        "more prerelease fields wins",
        semver_rule("app_version", "<", "1.0.0-alpha.1"),
        {"app_version": "1.0.0-alpha"},
        True,
    ),
    (
        "numeric identifier below alphanumeric",
        semver_rule("app_version", "<", "1.0.0-alpha.beta"),
        {"app_version": "1.0.0-alpha.1"},
        True,
    ),
    (
        "fewer fields below alphanumeric",
        semver_rule("app_version", "<", "1.0.0-alpha.beta"),
        {"app_version": "1.0.0-alpha"},
        True,
    ),
    (
        "numeric identifiers compare numerically",
        semver_rule("app_version", "<", "1.0.0-beta.11"),
        {"app_version": "1.0.0-beta.2"},
        True,
    ),
    (
        "dotted identifier ordering, letters",
        semver_rule("app_version", "<", "1.0.0-b.1"),
        {"app_version": "1.0.0-a.1"},
        True,
    ),
    (
        "dotted identifier ordering, digits",
        semver_rule("app_version", "<", "1.0.0-a.2"),
        {"app_version": "1.0.0-a.1"},
        True,
    ),
    (
        "identical prereleases are equal",
        semver_rule("app_version", "=", "1.0.0-rc1"),
        {"app_version": "1.0.0-rc1"},
        True,
    ),
    (
        "rc1 outranks dotted rc.1",
        semver_rule("app_version", ">", "1.0.0-rc.1"),
        {"app_version": "1.0.0-rc1"},
        True,
    ),
    (
        "core version dominates prerelease",
        semver_rule("app_version", ">", "1.9.9"),
        {"app_version": "2.0.0-alpha"},
        True,
    ),
    # A release outranks its own prerelease, asserted from both sides and under every symbol.
    (
        "release outranks its prerelease",
        semver_rule("app_version", ">", "1.0.0-alpha"),
        {"app_version": "1.0.0"},
        True,
    ),
    (
        "release at or above its prerelease",
        semver_rule("app_version", ">=", "1.0.0-rc1"),
        {"app_version": "1.0.0"},
        True,
    ),
    (
        "release differs from its prerelease",
        semver_rule("app_version", "!=", "1.0.0-alpha"),
        {"app_version": "1.0.0"},
        True,
    ),
    (
        "prerelease differs from its release",
        semver_rule("app_version", "!=", "1.0.0"),
        {"app_version": "1.0.0-alpha"},
        True,
    ),
    (
        "prerelease at or below its release",
        semver_rule("app_version", "<=", "1.0.0"),
        {"app_version": "1.0.0-alpha"},
        True,
    ),
    (
        "prerelease of a higher core still wins",
        semver_rule("app_version", ">", "0.9.9"),
        {"app_version": "1.0.0-alpha"},
        True,
    ),
    (
        "prerelease below the next patch",
        semver_rule("app_version", "<", "1.0.1"),
        {"app_version": "1.0.0-rc1"},
        True,
    ),
    # Prerelease identifier comparison, SemVer 2.0.0 section 11.4.
    (
        "numeric identifiers are not compared lexically",
        semver_rule("app_version", "<", "1.0.0-10"),
        {"app_version": "1.0.0-2"},
        True,
    ),
    (
        "numeric identifier ranks below alphanumeric",
        semver_rule("app_version", "<", "1.0.0-alpha"),
        {"app_version": "1.0.0-1"},
        True,
    ),
    (
        "hyphen inside an identifier sorts by ascii",
        semver_rule("app_version", "<", "1.0.0-alpha-1"),
        {"app_version": "1.0.0-alpha"},
        True,
    ),
    (
        "beta ranks below rc",
        semver_rule("app_version", "<", "1.0.0-rc.1"),
        {"app_version": "1.0.0-beta.11"},
        True,
    ),
    (
        "last prerelease ranks below the release",
        semver_rule("app_version", "<", "1.0.0"),
        {"app_version": "1.0.0-rc.1"},
        True,
    ),
    # Build metadata carries no precedence.
    (
        "build metadata ignored",
        semver_rule("app_version", "=", "1.0.0+build2"),
        {"app_version": "1.0.0+build1"},
        True,
    ),
    (
        "build metadata ignored with prerelease",
        semver_rule("app_version", "=", "1.0.0-alpha"),
        {"app_version": "1.0.0-alpha+build"},
        True,
    ),
    (
        "build metadata with hyphen ignored",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "1.2.3+build.1-2"},
        True,
    ),
    # Ignored means equal, so every symbol has to agree with that.
    (
        "build metadata leaves versions equal",
        semver_rule("app_version", "!=", "1.0.0+build2"),
        {"app_version": "1.0.0+build1"},
        False,
    ),
    (
        "build metadata is not less",
        semver_rule("app_version", "<", "1.0.0+build2"),
        {"app_version": "1.0.0+build1"},
        False,
    ),
    (
        "build metadata is not greater",
        semver_rule("app_version", ">", "1.0.0+build2"),
        {"app_version": "1.0.0+build1"},
        False,
    ),
    (
        "build metadata at or below",
        semver_rule("app_version", "<=", "1.0.0+build2"),
        {"app_version": "1.0.0+build1"},
        True,
    ),
    (
        "build metadata at or above",
        semver_rule("app_version", ">=", "1.0.0+build2"),
        {"app_version": "1.0.0+build1"},
        True,
    ),
    (
        "build metadata does not block ordering",
        semver_rule("app_version", "<", "1.0.1+build1"),
        {"app_version": "1.0.0+build9"},
        True,
    ),
    (
        "build metadata does not block reverse ordering",
        semver_rule("app_version", ">", "1.0.0+build9"),
        {"app_version": "1.0.1+build1"},
        True,
    ),
    # Partial versions keep their prerelease once zero-padded.
    (
        "partial version with prerelease",
        semver_rule("app_version", "=", "1.2.0-alpha"),
        {"app_version": "1.2-alpha"},
        True,
    ),
    (
        "partial prerelease below later minor",
        semver_rule("app_version", "<", "1.3.1"),
        {"app_version": "1.2-alpha"},
        True,
    ),
    (
        "partial prerelease below its release",
        semver_rule("app_version", "<", "1.2.0"),
        {"app_version": "1.2-alpha"},
        True,
    ),
    (
        "major-only with prerelease",
        semver_rule("app_version", "<", "1.0.0"),
        {"app_version": "1-rc1"},
        True,
    ),
    # An empty prerelease is invalid, so it is rejected rather than treated as the bare release.
    (
        "empty prerelease, no match",
        semver_rule("app_version", "=", "1.0.0"),
        {"app_version": "1.0.0-"},
        False,
    ),
    (
        "empty prerelease, not-equal also false",
        semver_rule("app_version", "!=", "1.0.0"),
        {"app_version": "1.0.0-"},
        False,
    ),
    (
        "empty prerelease on partial version, no match",
        semver_rule("app_version", "=", "1.2.0"),
        {"app_version": "1.2-"},
        False,
    ),
    (
        "empty prerelease on partial version, not-equal also false",
        semver_rule("app_version", "!=", "1.2.0"),
        {"app_version": "1.2-"},
        False,
    ),
    # Hyphens are legal inside a prerelease identifier, so these are NOT empty prereleases.
    (
        "trailing hyphen inside identifier",
        semver_rule("app_version", "<", "1.0.0"),
        {"app_version": "1.0.0-alpha-"},
        True,
    ),
    # SemVer 2.0.0 forbids leading zeros in the core, so these are rejected rather than normalized.
    (
        "leading zero in major, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "01.2.3"},
        False,
    ),
    (
        "leading zero in major, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "01.2.3"},
        False,
    ),
    (
        "leading zero in minor, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "1.02.3"},
        False,
    ),
    (
        "leading zero in minor, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "1.02.3"},
        False,
    ),
    (
        "leading zero in patch, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "1.2.03"},
        False,
    ),
    (
        "leading zero in patch, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "1.2.03"},
        False,
    ),
    (
        "leading zeros throughout, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "01.02.03"},
        False,
    ),
    (
        "leading zeros throughout, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "01.02.03"},
        False,
    ),
    # A numeric prerelease identifier may not carry a leading zero either (section 9).
    (
        "numeric prerelease with leading zero, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "1.2.3-01"},
        False,
    ),
    (
        "numeric prerelease with leading zero, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "1.2.3-01"},
        False,
    ),
    (
        "dotted numeric prerelease with leading zero, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "1.2.3-rc.01"},
        False,
    ),
    (
        "dotted numeric prerelease with leading zero, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "1.2.3-rc.01"},
        False,
    ),
    # An alphanumeric identifier may contain digits, so this one stays valid.
    (
        "alphanumeric prerelease with digits",
        semver_rule("app_version", "<", "1.2.3"),
        {"app_version": "1.2.3-rc01"},
        True,
    ),
    (
        "between, inside",
        custom_between("semver_compare", "app_version", "1.2.3", "2.0.0"),
        {"app_version": "1.5.0"},
        True,
    ),
    (
        "between, low boundary inclusive",
        custom_between("semver_compare", "app_version", "1.2.3", "2.0.0"),
        {"app_version": "1.2.3"},
        True,
    ),
    (
        "between, high boundary inclusive",
        custom_between("semver_compare", "app_version", "1.2.3", "2.0.0"),
        {"app_version": "2.0.0"},
        True,
    ),
    (
        "between, below",
        custom_between("semver_compare", "app_version", "1.2.3", "2.0.0"),
        {"app_version": "1.0.0"},
        False,
    ),
    (
        "between, above",
        custom_between("semver_compare", "app_version", "1.2.3", "2.0.0"),
        {"app_version": "2.0.1"},
        False,
    ),
    # A prerelease sits below its own release, which decides both boundary cases.
    (
        "between, prerelease inside",
        custom_between("semver_compare", "app_version", "1.2.3", "2.0.0"),
        {"app_version": "1.5.0-rc1"},
        True,
    ),
    (
        "between, prerelease below the high bound",
        custom_between("semver_compare", "app_version", "1.2.3", "2.0.0"),
        {"app_version": "2.0.0-rc1"},
        True,
    ),
    (
        "between, prerelease of the low bound falls out",
        custom_between("semver_compare", "app_version", "1.2.3", "2.0.0"),
        {"app_version": "1.2.3-rc1"},
        False,
    ),
    (
        "between, invalid version",
        custom_between("semver_compare", "app_version", "1.2.3", "2.0.0"),
        {"app_version": "not-a-version"},
        False,
    ),
    (
        "between, single-point range",
        custom_between("semver_compare", "app_version", "1.2.3", "1.2.3"),
        {"app_version": "1.2.3"},
        True,
    ),
    # Fail-closed: unparseable or missing values never match.
    (
        "invalid actual, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "not-a-version"},
        False,
    ),
    (
        "non-string actual, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": 123},
        False,
    ),
    ("missing property, no match", semver_rule("app_version", "=", "1.2.3"), {}, False),
    # A malformed version must never be padded or coerced into a real one. Both symbols are
    # asserted so that "accepted at all" is observable rather than masked by a single false.
    (
        "empty version, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": ""},
        False,
    ),
    (
        "empty version, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": ""},
        False,
    ),
    (
        "bare v, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "v"},
        False,
    ),
    (
        "bare v, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "v"},
        False,
    ),
    (
        "leading separator, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "-1.2.3"},
        False,
    ),
    (
        "leading separator, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "-1.2.3"},
        False,
    ),
    (
        "trailing dot, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "1."},
        False,
    ),
    (
        "trailing dot, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "1."},
        False,
    ),
    (
        "trailing dot after patch, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "1.2.3."},
        False,
    ),
    (
        "trailing dot after patch, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "1.2.3."},
        False,
    ),
    (
        "empty middle segment, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "1..2"},
        False,
    ),
    (
        "empty middle segment, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "1..2"},
        False,
    ),
    (
        "four components, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "1.2.3.4"},
        False,
    ),
    (
        "four components, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "1.2.3.4"},
        False,
    ),
    (
        "range prefix, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "^1.2.3"},
        False,
    ),
    (
        "range prefix, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "^1.2.3"},
        False,
    ),
    (
        "version inside text, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "abc1.2.3"},
        False,
    ),
    (
        "version inside text, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "abc1.2.3"},
        False,
    ),
    (
        "empty build metadata, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "1.2.3+"},
        False,
    ),
    (
        "empty build metadata, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "1.2.3+"},
        False,
    ),
    (
        "empty prerelease identifier, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "1.2.3-alpha..1"},
        False,
    ),
    (
        "empty prerelease identifier, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "1.2.3-alpha..1"},
        False,
    ),
    (
        "lone dot prerelease, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "1.2.3-."},
        False,
    ),
    (
        "lone dot prerelease, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "1.2.3-."},
        False,
    ),
    (
        "underscore in prerelease, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "1.2.3-ALPHA_BETA"},
        False,
    ),
    (
        "underscore in prerelease, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "1.2.3-ALPHA_BETA"},
        False,
    ),
    (
        "doubled v-prefix, no match",
        semver_rule("app_version", "=", "1.2.3"),
        {"app_version": "vv1.2.3"},
        False,
    ),
    (
        "doubled v-prefix, not-equal also false",
        semver_rule("app_version", "!=", "1.2.3"),
        {"app_version": "vv1.2.3"},
        False,
    ),
]

# Epoch-millisecond constants (UTC instants) used as datetime targets.
JUL16_MS = 1_784_160_000_000  # 2026-07-16T00:00:00Z
JAN1_MS = 1_767_225_600_000  # 2026-01-01T00:00:00Z
DEC31_MS = 1_798_675_200_000  # 2026-12-31T00:00:00Z
JUL16_END_MS = 1_784_246_399_999  # 2026-07-16T23:59:59.999Z
LEAP_DAY_MS = 1_709_164_800_000  # 2024-02-29T00:00:00Z
JUL16_INDIA_MS = 1_784_140_200_000  # 2026-07-16T00:00:00+05:30
JUL16_PACIFIC_MS = 1_784_188_800_000  # 2026-07-16T00:00:00-08:00

DATETIME_CASES = [
    # Asymmetric contract: subject (runtime var) is a strict RFC3339 string, target is epoch ms.
    (
        "before, true",
        datetime_rule("signup", "<", JUL16_MS),
        {"signup": "2026-07-15T00:00:00Z"},
        True,
    ),
    (
        "before, false",
        datetime_rule("signup", "<", JUL16_MS),
        {"signup": "2026-07-16T00:00:00Z"},
        False,
    ),
    (
        "on (equal), true",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00Z"},
        True,
    ),
    (
        "not on, true",
        datetime_rule("signup", "!=", JUL16_MS),
        {"signup": "2026-07-17T00:00:00Z"},
        True,
    ),
    (
        "since (>=), boundary",
        datetime_rule("signup", ">=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00Z"},
        True,
    ),
    (
        "after (>), true",
        datetime_rule("signup", ">", JUL16_MS),
        {"signup": "2026-07-17T00:00:00Z"},
        True,
    ),
    (
        "after (>), false",
        datetime_rule("signup", ">", JUL16_MS),
        {"signup": "2026-07-15T00:00:00Z"},
        False,
    ),
    # Every symbol is asserted in both directions.
    (
        "at or before, boundary",
        datetime_rule("signup", "<=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00Z"},
        True,
    ),
    (
        "at or before, after",
        datetime_rule("signup", "<=", JUL16_MS),
        {"signup": "2026-07-17T00:00:00Z"},
        False,
    ),
    (
        "on (equal), false",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-17T00:00:00Z"},
        False,
    ),
    (
        "not on, equal",
        datetime_rule("signup", "!=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00Z"},
        False,
    ),
    (
        "since (>=), before",
        datetime_rule("signup", ">=", JUL16_MS),
        {"signup": "2026-07-15T00:00:00Z"},
        False,
    ),
    (
        "between, inside",
        datetime_between("signup", JAN1_MS, DEC31_MS),
        {"signup": "2026-06-15T00:00:00Z"},
        True,
    ),
    (
        "between, low boundary inclusive",
        datetime_between("signup", JAN1_MS, DEC31_MS),
        {"signup": "2026-01-01T00:00:00Z"},
        True,
    ),
    (
        "between, high boundary inclusive",
        datetime_between("signup", JAN1_MS, DEC31_MS),
        {"signup": "2026-12-31T00:00:00Z"},
        True,
    ),
    (
        "between, before range",
        datetime_between("signup", JAN1_MS, DEC31_MS),
        {"signup": "2025-12-31T00:00:00Z"},
        False,
    ),
    (
        "between, after range",
        datetime_between("signup", JAN1_MS, DEC31_MS),
        {"signup": "2027-01-01T00:00:00Z"},
        False,
    ),
    (
        "negative epoch-ms target resolves to -1s",
        datetime_rule("signup", "=", -1_500),
        {"signup": "1969-12-31T23:59:59Z"},
        True,
    ),
    (
        "negative epoch-ms target, not equal",
        datetime_rule("signup", "!=", -1500),
        {"signup": "1969-12-31T23:59:59Z"},
        False,
    ),
    (
        "negative epoch-ms target, at or after",
        datetime_rule("signup", ">=", -1500),
        {"signup": "1969-12-31T23:59:59Z"},
        True,
    ),
    (
        "negative epoch-ms target, before",
        datetime_rule("signup", "<", -1500),
        {"signup": "1969-12-31T23:59:58Z"},
        True,
    ),
    (
        "negative epoch-ms target, after",
        datetime_rule("signup", ">", -2500),
        {"signup": "1969-12-31T23:59:59Z"},
        True,
    ),
    (
        "subject floors, it does not truncate",
        datetime_rule("signup", "=", -2000),
        {"signup": "1969-12-31T23:59:58.500Z"},
        True,
    ),
    (
        "subject floors, not to -1s",
        datetime_rule("signup", "!=", -1000),
        {"signup": "1969-12-31T23:59:58.500Z"},
        True,
    ),
    # A leap day is a real date.
    (
        "leap day",
        datetime_rule("signup", "=", LEAP_DAY_MS),
        {"signup": "2024-02-29T00:00:00Z"},
        True,
    ),
    # Time-zone offsets change the instant.
    (
        "offset with half-hour minutes",
        datetime_rule("signup", "=", JUL16_INDIA_MS),
        {"signup": "2026-07-16T00:00:00+05:30"},
        True,
    ),
    (
        "rfc3339 subject with offset",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16T02:00:00+02:00"},
        True,
    ),
    (
        "positive offset precedes utc midnight",
        datetime_rule("signup", "<", JUL16_MS),
        {"signup": "2026-07-16T00:00:00+05:30"},
        True,
    ),
    (
        "negative offset",
        datetime_rule("signup", "=", JUL16_PACIFIC_MS),
        {"signup": "2026-07-16T00:00:00-08:00"},
        True,
    ),
    (
        "negative offset follows utc midnight",
        datetime_rule("signup", ">", JUL16_MS),
        {"signup": "2026-07-16T00:00:00-08:00"},
        True,
    ),
    (
        "zero offset equals Z",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00+00:00"},
        True,
    ),
    # Sub-second precision is dropped, on both sides. The end-of-day rows are the window the UI
    # emits for a single date, whose upper bound carries .999.
    (
        "one-digit fraction",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00.5Z"},
        True,
    ),
    (
        "three-digit fraction",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00.500Z"},
        True,
    ),
    (
        "six-digit fraction",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00.123456Z"},
        True,
    ),
    (
        "nine-digit fraction",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00.999999999Z"},
        True,
    ),
    (
        "zero fraction",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00.0Z"},
        True,
    ),
    (
        "fractional seconds truncated",
        datetime_rule("signup", ">=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00.500Z"},
        True,
    ),
    (
        "end-of-day target drops its .999",
        datetime_rule("signup", "=", JUL16_END_MS),
        {"signup": "2026-07-16T23:59:59Z"},
        True,
    ),
    (
        "end-of-day target is an inclusive bound",
        datetime_rule("signup", "<=", JUL16_END_MS),
        {"signup": "2026-07-16T23:59:59Z"},
        True,
    ),
    (
        "end-of-day, fractional subject too",
        datetime_rule("signup", "=", JUL16_END_MS),
        {"signup": "2026-07-16T23:59:59.999Z"},
        True,
    ),
    (
        "end-of-day inclusive, fractional subject",
        datetime_rule("signup", "<=", JUL16_END_MS),
        {"signup": "2026-07-16T23:59:59.999Z"},
        True,
    ),
    # Fractional on both sides: the shape the UI actually round-trips.
    # Trimming and lowercasing.
    (
        "lowercased subject with fraction",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16t00:00:00.500z"},
        True,
    ),
    (
        "lowercased subject with offset",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16t02:00:00+02:00"},
        True,
    ),
    (
        "whitespace-padded subject",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": " 2026-07-16T00:00:00Z "},
        True,
    ),
    (
        "lowercased rfc3339 subject",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16t00:00:00z"},
        True,
    ),
    # Shape violations, asserted under both = and != so that "accepted at all" is observable.
    # RFC 3339 also permits 24:00:00 as end-of-day. Platforms disagree on it, so no vector
    # asserts it either way.
    (
        "one-digit month, no match",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-7-16T00:00:00Z"},
        False,
    ),
    (
        "one-digit month, not-equal also false",
        datetime_rule("signup", "!=", JUL16_MS),
        {"signup": "2026-7-16T00:00:00Z"},
        False,
    ),
    (
        "space separator, no match",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16 00:00:00Z"},
        False,
    ),
    (
        "space separator, not-equal also false",
        datetime_rule("signup", "!=", JUL16_MS),
        {"signup": "2026-07-16 00:00:00Z"},
        False,
    ),
    (
        "missing zone, no match",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00"},
        False,
    ),
    (
        "missing zone, not-equal also false",
        datetime_rule("signup", "!=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00"},
        False,
    ),
    (
        "empty fraction, no match",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00.Z"},
        False,
    ),
    (
        "empty fraction, not-equal also false",
        datetime_rule("signup", "!=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00.Z"},
        False,
    ),
    (
        "offset without colon, no match",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00+0200"},
        False,
    ),
    (
        "offset without colon, not-equal also false",
        datetime_rule("signup", "!=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00+0200"},
        False,
    ),
    (
        "short offset, no match",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00+02"},
        False,
    ),
    (
        "short offset, not-equal also false",
        datetime_rule("signup", "!=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00+02"},
        False,
    ),
    (
        "trailing junk, no match",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00Zextra"},
        False,
    ),
    (
        "trailing junk, not-equal also false",
        datetime_rule("signup", "!=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00Zextra"},
        False,
    ),
    (
        "basic format, no match",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "20260716T000000Z"},
        False,
    ),
    (
        "basic format, not-equal also false",
        datetime_rule("signup", "!=", JUL16_MS),
        {"signup": "20260716T000000Z"},
        False,
    ),
    (
        "zone after lowercase z, no match",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00z00:00"},
        False,
    ),
    (
        "zone after lowercase z, not-equal also false",
        datetime_rule("signup", "!=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00z00:00"},
        False,
    ),
    (
        "comma fractional separator, no match",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00,5Z"},
        False,
    ),
    (
        "comma fractional separator, not-equal also false",
        datetime_rule("signup", "!=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00,5Z"},
        False,
    ),
    # Fail-closed: subject must be an RFC3339 string, target must be an epoch-ms number.
    (
        "numeric subject, no match",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": JUL16_MS},
        False,
    ),
    (
        "negative epoch-ms target resolves to -1s",
        datetime_rule("signup", "=", -1500),
        {"signup": "1969-12-31T23:59:59Z"},
        True,
    ),
    (
        "target beyond representable range, no match",
        {"datetime_compare": [var_node("signup"), "=", 1e308]},
        {"signup": "2026-07-16T00:00:00Z"},
        False,
    ),
    (
        "target beyond representable range, greater-than also false",
        {"datetime_compare": [var_node("signup"), ">", 1e308]},
        {"signup": "2026-07-16T00:00:00Z"},
        False,
    ),
    (
        "target beyond representable range, less-than also false",
        {"datetime_compare": [var_node("signup"), "<", 1e308]},
        {"signup": "2026-07-16T00:00:00Z"},
        False,
    ),
    (
        "bare date subject, no match",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16"},
        False,
    ),
    (
        "bare date subject, not-equal also false",
        datetime_rule("signup", "!=", JUL16_MS),
        {"signup": "2026-07-16"},
        False,
    ),
    (
        "zoneless datetime subject, no match",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "2026-07-16T00:00:00"},
        False,
    ),
    (
        "non-datetime string, no match",
        datetime_rule("signup", "=", JUL16_MS),
        {"signup": "yesterday"},
        False,
    ),
    ("missing property, no match", datetime_rule("signup", "=", JUL16_MS), {}, False),
]


@pytest.mark.parametrize(
    ("rule", "data", "want"),
    [(rule, data, want) for _, rule, data, want in SEMVER_CASES],
    ids=[name for name, *_ in SEMVER_CASES],
)
def test_semver_compare_operator(rule, data, want):
    assert bool(json_logic.jsonLogic(rule, data)) is want


@pytest.mark.parametrize(
    ("rule", "data", "want"),
    [(rule, data, want) for _, rule, data, want in DATETIME_CASES],
    ids=[name for name, *_ in DATETIME_CASES],
)
def test_datetime_compare_operator(rule, data, want):
    assert bool(json_logic.jsonLogic(rule, data)) is want


# The cases below are not golden vectors. They pin fail-closed guards that are specific to this
# language — a rule shape the engine would never produce, and numeric types Python alone can hand the
# operator — so they are asserted here rather than shared across SDKs.


@pytest.mark.parametrize(
    ("values", "want"),
    [
        pytest.param(("1.2.3", "="), False, id="too few operands"),
        pytest.param(("1.2.3", "=", "1.2.3", "extra"), False, id="too many operands"),
        pytest.param(("1.2.3", 5, "1.2.3"), False, id="non-string symbol"),
    ],
)
def test_semver_compare_rejects_malformed_operands(values, want):
    assert semver_compare(*values) is want


@pytest.mark.parametrize(
    ("values", "want"),
    [
        pytest.param(("2026-07-16T00:00:00Z", "="), False, id="too few operands"),
        pytest.param(
            ("2026-07-16T00:00:00Z", "=", JUL16_MS, "extra"),
            False,
            id="too many operands",
        ),
        pytest.param(
            ("2026-07-16T00:00:00Z", 5, JUL16_MS), False, id="non-string symbol"
        ),
    ],
)
def test_datetime_compare_rejects_malformed_operands(values, want):
    assert datetime_compare(*values) is want


@pytest.mark.parametrize(
    ("target", "want"),
    [
        pytest.param(
            True, False, id="bool is an int subclass and must not pass as a target"
        ),
        pytest.param("2026-07-16T00:00:00Z", False, id="string target"),
        pytest.param(float("inf"), False, id="infinite target"),
        pytest.param(float("nan"), False, id="nan target"),
    ],
)
def test_datetime_compare_rejects_non_epoch_targets(target, want):
    assert datetime_compare("2026-07-16T00:00:00Z", "=", target) is want


def test_datetime_compare_rejects_a_date_that_cannot_exist():
    # The pattern only guarantees two digits per field, so the parser is what rejects 30 February.
    assert datetime_compare("2026-02-30T00:00:00Z", "=", JUL16_MS) is False
