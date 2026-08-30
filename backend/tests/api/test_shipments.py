import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import requires_db

TEST_USER = "owner@heat2shelf.dev"
OTHER_USER = "other@heat2shelf.dev"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


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


@requires_db
class TestCreateShipment:
    def test_create_shipment_draft(self, client: TestClient, approved_profile, isolated_db) -> None:
        resp = client.post(
            "/api/v1/shipments",
            json=shipment_payload(approved_profile),
            headers={"X-User-Email": TEST_USER},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "draft"
        assert uuid.UUID(body["id"])
        assert body["origin"]["label"] == "San Jose, CA"
        assert body["origin"]["coordinate"]["coordinates"] == [-121.8863, 37.3382]
        # departure normalized to UTC
        assert body["departure_time_utc"].endswith("+00:00") or body["departure_time_utc"].endswith("Z")

    def test_create_requires_approved_profile(self, client: TestClient, isolated_db) -> None:
        resp = client.post(
            "/api/v1/shipments",
            json={
                "product_id": str(uuid.uuid4()),
                "origin": {"label": "A", "latitude": 1.0, "longitude": 1.0},
                "destination": {"label": "B", "latitude": 2.0, "longitude": 2.0},
                "departure_time": "2026-08-21T12:00:00Z",
            },
            headers={"X-User-Email": TEST_USER},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "PRODUCT_PROFILE_UNAVAILABLE"

    def test_naive_departure_rejected(self, client: TestClient, approved_profile) -> None:
        payload = shipment_payload(approved_profile)
        payload["departure_time"] = "2026-08-21T12:00:00"
        resp = client.post(
            "/api/v1/shipments",
            json=payload,
            headers={"X-User-Email": TEST_USER},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_invalid_coordinates_rejected(self, client: TestClient, approved_profile) -> None:
        payload = shipment_payload(approved_profile)
        payload["origin"]["latitude"] = 95.0
        resp = client.post(
            "/api/v1/shipments",
            json=payload,
            headers={"X-User-Email": TEST_USER},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_COORDINATES"


@requires_db
class TestGetShipment:
    def test_get_own_shipment(self, client: TestClient, approved_profile, isolated_db) -> None:
        created = client.post(
            "/api/v1/shipments",
            json=shipment_payload(approved_profile),
            headers={"X-User-Email": TEST_USER},
        ).json()
        resp = client.get(
            f"/api/v1/shipments/{created['id']}",
            headers={"X-User-Email": TEST_USER},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_other_user_cannot_read(self, client: TestClient, approved_profile) -> None:
        created = client.post(
            "/api/v1/shipments",
            json=shipment_payload(approved_profile),
            headers={"X-User-Email": TEST_USER},
        ).json()
        resp = client.get(
            f"/api/v1/shipments/{created['id']}",
            headers={"X-User-Email": OTHER_USER},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "SHIPMENT_NOT_FOUND"

    def test_unknown_shipment_404(self, client: TestClient, isolated_db) -> None:
        resp = client.get(
            f"/api/v1/shipments/{uuid.uuid4()}",
            headers={"X-User-Email": TEST_USER},
        )
        assert resp.status_code == 404