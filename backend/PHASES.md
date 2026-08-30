# Heat-to-Shelf Backend — Phased Plan

Source: `Heat_to_Shelf_Backend_Plan.md` (section 13, Implementation order).
Each phase corresponds to one slice and ends with definition-of-done: runnable, tested, no scope creep.

## Phase 1 — Skeleton
- FastAPI app + settings (Pydantic-settings)
- structured JSON logging with request/correlation IDs
- stable error envelope (`error_code`, `message`, `request_id`)
- `GET /api/v1/health` (liveness + DB readiness, no secrets)
- Dockerfile + docker-compose with PostgreSQL/PostGIS
- Alembic wired to an initial empty/versioned migration

## Phase 2 — Domain & Approved Product
- `Coordinate`, `TimeWindow` value objects (WGS84 lon/lat, UTC, explicit order)
- `Product` and `ProductProfile` domain models (versioned, sourced, effective window)
- seed: single approved Fresh Produce profile with sourced thresholds + exposure rules
- unit tests for profile validation and source requirements

## Phase 3 — Shipment & Route
- shipments/routes/route_segments schema + migrations + repositories
- `POST /api/v1/shipments` (draft) with ownership
- `RoutingProvider` interface + adapter, route validation, segmentation

## Phase 4 — FortyGuard
- typed provider schemas, adapter behind `TemperatureProvider`
- timeout/retry/cache, request logging, sanitized errors
- GeoJSON/tile validation; fixture integration tests

## Phase 5 — Thermal Journey
- corridor + spatial intersection, segment ordering, time alignment
- thermal observation persistence, journey endpoint with GeoJSON

## Phase 6 — Risk Engine
- pure exposure engine, pure risk engine (weights/bands configurable)
- risk persistence, low/medium/high/missing tests

## Phase 7 — What-if & Recommendation
- scenarios endpoint reusing one pipeline, deterministic ranking
- recommendation evidence + exposure reduction

## Phase 8 — Demo Hardening
- lifecycle/failure states, caching + bounded retries, rate limiting
- observability, clearly-labeled fixture fallback, deployment config

## Phase 9 — Optional (after MVP)
- AI agent tool layer, NL input, reports, route comparison, more profiles