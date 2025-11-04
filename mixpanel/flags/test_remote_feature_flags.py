import pytest
import httpx
import respx
import asyncio
from typing import Dict
from unittest.mock import Mock
from .types import RemoteFlagsConfig, RemoteFlagsResponse, SelectedVariant
from .remote_feature_flags import RemoteFeatureFlagsProvider

ENDPOINT = "https://api.mixpanel.com/flags"

def create_success_response(assigned_variants_per_flag: Dict[str, SelectedVariant]) -> httpx.Response:
    serialized_response = RemoteFlagsResponse(code=200, flags=assigned_variants_per_flag).model_dump()
    return httpx.Response(status_code=200, json=serialized_response)

class TestRemoteFeatureFlagsProviderAsync:
    @pytest.fixture(autouse=True)
    async def setup_method(self):
        config = RemoteFlagsConfig()
        self.mock_tracker = Mock()
        self._flags = RemoteFeatureFlagsProvider("test-token", config, "1.0.0", self.mock_tracker)
        yield
        await self._flags.__aexit__(None, None, None)

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_variant_value_is_fallback_if_call_fails(self):
        respx.get(ENDPOINT).mock(side_effect=httpx.RequestError("Network error"))

        result = await self._flags.aget_variant_value("test_flag", "control", {"distinct_id": "user123"})
        assert result == "control" 

    @respx.mock
    async def test_get_variant_value_is_fallback_if_bad_response_format(self):
        respx.get(ENDPOINT).mock(return_value=httpx.Response(200, text="invalid json"))

        result = await self._flags.aget_variant_value("test_flag", "control", {"distinct_id": "user123"})
        assert result == "control"

    @respx.mock
    async def test_get_variant_value_is_fallback_if_success_but_no_flag_found(self):
        respx.get(ENDPOINT).mock(
            return_value=create_success_response({}))

        result = await self._flags.aget_variant_value("test_flag", "control", {"distinct_id": "user123"})
        assert result == "control"

    @respx.mock
    async def test_get_variant_value_returns_expected_variant_from_api(self):
        respx.get(ENDPOINT).mock(
            return_value=create_success_response({"test_flag": SelectedVariant(variant_key="treatment", variant_value="treatment")}))

        result = await self._flags.aget_variant_value("test_flag", "control", {"distinct_id": "user123"})
        assert result == "treatment"

    @respx.mock
    async def test_get_variant_value_tracks_exposure_event_if_variant_selected(self):
        respx.get(ENDPOINT).mock(
            return_value=create_success_response({"test_flag": SelectedVariant(variant_key="treatment", variant_value="treatment")}))

        await self._flags.aget_variant_value("test_flag", "control", {"distinct_id": "user123"})

        pending = [task for task in asyncio.all_tasks() if not task.done() and task != asyncio.current_task()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        self.mock_tracker.assert_called_once()

    @respx.mock
    async def test_get_variant_value_does_not_track_exposure_event_if_fallback(self): 
        respx.get(ENDPOINT).mock(side_effect=httpx.RequestError("Network error"))
        await self._flags.aget_variant_value("test_flag", "control", {"distinct_id": "user123"})
        self.mock_tracker.assert_not_called()

    @respx.mock
    async def test_ais_enabled_returns_true_for_true_variant_value(self):
        respx.get(ENDPOINT).mock(
            return_value=create_success_response({"test_flag": SelectedVariant(variant_key="enabled", variant_value=True)}))

        result = await self._flags.ais_enabled("test_flag", {"distinct_id": "user123"})
        assert result == True

    @respx.mock
    async def test_ais_enabled_returns_false_for_false_variant_value(self):
        respx.get(ENDPOINT).mock(
            return_value=create_success_response({"test_flag": SelectedVariant(variant_key="disabled", variant_value=False)}))

        result = await self._flags.ais_enabled("test_flag", {"distinct_id": "user123"})
        assert result == False

    @respx.mock
    async def test_aget_all_variants_returns_all_variants_from_api(self):
        variants = {
            "flag1": SelectedVariant(variant_key="treatment1", variant_value="value1"),
            "flag2": SelectedVariant(variant_key="treatment2", variant_value="value2")
        }
        respx.get(ENDPOINT).mock(return_value=create_success_response(variants))

        result = await self._flags.aget_all_variants({"distinct_id": "user123"})

        assert result == variants

    @respx.mock
    async def test_aget_all_variants_returns_none_on_network_error(self):
        respx.get(ENDPOINT).mock(side_effect=httpx.RequestError("Network error"))

        result = await self._flags.aget_all_variants({"distinct_id": "user123"})

        assert result is None

    @respx.mock
    async def test_aget_all_variants_does_not_track_exposure_events(self):
        variants = {
            "flag1": SelectedVariant(variant_key="treatment1", variant_value="value1"),
            "flag2": SelectedVariant(variant_key="treatment2", variant_value="value2")
        }
        respx.get(ENDPOINT).mock(return_value=create_success_response(variants))

        await self._flags.aget_all_variants({"distinct_id": "user123"})

        self.mock_tracker.assert_not_called()

    @respx.mock
    async def test_aget_all_variants_handles_empty_response(self):
        respx.get(ENDPOINT).mock(return_value=create_success_response({}))

        result = await self._flags.aget_all_variants({"distinct_id": "user123"})

        assert result == {}

    @respx.mock
    async def test_atrack_exposure_event_successfully_tracks(self):
        variant = SelectedVariant(variant_key="treatment", variant_value="treatment")

        await self._flags.atrack_exposure_event("test_flag", variant, {"distinct_id": "user123"})

        pending = [task for task in asyncio.all_tasks() if not task.done() and task != asyncio.current_task()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        self.mock_tracker.assert_called_once()

class TestRemoteFeatureFlagsProviderSync:
    def setup_method(self):
        config = RemoteFlagsConfig()
        self.mock_tracker = Mock()
        self._flags = RemoteFeatureFlagsProvider("test-token", config, "1.0.0", self.mock_tracker)

    def teardown_method(self):
        self._flags.__exit__(None, None, None)

    @respx.mock
    def test_get_variant_value_is_fallback_if_call_fails(self):
        respx.get(ENDPOINT).mock(side_effect=httpx.RequestError("Network error"))

        result = self._flags.get_variant_value("test_flag", "control", {"distinct_id": "user123"})
        assert result == "control"

    @respx.mock
    def test_get_variant_value_is_fallback_if_bad_response_format(self):
        respx.get(ENDPOINT).mock(return_value=httpx.Response(200, text="invalid json"))

        result = self._flags.get_variant_value("test_flag", "control", {"distinct_id": "user123"})
        assert result == "control"

    @respx.mock
    def test_get_variant_value_is_fallback_if_success_but_no_flag_found(self):
        respx.get(ENDPOINT).mock(
            return_value=create_success_response({}))

        result = self._flags.get_variant_value("test_flag", "control", {"distinct_id": "user123"})
        assert result == "control"

    @respx.mock
    def test_get_variant_value_returns_expected_variant_from_api(self):
        respx.get(ENDPOINT).mock(
            return_value=create_success_response({"test_flag": SelectedVariant(variant_key="treatment", variant_value="treatment")}))

        result = self._flags.get_variant_value("test_flag", "control", {"distinct_id": "user123"})
        assert result == "treatment"

    @respx.mock
    def test_get_variant_value_tracks_exposure_event_if_variant_selected(self):
        respx.get(ENDPOINT).mock(
            return_value=create_success_response({"test_flag": SelectedVariant(variant_key="treatment", variant_value="treatment")}))

        self._flags.get_variant_value("test_flag", "control", {"distinct_id": "user123"})
        self.mock_tracker.assert_called_once()

    @respx.mock
    def test_get_variant_value_does_not_track_exposure_event_if_fallback(self):
        respx.get(ENDPOINT).mock(side_effect=httpx.RequestError("Network error"))
        self._flags.get_variant_value("test_flag", "control", {"distinct_id": "user123"})
        self.mock_tracker.assert_not_called()

    @respx.mock
    def test_is_enabled_returns_true_for_true_variant_value(self):
        respx.get(ENDPOINT).mock(
            return_value=create_success_response({"test_flag": SelectedVariant(variant_key="enabled", variant_value=True)}))

        result = self._flags.is_enabled("test_flag", {"distinct_id": "user123"})
        assert result == True

    @respx.mock
    def test_is_enabled_returns_false_for_false_variant_value(self):
        respx.get(ENDPOINT).mock(
            return_value=create_success_response({"test_flag": SelectedVariant(variant_key="disabled", variant_value=False)}))

        result = self._flags.is_enabled("test_flag", {"distinct_id": "user123"})
        assert result == False

    @respx.mock
    def test_get_all_variants_returns_all_variants_from_api(self):
        variants = {
            "flag1": SelectedVariant(variant_key="treatment1", variant_value="value1"),
            "flag2": SelectedVariant(variant_key="treatment2", variant_value="value2")
        }
        respx.get(ENDPOINT).mock(return_value=create_success_response(variants))

        result = self._flags.get_all_variants({"distinct_id": "user123"})

        assert result == variants

    @respx.mock
    def test_get_all_variants_returns_none_on_network_error(self):
        respx.get(ENDPOINT).mock(side_effect=httpx.RequestError("Network error"))

        result = self._flags.get_all_variants({"distinct_id": "user123"})

        assert result is None

    @respx.mock
    def test_get_all_variants_does_not_track_exposure_events(self):
        variants = {
            "flag1": SelectedVariant(variant_key="treatment1", variant_value="value1"),
            "flag2": SelectedVariant(variant_key="treatment2", variant_value="value2")
        }
        respx.get(ENDPOINT).mock(return_value=create_success_response(variants))

        self._flags.get_all_variants({"distinct_id": "user123"})

        self.mock_tracker.assert_not_called()

    @respx.mock
    def test_get_all_variants_handles_empty_response(self):
        respx.get(ENDPOINT).mock(return_value=create_success_response({}))

        result = self._flags.get_all_variants({"distinct_id": "user123"})

        assert result == {}

    @respx.mock
    def test_track_exposure_event_successfully_tracks(self):
        variant = SelectedVariant(variant_key="treatment", variant_value="treatment")

        self._flags.track_exposure_event("test_flag", variant, {"distinct_id": "user123"})

        self.mock_tracker.assert_called_once()

