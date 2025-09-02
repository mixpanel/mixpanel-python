import pytest
import respx
import httpx
from unittest.mock import Mock, patch
from typing import Dict, Optional
from .types import LocalFlagsConfig, ExperimentationFlag, RuleSet, Variant, Rollout, FlagTestUsers, ExperimentationFlags
from .local_feature_flags import LocalFeatureFlagsProvider

@pytest.mark.asyncio
class TestLocalFeatureFlagsProvider:
    async def setup_flags(self, flags):
        respx.get("https://api.mixpanel.com/flags/definitions").mock(
            return_value=self.create_flags_response(flags))

        config = LocalFlagsConfig()
        config.enable_polling = False
        mock_tracker = Mock()
        flags_provider = LocalFeatureFlagsProvider("test-token", config, "1.0.0", mock_tracker)
        await flags_provider.astart_polling_for_definitions()
        return flags_provider

    @staticmethod
    def create_test_flag(
        flag_key: str = "test_flag",
        context: str = "distinct_id", 
        variants: Optional[list]= None,
        rollout_percentage: float = 100.0,
        runtime_evaluation: Optional[Dict] = None,
        test_users: Optional[Dict[str, str]] = None) -> ExperimentationFlag:

        if variants is None:
            variants = [
                Variant(key="control", value="control", is_control=True, split=50.0),
                Variant(key="treatment", value="treatment", is_control=False, split=50.0)
            ]

        rollouts = [Rollout(
            rollout_percentage=rollout_percentage,
            runtime_evaluation_definition=runtime_evaluation,
            variant_override=None
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
            context=context
        )

    def create_flags_response(self, flags: list) -> httpx.Response:
        if flags is None:
            flags = []
        response_data = ExperimentationFlags(flags=flags).model_dump()
        return httpx.Response(status_code=200, json=response_data)

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_no_flag_definitions(self):
        flags = await self.setup_flags([])
        result = flags.get_variant_value("nonexistent_flag", "control", {"distinct_id": "user123"})
        assert result == "control"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_flag_does_not_exist(self):
        other_flag = self.create_test_flag("other_flag")
        flags = await self.setup_flags([other_flag])
        result = flags.get_variant_value("nonexistent_flag", "control", {"distinct_id": "user123"})
        assert result == "control"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_no_context(self):
        flag = self.create_test_flag(context="distinct_id")
        flags = await self.setup_flags([flag])
        result = flags.get_variant_value("test_flag", "fallback", {})
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_wrong_context_key(self):
        flag = self.create_test_flag(context="user_id")
        flags = await self.setup_flags([flag])
        result = flags.get_variant_value("test_flag", "fallback", {"distinct_id": "user123"})
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_returns_test_user_variant_when_configured(self):
        variants = [
            Variant(key="control", value="false", is_control=True, split=50.0),
            Variant(key="treatment", value="true", is_control=False, split=50.0)
        ]
        flag = self.create_test_flag(
            variants=variants,
            test_users={"test_user": "treatment"}
        )

        flags = await self.setup_flags([flag])

        result = flags.get_variant_value("test_flag", "control", {"distinct_id": "test_user"})

        assert result == "true"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_test_user_variant_not_configured(self):
        variants = [
            Variant(key="control", value="false", is_control=True, split=50.0),
            Variant(key="treatment", value="true", is_control=False, split=50.0)
        ]
        flag = self.create_test_flag(
            variants=variants,
            test_users={"test_user": "nonexistent_variant"}
        )
        flags = await self.setup_flags([flag])

        with patch('mixpanel.flags.utils.normalized_hash') as mock_hash:
            mock_hash.return_value = 0.5
            result = flags.get_variant_value("test_flag", "fallback", {"distinct_id": "test_user"})
            assert result == "false"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_rollout_percentage_zero(self):
        flag = self.create_test_flag(rollout_percentage=0.0)
        flags = await self.setup_flags([flag])

        result = flags.get_variant_value("test_flag", "fallback", {"distinct_id": "user123"})
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_returns_variant_when_rollout_percentage_hundred(self):
        flag = self.create_test_flag(rollout_percentage=100.0)
        flags = await self.setup_flags([flag])
        result = flags.get_variant_value("test_flag", "fallback", {"distinct_id": "user123"})
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_respects_runtime_evaluation_satisfied(self):
        runtime_eval = {"plan": "premium", "region": "US"}
        flag = self.create_test_flag(runtime_evaluation=runtime_eval)
        flags = await self.setup_flags([flag])
        context = {
            "distinct_id": "user123",
            "custom_properties": {
                "plan": "premium",
                "region": "US"
            }
        }

        result = flags.get_variant_value("test_flag", "fallback", context)
        assert result != "fallback"

    @respx.mock
    async def test_get_variant_value_returns_fallback_when_runtime_evaluation_not_satisfied(self):
        runtime_eval = {"plan": "premium", "region": "US"}
        flag = self.create_test_flag(runtime_evaluation=runtime_eval)
        flags = await self.setup_flags([flag])

        context = {
            "distinct_id": "user123",
            "custom_properties": {
                "plan": "basic",
                "region": "US"
            }
        }

        result = flags.get_variant_value("test_flag", "fallback", context)
        assert result == "fallback"

    @respx.mock
    async def test_get_variant_value_picks_correct_variant_with_hundred_percent_split(self):
        variants = [
            Variant(key="A", value="variant_a", is_control=False, split=100.0),
            Variant(key="B", value="variant_b", is_control=False, split=0.0),
            Variant(key="C", value="variant_c", is_control=False, split=0.0)
        ]
        flag = self.create_test_flag(variants=variants, rollout_percentage=100.0)
        flags = await self.setup_flags([flag])

        result = flags.get_variant_value("test_flag", "fallback", {"distinct_id": "user123"})
        assert result == "variant_a"

    @respx.mock
    async def test_get_variant_value_tracks_exposure_when_variant_selected(self):
        flag = self.create_test_flag()
        flags = await self.setup_flags([flag])
        with patch('mixpanel.flags.utils.normalized_hash') as mock_hash:
            mock_hash.return_value = 0.5
            _ = flags.get_variant_value("test_flag", "fallback", {"distinct_id": "user123"})
            flags._tracker.assert_called_once()

    @respx.mock
    async def test_get_variant_value_does_not_track_exposure_on_fallback(self):
        flags = await self.setup_flags([])
        _ = flags.get_variant_value("nonexistent_flag", "fallback", {"distinct_id": "user123"})

        flags._tracker.assert_not_called()