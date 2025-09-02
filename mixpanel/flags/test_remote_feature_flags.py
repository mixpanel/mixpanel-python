import pytest
import httpx
import respx
import asyncio
from typing import Dict
from unittest.mock import Mock
from .types import RemoteFlagsConfig, ExperimentationFlags, RemoteFlagsResponse, SelectedVariant
from .remote_feature_flags import RemoteFeatureFlagsProvider

ENDPOINT = "https://api.mixpanel.com/flags"

@pytest.mark.asyncio
class TestRemoteFeatureFlagsProvider:
    def setup_method(self):
        config = RemoteFlagsConfig()
        mock_tracker = Mock()
        self._flags = RemoteFeatureFlagsProvider("test-token", config, "1.0.0", mock_tracker)

    @staticmethod
    def create_success_response(assigned_variants_per_flag: Dict[str, SelectedVariant]) -> httpx.Response:
        serialized_response = RemoteFlagsResponse(code=200, flags=assigned_variants_per_flag).model_dump()
        return httpx.Response(status_code=200, json=serialized_response)

    @respx.mock
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
            return_value=self.create_success_response({}))

        result = await self._flags.aget_variant_value("test_flag", "control", {"distinct_id": "user123"})

        assert result == "control"

    @respx.mock
    async def test_get_variant_value_returns_expected_variant_from_api(self):
        respx.get(ENDPOINT).mock(
            return_value=self.create_success_response({"test_flag": SelectedVariant(variant_key="treatment", variant_value="treatment")}))

        result = await self._flags.aget_variant_value("test_flag", "control", {"distinct_id": "user123"})

        assert result == "treatment"

    @respx.mock
    async def test_get_variant_value_tracks_exposure_event_if_variant_selected(self):
        respx.get(ENDPOINT).mock(
            return_value=self.create_success_response({"test_flag": SelectedVariant(variant_key="treatment", variant_value="treatment")}))

        await self._flags.aget_variant_value("test_flag", "control", {"distinct_id": "user123"})

        pending = [task for task in asyncio.all_tasks() if not task.done() and task != asyncio.current_task()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        self._flags._tracker.assert_called_once()

    @respx.mock
    async def test_get_variant_value_does_not_track_exposure_event_if_fallback(self): 
        respx.get(ENDPOINT).mock(side_effect=httpx.RequestError("Network error"))

        await self._flags.aget_variant_value("test_flag", "control", {"distinct_id": "user123"})

        self._flags._tracker.assert_not_called()