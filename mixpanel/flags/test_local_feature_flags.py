import asyncio
import pytest
import respx
import httpx
import threading
from unittest.mock import Mock, patch
from typing import Dict, Optional, List
from itertools import chain, repeat
from .types import LocalFlagsConfig, ExperimentationFlag, RuleSet, Variant, Rollout, FlagTestUsers, ExperimentationFlags, VariantOverride, SelectedVariant
from .local_feature_flags import LocalFeatureFlagsProvider


def create_test_flag(
    flag_key: str = "test_flag",
    context: str = "distinct_id",
    variants: Optional[list[Variant]] = None,
    variant_override: Optional[VariantOverride] = None,
    rollout_percentage: float = 100.0,
    runtime_evaluation: Optional[Dict] = None,
    test_users: Optional[Dict[str, str]] = None,
    experiment_id: Optional[str] = None,
    is_experiment_active: Optional[bool] = None,
    variant_splits: Optional[Dict[str, float]] = None,
    hash_salt: Optional[str] = None) -> ExperimentationFlag:
    if variants is None:
        variants = [
            Variant(key="control", value="control", is_control=True, split=50.0),
            Variant(key="treatment", value="treatment", is_control=False, split=50.0)
        ]

    rollouts = [Rollout(
        rollout_percentage=rollout_percentage,
        runtime_evaluation_definition=runtime_evaluation,
        variant_override=variant_override,
        variant_splits=variant_splits
    )]

    test_config = None
    if test_users:
        test_config = FlagTestUsers(users=test_users)

    ruleset = RuleSet(
        variants=variants,
        rollout=rollouts,
        test=test_config
    )

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
        hash_salt=hash_salt
    )


def create_flags_response(flags: List[ExperimentationFlag]) -> httpx.Response:
    if flags is None:
        flags = []
    response_data = ExperimentationFlags(flags=flags).model_dump()
    return httpx.Response(status_code=200, json=response_data)


@pytest.mark.asyncio
class TestLocalFeatureFlagsProviderAsync:
    @pytest.fixture(autouse=True)
    async def setup_method(self):
        self._mock_tracker = Mock()

        config_no_polling = LocalFlagsConfig(enable_polling=False)
        self._flags = LocalFeatureFlagsProvider("test-token", config_no_polling, "1.0.0", self._mock_tracker)

        config_with_polling = LocalFlagsConfig(enable_polling=True, polling_interval_in_seconds=0)
        self._flags_with_polling = LocalFeatureFlagsProvider("test-token", config_with_polling, "1.0.0", self._mock_tracker)

        yield

        await self._flags.__aexit__(None, None, None)
        await self._flags_with_polling.__aexit__(None, None, None)

    async def setup_flags(self, flags: List[ExperimentationFlag]):
        respx.get("https://api.mixpanel.com/flags/definitions").mock(
            return_value=create_flags_response(flags))
        await self._flags.astart_polling_for_definitions()

    async def setup_flags_with_polling(self, flags_in_order: List[List[ExperimentationFlag]] = [[]]):
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
        result = self._flags.get_variant_value("nonexistent_flag", "control", {"distinct_id": "user123"})
        assert result == "control"

    @respx.mock
    async def test_get_variant_value_returns_fallback_if_flag_definition_call_fails(self):
        respx.get("https://api.mixpanel.com/flags/definitions").mock(
            return_value=httpx.Response(status_code=500)
        )

        await self._flags.astart_polling_for_definitions()
        result = self._flags.get_variant_value("nonexistent_flag", "control", {"distinct_id": "user123"})
        assert result == "control"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_flag_does_not_exist(self):
        other_flag = create_test_flag("other_flag")
        await self.setup_flags([other_flag])
        result = self._flags.get_variant_value("nonexistent_flag", "control", {"distinct_id": "user123"})
        assert result == "control"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_no_context(self):
        flag = create_test_flag(context="distinct_id")
        await self.setup_flags([flag])
        result = self._flags.get_variant_value("test_flag", "fallback", {})
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_wrong_context_key(self):
        flag = create_test_flag(context="user_id")
        await self.setup_flags([flag])
        result = self._flags.get_variant_value("test_flag", "fallback", {"distinct_id": "user123"})
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_returns_test_user_variant_when_configured(self):
        variants = [
            Variant(key="control", value="false", is_control=True, split=50.0),
            Variant(key="treatment", value="true", is_control=False, split=50.0)
        ]
        flag = create_test_flag(
            variants=variants,
            test_users={"test_user": "treatment"}
        )

        await self.setup_flags([flag])
        result = self._flags.get_variant_value("test_flag", "control", {"distinct_id": "test_user"})
        assert result == "true"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_test_user_variant_not_configured(self):
        variants = [
            Variant(key="control", value="false", is_control=True, split=50.0),
            Variant(key="treatment", value="true", is_control=False, split=50.0)
        ]
        flag = create_test_flag(
            variants=variants,
            test_users={"test_user": "nonexistent_variant"}
        )
        await self.setup_flags([flag])
        with patch('mixpanel.flags.utils.normalized_hash') as mock_hash:
            mock_hash.return_value = 0.5
            result = self._flags.get_variant_value("test_flag", "fallback", {"distinct_id": "test_user"})
            assert result == "false"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_rollout_percentage_zero(self):
        flag = create_test_flag(rollout_percentage=0.0)
        await self.setup_flags([flag])
        result = self._flags.get_variant_value("test_flag", "fallback", {"distinct_id": "user123"})
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_returns_variant_when_rollout_percentage_hundred(self):
        flag = create_test_flag(rollout_percentage=100.0)
        await self.setup_flags([flag])
        result = self._flags.get_variant_value("test_flag", "fallback", {"distinct_id": "user123"})
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_respects_runtime_evaluation_satisfied(self):
        runtime_eval = {"plan": "premium", "region": "US"}
        flag = create_test_flag(runtime_evaluation=runtime_eval)
        await self.setup_flags([flag])
        context = {
            "distinct_id": "user123",
            "custom_properties": {
                "plan": "premium",
                "region": "US"
            }
        }
        result = self._flags.get_variant_value("test_flag", "fallback", context)
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_runtime_evaluation_not_satisfied(self):
        runtime_eval = {"plan": "premium", "region": "US"}
        flag = create_test_flag(runtime_evaluation=runtime_eval)
        await self.setup_flags([flag])
        context = {
            "distinct_id": "user123",
            "custom_properties": {
                "plan": "basic",
                "region": "US"
            }
        }
        result = self._flags.get_variant_value("test_flag", "fallback", context)
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_picks_correct_variant_with_hundred_percent_split(self):
        variants = [
            Variant(key="A", value="variant_a", is_control=False, split=100.0),
            Variant(key="B", value="variant_b", is_control=False, split=0.0),
            Variant(key="C", value="variant_c", is_control=False, split=0.0)
        ]
        flag = create_test_flag(variants=variants, rollout_percentage=100.0)
        await self.setup_flags([flag])
        result = self._flags.get_variant_value("test_flag", "fallback", {"distinct_id": "user123"})
        assert result == "variant_a"

    @respx.mock
    async def test_get_variant_value_picks_correct_variant_with_half_migrated_group_splits(self):
        variants = [
            Variant(key="A", value="variant_a", is_control=False, split=100.0),
            Variant(key="B", value="variant_b", is_control=False, split=0.0),
            Variant(key="C", value="variant_c", is_control=False, split=0.0)
        ]
        variant_splits = {"A": 0.0, "B": 100.0, "C": 0.0}
        flag = create_test_flag(variants=variants, rollout_percentage=100.0, variant_splits=variant_splits)
        await self.setup_flags([flag])
        result = self._flags.get_variant_value("test_flag", "fallback", {"distinct_id": "user123"})
        assert result == "variant_b"

    @respx.mock
    async def test_get_variant_value_picks_correct_variant_with_full_migrated_group_splits(self):
        variants = [
            Variant(key="A", value="variant_a", is_control=False),
            Variant(key="B", value="variant_b", is_control=False),
            Variant(key="C", value="variant_c", is_control=False),
        ]
        variant_splits = {"A": 0.0, "B": 0.0, "C": 100.0}
        flag = create_test_flag(variants=variants, rollout_percentage=100.0, variant_splits=variant_splits)
        await self.setup_flags([flag])
        result = self._flags.get_variant_value("test_flag", "fallback", {"distinct_id": "user123"})
        assert result == "variant_c"

    @respx.mock
    async def test_get_variant_value_picks_overriden_variant(self):
        variants = [
            Variant(key="A", value="variant_a", is_control=False, split=100.0),
            Variant(key="B", value="variant_b", is_control=False, split=0.0),
        ]
        flag = create_test_flag(variants=variants, variant_override=VariantOverride(key="B"))
        await self.setup_flags([flag])
        result = self._flags.get_variant_value("test_flag", "control", {"distinct_id": "user123"})
        assert result == "variant_b"

    @respx.mock
    async def test_get_variant_value_tracks_exposure_when_variant_selected(self):
        flag = create_test_flag()
        await self.setup_flags([flag])
        with patch('mixpanel.flags.utils.normalized_hash') as mock_hash:
            mock_hash.return_value = 0.5
            _ = self._flags.get_variant_value("test_flag", "fallback", {"distinct_id": "user123"})
            self._mock_tracker.assert_called_once()

    @respx.mock
    @pytest.mark.parametrize("experiment_id,is_experiment_active,use_qa_user", [
        ("exp-123", True, True),   # QA tester with active experiment
        ("exp-456", False, True),  # QA tester with inactive experiment
        ("exp-789", True, False),  # Regular user with active experiment
        ("exp-000", False, False), # Regular user with inactive experiment
        (None, None, True),        # QA tester with no experiment
        (None, None, False),       # Regular user with no experiment
    ])
    async def test_get_variant_value_tracks_exposure_with_correct_properties(self, experiment_id, is_experiment_active, use_qa_user):
        flag = create_test_flag(
            experiment_id=experiment_id,
            is_experiment_active=is_experiment_active,
            test_users={"qa_user": "treatment"}
        )

        await self.setup_flags([flag])

        distinct_id = "qa_user" if use_qa_user else "regular_user"

        with patch('mixpanel.flags.utils.normalized_hash') as mock_hash:
            mock_hash.return_value = 0.5
            _ = self._flags.get_variant_value("test_flag", "fallback", {"distinct_id": distinct_id})

        self._mock_tracker.assert_called_once()

        call_args = self._mock_tracker.call_args
        properties = call_args[0][2]

        assert properties["$experiment_id"] == experiment_id
        assert properties["$is_experiment_active"] == is_experiment_active

        if use_qa_user:
            assert properties["$is_qa_tester"] == True
        else:
            assert properties.get("$is_qa_tester") is None

    @respx.mock
    async def test_get_variant_value_does_not_track_exposure_on_fallback(self):
        await self.setup_flags([])
        _ = self._flags.get_variant_value("nonexistent_flag", "fallback", {"distinct_id": "user123"})
        self._mock_tracker.assert_not_called()

    @respx.mock
    async def test_get_variant_value_does_not_track_exposure_without_distinct_id(self):
        flag = create_test_flag(context="company")
        await self.setup_flags([flag])
        _ = self._flags.get_variant_value("nonexistent_flag", "fallback", {"company_id": "company123"})
        self._mock_tracker.assert_not_called()

    @respx.mock
    async def test_get_all_variants_returns_all_variants_when_user_in_rollout(self):
        flag1 = create_test_flag(flag_key="flag1", rollout_percentage=100.0)
        flag2 = create_test_flag(flag_key="flag2", rollout_percentage=100.0)
        await self.setup_flags([flag1, flag2])

        result = self._flags.get_all_variants({"distinct_id": "user123"})

        assert len(result) == 2 and "flag1" in result and "flag2" in result

    @respx.mock
    async def test_get_all_variants_returns_partial_variants_when_user_in_some_rollout(self):
        flag1 = create_test_flag(flag_key="flag1", rollout_percentage=100.0)
        flag2 = create_test_flag(flag_key="flag2", rollout_percentage=0.0)
        await self.setup_flags([flag1, flag2])

        result = self._flags.get_all_variants({"distinct_id": "user123"})

        assert len(result) == 1 and "flag1" in result and "flag2" not in result

    @respx.mock
    async def test_get_all_variants_returns_empty_dict_when_no_flags_configured(self):
        await self.setup_flags([])

        result = self._flags.get_all_variants({"distinct_id": "user123"})

        assert result == {}

    @respx.mock
    async def test_get_all_variants_does_not_track_exposure_events(self):
        flag1 = create_test_flag(flag_key="flag1", rollout_percentage=100.0)
        flag2 = create_test_flag(flag_key="flag2", rollout_percentage=100.0)
        await self.setup_flags([flag1, flag2])

        _ = self._flags.get_all_variants({"distinct_id": "user123"})

        self._mock_tracker.assert_not_called()

    @respx.mock
    async def test_track_exposure_event_successfully_tracks(self):
        flag = create_test_flag()
        await self.setup_flags([flag])

        variant = SelectedVariant(key="treatment", variant_value="treatment")
        self._flags.track_exposure_event("test_flag", variant, {"distinct_id": "user123"})

        self._mock_tracker.assert_called_once()

    @respx.mock
    async def test_are_flags_ready_returns_true_when_flags_loaded(self):
        flag = create_test_flag()
        await self.setup_flags([flag])
        assert self._flags.are_flags_ready() == True

    @respx.mock
    async def test_are_flags_ready_returns_true_when_empty_flags_loaded(self):
        flag = create_test_flag()
        await self.setup_flags([])
        assert self._flags.are_flags_ready() == True


    @respx.mock
    async def test_is_enabled_returns_false_for_nonexistent_flag(self):
        await self.setup_flags([])
        result = self._flags.is_enabled("nonexistent_flag", {"distinct_id": "user123"})
        assert result == False

    @respx.mock
    async def test_is_enabled_returns_true_for_true_variant_value(self):
        variants = [
            Variant(key="treatment", value=True, is_control=False, split=100.0)
        ]
        flag = create_test_flag(variants=variants, rollout_percentage=100.0)
        await self.setup_flags([flag])
        result = self._flags.is_enabled("test_flag", {"distinct_id": "user123"})
        assert result == True

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

        with patch.object(LocalFeatureFlagsProvider, '_afetch_flag_definitions', track_fetch_calls):
            flag_v1 = create_test_flag(rollout_percentage=0.0)
            flag_v2 = create_test_flag(rollout_percentage=100.0)

            flags_in_order=[[flag_v1], [flag_v2]]
            await self.setup_flags_with_polling(flags_in_order)
            async with polling_limit_check:
                await polling_limit_check.wait_for(lambda: polling_iterations >= len(flags_in_order))

            result2 = self._flags_with_polling.get_variant_value("test_flag", "fallback", {"distinct_id": "user123"})
            assert result2 != "fallback"

class TestLocalFeatureFlagsProviderSync:
    def setup_method(self):
        self.mock_tracker = Mock()
        config_with_polling = LocalFlagsConfig(enable_polling=True, polling_interval_in_seconds=0)
        self._flags_with_polling = LocalFeatureFlagsProvider("test-token", config_with_polling, "1.0.0", self.mock_tracker)

    def teardown_method(self):
        self._flags_with_polling.__exit__(None, None, None)

    def setup_flags_with_polling(self, flags_in_order: List[List[ExperimentationFlag]] = [[]]):
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
        flags_in_order=[[flag_v1], [flag_v2]]

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

        with patch.object(LocalFeatureFlagsProvider, '_fetch_flag_definitions', track_fetch_calls):
            self.setup_flags_with_polling(flags_in_order)
            polling_event.wait(timeout=5.0)
            assert (polling_iterations >= 3 )
            result2 = self._flags_with_polling.get_variant_value("test_flag", "fallback", {"distinct_id": "user123"})
            assert result2 != "fallback"
