from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from itertools import chain, repeat
from typing import Any
from unittest.mock import Mock, patch

import httpx
import pytest
import respx

from mixpanel import Mixpanel
from mixpanel.credentials import ServiceAccountCredentials
from mixpanel.identity import MixpanelIdentity

from .local_feature_flags import LocalFeatureFlagsProvider
from .types import (
    ExperimentationFlag,
    ExperimentationFlags,
    FlagTestUsers,
    LocalFlagsConfig,
    RemoteFlagsConfig,
    Rollout,
    RuleSet,
    SelectedVariant,
    Variant,
    VariantOverride,
    VariantSource,
)

TEST_FLAG_KEY = "test_flag"
DISTINCT_ID = "user123"
USER_CONTEXT = {"distinct_id": DISTINCT_ID}


def create_test_flag(
    flag_key: str = TEST_FLAG_KEY,
    context: str = "distinct_id",
    variants: list[Variant] | None = None,
    variant_override: VariantOverride | None = None,
    rollout_percentage: float = 100.0,
    runtime_evaluation_legacy_definition: dict | None = None,
    runtime_evaluation_rule: dict | None = None,
    test_users: dict[str, str] | None = None,
    experiment_id: str | None = None,
    is_experiment_active: bool | None = None,
    variant_splits: dict[str, float] | None = None,
    hash_salt: str | None = None,
) -> ExperimentationFlag:
    if variants is None:
        variants = [
            Variant(key="control", value="control", is_control=True, split=50.0),
            Variant(key="treatment", value="treatment", is_control=False, split=50.0),
        ]

    rollouts = [
        Rollout(
            rollout_percentage=rollout_percentage,
            runtime_evaluation_definition=runtime_evaluation_legacy_definition,
            runtime_evaluation_rule=runtime_evaluation_rule,
            variant_override=variant_override,
            variant_splits=variant_splits,
        )
    ]

    test_config = None
    if test_users:
        test_config = FlagTestUsers(users=test_users)

    ruleset = RuleSet(variants=variants, rollout=rollouts, test=test_config)

    return ExperimentationFlag(
        id="test-id",
        name="Test Flag",
        key=flag_key,
        status="active",
        project_id=123,
        ruleset=ruleset,
        context=context,
        experiment_id=experiment_id,
        is_experiment_active=is_experiment_active,
        hash_salt=hash_salt,
    )


def create_flags_response(flags: list[ExperimentationFlag]) -> httpx.Response:
    if flags is None:
        flags = []
    response_data = asdict(ExperimentationFlags(flags=flags))
    return httpx.Response(status_code=200, json=response_data)


@pytest.mark.asyncio
class TestLocalFeatureFlagsProviderAsync:
    @pytest.fixture(autouse=True)
    async def setup_method(self):
        self._mock_tracker = Mock()

        config_no_polling = LocalFlagsConfig(enable_polling=False)
        self._flags = LocalFeatureFlagsProvider(
            "test-token", config_no_polling, "1.0.0", self._mock_tracker
        )

        config_with_polling = LocalFlagsConfig(
            enable_polling=True, polling_interval_in_seconds=0
        )
        self._flags_with_polling = LocalFeatureFlagsProvider(
            "test-token", config_with_polling, "1.0.0", self._mock_tracker
        )

        yield

        await self._flags.__aexit__(None, None, None)
        await self._flags_with_polling.__aexit__(None, None, None)

    async def setup_flags(self, flags: list[ExperimentationFlag]):
        respx.get("https://api.mixpanel.com/flags/definitions").mock(
            return_value=create_flags_response(flags)
        )
        await self._flags.astart_polling_for_definitions()

    async def setup_flags_with_polling(
        self, flags_in_order: list[list[ExperimentationFlag]] = [[]]
    ):
        responses = [create_flags_response(flag) for flag in flags_in_order]

        respx.get("https://api.mixpanel.com/flags/definitions").mock(
            side_effect=chain(
                responses,
                repeat(responses[-1]),
            )
        )
        await self._flags_with_polling.astart_polling_for_definitions()

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_no_flag_definitions(self):
        await self.setup_flags([])
        result = self._flags.get_variant_value(
            "nonexistent_flag", "control", USER_CONTEXT
        )
        assert result == "control"

    @respx.mock
    async def test_get_variant_value_returns_fallback_if_flag_definition_call_fails(
        self,
    ):
        respx.get("https://api.mixpanel.com/flags/definitions").mock(
            return_value=httpx.Response(status_code=500)
        )

        await self._flags.astart_polling_for_definitions()
        result = self._flags.get_variant_value(
            "nonexistent_flag", "control", USER_CONTEXT
        )
        assert result == "control"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_flag_does_not_exist(self):
        other_flag = create_test_flag("other_flag")
        await self.setup_flags([other_flag])
        result = self._flags.get_variant_value(
            "nonexistent_flag", "control", USER_CONTEXT
        )
        assert result == "control"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_no_context(self):
        flag = create_test_flag(context="distinct_id")
        await self.setup_flags([flag])
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", {})
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_wrong_context_key(self):
        flag = create_test_flag(context="user_id")
        await self.setup_flags([flag])
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", USER_CONTEXT)
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_returns_test_user_variant_when_configured(self):
        variants = [
            Variant(key="control", value="false", is_control=True, split=50.0),
            Variant(key="treatment", value="true", is_control=False, split=50.0),
        ]
        flag = create_test_flag(
            variants=variants, test_users={"test_user": "treatment"}
        )

        await self.setup_flags([flag])
        result = self._flags.get_variant_value(
            TEST_FLAG_KEY, "control", {"distinct_id": "test_user"}
        )
        assert result == "true"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_test_user_variant_not_configured(
        self,
    ):
        variants = [
            Variant(key="control", value="false", is_control=True, split=50.0),
            Variant(key="treatment", value="true", is_control=False, split=50.0),
        ]
        flag = create_test_flag(
            variants=variants, test_users={"test_user": "nonexistent_variant"}
        )
        await self.setup_flags([flag])
        with patch("mixpanel.flags.utils.normalized_hash") as mock_hash:
            mock_hash.return_value = 0.5
            result = self._flags.get_variant_value(
                TEST_FLAG_KEY, "fallback", {"distinct_id": "test_user"}
            )
            assert result == "false"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_rollout_percentage_zero(
        self,
    ):
        flag = create_test_flag(rollout_percentage=0.0)
        await self.setup_flags([flag])
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", USER_CONTEXT)
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_returns_variant_when_rollout_percentage_hundred(
        self,
    ):
        flag = create_test_flag(rollout_percentage=100.0)
        await self.setup_flags([flag])
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", USER_CONTEXT)
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_respects_runtime_evaluation_rule_satisfied(self):
        runtime_eval = {"==": [{"var": "plan"}, "premium"]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties(
            {
                "plan": "premium",
            }
        )
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_respects_runtime_evaluation_rule_not_satisfied(
        self,
    ):
        runtime_eval = {"==": [{"var": "plan"}, "premium"]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties(
            {
                "plan": "basic",
            }
        )
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_invalid_runtime_rule_resorts_to_fallback(self):
        runtime_eval = {"=oops=": [{"var": "plan"}, "premium"]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties(
            {
                "plan": "basic",
            }
        )
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_respects_runtime_evaluation_rule_not_satisfied_when_no_custom_properties_provided(
        self,
    ):
        runtime_eval = {"=": [{"var": "plan"}, "premium"]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties({})
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_respects_runtime_evaluation_rule_caseinsensitive_param_value__satisfied(
        self,
    ):
        runtime_eval = {"==": [{"var": "plan"}, "premium"]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties(
            {
                "plan": "PremIum",
            }
        )
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_respects_runtime_evaluation_rule_caseinsensitive_varnames__satisfied(
        self,
    ):
        runtime_eval = {"==": [{"var": "Plan"}, "premium"]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties(
            {
                "plan": "premium",
            }
        )
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_respects_runtime_evaluation_rule_caseinsensitive_rule_value__satisfied(
        self,
    ):
        runtime_eval = {"==": [{"var": "plan"}, "pREMIUm"]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties(
            {
                "plan": "premium",
            }
        )
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_respects_runtime_evaluation_rule_contains_satisfied(
        self,
    ):
        runtime_eval = {"in": ["Springfield", {"var": "url"}]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties(
            {
                "url": "https://helloworld.com/Springfield/all-about-it",
            }
        )
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_respects_runtime_evaluation_rule_contains_not_satisfied(
        self,
    ):
        runtime_eval = {"in": ["Springfield", {"var": "url"}]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties(
            {
                "url": "https://helloworld.com/Boston/all-about-it",
            }
        )
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_respects_runtime_evaluation_rule_multi_value_satisfied(
        self,
    ):
        runtime_eval = {"in": [{"var": "name"}, ["a", "b", "c", "all-from-the-ui"]]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties(
            {
                "name": "b",
            }
        )
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_respects_runtime_evaluation_rule_multi_value_not_satisfied(
        self,
    ):
        runtime_eval = {"in": [{"var": "name"}, ["a", "b", "c", "all-from-the-ui"]]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties(
            {
                "name": "d",
            }
        )
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_respects_runtime_evaluation_rule_and_satisfied(
        self,
    ):
        runtime_eval = {
            "and": [
                {"==": [{"var": "name"}, "Johannes"]},
                {"==": [{"var": "country"}, "Deutschland"]},
            ]
        }
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties(
            {
                "name": "Johannes",
                "country": "Deutschland",
            }
        )
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_respects_runtime_evaluation_rule_and_not_satisfied(
        self,
    ):
        runtime_eval = {
            "and": [
                {"==": [{"var": "name"}, "Johannes"]},
                {"==": [{"var": "country"}, "Deutschland"]},
            ]
        }
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties(
            {
                "name": "Johannes",
                "country": "France",
            }
        )
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_respects_runtime_evaluation_rule_comparison_satisfied(
        self,
    ):
        runtime_eval = {">": [{"var": "queries_ran"}, 25]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties(
            {
                "queries_ran": 30,
            }
        )
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_respects_runtime_evaluation_rule_comparison_not_satisfied(
        self,
    ):
        runtime_eval = {">": [{"var": "queries_ran"}, 25]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties(
            {
                "queries_ran": 20,
            }
        )
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_respects_semver_compare_rule_satisfied(self):
        runtime_eval = {"semver_compare": [{"var": "app_version"}, ">=", "1.2.3"]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties({"app_version": "v1.10.0"})
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_respects_semver_compare_rule_not_satisfied(self):
        runtime_eval = {"semver_compare": [{"var": "app_version"}, ">=", "1.2.3"]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties({"app_version": "1.0.0"})
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_respects_datetime_compare_rule_satisfied(self):
        # 1784160000000 == 2026-07-16T00:00:00Z (epoch milliseconds).
        runtime_eval = {"datetime_compare": [{"var": "signup"}, "<", 1_784_160_000_000]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties({"signup": "2026-07-15T00:00:00Z"})
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_respects_datetime_compare_rule_not_satisfied(self):
        runtime_eval = {"datetime_compare": [{"var": "signup"}, "<", 1_784_160_000_000]}
        flag = create_test_flag(runtime_evaluation_rule=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties({"signup": "2026-07-17T00:00:00Z"})
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result == "fallback"

    def user_context_with_properties(
        self, properties: dict[str, Any]
    ) -> dict[str, Any]:
        return {"distinct_id": DISTINCT_ID, "custom_properties": properties}

    @respx.mock
    async def test_get_variant_value_ignores_legacy_runtime_evaluation_definition_when_runtime_evaluation_rule_is_present__satisfied(
        self,
    ):
        runtime_rule = {"==": [{"var": "plan"}, "premium"]}
        legacy_runtime_definition = {"plan": "basic"}
        flag = create_test_flag(
            runtime_evaluation_rule=runtime_rule,
            runtime_evaluation_legacy_definition=legacy_runtime_definition,
        )
        await self.setup_flags([flag])
        context = self.user_context_with_properties(
            {
                "plan": "premium",
            }
        )
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_ignores_legacy_runtime_evaluation_definition_when_runtime_evaluation_rule_is_present__not_satisfied(
        self,
    ):
        runtime_rule = {"==": [{"var": "plan"}, "basic"]}
        legacy_runtime_definition = {"plan": "premium"}
        flag = create_test_flag(
            runtime_evaluation_rule=runtime_rule,
            runtime_evaluation_legacy_definition=legacy_runtime_definition,
        )
        await self.setup_flags([flag])
        context = self.user_context_with_properties(
            {
                "plan": "premium",
            }
        )
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_respects_legacy_runtime_evaluation_satisfied(self):
        runtime_eval = {"plan": "premium", "region": "US"}
        flag = create_test_flag(runtime_evaluation_legacy_definition=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties({"plan": "premium", "region": "US"})
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_legacy_runtime_evaluation_not_satisfied(
        self,
    ):
        runtime_eval = {"plan": "premium", "region": "US"}
        flag = create_test_flag(runtime_evaluation_legacy_definition=runtime_eval)
        await self.setup_flags([flag])
        context = self.user_context_with_properties({"plan": "basic", "region": "US"})
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", context)
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_picks_correct_variant_with_hundred_percent_split(
        self,
    ):
        variants = [
            Variant(key="A", value="variant_a", is_control=False, split=100.0),
            Variant(key="B", value="variant_b", is_control=False, split=0.0),
            Variant(key="C", value="variant_c", is_control=False, split=0.0),
        ]
        flag = create_test_flag(variants=variants, rollout_percentage=100.0)
        await self.setup_flags([flag])
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", USER_CONTEXT)
        assert result == "variant_a"

    @respx.mock
    async def test_get_variant_value_picks_correct_variant_with_half_migrated_group_splits(
        self,
    ):
        variants = [
            Variant(key="A", value="variant_a", is_control=False, split=100.0),
            Variant(key="B", value="variant_b", is_control=False, split=0.0),
            Variant(key="C", value="variant_c", is_control=False, split=0.0),
        ]
        variant_splits = {"A": 0.0, "B": 100.0, "C": 0.0}
        flag = create_test_flag(
            variants=variants, rollout_percentage=100.0, variant_splits=variant_splits
        )
        await self.setup_flags([flag])
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", USER_CONTEXT)
        assert result == "variant_b"

    @respx.mock
    async def test_get_variant_value_picks_correct_variant_with_full_migrated_group_splits(
        self,
    ):
        variants = [
            Variant(key="A", value="variant_a", is_control=False),
            Variant(key="B", value="variant_b", is_control=False),
            Variant(key="C", value="variant_c", is_control=False),
        ]
        variant_splits = {"A": 0.0, "B": 0.0, "C": 100.0}
        flag = create_test_flag(
            variants=variants, rollout_percentage=100.0, variant_splits=variant_splits
        )
        await self.setup_flags([flag])
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", USER_CONTEXT)
        assert result == "variant_c"

    @respx.mock
    async def test_get_variant_value_picks_overriden_variant(self):
        variants = [
            Variant(key="A", value="variant_a", is_control=False, split=100.0),
            Variant(key="B", value="variant_b", is_control=False, split=0.0),
        ]
        flag = create_test_flag(
            variants=variants, variant_override=VariantOverride(key="B")
        )
        await self.setup_flags([flag])
        result = self._flags.get_variant_value(TEST_FLAG_KEY, "control", USER_CONTEXT)
        assert result == "variant_b"

    @respx.mock
    async def test_get_variant_value_tracks_exposure_when_variant_selected(self):
        flag = create_test_flag()
        await self.setup_flags([flag])
        with patch("mixpanel.flags.utils.normalized_hash") as mock_hash:
            mock_hash.return_value = 0.5
            _ = self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", USER_CONTEXT)
            self._mock_tracker.assert_called_once()

    @respx.mock
    @pytest.mark.parametrize(
        ("experiment_id", "is_experiment_active", "use_qa_user"),
        [
            ("exp-123", True, True),  # QA tester with active experiment
            ("exp-456", False, True),  # QA tester with inactive experiment
            ("exp-789", True, False),  # Regular user with active experiment
            ("exp-000", False, False),  # Regular user with inactive experiment
            (None, None, True),  # QA tester with no experiment
            (None, None, False),  # Regular user with no experiment
        ],
    )
    async def test_get_variant_value_tracks_exposure_with_correct_properties(
        self, experiment_id, is_experiment_active, use_qa_user
    ):
        flag = create_test_flag(
            experiment_id=experiment_id,
            is_experiment_active=is_experiment_active,
            test_users={"qa_user": "treatment"},
        )

        await self.setup_flags([flag])

        distinct_id = "qa_user" if use_qa_user else "regular_user"

        with patch("mixpanel.flags.utils.normalized_hash") as mock_hash:
            mock_hash.return_value = 0.5
            _ = self._flags.get_variant_value(
                TEST_FLAG_KEY, "fallback", {"distinct_id": distinct_id}
            )

        self._mock_tracker.assert_called_once()

        call_args = self._mock_tracker.call_args
        properties = call_args[0][2]

        assert properties["$experiment_id"] == experiment_id
        assert properties["$is_experiment_active"] == is_experiment_active

        if use_qa_user:
            assert properties["$is_qa_tester"] is True
        else:
            assert properties.get("$is_qa_tester") is None

    @respx.mock
    async def test_get_variant_value_does_not_track_exposure_on_fallback(self):
        await self.setup_flags([])
        _ = self._flags.get_variant_value("nonexistent_flag", "fallback", USER_CONTEXT)
        self._mock_tracker.assert_not_called()

    @respx.mock
    async def test_get_variant_value_does_not_track_exposure_without_distinct_id(self):
        flag = create_test_flag(context="company")
        await self.setup_flags([flag])
        _ = self._flags.get_variant_value(
            "nonexistent_flag", "fallback", {"company_id": "company123"}
        )
        self._mock_tracker.assert_not_called()

    @respx.mock
    async def test_default_exposure_runs_inline_on_calling_thread(self):
        """Smoke test: exposure_executor defaults to None, tracker runs inline."""
        flag = create_test_flag(rollout_percentage=100.0)
        await self.setup_flags([flag])

        called_on: list[threading.Thread] = []

        def tracker(_distinct_id, _event, _properties):
            called_on.append(threading.current_thread())

        self._mock_tracker.side_effect = tracker
        self._flags.get_variant_value(TEST_FLAG_KEY, "fallback", USER_CONTEXT)
        assert called_on == [threading.current_thread()]

    @respx.mock
    async def test_track_exposure_event_routes_through_executor(self):
        """Manual API also honors exposure_executor."""
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="exposure")
        try:
            tracker_done = threading.Event()
            captured: list[threading.Thread] = []

            def tracker(_distinct_id, _event, _properties):
                captured.append(threading.current_thread())
                tracker_done.set()

            config = LocalFlagsConfig(enable_polling=False, exposure_executor=executor)
            provider = LocalFeatureFlagsProvider(
                "test-token", config, "1.0.0", Mock(side_effect=tracker)
            )
            try:
                provider.track_exposure_event(
                    "manual",
                    SelectedVariant(variant_key="treatment", variant_value="x"),
                    USER_CONTEXT,
                )
                assert tracker_done.wait(timeout=2.0)
                assert captured[0] is not threading.current_thread()
                assert captured[0].name.startswith("exposure")
            finally:
                await provider.__aexit__(None, None, None)
        finally:
            executor.shutdown(wait=True)

    @respx.mock
    async def test_exposure_executor_dispatches_tracker_off_calling_thread(self):
        flag = create_test_flag(rollout_percentage=100.0)
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="exposure")
        try:
            calling_thread = threading.current_thread()
            tracker_thread = threading.Event()
            captured_thread: list[threading.Thread] = []

            def tracker(_distinct_id, _event, _properties):
                captured_thread.append(threading.current_thread())
                tracker_thread.set()

            tracker_mock = Mock(side_effect=tracker)
            config = LocalFlagsConfig(enable_polling=False, exposure_executor=executor)
            provider = LocalFeatureFlagsProvider(
                "test-token", config, "1.0.0", tracker_mock
            )
            try:
                respx.get("https://api.mixpanel.com/flags/definitions").mock(
                    return_value=create_flags_response([flag])
                )
                await provider.astart_polling_for_definitions()
                provider.get_variant_value(TEST_FLAG_KEY, "fallback", USER_CONTEXT)
                assert tracker_thread.wait(timeout=2.0), "tracker never ran"
                assert captured_thread[0] is not calling_thread
                assert captured_thread[0].name.startswith("exposure")
            finally:
                await provider.__aexit__(None, None, None)
        finally:
            executor.shutdown(wait=True)

    @respx.mock
    async def test_get_all_variants_returns_all_variants_when_user_in_rollout(self):
        flag1 = create_test_flag(flag_key="flag1", rollout_percentage=100.0)
        flag2 = create_test_flag(flag_key="flag2", rollout_percentage=100.0)
        await self.setup_flags([flag1, flag2])

        result = self._flags.get_all_variants(USER_CONTEXT)

        assert len(result) == 2 and "flag1" in result and "flag2" in result

    @respx.mock
    async def test_get_all_variants_returns_partial_variants_when_user_in_some_rollout(
        self,
    ):
        flag1 = create_test_flag(flag_key="flag1", rollout_percentage=100.0)
        flag2 = create_test_flag(flag_key="flag2", rollout_percentage=0.0)
        await self.setup_flags([flag1, flag2])

        result = self._flags.get_all_variants(USER_CONTEXT)

        assert len(result) == 1 and "flag1" in result and "flag2" not in result

    @respx.mock
    async def test_get_all_variants_returns_empty_dict_when_no_flags_configured(self):
        await self.setup_flags([])

        result = self._flags.get_all_variants(USER_CONTEXT)

        assert result == {}

    @respx.mock
    async def test_get_all_variants_does_not_track_exposure_events(self):
        flag1 = create_test_flag(flag_key="flag1", rollout_percentage=100.0)
        flag2 = create_test_flag(flag_key="flag2", rollout_percentage=100.0)
        await self.setup_flags([flag1, flag2])

        _ = self._flags.get_all_variants(USER_CONTEXT)

        self._mock_tracker.assert_not_called()

    @respx.mock
    async def test_track_exposure_event_successfully_tracks(self):
        flag = create_test_flag()
        await self.setup_flags([flag])

        variant = SelectedVariant(variant_key="treatment", variant_value="treatment")
        self._flags.track_exposure_event(TEST_FLAG_KEY, variant, USER_CONTEXT)

        self._mock_tracker.assert_called_once()

    @respx.mock
    async def test_are_flags_ready_returns_true_when_flags_loaded(self):
        flag = create_test_flag()
        await self.setup_flags([flag])
        assert self._flags.are_flags_ready() is True

    @respx.mock
    async def test_are_flags_ready_returns_true_when_empty_flags_loaded(self):
        await self.setup_flags([])
        assert self._flags.are_flags_ready() is True

    @respx.mock
    async def test_is_enabled_returns_false_for_nonexistent_flag(self):
        await self.setup_flags([])
        result = self._flags.is_enabled("nonexistent_flag", USER_CONTEXT)
        assert result is False

    @respx.mock
    async def test_is_enabled_returns_true_for_true_variant_value(self):
        variants = [Variant(key="treatment", value=True, is_control=False, split=100.0)]
        flag = create_test_flag(variants=variants, rollout_percentage=100.0)
        await self.setup_flags([flag])
        result = self._flags.is_enabled(TEST_FLAG_KEY, USER_CONTEXT)
        assert result is True

    @respx.mock
    async def test_get_variant_tags_match_as_local(self):
        flag = create_test_flag(rollout_percentage=100.0)
        await self.setup_flags([flag])
        fallback = SelectedVariant(variant_value="fb")
        result = self._flags.get_variant(TEST_FLAG_KEY, fallback, USER_CONTEXT)
        assert result.variant_source == VariantSource.LOCAL
        assert result.fallback_reason is None
        assert result.variant_key is not None

    @respx.mock
    async def test_get_variant_tags_missing_flag(self):
        await self.setup_flags([])
        fallback = SelectedVariant(variant_value="fb")
        result = self._flags.get_variant("missing", fallback, USER_CONTEXT)
        assert result.variant_source == VariantSource.FALLBACK
        assert result.fallback_reason.kind == "FLAG_NOT_FOUND"
        assert result.fallback_reason.message is None
        assert result.variant_value == "fb"

    @respx.mock
    async def test_get_variant_tags_missing_context(self):
        flag = create_test_flag(context="distinct_id")
        await self.setup_flags([flag])
        fallback = SelectedVariant(variant_value="fb")
        result = self._flags.get_variant(TEST_FLAG_KEY, fallback, {})
        assert result.variant_source == VariantSource.FALLBACK
        assert result.fallback_reason.kind == "MISSING_CONTEXT_KEY"
        assert result.fallback_reason.message == "distinct_id"

    @respx.mock
    async def test_get_variant_tags_no_rollout_match(self):
        flag = create_test_flag(rollout_percentage=0.0)
        await self.setup_flags([flag])
        fallback = SelectedVariant(variant_value="fb")
        result = self._flags.get_variant(TEST_FLAG_KEY, fallback, USER_CONTEXT)
        assert result.variant_source == VariantSource.FALLBACK
        assert result.fallback_reason.kind == "NO_ROLLOUT_MATCH"

    @respx.mock
    async def test_get_variant_value_uses_most_recent_polled_flag(self):
        polling_iterations = 0
        polling_limit_check = asyncio.Condition()
        original_fetch = LocalFeatureFlagsProvider._afetch_flag_definitions

        async def track_fetch_calls(self):
            nonlocal polling_iterations
            async with polling_limit_check:
                polling_iterations += 1
                polling_limit_check.notify_all()
            return await original_fetch(self)

        with patch.object(
            LocalFeatureFlagsProvider, "_afetch_flag_definitions", track_fetch_calls
        ):
            flag_v1 = create_test_flag(rollout_percentage=0.0)
            flag_v2 = create_test_flag(rollout_percentage=100.0)

            flags_in_order = [[flag_v1], [flag_v2]]
            await self.setup_flags_with_polling(flags_in_order)
            async with polling_limit_check:
                await polling_limit_check.wait_for(
                    lambda: polling_iterations >= len(flags_in_order)
                )

            result2 = self._flags_with_polling.get_variant_value(
                TEST_FLAG_KEY, "fallback", USER_CONTEXT
            )
            assert result2 != "fallback"


class TestLocalFeatureFlagsProviderSync:
    def setup_method(self):
        self.mock_tracker = Mock()
        config_with_polling = LocalFlagsConfig(
            enable_polling=True, polling_interval_in_seconds=0
        )
        self._flags_with_polling = LocalFeatureFlagsProvider(
            "test-token", config_with_polling, "1.0.0", self.mock_tracker
        )

    def teardown_method(self):
        self._flags_with_polling.__exit__(None, None, None)

    def setup_flags_with_polling(
        self, flags_in_order: list[list[ExperimentationFlag]] = [[]]
    ):
        responses = [create_flags_response(flag) for flag in flags_in_order]

        respx.get("https://api.mixpanel.com/flags/definitions").mock(
            side_effect=chain(
                responses,
                repeat(responses[-1]),
            )
        )

        self._flags_with_polling.start_polling_for_definitions()

    @respx.mock
    def test_get_variant_value_uses_most_recent_polled_flag(self):
        flag_v1 = create_test_flag(rollout_percentage=0.0)
        flag_v2 = create_test_flag(rollout_percentage=100.0)
        flags_in_order = [[flag_v1], [flag_v2]]

        polling_iterations = 0
        polling_event = threading.Event()
        original_fetch = LocalFeatureFlagsProvider._fetch_flag_definitions

        # Hook into the fetch method to signal when we've polled multiple times.
        def track_fetch_calls(self):
            nonlocal polling_iterations
            polling_iterations += 1
            if polling_iterations >= 3:
                polling_event.set()
            return original_fetch(self)

        with patch.object(
            LocalFeatureFlagsProvider, "_fetch_flag_definitions", track_fetch_calls
        ):
            self.setup_flags_with_polling(flags_in_order)
            polling_event.wait(timeout=5.0)
            assert polling_iterations >= 3
            result2 = self._flags_with_polling.get_variant_value(
                TEST_FLAG_KEY, "fallback", USER_CONTEXT
            )
            assert result2 != "fallback"


def test_local_flags_with_service_account_credentials():
    """Test LocalFeatureFlagsProvider accepts httpx client params with service account auth."""
    config = LocalFlagsConfig(
        api_host="api.mixpanel.com", request_timeout_in_seconds=10
    )

    # Create service account credentials
    credentials = ServiceAccountCredentials(
        username="test-service-account",
        secret="test-service-secret",
        project_id="12345",
    )

    tracker = Mock()
    provider = LocalFeatureFlagsProvider(
        token="test-token",
        config=config,
        version="1.0.0",
        tracker=tracker,
        credentials=credentials,
    )

    # Verify the httpx clients were configured with httpx.BasicAuth
    assert provider._sync_client.auth is not None
    assert isinstance(provider._sync_client.auth, httpx.BasicAuth)
    assert provider._async_client.auth is not None
    assert isinstance(provider._async_client.auth, httpx.BasicAuth)

    # Verify query params include both token and project_id
    assert "project_id" in provider._request_params
    assert provider._request_params["project_id"] == "12345"
    assert "token" in provider._request_params
    assert provider._request_params["token"] == "test-token"
    assert provider._request_params["mp_lib"] == "python"
    assert provider._request_params["lib_version"] == "1.0.0"

    provider.shutdown()


@pytest.mark.asyncio
async def test_local_flags_async_with_service_account_credentials():
    """Test LocalFeatureFlagsProvider async client works with service account auth."""
    config = LocalFlagsConfig(
        api_host="api.mixpanel.com", request_timeout_in_seconds=10
    )

    # Create service account credentials
    credentials = ServiceAccountCredentials(
        username="test-service-account",
        secret="test-service-secret",
        project_id="12345",
    )

    tracker = Mock()
    provider = LocalFeatureFlagsProvider(
        token="test-token",
        config=config,
        version="1.0.0",
        tracker=tracker,
        credentials=credentials,
    )

    # Verify auth configured with httpx.BasicAuth
    assert provider._async_client.auth is not None
    assert isinstance(provider._async_client.auth, httpx.BasicAuth)

    await provider.__aexit__(None, None, None)


def test_local_flags_fallback_to_token_without_credentials():
    """Test LocalFeatureFlagsProvider works with token auth (no credentials)."""
    config = LocalFlagsConfig(
        api_host="api.mixpanel.com", request_timeout_in_seconds=10
    )

    tracker = Mock()
    provider = LocalFeatureFlagsProvider(
        token="test-token",
        config=config,
        version="1.0.0",
        tracker=tracker,
        credentials=None,
    )

    # Verify auth still configured (using token)
    assert provider._sync_client.auth is not None
    assert isinstance(provider._sync_client.auth, httpx.BasicAuth)
    assert provider._async_client.auth is not None
    assert isinstance(provider._async_client.auth, httpx.BasicAuth)

    # Verify query params use token instead of project_id
    assert "token" in provider._request_params
    assert provider._request_params["token"] == "test-token"
    assert "project_id" not in provider._request_params
    assert provider._request_params["mp_lib"] == "python"
    assert provider._request_params["lib_version"] == "1.0.0"

    provider.shutdown()


# SDK-85: sync __exit__ and shutdown() historically only closed
# _sync_client, leaking _async_client's connection pool + background
# transport. The two tests below fail on the pre-fix code.


def test_sync_shutdown_closes_both_clients():
    config = LocalFlagsConfig(enable_polling=False)
    provider = LocalFeatureFlagsProvider("test-token", config, "1.0.0", Mock())

    assert not provider._sync_client.is_closed
    assert not provider._async_client.is_closed

    provider.shutdown()

    assert provider._sync_client.is_closed
    assert provider._async_client.is_closed


def test_sync_context_manager_exit_closes_both_clients():
    config = LocalFlagsConfig(enable_polling=False)
    with LocalFeatureFlagsProvider("test-token", config, "1.0.0", Mock()) as provider:
        assert not provider._sync_client.is_closed
        assert not provider._async_client.is_closed

    assert provider._sync_client.is_closed
    assert provider._async_client.is_closed


# Hierarchical groups: context_template and exposure attribution.

HG_FLAG_KEY = "hg-test"
HG_TEMPLATE = "$company:{$company_id}|$user:{$user_id}"
DEFINITIONS_URL = "https://api.mixpanel.com/flags/definitions"


def raw_flag(
    key: str = HG_FLAG_KEY,
    context: str = "distinct_id",
    rollout_percentage: float = 1.0,
    test_users: dict[str, str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """A flag definition as the definitions endpoint sends it."""
    definition = {
        "id": "hg-id",
        "name": "HG Flag",
        "key": key,
        "status": "active",
        "project_id": 1,
        "context": context,
        "ruleset": {
            "variants": [
                {
                    "key": "control",
                    "value": "control-value",
                    "is_control": True,
                    "split": 1.0,
                },
                {
                    "key": "treatment",
                    "value": "treatment-value",
                    "is_control": False,
                    "split": 0.0,
                },
            ],
            "rollout": [{"rollout_percentage": rollout_percentage}],
            "test": {"users": test_users or {}},
        },
    }
    definition.update(extra)
    return definition


# The definition from the hierarchical groups flags contract.
HG_KEY_TEST_DEFINITION = {
    "id": "hg-id",
    "name": "HG Flag",
    "key": HG_FLAG_KEY,
    "status": "active",
    "project_id": 1,
    "serving_method": "client",
    "context": "distinct_id",
    "context_template": HG_TEMPLATE,
    "hash_salt": "880dc3e584b4452fb769808ca18dc9a6",
    "ruleset": {
        "variants": [
            {"key": "On", "value": True, "is_control": False, "split": 1},
            {"key": "Off", "value": False, "is_control": True, "split": 0},
        ],
        "rollout": [{"rollout_percentage": 0.5, "variant_splits": {"Off": 0, "On": 1}}],
        "test": {"users": {}},
    },
}


class TestLocalFlagsHierarchicalGroups:
    @pytest.fixture(autouse=True)
    def _providers(self):
        self._created: list[LocalFeatureFlagsProvider] = []
        self.tracker = Mock()
        yield
        for provider in self._created:
            provider.shutdown()

    def provider(
        self,
        definitions: list[dict[str, Any]],
        hierarchical_groups: bool = True,
        tracker: Any = None,
    ) -> LocalFeatureFlagsProvider:
        provider = LocalFeatureFlagsProvider(
            "test-token",
            LocalFlagsConfig(enable_polling=False),
            "1.0.0",
            tracker or self.tracker,
            hierarchical_groups=hierarchical_groups,
        )
        self._created.append(provider)
        with respx.mock:
            respx.get(DEFINITIONS_URL).mock(
                return_value=httpx.Response(200, json={"flags": definitions})
            )
            provider.start_polling_for_definitions()
        return provider

    @staticmethod
    def hashed_rollout_values(provider, flag_key, context) -> list[str]:
        """Evaluate and return the keys passed to the rollout hash."""
        from . import local_feature_flags

        with patch.object(
            local_feature_flags,
            "normalized_hash",
            wraps=local_feature_flags.normalized_hash,
        ) as hashed:
            provider.get_variant_value(flag_key, "fallback", context)
        return [
            call.args[0]
            for call in hashed.call_args_list
            if not call.args[1].endswith("variant")
        ]

    # Definition parsing

    def test_template_fields_parsed(self):
        provider = self.provider(
            [raw_flag(context_template=HG_TEMPLATE, context_template_version=1)]
        )
        flag = provider._flag_definitions[HG_FLAG_KEY]
        assert flag.context_template == HG_TEMPLATE
        assert flag.context_template_version == 1

    def test_flag_with_newer_template_version_is_dropped(self, caplog):
        provider = self.provider([raw_flag(context_template_version=99)])
        variant = provider.get_variant(
            HG_FLAG_KEY,
            SelectedVariant(variant_value="fallback"),
            {"distinct_id": "user-123"},
        )
        assert variant.variant_value == "fallback"
        assert variant.fallback_reason.kind == "FLAG_NOT_FOUND"
        assert any(
            HG_FLAG_KEY in r.getMessage()
            and "context_template_version 99" in r.getMessage()
            for r in caplog.records
        )

    @pytest.mark.parametrize(
        "template",
        [
            "$company:no-placeholders",
            "$company:{}|$user:{$user_id}",
            "$company:{  }|$user:{$user_id}",
        ],
    )
    def test_flag_with_malformed_template_is_dropped(self, template, caplog):
        provider = self.provider([raw_flag(context_template=template)])
        assert HG_FLAG_KEY not in provider._flag_definitions
        assert any(HG_FLAG_KEY in r.getMessage() for r in caplog.records)

    def test_other_flags_survive_a_dropped_one(self):
        provider = self.provider(
            [raw_flag(key="good-flag"), raw_flag(context_template_version=99)]
        )
        context = {"distinct_id": "user-123"}
        assert (
            provider.get_variant_value("good-flag", "fallback", context)
            == "control-value"
        )
        assert (
            provider.get_variant_value(HG_FLAG_KEY, "fallback", context) == "fallback"
        )

    def test_empty_template_is_no_template(self):
        provider = self.provider([raw_flag(context_template="")])
        assert HG_FLAG_KEY in provider._flag_definitions

    # Resolving the assignment key

    def test_pair_only_context_without_template_falls_back(self):
        provider = self.provider([raw_flag()])
        variant = provider.get_variant(
            HG_FLAG_KEY,
            SelectedVariant(variant_value="fallback"),
            {"$user_id": "user-123", "$company_id": "acme"},
        )
        assert variant.variant_value == "fallback"
        assert variant.fallback_reason.kind == "MISSING_CONTEXT_KEY"
        self.tracker.assert_not_called()

    def test_template_resolves_the_assignment_key(self):
        provider = self.provider([raw_flag(context_template=HG_TEMPLATE)])
        hashed = self.hashed_rollout_values(
            provider, HG_FLAG_KEY, {"$user_id": "user-123", "$company_id": "acme"}
        )
        assert hashed == ["$company:acme|$user:user-123"]

    def test_template_matches_distinct_id_for_many_users(self):
        provider = self.provider([HG_KEY_TEST_DEFINITION])
        outcomes = set()
        for i in range(50):
            user_id = f"u{i}"
            from_pair = provider.get_variant(
                HG_FLAG_KEY,
                SelectedVariant(variant_value="fallback"),
                {"$company_id": "acme", "$user_id": user_id},
                report_exposure=False,
            )
            from_distinct_id = provider.get_variant(
                HG_FLAG_KEY,
                SelectedVariant(variant_value="fallback"),
                {"distinct_id": f"$company:acme|$user:{user_id}"},
                report_exposure=False,
            )
            assert from_pair == from_distinct_id
            outcomes.add(from_pair.variant_value)
        # The 50% rollout puts some users in and leaves some out.
        assert outcomes == {True, "fallback"}

    @pytest.mark.parametrize(
        "context",
        [
            {"$user_id": "u1"},
            {"$company_id": "acme"},
            {"$company_id": "", "$user_id": "u1"},
            {"$company_id": None, "$user_id": "u1"},
        ],
    )
    def test_template_needs_every_placeholder(self, context):
        provider = self.provider([HG_KEY_TEST_DEFINITION])
        variant = provider.get_variant(
            HG_FLAG_KEY, SelectedVariant(variant_value="fallback"), context
        )
        assert variant.variant_value == "fallback"
        assert variant.fallback_reason.kind == "MISSING_CONTEXT_KEY"

    def test_template_is_not_gated_on_hierarchical_groups(self):
        provider = self.provider(
            [raw_flag(context_template=HG_TEMPLATE)], hierarchical_groups=False
        )
        hashed = self.hashed_rollout_values(
            provider, HG_FLAG_KEY, {"$user_id": "user-123", "$company_id": "acme"}
        )
        assert hashed == ["$company:acme|$user:user-123"]

    def test_template_placeholder_name_is_used_verbatim(self):
        provider = self.provider([raw_flag(context_template="org:{ org }")])
        assert (
            provider.get_variant_value(HG_FLAG_KEY, "fallback", {"org": "x"})
            == "fallback"
        )
        hashed = self.hashed_rollout_values(provider, HG_FLAG_KEY, {" org ": "x"})
        assert hashed == ["org:x"]

    def test_distinct_id_is_hashed_as_sent(self):
        provider = self.provider([raw_flag(context_template=HG_TEMPLATE)])
        hashed = self.hashed_rollout_values(
            provider,
            HG_FLAG_KEY,
            {"distinct_id": "other", "$user_id": "user-123", "$company_id": "acme"},
        )
        assert hashed == ["other"]

    @pytest.mark.parametrize(
        ("context_property", "value"), [("department", "finance"), ("device_id", "dev")]
    )
    def test_non_distinct_id_flag_hashes_raw_value(self, context_property, value):
        provider = self.provider([raw_flag(context=context_property)])
        hashed = self.hashed_rollout_values(
            provider,
            HG_FLAG_KEY,
            {"$user_id": "user-123", "$company_id": "acme", context_property: value},
        )
        assert hashed == [value]

    # Test-user overrides

    def test_template_resolves_test_user_overrides(self):
        provider = self.provider(
            [
                raw_flag(
                    context_template=HG_TEMPLATE,
                    test_users={"$company:acme|$user:user-123": "treatment"},
                )
            ]
        )
        result = provider.get_variant_value(
            HG_FLAG_KEY, "fallback", {"$user_id": "user-123", "$company_id": "acme"}
        )
        assert result == "treatment-value"

    def test_test_user_override_matches_distinct_id_as_sent(self):
        provider = self.provider(
            [raw_flag(test_users={"$company:acme|$user:user-123": "treatment"})]
        )
        result = provider.get_variant_value(
            HG_FLAG_KEY,
            "fallback",
            {
                "distinct_id": "$company:acme|$user:user-123",
                "$user_id": "user-123",
                "$company_id": "acme",
            },
        )
        assert result == "treatment-value"

    def test_template_does_not_resolve_overrides_for_other_context(self):
        # Overrides are keyed by distinct id; a device-keyed template is not one.
        provider = self.provider(
            [
                raw_flag(
                    context="device_id",
                    context_template="dev:{$device_id}",
                    test_users={"dev:d1": "treatment"},
                )
            ]
        )
        result = provider.get_variant_value(
            HG_FLAG_KEY, "fallback", {"$device_id": "d1"}
        )
        assert result == "control-value"

    # Exposure

    def test_exposure_carries_user_and_company_without_distinct_id(self):
        provider = self.provider([raw_flag(context_template=HG_TEMPLATE)])
        provider.get_variant_value(
            HG_FLAG_KEY, "fallback", {"$user_id": "user-123", "$company_id": "acme"}
        )
        self.tracker.assert_called_once()
        identity, event, _ = self.tracker.call_args.args
        assert identity == MixpanelIdentity(user_id="user-123", company_id="acme")
        assert event == "$experiment_started"

    def test_exposure_carries_distinct_id_user_and_company(self):
        provider = self.provider([raw_flag()])
        provider.get_variant_value(
            HG_FLAG_KEY,
            "fallback",
            {
                "distinct_id": "$company:acme|$user:user-123",
                "$user_id": "user-123",
                "$company_id": "acme",
            },
        )
        identity = self.tracker.call_args.args[0]
        assert identity == MixpanelIdentity(
            distinct_id="$company:acme|$user:user-123",
            user_id="user-123",
            company_id="acme",
        )

    def test_exposure_attributed_by_distinct_id_alone(self):
        provider = self.provider([raw_flag()])
        assert (
            provider.get_variant_value(
                HG_FLAG_KEY, "fallback", {"distinct_id": "user-123"}
            )
            == "control-value"
        )
        identity = self.tracker.call_args.args[0]
        assert identity == MixpanelIdentity(distinct_id="user-123")

    def test_exposure_omits_user_id_without_company(self):
        provider = self.provider([raw_flag()])
        provider.get_variant_value(
            HG_FLAG_KEY, "fallback", {"distinct_id": "d1", "$user_id": "user-123"}
        )
        assert self.tracker.call_args.args[0] == MixpanelIdentity(distinct_id="d1")

    def test_exposure_without_company_or_distinct_id_is_dropped(self, caplog):
        provider = self.provider([raw_flag(context="device_id")])
        result = provider.get_variant_value(
            HG_FLAG_KEY, "fallback", {"device_id": "dev", "$user_id": "user-123"}
        )
        assert result == "control-value"
        self.tracker.assert_not_called()
        assert any(
            "without a $company_id in the context" in r.getMessage()
            for r in caplog.records
        )

    def test_manual_exposure_uses_identity(self):
        provider = self.provider([])
        provider.track_exposure_event(
            HG_FLAG_KEY,
            SelectedVariant(variant_key="treatment", variant_value="treatment-value"),
            {"$user_id": "user-123", "$company_id": "acme"},
        )
        assert self.tracker.call_args.args[0] == MixpanelIdentity(
            user_id="user-123", company_id="acme"
        )

    def test_exposure_through_client_track_has_no_distinct_id(self):
        consumer = Mock()
        mp = Mixpanel("test-token", consumer=consumer, hierarchical_groups=True)
        provider = self.provider(
            [raw_flag(context_template=HG_TEMPLATE)], tracker=mp.track
        )
        provider.get_variant_value(
            HG_FLAG_KEY, "fallback", {"$user_id": "user-123", "$company_id": "acme"}
        )
        endpoint, message = consumer.send.call_args.args
        properties = json.loads(message)["properties"]
        assert endpoint == "events"
        assert "distinct_id" not in properties
        assert properties["$user_id"] == "user-123"
        assert properties["$company_id"] == "acme"
        assert properties["Experiment name"] == HG_FLAG_KEY

    # Without hierarchical groups, behavior is unchanged

    def test_legacy_project_ignores_company_id_in_context(self):
        provider = self.provider([raw_flag()], hierarchical_groups=False)
        hashed = self.hashed_rollout_values(
            provider,
            HG_FLAG_KEY,
            {"distinct_id": "user-123", "$user_id": "user-123", "$company_id": "acme"},
        )
        assert hashed == ["user-123"]
        distinct_id, _, properties = self.tracker.call_args.args
        assert distinct_id == "user-123"
        assert "$company_id" not in properties
        assert "$user_id" not in properties

    def test_legacy_exposure_is_unchanged(self):
        provider = self.provider([raw_flag()], hierarchical_groups=False)
        provider.get_variant_value(HG_FLAG_KEY, "fallback", {"distinct_id": "user-123"})
        distinct_id, event, properties = self.tracker.call_args.args
        assert distinct_id == "user-123"
        assert event == "$experiment_started"
        properties.pop("Variant fetch latency (ms)")
        assert properties == {
            "Experiment name": HG_FLAG_KEY,
            "Variant name": "control",
            "$experiment_type": "feature_flag",
            "Flag evaluation mode": "local",
            "$experiment_id": None,
            "$is_experiment_active": None,
            "$is_qa_tester": None,
        }

    def test_legacy_company_only_context_is_not_attributed(self, caplog):
        provider = self.provider(
            [raw_flag(context="device_id")], hierarchical_groups=False
        )
        provider.get_variant_value(
            HG_FLAG_KEY, "fallback", {"device_id": "dev", "$company_id": "acme"}
        )
        self.tracker.assert_not_called()
        assert any(
            r.getMessage()
            == "Cannot track exposure event without a distinct_id in the context"
            for r in caplog.records
        )

    def test_client_passes_hierarchical_groups_to_providers(self):
        mp = Mixpanel(
            "test-token",
            local_flags_config=LocalFlagsConfig(enable_polling=False),
            remote_flags_config=RemoteFlagsConfig(),
            hierarchical_groups=True,
        )
        try:
            assert mp.local_flags._hierarchical_groups is True
            assert mp.remote_flags._hierarchical_groups is True
        finally:
            mp.local_flags.shutdown()
            mp.remote_flags.shutdown()
        legacy = Mixpanel(
            "test-token", local_flags_config=LocalFlagsConfig(enable_polling=False)
        )
        assert legacy.local_flags._hierarchical_groups is False
        legacy.local_flags.shutdown()
