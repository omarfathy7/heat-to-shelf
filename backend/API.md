# Heat-to-Shelf Backend — API & Project Documentation

## Mission

Given heat-sensitive cargo, an origin, a destination, and a departure time, the
backend:

1. generates a route (20 segments) using a routing provider,
2. maps each segment to spatial- and time-aligned **FortyGuard** heatmap observations,
3. builds an ordered thermal journey,
4. quantifies **cargo risk** (0–100 score, `safe | warning | high | critical`),
5. compares candidate **departure scenarios** with the same pipeline,
6. produces a **deterministic recommendation** with exposure reduction.

> The backend reports **modeled thermal exposure and operational risk** — it never
> claims spoilage or safe-for-consumption. Missing provider data is explicit
> uncertainty, never silently substituted.

## Stack

- Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · PostgreSQL + PostGIS
- Units: temperature °C, distance metres, durations seconds, timestamps UTC
- Geography: longitude/latitude WGS84 (SRID 4326)
- Layers: `api` (routers/DTOs) → `application` (use cases) → `domain` (pure logic/entities) → `infrastructure` (PostgreSQL, FortyGuard, routing, cache)

---

## Quick Start

### Prerequisites

Docker (for PostGIS) and the project virtualenv:

```bash
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

### Database (PostGIS on host port 5433)

> The compose file maps `5432` inside the container to a configurable host port.
> Both the app default and your local Postgres use `5432`, so always pin **5433**:

```bash
POSTGRES_HOST_PORT=5433 docker compose up -d db
```

Access: `postgresql+psycopg://heat:heat@localhost:5433/heat2shelf`

### Migrations

```bash
DATABASE_URL="postgresql+psycopg://heat:heat@localhost:5433/heat2shelf" \
  .venv/bin/python -m alembic upgrade head
```

Current head: `0004_scenarios_recommendations`.

### Configuration

Copy `.env.example` to `.env` and set at least:

- `DATABASE_URL` (point at 5433 in local dev)
- `FORTYGUARD_API_KEY` — required for real analysis; without it `/analyze` returns 503 (no fabricated temperatures)
- `ROUTING_PROVIDER=fixture` — California (San Jose → San Francisco) demo fixture, clearly labeled `provider="fixture"`

### Run

```bash
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Tests

```bash
# with database available (full coverage)
DATABASE_URL="postgresql+psycopg://heat:heat@localhost:5433/heat2shelf" \
  .venv/bin/python -m pytest -q

# without database (DB-gated tests skip)
env -u DATABASE_URL .venv/bin/python -m pytest -q
```

Status: **137 passed with DB · 100 passed / 30 skipped without DB.**

---

## Conventions

### Auth

Simple MVP user boundary. Identity comes from the `X-User-Email` header; it
defaults to `demo@heat2shelf.dev`. Every shipment read/write is ownership-checked.

```http
X-User-Email: owner@heat2shelf.dev
```

### Base path

All business endpoints are under **`/api/v1`**.

### Error envelope

Every error returns a stable envelope; never a stack trace:

```json
{
  "error": {
    "code": "SHIPMENT_NOT_FOUND",
    "message": "shipment not found",
    "request_id": "a1b2c3…",
    "details": {}
  }
}
```

Stable error codes:

| Code | HTTP | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Request validation failed |
| `SHIPMENT_NOT_FOUND` | 404 | Shipment missing or not owned by the user |
| `PRODUCT_PROFILE_UNAVAILABLE` | 404 | Product profile no longer available |
| `INVALID_COORDINATES` | 400 | Coordinate validation failed |
| `INVALID_TIME_WINDOW` | 422 | Departure time outside the scenario horizon |
| `THERMAL_DATA_MISSING` | 422 | No thermal journey to assess |
| `ROUTING_PROVIDER_FAILED` | 5xx | Routing provider failure |
| `FORTYGUARD_PROVIDER_FAILED` | 5xx | FortyGuard failure / not configured |
| `FORTYGUARD_RESPONSE_INVALID` | 502 | FortyGuard payload failed validation |
| `ANALYSIS_FAILED` | 502 | Analysis/scenario run could not complete |
| `RECOMMENDATION_UNAVAILABLE` | 404 | No recommendation produced yet |
| `RATE_LIMITED` | 429 | Analysis rate limit exceeded |
| `INTERNAL_ERROR` | 500 | Unhandled error |

Each request carries an `X-Request-ID` (correlation ID) in the response headers and structured JSON logs.

### Shipment lifecycle

```
draft → routing → analyzing → ready | failed
```

`/analyze` drives the whole transition synchronously; on error the shipment is
marked `failed` with `error_code`/`error_message`.

### Rate limiting

`POST /analyze` and `POST /scenarios` are limited to **10 requests / 60 s per user**
(configure: `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS`). Exceeding it
returns `429 RATE_LIMITED` with `retry_after_seconds`.

---

## Endpoints

### `GET /health`

Liveness — never blocks on external dependencies.

```json
{ "status": "ok", "version": "0.1.0" }
```

### `GET /health/ready`

Readiness — verifies PostgreSQL connectivity only.

```json
{ "status": "ready", "db": "up" }
```

### `GET /api/v1/products`

Enabled products with their **approved, sourced** profiles.

```json
[
  {
    "id": "3f6f…",
    "name": "Fresh Produce",
    "category": "Perishables",
    "profiles": [
      {
        "id": "9a2a…",
        "version": 1,
        "min_temp_c": 0.0,
        "max_temp_c": 4.0,
        "warning_threshold_c": 8.0,
        "critical_threshold_c": 12.0,
        "source_name": "…",
        "source_url": "https://…",
        "source_published_at": "2024-01-01T00:00:00Z"
      }
    ]
  }
]
```

> In the repo, the real profile stays `PENDING_PRODUCT_REVIEW` until a product
> member supplies a credible source; tests use an in-memory approved profile.

### `POST /api/v1/shipments` → `201`

Create a shipment in `draft`.

```json
{
  "product_id": "9a2a…",
  "origin": { "label": "San Jose, CA", "latitude": 37.3382, "longitude": -121.8863 },
  "destination": { "label": "San Francisco, CA", "latitude": 37.7749, "longitude": -122.4194 },
  "departure_time": "2026-08-21T12:00:00-07:00"
}
```

Response:

```json
{
  "id": "8c1e…",
  "product_id": "9a2a…",
  "origin": { "label": "San Jose, CA", "coordinate": { "type": "Point", "coordinates": [-121.8863, 37.3382] } },
  "destination": { "label": "San Francisco, CA", "coordinate": { "type": "Point", "coordinates": [-122.4194, 37.7749] } },
  "departure_time_utc": "2026-08-21T19:00:00Z",
  "status": "draft",
  "estimated_duration_seconds": null,
  "distance_meters": null,
  "error_code": null,
  "error_message": null,
  "created_at": "2026-08-20T10:00:00Z",
  "updated_at": "2026-08-20T10:00:00Z"
}
```

### `GET /api/v1/shipments/{shipment_id}`

Retrieve a shipment (same shape as above). `404 SHIPMENT_NOT_FOUND` when missing or not owned.

### `POST /api/v1/shipments/{shipment_id}/analyze` → `202`

Synchronous (MVP): build/reuse the route, request sampled FortyGuard heatmaps,
match tiles to segments, classify against the profile, persist observations,
and move the shipment to `ready` (or `failed`).

```json
{
  "shipment_id": "8c1e…",
  "status": "ready",
  "developed_segments": 20,
  "observed_segments": 20,
  "error_code": null,
  "error_message": null
}
```

Missing/mismatched tiles don't fail the run — affected segments become
`threshold_status: "unknown"` and `observed_segments` reflects how many matched.
Provider failures (timeout, bad payload, unconfigured key) return the mapped
error status (e.g. `502 FORTYGUARD_RESPONSE_INVALID`), the shipment becomes
`failed` with `error_code`/`error_message`, and `503 FORTYGUARD_PROVIDER_FAILED`
is returned when no API key is configured.

### `GET /api/v1/shipments/{shipment_id}/thermal-journey`

Ordered segments, observations, statuses, plus GeoJSON for map rendering.

```json
{
  "shipment_id": "8c1e…",
  "status": "ready",
  "segments": [
    {
      "sequence": 1,
      "start_distance_meters": 0.0,
      "end_distance_meters": 2246.5,
      "estimated_arrival_utc": "2026-08-21T19:04:12Z",
      "duration_seconds": 252,
      "midpoint": { "longitude": -121.8604, "latitude": 37.3395 },
      "observation": {
        "temperature_c": 25.0,
        "observed_at_utc": "2026-08-21T19:04:00Z",
        "threshold_status": "critical",
        "latitude": 37.3395,
        "longitude": -121.8604,
        "source": "fortyguard",
        "source_request_hash": "…",
        "data_quality": { "quality": "good", "stale": false, "stale_minutes": 0, "matched": true }
      }
    }
  ],
  "geojson": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "properties": { "sequence": 1, "threshold_status": "critical" },
        "geometry": { "type": "LineString", "coordinates": [[-121.8863, 37.3382], [-121.8604, 37.3395]] }
      }
    ]
  }
}
```

Missing/stale matches appear as `threshold_status: "unknown"` observation —
never substituted values.

### `GET /api/v1/shipments/{shipment_id}/risk`

Deterministic, versioned cargo-risk assessment. Recomputes idempotently from the
persisted journey (replaces the prior baseline).

```json
{
  "shipment_id": "8c1e…",
  "scenario_id": null,
  "score": 87.5,
  "level": "critical",
  "components": {
    "peak_temperature": 100.0,
    "duration": 50.0,
    "persistence": 100.0,
    "high_risk_segments": 100.0
  },
  "peak_temperature_c": 25.0,
  "time_above_threshold_hours": 12.0,
  "longest_persistence_hours": 12.0,
  "high_risk_segment_count": 3,
  "exposure_reduction_percent": null,
  "calculation_version": "1.0.0",
  "explanation_factors": { "observed_segments": 20, "total_segments": 20 },
  "created_at": "2026-08-20T10:05:00Z"
}
```

`422 THERMAL_DATA_MISSING` before an analysis exists.

### `POST /api/v1/shipments/{shipment_id}/scenarios`

Evaluate candidate departure times using the **same exposure + risk engine** over
the same route. Each scenario gets a persisted risk assessment; scenarios are
ranked (lower score first, ties → earlier departure) and a recommendation is
produced against the original baseline.

```json
{
  "departure_times": [
    "2026-08-21T06:00:00-07:00",
    "2026-08-21T12:00:00-07:00",
    "2026-08-21T19:00:00-07:00"
  ]
}
```

Response `200`:

```json
{
  "shipment_id": "8c1e…",
  "baseline": { "shipment_id": "8c1e…", "scenario_id": null, "score": 87.5, "level": "critical", "…": "…" },
  "scenarios": [
    {
      "id": "c0a3…",
      "departure_time_utc": "2026-08-21T13:00:00Z",
      "status": "completed",
      "rank": 1,
      "is_recommended": true,
      "score": 45.2,
      "level": "warning",
      "components": { "peak_temperature": 40.0, "duration": 40.0, "persistence": 50.0, "high_risk_segments": 60.0 },
      "peak_temperature_c": 11.0,
      "time_above_threshold_hours": 4.0,
      "longest_persistence_hours": 2.0,
      "high_risk_segment_count": 8
    }
  ],
  "recommendation": {
    "shipment_id": "8c1e…",
    "recommended_scenario_id": "c0a3…",
    "recommended_departure_time_utc": "2026-08-21T13:00:00Z",
    "original_score": 87.5,
    "recommended_score": 45.2,
    "exposure_reduction_percent": 48.3,
    "original_level": "critical",
    "recommended_level": "warning",
    "level_improved": true,
    "reason_codes": [
      "lower_risk_score",
      "lower_peak_temperature",
      "less_time_above_threshold",
      "lower_persistence",
      "fewer_high_risk_segments"
    ],
    "explanation_factors": {
      "original_score": 87.5,
      "recommended_score": 45.2,
      "exposure_reduction_percent": 48.3,
      "original_level": "critical",
      "recommended_level": "warning",
      "level_improved": true,
      "component_deltas_before_minus_after": { "peak_temperature": 60.0, "duration": 10.0, "persistence": 50.0, "high_risk_segments": 40.0 }
    },
    "id": null,
    "created_at": null
  }
}
```

Rules: times must be timezone-aware and unique; candidates beyond
`SCENARIO_HORIZON_HOURS` (default 168) from the shipment → `422 INVALID_TIME_WINDOW`.
If every scenario fails, the run returns `502 ANALYSIS_FAILED`.

### `GET /api/v1/shipments/{shipment_id}/recommendation`

Latest persisted recommendation (same `recommendation` shape as above, but with
`id`/`created_at` populated).

`404 RECOMMENDATION_UNAVAILABLE` before a scenario run exists.

### `GET /api/v1/assess`

Risk assessment for a study date/hour window. Queries thermal observations within the
specified hour and computes a deterministic risk score using the current weight
configuration. Does not require a shipment ID — operates directly on observed data.

**Query parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `study_date` | `YYYY-MM-DD` | yes | Study date |
| `hour` | `HH:MM` | yes | Hour in 24h format (UTC) |

```bash
curl "http://localhost:8000/api/v1/assess?study_date=2026-08-19&hour=16:00"
```

Response `200`:

```json
{
  "study_date": "2026-08-19",
  "hour": "16:00",
  "score": 83.5,
  "level": "critical",
  "components": {
    "peak_temperature": 100.0,
    "duration": 63.33,
    "persistence": 0.0,
    "high_risk_segments": 0.0
  },
  "peak_temperature_c": 25.0,
  "time_above_threshold_hours": 12.0,
  "longest_persistence_hours": 0.0,
  "high_risk_segment_count": 0,
  "segment_count": 20,
  "explanation_factors": {
    "observed_segments": 20,
    "total_segments": 20
  }
}
```

**Level override rule:** If *any* segment has a `temperature_c >= critical_threshold_c`
(from the resolved product profile), the level is forced to `CRITICAL` regardless of
the aggregated score.

`422 THERMAL_DATA_MISSING` when no observations exist in the window.
`422 INVALID_TIME_WINDOW` when `hour` is not in `HH:MM` format.

---

## Risk model

Deterministic, versioned formula (`calculation_version: "1.0.0"`):

```text
risk_score = clamp(
    weight_peak_temperature    * peak_temperature_component    +
    weight_duration            * duration_component            +
    weight_persistence         * persistence_component          +
    weight_high_risk_segments  * high_risk_segments_component
, 0, 100)
```

Each component is normalized to 0–100. Default weights and semantic bands are
**configuration** (Settings / `.env`), not scattered constants:

| Parameter | Default |
|---|---|
| `RISK_WEIGHT_PEAK_TEMPERATURE` | 0.55 |
| `RISK_WEIGHT_DURATION` | 0.45 |
| `RISK_WEIGHT_PERSISTENCE` | 0.0 |
| `RISK_WEIGHT_HIGH_RISK_SEGMENTS` | 0.0 |
| `RISK_BAND_WARNING_AT` / `HIGH_AT` / `CRITICAL_AT` | 25 / 50 / 75 |

Weights are **normalized** so active components always sum to 1.0. With the defaults,
only `peak_temperature` (55%) and `duration` (45%) contribute to the score.

Bands: **safe 0–24 · warning 25–49 · high 50–74 · critical 75–100**.

**Critical threshold override:** Immediately after the weighted score is computed,
if *any* segment has `temperature_c >= critical_threshold_c` (from the product
profile), the risk level is forced to `CRITICAL` regardless of the aggregated score.
This ensures that any observed extreme temperature event is surfaced.

Reason codes (recommendation): `lower_risk_score`,
`lower_peak_temperature`, `less_time_above_threshold`,
`lower_persistence`, `fewer_high_risk_segments`.

Exposure reduction (handles zero original score):

```text
exposure_reduction_percent = (original_score - recommended_score) / original_score * 100
```

---

## What was built (slices)

| # | Slice | Delivered |
|---|---|---|
| 1 | Skeleton | FastAPI app, settings, error envelope, structured JSON logs, request-ID middleware, health/readiness, PostGIS compose, Alembic |
| 2 | Domain & product | Coordinate/place/time value objects, product + versioned sourced profile, seed (profile kept inactive pending source) |
| 3 | Shipment & route | Shipment repository/endpoint, routing interface, fixture provider (labeled), route persistence + 20-segment segmentation |
| 4 | FortyGuard | Typed provider schemas, adapter with validation, timeout/retry/backoff, rate-limit handling, TTL cache, sanitized errors, usage metadata |
| 5 | Thermal journey | Corridor, spatial tile matching, time alignment, observation builder (never fabricates), observation persistence, journey endpoint |
| 6 | Risk engine | Pure exposure engine + risk engine (weights/bands configurable), risk persistence, `GET /risk` |
| 7 | What-if & recommendation | Scenario endpoint reusing the same pipeline, deterministic ranking, recommendation reason codes + reduction, `GET /recommendation` |
| 8 | Demo hardening | `analyzing` lifecycle transition, rate limiting on analyze/scenarios, operation observability logs, `.dockerignore` |
| 9 | Risk refactor | Updated weights (peak 0.55 / duration 0.45, persistence & high_risk zeroed), critical threshold override logic, `GET /assess` endpoint for study-date risk queries |

---

## Known limits / next steps

- Requires a **real `FORTYGUARD_API_KEY`** for live analysis; the demo routing
  fallback is a clearly-labeled San Jose → San Francisco fixture.
- The sole Fresh Produce profile awaits a **credible source from the product
  member** before activation.
- Optional post-MVP (Slice 10): AI agent tool layer, natural-language shipment
  input, `GET /report` read model, route comparison, additional cargo profiles.