import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.api.test_shipments_thermal_journey import (
    FakeHeatProvider,
    create_shipment,
    patch_heat_provider,
)
from tests.conftest import requires_db

TEST_USER = "owner@heat2shelf.dev"
OTHER_USER = "other@heat2shelf.dev"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@requires_db
class TestShipmentRisk:
    def test_risk_requires_thermal_data(
        self, client: TestClient, approved_profile, isolated_db
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        resp = client.get(
            f"/api/v1/shipments/{created['id']}/risk",
            headers={"X-User-Email": TEST_USER},
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["error"]["code"] == "THERMAL_DATA_MISSING"

    def test_risk_after_analyze_reports_critical_level(
        self, client: TestClient, approved_profile, isolated_db, patch_heat_provider
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        analyze = client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        assert analyze.status_code == 202, analyze.text

        resp = client.get(
            f"/api/v1/shipments/{created['id']}/risk",
            headers={"X-User-Email": TEST_USER},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["shipment_id"] == created["id"]
        assert body["scenario_id"] is None
        assert 0.0 <= body["score"] <= 100.0
        assert body["level"] in {"safe", "warning", "high", "critical"}
        assert body["peak_temperature_c"] == 25.0
        assert body["time_above_threshold_hours"] > 0.0
        assert body["longest_persistence_hours"] > 0.0
        assert body["high_risk_segment_count"] == 20
        assert body["calculation_version"] == "1.0.0"
        assert isinstance(body["components"], dict)
        assert set(body["components"]) == {
            "peak_temperature",
            "duration",
            "persistence",
            "high_risk_segments",
        }
        assert body["explanation_factors"]["observed_segments"] == 20

    def test_risk_requires_ownership(
        self, client: TestClient, approved_profile, isolated_db, patch_heat_provider
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        resp = client.get(
            f"/api/v1/shipments/{created['id']}/risk",
            headers={"X-User-Email": OTHER_USER},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "SHIPMENT_NOT_FOUND"

    def test_risk_is_idempotent(
        self, client: TestClient, approved_profile, isolated_db, patch_heat_provider
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        first = client.get(
            f"/api/v1/shipments/{created['id']}/risk",
            headers={"X-User-Email": TEST_USER},
        ).json()
        second = client.get(
            f"/api/v1/shipments/{created['id']}/risk",
            headers={"X-User-Email": TEST_USER},
        ).json()
        assert first["score"] == second["score"]
        assert first["level"] == second["level"]
        assert first["calculation_version"] == second["calculation_version"]