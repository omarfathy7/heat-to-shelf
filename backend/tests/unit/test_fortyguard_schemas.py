import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.errors import AppError, ErrorCode
from app.infrastructure.fortyguard.schemas import HeatmapResponse, is_stale

FIXTURES = Path(__file__).parents[1] / "fixtures" / "fortyguard"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class TestHeatmapValidation:
    def test_valid_fixture_parses(self) -> None:
        response = HeatmapResponse.model_validate(load("heatmap_valid.json"))
        assert response.type == "FeatureCollection"
        assert len(response.features) == 2
        # temperatures stay in Celsius, coordinates preserve lon/lat order
        assert response.features[0].properties.temperature_c == 28.4
        assert response.features[0].geometry.coordinates[0][0] == [-121.89, 37.34]

    def test_bad_geometry_rejected(self) -> None:
        with pytest.raises((AppError, ValueError)):
            HeatmapResponse.model_validate(load("heatmap_bad_geometry.json"))

    def test_reversed_coordinate_order_rejected(self) -> None:
        with pytest.raises(AppError) as exc:
            HeatmapResponse.model_validate(load("heatmap_reversed_coords.json"))
        assert exc.value.code == ErrorCode.FORTYGUARD_RESPONSE_INVALID

    def test_fahrenheit_scale_rejected(self) -> None:
        with pytest.raises(AppError) as exc:
            HeatmapResponse.model_validate(load("heatmap_fahrenheit.json"))
        assert exc.value.code == ErrorCode.FORTYGUARD_RESPONSE_INVALID

    def test_missing_temperature_rejected(self) -> None:
        with pytest.raises((AppError, ValueError)):
            HeatmapResponse.model_validate(load("heatmap_missing_temp.json"))

    def test_empty_feature_collection_rejected(self) -> None:
        with pytest.raises(AppError) as exc:
            HeatmapResponse.model_validate({"type": "FeatureCollection", "features": []})
        assert exc.value.code == ErrorCode.FORTYGUARD_RESPONSE_INVALID


class TestIsStale:
    def test_within_window_not_stale(self) -> None:
        ref = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)
        obs = ref - timedelta(minutes=30)
        assert is_stale(obs, ref, max_staleness_minutes=60) is False

    def test_beyond_window_stale(self) -> None:
        ref = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)
        obs = ref - timedelta(hours=2)
        assert is_stale(obs, ref, max_staleness_minutes=60) is True