# 🌡️ Heat-to-Shelf

**Thermal Decision Intelligence for Heat-Sensitive Cargo**
*FortyGuard Global AI Hackathon 2026 — Track 3: Industrial & Enterprise*

> "A logistics route/temperature tool that protects heat-sensitive cargo and worker safety on last-mile routes" — this project is a direct response to FortyGuard's own listed Track 3 example.

**Live demo:** *[add Streamlit Cloud link here]*
**Demo video (≤3 min):** *[add link here]*

---

## The Problem

Temperature-sensitive shipments leave based on a dispatcher's intuition about **city-wide** weather. But ambient temperature along a real route can vary far more than that single number suggests. On our validated corridor (San Jose → San Francisco, 77.8 km, 61 minutes), the same hour of the same day showed a **11.55°C spread** between the inland origin and the coastal destination — from 30.04°C down to 18.49°C.

The FDA's FSMA Sanitary Transportation Rule (2016) already requires shippers to specify written temperature requirements and carriers to monitor and retain 12-month records — but provides no tooling for *route-level* thermal analysis. Most dispatchers still decide departure time by checking one city's forecast.

**The question dispatchers actually need answered:** *given this cargo, this route, and this date — what time should this shipment leave?*

---

## The Solution

Heat-to-Shelf is **not another heatmap.** FortyGuard already provides world-class temperature intelligence (heatmaps, exceedance, persistence, environmental parameters). We add the missing **decision layer** on top of it:

```
FortyGuard Temperature Intelligence
              ↓
   Route + Time Alignment
              ↓
      Thermal Journey
              ↓
     Thermal Exposure
              ↓
       Cargo Risk Score
              ↓
   Scenario Comparison (What-if)
              ↓
   Operational Recommendation
```

Given a cargo type, a route, and a set of candidate departure times, Heat-to-Shelf tells you which one keeps the shipment safest — and shows its work.

---

## Architecture

```
                         ┌─────────────────────────┐
                         │   FortyGuard Temperature │
                         │   API (Create Heatmap,   │
                         │   Environmental Params)  │
                         └────────────┬─────────────┘
                                      │  single-hour tcm heatmap
                                      │  per candidate departure hour
                                      ▼
   ┌──────────────┐         ┌─────────────────────┐
   │  OSRM Route   │────────▶│  Corridor AOI +      │
   │  (SJ → SF)    │  150    │  Spatial Join         │
   │  77.8 km      │ samples │  (GeoPandas, "within")│
   └──────────────┘         └──────────┬───────────┘
                                        │ 100% match rate
                                        ▼
                             ┌─────────────────────┐
                             │  Thermal Observations │
                             │  (per-segment temp,   │
                             │   distance, ETA)       │
                             └──────────┬───────────┘
                                        ▼
                             ┌─────────────────────┐
                             │  Risk Engine v0.1     │
                             │  Severity + Duration  │
                             │  + Critical Override  │
                             └──────────┬───────────┘
                                        ▼
                             ┌─────────────────────┐
                             │  Streamlit UI         │
                             │  Cargo selector ·     │
                             │  Scenario comparison ·│
                             │  Thermal map & chart  │
                             └───────────────────────┘
```

**Why single-hour, spatially-joined tiles (not per-second lookups):** FortyGuard's finest temporal resolution is one hour. For a ~1-hour trip, this means **one heatmap call per candidate departure hour**, covering the whole corridor — the thermal variation across the journey comes from *where* each segment sits (inland vs. coastal), not from time passing during the trip itself.

---

## FortyGuard Endpoints Used

| Endpoint | Purpose | Notes |
|---|---|---|
| `POST /v1/heatmap` (`tcm`, `filter_type=1`) | Per-hour thermal snapshot over the route corridor | 100m granularity, 100% spatial match rate on 150 route samples |
| `POST /v1/env_params` | Worker-safety context (NOAA heat index, wet-bulb, humidity) | Called with the real per-hour temperature anchor, not a flat/incorrect one |
| `GET /v1/status/{activity_id}` | Async result polling | Standard submit → poll → retrieve pattern throughout |

We deliberately do **not** use FortyGuard's 12-hour forecast window in the MVP — it's a real, documented capability, but narrower than the planning horizon most dispatch decisions need. Every number in this demo comes from historical/available thermal data for a specific analysis date, never a prediction.

---

## Methodology v0.1

```
Risk Score = 0.55 × Severity + 0.45 × Duration
```

- **Severity** — peak observed temperature, normalized against the cargo's warning/critical thresholds.
- **Duration** — the fraction of transit time the shipment spends above the warning threshold, computed from route physics (segment distance ÷ route speed), not from FortyGuard's `exceedance` field directly (that field is a location aggregate over an independently-chosen time window, used as context, not substituted for duration).
- **Critical Override** — if *any* segment reaches or exceeds the cargo's critical threshold, the risk level is force-set to `CRITICAL` regardless of the weighted score. A brief breach is still a breach.
- Weights are **provisional v0.1**, tested for ranking stability against an alternative weighting; the scenario ordering (best → worst departure hour) held in both cases.

**Risk levels — single source of truth across engine, UI, and reports:** `SAFE` → `WARNING` → `HIGH` → `CRITICAL`.

---

## Cargo Profiles — Honest Sourcing

Three profiles are documented and available in the demo, each playing a different role:

| Cargo | Warning | Critical | Source | Role |
|---|---|---|---|---|
| 🍫 **Chocolate** | 25°C | 28°C | 4 independent shipping specialists (Suaid Global, IPC, ParcelPath, TemperPack) — convergent on softening onset ~25°C, structural damage in the 80-90°F range | Primary demo — shows full SAFE → WARNING → CRITICAL separation |
| 🍷 **Wine** | 25°C | 28°C | TGL – Team Global Logistics (freight specialist): *"ambient temperature doesn't exceed 25 to 28°C"* cited directly as the comfort zone | Confirms the engine generalizes across cargo types |
| 💄 **Lipstick** | 45°C | 54.4°C | Cosmetic chemist consultation (Perry Romanowski) via The Zoe Report: standard lipstick is stable to ~130°F/54.4°C | **Deliberate null result** — every one of the 10 tested hours reports SAFE, because lipstick genuinely isn't at risk on this corridor. Included for research transparency: the engine reports what the physics say, not a pre-written story. |

We do not claim a single perfect citation for every number — where a threshold is a conservative estimate within a documented range rather than an exact quote, that is stated explicitly in the code's `source_notes`, not hidden.

---

## Results — San Jose → San Francisco, 2026-08-19

10 departure hours were tested against the chocolate/wine profile:

| Hour | Peak | Exposure | Risk Score | Level |
|---|---|---|---|---|
| 04:00 | 16.2°C | 0.0 min | 0.0 | SAFE |
| 06:00 | 16.9°C | 0.0 min | 0.0 | SAFE |
| 08:00 | 18.1°C | 0.0 min | 0.0 | SAFE |
| 10:00 | 20.1°C | 0.0 min | 0.0 | SAFE |
| 12:00 | 27.2°C | 6.1 min | 44.1 | HIGH |
| **14:00** | **30.1°C** | **24.4 min** | **73.0** | **CRITICAL** 🚨 |
| **16:00** | **30.1°C** | **38.8 min** | **83.5** | **CRITICAL** 🚨 |
| 18:00 | 27.2°C | 2.5 min | 42.1 | HIGH |
| 20:00 | 21.3°C | 0.0 min | 0.0 | SAFE |
| 22:00 | 17.7°C | 0.0 min | 0.0 | SAFE |

**The story:** a 9-hour safe window, a 3-hour danger window, and a 2-hour critical window — with a "cliff" between 10:00 (SAFE) and 12:00 (HIGH), a 7°C jump in two hours. Switching a shipment from 16:00 to 06:00 removes **38.8 minutes of threshold exposure** — same route, same cargo, same date. The only variable is departure time.

---

## Validation

- **Spatial matching:** 150 route samples, precise point-in-polygon spatial join (GeoPandas `sjoin`, `predicate="within"`) — **100% match rate**.
- **Multi-date validation:** the same 06:00/12:00/16:00 comparison was re-run on three separate dates (9 heatmap calls total). Scenario separation held on all three; on one date (2026-08-10), midday measured hotter than late afternoon — a real, non-obvious marine-layer pattern that a simple time-of-day heuristic would miss.
- **Driver vs. cargo divergence:** worker-safety scoring (NOAA heat index, using the real per-hour temperature anchor) was computed alongside cargo risk. At 12:00, the driver is NOAA-SAFE (heat index 26.9°C) while the cargo is already at HIGH risk — driver safety cannot proxy for cargo safety, and the two are tracked separately.
- **Test suite:** 20/20 unit tests passing on the risk engine (score computation, override triggering, missing-data handling).

---

## Tech Stack

- **Data source:** FortyGuard Temperature API (heatmap + environmental parameters)
- **Routing:** OSRM (San Jose → San Francisco)
- **Geospatial:** GeoPandas, Shapely (UTM projection, spatial join)
- **Risk engine:** Python, deterministic rule-based scoring (no LLM in the numeric path)
- **UI:** Streamlit, Plotly (thermal journey chart), Folium (route map)
- **Production API (roadmap):** FastAPI + PostgreSQL/PostGIS — architecture designed, not required for this MVP demo

---

- This project was built on FortyGuard's official `temperature-api-quickstart`
- repository (client package and starter notebooks). All original FortyGuard
- files are credited; our additions are the decision-layer logic, risk engine,
- evaluation pipeline, and Streamlit application.

---

## Running It Locally

```bash
git clone <this-repo-url>
cd heat-to-shelf
python -m venv venv && venv\Scripts\activate   # or source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The demo runs entirely from cached FortyGuard responses (`cache/`) — **zero live API calls, zero credit cost** to explore it. A `FORTYGUARD_API_KEY` in `.env` is only needed to regenerate the cache against new routes or dates.

---

## What We Are Honest About

- **v0.1 weights are provisional**, not a scientific claim — documented as such in the risk engine.
- **Not all cargo citations are equally strong** — chocolate and wine have multi-source or direct-match citations; where a number is a conservative estimate within a range rather than an exact quote, the code says so.
- **This is historical/available-data analysis, not weather forecasting** — even though FortyGuard's API does support a 12-hour forecast window we chose not to build on yet (see Roadmap).
- **Persistence is computed but not yet weighted** in the v0.1 score — tracked as context, pending a mathematically justified conversion from FortyGuard's location-aggregate `exceedance`/`persistence` fields to a per-shipment multiplier.

---

## Roadmap

**Near-term:**

- Genuine forecast-backed risk for shipments departing within FortyGuard's 12-hour forecast window
- Route comparison (multiple candidate routes, not just multiple departure times)
- Additional cargo categories with rigorously sourced thresholds
- Live shipment monitoring during transit

**Longer-term:**

- Production FastAPI + PostgreSQL/PostGIS backend (architecture already designed — see `backend/`)
- Fleet-level dashboards and portfolio risk reporting
- API product for logistics platforms to integrate thermal risk directly

---

## Team

- **AI/Data:** thermal intelligence pipeline, exposure/risk engine, evaluation
- **Backend:** FortyGuard integration, API design, data architecture
- **Business/Product:** research, cargo sourcing, positioning, submission materials

---

## Track Alignment

Built for **Track 3 — Industrial & Enterprise**, directly answering FortyGuard's own stated example. The exposure methodology (temperature × duration × persistence → risk) also touches **Track 7 — Data Analysis & Correlation**.
