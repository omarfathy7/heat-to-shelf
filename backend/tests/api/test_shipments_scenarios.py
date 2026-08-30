import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.api.test_shipments_thermal_journey import create_shipment, patch_heat_provider
from tests.conftest import requires_db

TEST_USER = "owner@heat2shelf.dev"
OTHER_USER = "other@heat2shelf.dev"


class FakeScenarioProvider:
    """Temperature varies with observation hour so departure times differ."""

    calls = 0

    @classmethod
    def reset(cls) -> None:
        cls.calls = 0

    def __init__(self, **_) -> None:
        pass

    async def get_heatmap(self, aoi, observation_time):
        type(self).calls += 1
        from app.domain.value_objects.thermal import HeatmapData, ThermalTile

        temperature_c = 8.0 + (observation_time.hour % 12)
        lon, lat = (aoi.min_lon + aoi.max_lon) / 2, (aoi.min_lat + aoi.max_lat) / 2
        ring = [
            (aoi.min_lon, aoi.min_lat),
            (aoi.max_lon, aoi.min_lat),
            (aoi.max_lon, aoi.max_lat),
            (aoi.min_lon, aoi.max_lat),
            (aoi.min_lon, aoi.min_lat),
        ]
        tile = ThermalTile(
            tile_id=f"fake-s{type(self).calls}",
            longitude=lon,
            latitude=lat,
            temperature_c=temperature_c,
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
def patch_scenario_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeScenarioProvider.reset()
    monkeypatch.setattr(
        "app.application.use_cases.run_scenarios.FortyGuardTemperatureProvider",
        FakeScenarioProvider,
    )


def scenario_times() -> list[str]:
    return [
        "2026-08-21T06:00:00-07:00",
        "2026-08-21T12:00:00-07:00",
        "2026-08-21T19:00:00-07:00",
    ]


def post_scenarios(client, shipment_id, times, user=TEST_USER):
    return client.post(
        f"/api/v1/shipments/{shipment_id}/scenarios",
        json={"departure_times": times},
        headers={"X-User-Email": user},
    )


@requires_db
class TestScenarios:
    def test_scenarios_require_analyzed_journey(
        self, client: TestClient, approved_profile, isolated_db, patch_scenario_provider
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        resp = post_scenarios(client, created["id"], scenario_times())
        assert resp.status_code == 422, resp.text
        assert resp.json()["error"]["code"] == "THERMAL_DATA_MISSING"

    def test_scenarios_rank_and_recommend(
        self,
        client: TestClient,
        approved_profile,
        isolated_db,
        patch_heat_provider,
        patch_scenario_provider,
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        analyze = client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        assert analyze.status_code == 202, analyze.text

        resp = post_scenarios(client, created["id"], scenario_times())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["shipment_id"] == created["id"]
        assert body["baseline"]["scenario_id"] is None
        assert 0.0 <= body["baseline"]["score"] <= 100.0

        scenarios = body["scenarios"]
        assert len(scenarios) == 3
        assert all(s["status"] == "completed" for s in scenarios)
        assert {s["rank"] for s in scenarios} == {1, 2, 3}
        assert [s["score"] is not None for s in scenarios].count(True) == 3
        chosen = [s for s in scenarios if s["is_recommended"]]
        assert len(chosen) == 1
        recommended = chosen[0]
        assert recommended["rank"] == 1
        assert recommended["score"] == min(s["score"] for s in scenarios)

        rec = body["recommendation"]
        assert rec["recommended_scenario_id"] == recommended["id"]
        assert rec["recommended_departure_time_utc"] == recommended["departure_time_utc"]
        assert rec["original_score"] == body["baseline"]["score"]
        assert rec["recommended_score"] == recommended["score"]
        assert rec["exposure_reduction_percent"] >= 0.0
        assert rec["original_level"] in {"safe", "warning", "high", "critical"}
        assert rec["recommended_level"] in {"safe", "warning", "high", "critical"}
        assert rec["reason_codes"] != []
        assert FakeScenarioProvider.calls > 0

    def test_scenarios_requires_ownership(
        self,
        client: TestClient,
        approved_profile,
        isolated_db,
        patch_heat_provider,
        patch_scenario_provider,
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        resp = post_scenarios(client, created["id"], scenario_times(), user=OTHER_USER)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "SHIPMENT_NOT_FOUND"

    def test_scenarios_require_aware_times(
        self, client: TestClient, approved_profile, isolated_db, patch_scenario_provider
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        resp = post_scenarios(
            client,
            created["id"],
            ["2026-08-21T06:00:00", "2026-08-21T12:00:00"],
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_scenarios_outside_horizon_rejected(
        self,
        client: TestClient,
        approved_profile,
        isolated_db,
        patch_heat_provider,
        patch_scenario_provider,
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        resp = post_scenarios(client, created["id"], ["2027-01-01T12:00:00-07:00"])
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "INVALID_TIME_WINDOW"

    def test_scenarios_all_failed_reports_analysis_failed(
        self, client: TestClient, approved_profile, isolated_db, monkeypatch
    ) -> None:
        from app.core.errors import AppError, ErrorCode

        class FailingProvider:
            def __init__(self, **_) -> None:
                pass

            async def get_heatmap(self, aoi, observation_time):
                raise AppError(
                    ErrorCode.FORTYGUARD_PROVIDER_FAILED,
                    "simulated provider outage",
                    status_code=502,
                )

        monkeypatch.setattr(
            "app.application.use_cases.run_scenarios.FortyGuardTemperatureProvider",
            FailingProvider,
        )
        created = create_shipment(client, approved_profile).json()
        client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        resp = post_scenarios(client, created["id"], scenario_times())
        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == "ANALYSIS_FAILED"


@requires_db
class TestRecommendation:
    def test_recommendation_missing_before_scenarios(
        self, client: TestClient, approved_profile, isolated_db, patch_heat_provider
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        resp = client.get(
            f"/api/v1/shipments/{created['id']}/recommendation",
            headers={"X-User-Email": TEST_USER},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "RECOMMENDATION_UNAVAILABLE"

    def test_recommendation_returns_latest(
        self,
        client: TestClient,
        approved_profile,
        isolated_db,
        patch_heat_provider,
        patch_scenario_provider,
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        run = post_scenarios(client, created["id"], scenario_times()).json()

        resp = client.get(
            f"/api/v1/shipments/{created['id']}/recommendation",
            headers={"X-User-Email": TEST_USER},
        )
        assert resp.status_code == 200, resp.text
        got = resp.json()
        assert got["recommended_scenario_id"] == run["recommendation"]["recommended_scenario_id"]
        assert got["recommended_departure_time_utc"] == run["recommendation"][
            "recommended_departure_time_utc"
        ]
        assert got["original_score"] == run["recommendation"]["original_score"]
        assert got["recommended_score"] == run["recommendation"]["recommended_score"]
        assert got["exposure_reduction_percent"] == run["recommendation"][
            "exposure_reduction_percent"
        ]
        assert got["id"] is not None
        assert got["created_at"] is not None

    def test_recommendation_requires_ownership(
        self,
        client: TestClient,
        approved_profile,
        isolated_db,
        patch_heat_provider,
        patch_scenario_provider,
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        post_scenarios(client, created["id"], scenario_times())
        resp = client.get(
            f"/api/v1/shipments/{created['id']}/recommendation",
            headers={"X-User-Email": OTHER_USER},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "SHIPMENT_NOT_FOUND"


@requires_db
class TestScenariosIdempotency:
    def test_rerun_replaces_prior_outputs(
        self,
        client: TestClient,
        approved_profile,
        isolated_db,
        patch_heat_provider,
        patch_scenario_provider,
    ) -> None:
        created = create_shipment(client, approved_profile).json()
        client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        first = post_scenarios(client, created["id"], scenario_times())
        assert first.status_code == 200, first.text
        second = post_scenarios(
            client,
            created["id"],
            ["2026-08-21T06:00:00-07:00", "2026-08-21T19:00:00-07:00"],
        )
        assert second.status_code == 200, second.text
        body = second.json()
        assert len(body["scenarios"]) == 2
        assert {s["rank"] for s in body["scenarios"]} == {1, 2}
        # recommendation reflects the latest run
        got = client.get(
            f"/api/v1/shipments/{created['id']}/recommendation",
            headers={"X-User-Email": TEST_USER},
        ).json()
        assert got["recommended_scenario_id"] == body["recommendation"][
            "recommended_scenario_id"
        ]


@requires_db
class TestAnalysisRateLimit:
    def test_analyze_returns_429_when_limited(
        self, client: TestClient, approved_profile, isolated_db, monkeypatch
    ) -> None:
        import app.api.rate_limit as rate_limit_module

        rate_limit_module._limiter = rate_limit_module.SlidingWindowLimiter(1, 60)
        created = create_shipment(client, approved_profile).json()
        client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        resp = client.post(
            f"/api/v1/shipments/{created['id']}/analyze",
            headers={"X-User-Email": TEST_USER},
        )
        assert resp.status_code == 429, resp.text
        assert resp.json()["error"]["code"] == "RATE_LIMITED"