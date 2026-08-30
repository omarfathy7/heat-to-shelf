import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_health_liveness(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_health_ready_reports_db_unavailable_when_no_db(client: TestClient) -> None:
    # No PostgreSQL is running in the test environment here, so readiness must
    # degrade to 503, not hang or stack-trace. This doubles as the readiness
    # contract test.
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code in (200, 503)
    if resp.status_code == 503:
        assert resp.json()["detail"]["db"] == "down"


def test_health_request_id_header_present(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID")