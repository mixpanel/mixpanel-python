import json
import pathlib

import json_logic
import pytest

import mixpanel.flags.custom_operators  # noqa: F401  (registers the operators)
from mixpanel.flags.custom_operators import datetime_compare, semver_compare

# The golden vectors are the cross-SDK contract for the custom operators; the canonical copy and its
# README live in the analytics monorepo. Cases run through json_logic so that operator registration is
# covered alongside the comparison itself.
_TEST_DATA = pathlib.Path(__file__).parent / "test-data"

# 2026-07-16T00:00:00Z, as epoch milliseconds.
JUL16_MS = 1_784_160_000_000

# The property key the vectors are evaluated against. It is plumbing the test supplies, so any name
# works as long as the rule and the data agree on it.
_VECTOR_KEY = "value"


def _rule_for(operator, symbol, target):
    """Build the rule a case evaluates: {"<op>_compare": [{"var": key}, symbol, target]}."""
    return {f"{operator}_compare": [{"var": _VECTOR_KEY}, symbol, target]}


def _data_for(subject):
    """Build the event the rule reads from, omitting the key entirely for an unset property."""
    return {} if subject is None else {_VECTOR_KEY: subject}


def load_vectors(operator):
    """Read a golden-vector file. String entries are headings, list entries are cases."""
    entries = json.loads((_TEST_DATA / f"{operator}_compare_tests.json").read_text())

    section = ""
    cases = []
    for index, entry in enumerate(entries):
        if isinstance(entry, str):
            section = entry
            continue
        subject, symbol, target, want = entry
        cases.append(
            pytest.param(
                _rule_for(operator, symbol, target),
                _data_for(subject),
                want,
                id=f"{index} {section}: {json.dumps(subject)} {symbol} {json.dumps(target)}",
            )
        )
    return cases


SEMVER_CASES = load_vectors("semver")
DATETIME_CASES = load_vectors("datetime")


@pytest.mark.parametrize(("rule", "data", "want"), SEMVER_CASES)
def test_semver_compare_operator(rule, data, want):
    assert bool(json_logic.jsonLogic(rule, data)) is want


@pytest.mark.parametrize(("rule", "data", "want"), DATETIME_CASES)
def test_datetime_compare_operator(rule, data, want):
    assert bool(json_logic.jsonLogic(rule, data)) is want


# An unset property must produce an event with no key at all, rather than a key holding a None. Both
# spellings fail closed, so the vectors alone cannot tell them apart.
def test_unset_subject_omits_the_property():
    assert _data_for(None) == {}
    assert _data_for("1.2.3") == {_VECTOR_KEY: "1.2.3"}


# The cases below are not golden vectors. They pin fail-closed guards that are specific to this
# language — a rule shape the engine would never produce, and numeric types Python alone can hand the
# operator — so they are asserted here rather than shared across SDKs.


@pytest.mark.parametrize(
    ("values", "want"),
    [
        pytest.param(("1.2.3", "==="), False, id="too few operands"),
        pytest.param(("1.2.3", "===", "1.2.3", "extra"), False, id="too many operands"),
        pytest.param(("1.2.3", 5, "1.2.3"), False, id="non-string symbol"),
    ],
)
def test_semver_compare_rejects_malformed_operands(values, want):
    assert semver_compare(*values) is want


@pytest.mark.parametrize(
    ("values", "want"),
    [
        pytest.param(("2026-07-16T00:00:00Z", "==="), False, id="too few operands"),
        pytest.param(
            ("2026-07-16T00:00:00Z", "===", JUL16_MS, "extra"),
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
    assert datetime_compare("2026-07-16T00:00:00Z", "===", target) is want


def test_datetime_compare_rejects_a_date_that_cannot_exist():
    # The pattern only guarantees two digits per field, so the parser is what rejects 30 February.
    assert datetime_compare("2026-02-30T00:00:00Z", "===", JUL16_MS) is False
