import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import requires_db

UTC = timezone.utc
TEST_USER = "owner@heat2shelf.dev"
OTHER_USER = "other@heat2shelf.dev"


class FakeHeatProvider:
    """In-memory TemperatureProvider for the analyze flow (shared call counter)."""

    calls = 0
    no_overlap = False

    @classmethod
    def reset(cls) -> None:
        cls.calls = 0
        cls.no_overlap = False

    def __init__(self, **_) -> None:
        pass

    async def get_heatmap(self, aoi, observation_time):
        type(self).calls += 1
        if type(self).no_overlap:
            ring = [(100.0, 100.0), (101.0, 100.0), (101.0, 101.0), (100.0, 101.0), (100.0, 100.0)]
            lon, lat = 100.5, 100.5
        else:
            ring = [
                (aoi.min_lon, aoi.min_lat),
                (aoi.max_lon, aoi.min_lat),
                (aoi.max_lon, aoi.max_lat),
                (aoi.min_lon, aoi.max_lat),
                (aoi.min_lon, aoi.min_lat),
            ]
            lon, lat = (aoi.min_lon + aoi.max_lon) / 2, (aoi.min_lat + aoi.max_lat) / 2
        from app.domain.value_objects.thermal import HeatmapData, ThermalTile

        tile = ThermalTile(
            tile_id=f"fake-t{type(self).calls}",
            longitude=lon,
            latitude=lat,
            temperature_c=25.0,
            observed_at_utc=observation_time,
            polygon=ring,
            data_quality={"quality": "good", "stale": False, "stale_minutes": 0},
        )
        return HeatmapData(
            source="fortyguard",
            observation_time=observation_time,
            bbox=aoi,
            tiles=[tile],
            request_metadata={"fixture": True},
        )


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def patch_heat_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeHeatProvider.reset()
    monkeypatch.setattr(
        "app.application.use_cases.analyze_shipment.FortyGuardTemperatureProvider",
        FakeHeatProvider,
    )


def shipment_payload(profile) -> dict:
    return {
        "product_id": str(profile.product_id),
        "origin": {
            "label": "San Jose, CA",
            "latitude": 37.3382,
            "longitude": -121.8863,
        },
        "destination": {
            "label": "San Francisco, CA",
            "latitude": 37.7749,
            "longitude": -122.4194,
        },
        "departure_time": "2026-08-21T12:00:00-07:00",
    }


def create_shipment(client, profile):
    return client.post(
        "/api/v1/shipments",
        json=shipment_payload(profile),
        headers={"X-User-Email": TEST_USER},
    )


@requires_db
class TestAnalyze:
    def test_analyze_develops_thermal_journey(
        self, client: TestClient, approved_profile, isolated_db, patch_heat_provider
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        resp = client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["shipment_id"] == created["id"]
        assert body["status"] == "ready"
        assert body["developed_segments"] == 20
        assert body["observed_segments"] == 20
        assert FakeHeatProvider.calls >= 1

    def test_analyze_unknown_when_tiles_missing(
        self, client: TestClient, approved_profile, isolated_db, monkeypatch
    ) -> None:
        class NoOverlap(FakeHeatProvider):
            pass

        NoOverlap.no_overlap = True
        monkeypatch.setattr(
            "app.application.use_cases.analyze_shipment.FortyGuardTemperatureProvider",
            NoOverlap,
        )
        created = create_shipment(client, approved_profile).json()
        resp = client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["observed_segments"] == 0
        related = client.get(
            f"/api/v1/shipments/{created['id']}/thermal-journey",
            headers={"X-User-Email": TEST_USER},
        ).json()
        assert all(seg["observation"]["threshold_status"] == "unknown" for seg in related["segments"])

    def test_analyze_requires_ownership(
        self, client: TestClient, approved_profile, isolated_db, patch_heat_provider
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        resp = client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": OTHER_USER},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "SHIPMENT_NOT_FOUND"

    def test_analyze_provider_failure_reported(
        self, client: TestClient, approved_profile, isolated_db, monkeypatch
    ) -> None:
        from app.core.errors import AppError, ErrorCode

        class FailingProvider:
            def __init__(self, **_) -> None:
                pass

            async def get_heatmap(self, aoi, observation_time):
                raise AppError(
                    ErrorCode.FORTYGUARD_RESPONSE_INVALID,
                    "heatmap payload rejected",
                    status_code=502,
                )

        monkeypatch.setattr(
            "app.application.use_cases.analyze_shipment.FortyGuardTemperatureProvider",
            FailingProvider,
        )
        created = create_shipment(client, approved_profile).json()
        resp = client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == "FORTYGUARD_RESPONSE_INVALID"


@requires_db
class TestThermalJourney:
    def test_journey_empty_before_analyze(
        self, client: TestClient, approved_profile, isolated_db
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        resp = client.get(
            f"/api/v1/shipments/{created['id']}/thermal-journey",
            headers={"X-User-Email": TEST_USER},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["segments"] == []
        assert body["geojson"]["features"] == []

    def test_journey_after_analyze_has_geojson(
        self, client: TestClient, approved_profile, isolated_db, patch_heat_provider
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        body = client.get(
            f"/api/v1/shipments/{created['id']}/thermal-journey",
            headers={"X-User-Email": TEST_USER},
        ).json()

        assert body["status"] == "ready"
        assert len(body["segments"]) == 20
        assert len(body["geojson"]["features"]) == 20
        first = body["segments"][0]
        assert first["sequence"] == 1
        assert first["observation"]["threshold_status"] == "critical"
        assert first["observation"]["temperature_c"] == 25.0
        assert first["observation"]["latitude"] is not None
        geom = body["geojson"]["features"][0]["geometry"]
        assert geom["type"] == "LineString"
        assert len(geom["coordinates"]) >= 2
        assert body["geojson"]["features"][0]["properties"]["threshold_status"] == "critical"

    def test_journey_ownership(
        self, client: TestClient, approved_profile, isolated_db, patch_heat_provider
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        resp = client.get(
            f"/api/v1/shipments/{created['id']}/thermal-journey",
            headers={"X-User-Email": OTHER_USER},
        )
        assert resp.status_code == 404


@requires_db
class TestAnalyzeIdempotency:
    def test_reanalyze_replaces_observations(
        self, client: TestClient, approved_profile, isolated_db, patch_heat_provider
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        resp = client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["developed_segments"] == 20
        journey = client.get(
            f"/api/v1/shipments/{created['id']}/thermal-journey",
            headers={"X-User-Email": TEST_USER},
        ).json()
        assert len(journey["segments"]) == 20
        assert all(seg["observation"] is not None for seg in journey["segments"])