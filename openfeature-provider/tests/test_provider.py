from unittest.mock import MagicMock
import pytest
from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import ErrorCode
from openfeature.flag_evaluation import Reason

from mixpanel.flags.types import SelectedVariant
from mixpanel_openfeature import MixpanelProvider


@pytest.fixture
def mock_flags():
    flags = MagicMock()
    flags.are_flags_ready.return_value = True
    return flags


@pytest.fixture
def provider(mock_flags):
    return MixpanelProvider(mock_flags)


def setup_flag(mock_flags, flag_key, value, variant_key="variant-key"):
    """Configure mock to return a SelectedVariant with the given value."""
    mock_flags.get_variant.side_effect = (
        lambda key, fallback, ctx, report_exposure=True: (
            SelectedVariant(variant_key=variant_key, variant_value=value)
            if key == flag_key
            else fallback
        )
    )


def setup_flag_not_found(mock_flags, flag_key):
    """Configure mock to return the fallback (identity check triggers FLAG_NOT_FOUND)."""
    mock_flags.get_variant.side_effect = (
        lambda key, fallback, ctx, report_exposure=True: fallback
    )


# --- Metadata ---


def test_metadata_name(provider):
    assert provider.get_metadata().name == "mixpanel-provider"


# --- Boolean evaluation ---


def test_resolves_boolean_true(provider, mock_flags):
    setup_flag(mock_flags, "bool-flag", True)
    result = provider.resolve_boolean_details("bool-flag", False)
    assert result.value is True
    assert result.reason == Reason.STATIC
    assert result.error_code is None


def test_resolves_boolean_false(provider, mock_flags):
    setup_flag(mock_flags, "bool-flag", False)
    result = provider.resolve_boolean_details("bool-flag", True)
    assert result.value is False
    assert result.reason == Reason.STATIC


# --- String evaluation ---


def test_resolves_string(provider, mock_flags):
    setup_flag(mock_flags, "string-flag", "hello")
    result = provider.resolve_string_details("string-flag", "default")
    assert result.value == "hello"
    assert result.reason == Reason.STATIC
    assert result.error_code is None


# --- Integer evaluation ---


def test_resolves_integer(provider, mock_flags):
    setup_flag(mock_flags, "int-flag", 42)
    result = provider.resolve_integer_details("int-flag", 0)
    assert result.value == 42
    assert result.reason == Reason.STATIC
    assert result.error_code is None


def test_resolves_integer_from_float_no_fraction(provider, mock_flags):
    setup_flag(mock_flags, "int-flag", 42.0)
    result = provider.resolve_integer_details("int-flag", 0)
    assert result.value == 42
    assert isinstance(result.value, int)
    assert result.reason == Reason.STATIC


# --- Float evaluation ---


def test_resolves_float(provider, mock_flags):
    setup_flag(mock_flags, "float-flag", 3.14)
    result = provider.resolve_float_details("float-flag", 0.0)
    assert result.value == pytest.approx(3.14)
    assert result.reason == Reason.STATIC
    assert result.error_code is None


def test_resolves_float_from_integer(provider, mock_flags):
    setup_flag(mock_flags, "float-flag", 42)
    result = provider.resolve_float_details("float-flag", 0.0)
    assert result.value == 42.0
    assert isinstance(result.value, float)
    assert result.reason == Reason.STATIC


# --- Object evaluation ---


def test_resolves_object_with_dict(provider, mock_flags):
    setup_flag(mock_flags, "obj-flag", {"key": "value"})
    result = provider.resolve_object_details("obj-flag", {})
    assert result.value == {"key": "value"}
    assert result.reason == Reason.STATIC
    assert result.error_code is None


def test_resolves_object_with_list(provider, mock_flags):
    setup_flag(mock_flags, "obj-flag", [1, 2, 3])
    result = provider.resolve_object_details("obj-flag", [])
    assert result.value == [1, 2, 3]
    assert result.reason == Reason.STATIC


def test_resolves_object_with_string(provider, mock_flags):
    setup_flag(mock_flags, "obj-flag", "hello")
    result = provider.resolve_object_details("obj-flag", {})
    assert result.value == "hello"
    assert result.reason == Reason.STATIC


def test_resolves_object_with_bool(provider, mock_flags):
    setup_flag(mock_flags, "obj-flag", True)
    result = provider.resolve_object_details("obj-flag", {})
    assert result.value is True
    assert result.reason == Reason.STATIC


# --- Error: FLAG_NOT_FOUND ---


def test_flag_not_found_boolean(provider, mock_flags):
    setup_flag_not_found(mock_flags, "missing-flag")
    result = provider.resolve_boolean_details("missing-flag", True)
    assert result.value is True
    assert result.error_code == ErrorCode.FLAG_NOT_FOUND
    assert result.reason == Reason.ERROR


def test_flag_not_found_string(provider, mock_flags):
    setup_flag_not_found(mock_flags, "missing-flag")
    result = provider.resolve_string_details("missing-flag", "fallback")
    assert result.value == "fallback"
    assert result.error_code == ErrorCode.FLAG_NOT_FOUND
    assert result.reason == Reason.ERROR


def test_flag_not_found_integer(provider, mock_flags):
    setup_flag_not_found(mock_flags, "missing-flag")
    result = provider.resolve_integer_details("missing-flag", 99)
    assert result.value == 99
    assert result.error_code == ErrorCode.FLAG_NOT_FOUND
    assert result.reason == Reason.ERROR


def test_flag_not_found_float(provider, mock_flags):
    setup_flag_not_found(mock_flags, "missing-flag")
    result = provider.resolve_float_details("missing-flag", 1.5)
    assert result.value == 1.5
    assert result.error_code == ErrorCode.FLAG_NOT_FOUND
    assert result.reason == Reason.ERROR


def test_flag_not_found_object(provider, mock_flags):
    setup_flag_not_found(mock_flags, "missing-flag")
    result = provider.resolve_object_details("missing-flag", {"default": True})
    assert result.value == {"default": True}
    assert result.error_code == ErrorCode.FLAG_NOT_FOUND
    assert result.reason == Reason.ERROR


# --- Error: TYPE_MISMATCH ---


def test_type_mismatch_boolean_gets_string(provider, mock_flags):
    setup_flag(mock_flags, "string-flag", "not-a-bool")
    result = provider.resolve_boolean_details("string-flag", False)
    assert result.value is False
    assert result.error_code == ErrorCode.TYPE_MISMATCH
    assert result.reason == Reason.ERROR


def test_type_mismatch_string_gets_boolean(provider, mock_flags):
    setup_flag(mock_flags, "bool-flag", True)
    result = provider.resolve_string_details("bool-flag", "default")
    assert result.value == "default"
    assert result.error_code == ErrorCode.TYPE_MISMATCH
    assert result.reason == Reason.ERROR


def test_type_mismatch_integer_gets_string(provider, mock_flags):
    setup_flag(mock_flags, "string-flag", "not-a-number")
    result = provider.resolve_integer_details("string-flag", 0)
    assert result.value == 0
    assert result.error_code == ErrorCode.TYPE_MISMATCH
    assert result.reason == Reason.ERROR


def test_type_mismatch_float_gets_string(provider, mock_flags):
    setup_flag(mock_flags, "string-flag", "not-a-number")
    result = provider.resolve_float_details("string-flag", 0.0)
    assert result.value == 0.0
    assert result.error_code == ErrorCode.TYPE_MISMATCH
    assert result.reason == Reason.ERROR


def test_type_mismatch_integer_gets_float_with_fraction(provider, mock_flags):
    setup_flag(mock_flags, "float-flag", 3.14)
    result = provider.resolve_integer_details("float-flag", 0)
    assert result.value == 0
    assert result.error_code == ErrorCode.TYPE_MISMATCH
    assert result.reason == Reason.ERROR


def test_type_mismatch_integer_gets_boolean(provider, mock_flags):
    setup_flag(mock_flags, "bool-flag", True)
    result = provider.resolve_integer_details("bool-flag", 0)
    assert result.value == 0
    assert result.error_code == ErrorCode.TYPE_MISMATCH
    assert result.reason == Reason.ERROR


def test_type_mismatch_float_gets_boolean(provider, mock_flags):
    setup_flag(mock_flags, "bool-flag", True)
    result = provider.resolve_float_details("bool-flag", 0.0)
    assert result.value == 0.0
    assert result.error_code == ErrorCode.TYPE_MISMATCH
    assert result.reason == Reason.ERROR


# --- Error: PROVIDER_NOT_READY ---


def test_provider_not_ready_boolean(mock_flags):
    mock_flags.are_flags_ready.return_value = False
    provider = MixpanelProvider(mock_flags)
    result = provider.resolve_boolean_details("any-flag", True)
    assert result.value is True
    assert result.error_code == ErrorCode.PROVIDER_NOT_READY
    assert result.reason == Reason.ERROR


def test_provider_not_ready_string(mock_flags):
    mock_flags.are_flags_ready.return_value = False
    provider = MixpanelProvider(mock_flags)
    result = provider.resolve_string_details("any-flag", "default")
    assert result.value == "default"
    assert result.error_code == ErrorCode.PROVIDER_NOT_READY
    assert result.reason == Reason.ERROR


def test_provider_not_ready_integer(mock_flags):
    mock_flags.are_flags_ready.return_value = False
    provider = MixpanelProvider(mock_flags)
    result = provider.resolve_integer_details("any-flag", 5)
    assert result.value == 5
    assert result.error_code == ErrorCode.PROVIDER_NOT_READY
    assert result.reason == Reason.ERROR


def test_provider_not_ready_float(mock_flags):
    mock_flags.are_flags_ready.return_value = False
    provider = MixpanelProvider(mock_flags)
    result = provider.resolve_float_details("any-flag", 2.5)
    assert result.value == 2.5
    assert result.error_code == ErrorCode.PROVIDER_NOT_READY
    assert result.reason == Reason.ERROR


def test_provider_not_ready_object(mock_flags):
    mock_flags.are_flags_ready.return_value = False
    provider = MixpanelProvider(mock_flags)
    result = provider.resolve_object_details("any-flag", {"default": True})
    assert result.value == {"default": True}
    assert result.error_code == ErrorCode.PROVIDER_NOT_READY
    assert result.reason == Reason.ERROR


# --- Remote provider (no are_flags_ready) is always ready ---


def test_remote_provider_always_ready():
    remote_flags = MagicMock(spec=[])  # empty spec = no attributes
    remote_flags.get_variant = MagicMock(
        side_effect=lambda key, fallback, ctx, report_exposure=True: SelectedVariant(
            variant_key="v1", variant_value=True
        )
    )
    provider = MixpanelProvider(remote_flags)
    result = provider.resolve_boolean_details("flag", False)
    assert result.value is True
    assert result.reason == Reason.STATIC


# --- Lifecycle ---


def test_shutdown_is_noop(provider):
    provider.shutdown()  # Should not raise


# --- EvaluationContext forwarding ---


def test_forwards_targeting_key(provider, mock_flags):
    setup_flag(mock_flags, "flag", "val")
    ctx = EvaluationContext(targeting_key="user-123")
    provider.resolve_string_details("flag", "default", ctx)
    _, _, user_context = mock_flags.get_variant.call_args[0]
    assert user_context["targetingKey"] == "user-123"


def test_forwards_attributes_flat(provider, mock_flags):
    setup_flag(mock_flags, "flag", "val")
    ctx = EvaluationContext(attributes={"plan": "pro", "beta": True})
    provider.resolve_string_details("flag", "default", ctx)
    _, _, user_context = mock_flags.get_variant.call_args[0]
    assert user_context["plan"] == "pro"
    assert user_context["beta"] is True


def test_forwards_full_context(provider, mock_flags):
    setup_flag(mock_flags, "flag", "val")
    ctx = EvaluationContext(targeting_key="user-456", attributes={"tier": "enterprise"})
    provider.resolve_string_details("flag", "default", ctx)
    _, _, user_context = mock_flags.get_variant.call_args[0]
    assert user_context == {
        "targetingKey": "user-456",
        "tier": "enterprise",
    }


def test_no_context_passes_empty_dict(provider, mock_flags):
    setup_flag(mock_flags, "flag", "val")
    provider.resolve_string_details("flag", "default")
    _, _, user_context = mock_flags.get_variant.call_args[0]
    assert user_context == {}


# --- Variant key passthrough ---


def test_variant_key_present_in_boolean_resolution(provider, mock_flags):
    setup_flag(mock_flags, "bool-flag", True, variant_key="control")
    result = provider.resolve_boolean_details("bool-flag", False)
    assert result.value is True
    assert result.variant == "control"
    assert result.reason == Reason.STATIC


def test_variant_key_present_in_string_resolution(provider, mock_flags):
    setup_flag(mock_flags, "string-flag", "hello", variant_key="treatment-a")
    result = provider.resolve_string_details("string-flag", "default")
    assert result.value == "hello"
    assert result.variant == "treatment-a"
    assert result.reason == Reason.STATIC


def test_variant_key_present_in_integer_resolution(provider, mock_flags):
    setup_flag(mock_flags, "int-flag", 42, variant_key="v2")
    result = provider.resolve_integer_details("int-flag", 0)
    assert result.value == 42
    assert result.variant == "v2"
    assert result.reason == Reason.STATIC


def test_variant_key_present_in_float_resolution(provider, mock_flags):
    setup_flag(mock_flags, "float-flag", 3.14, variant_key="v3")
    result = provider.resolve_float_details("float-flag", 0.0)
    assert result.value == pytest.approx(3.14)
    assert result.variant == "v3"
    assert result.reason == Reason.STATIC


def test_variant_key_present_in_object_resolution(provider, mock_flags):
    setup_flag(mock_flags, "obj-flag", {"key": "value"}, variant_key="v4")
    result = provider.resolve_object_details("obj-flag", {})
    assert result.value == {"key": "value"}
    assert result.variant == "v4"
    assert result.reason == Reason.STATIC


# --- SDK exception handling ---


def test_sdk_exception_returns_default_boolean(provider, mock_flags):
    mock_flags.get_variant.side_effect = RuntimeError("SDK failure")
    result = provider.resolve_boolean_details("flag", True)
    assert result.value is True
    assert result.error_code == ErrorCode.GENERAL
    assert result.reason == Reason.ERROR


def test_sdk_exception_returns_default_string(provider, mock_flags):
    mock_flags.get_variant.side_effect = RuntimeError("SDK failure")
    result = provider.resolve_string_details("flag", "fallback")
    assert result.value == "fallback"
    assert result.error_code == ErrorCode.GENERAL
    assert result.reason == Reason.ERROR


def test_sdk_exception_returns_default_integer(provider, mock_flags):
    mock_flags.get_variant.side_effect = RuntimeError("SDK failure")
    result = provider.resolve_integer_details("flag", 99)
    assert result.value == 99
    assert result.error_code == ErrorCode.GENERAL
    assert result.reason == Reason.ERROR


# --- Null variant key ---


def test_null_variant_key_boolean(provider, mock_flags):
    setup_flag(mock_flags, "flag", True, variant_key=None)
    result = provider.resolve_boolean_details("flag", False)
    assert result.value is True
    assert result.variant is None
    assert result.reason == Reason.STATIC
    assert result.error_code is None


def test_null_variant_key_string(provider, mock_flags):
    setup_flag(mock_flags, "flag", "hello", variant_key=None)
    result = provider.resolve_string_details("flag", "default")
    assert result.value == "hello"
    assert result.variant is None
    assert result.reason == Reason.STATIC
    assert result.error_code is None


def test_null_variant_key_object(provider, mock_flags):
    setup_flag(mock_flags, "flag", {"key": "value"}, variant_key=None)
    result = provider.resolve_object_details("flag", {})
    assert result.value == {"key": "value"}
    assert result.variant is None
    assert result.reason == Reason.STATIC
    assert result.error_code is None
