"""Integration layer: cache files -> SegmentObservations -> RiskEngine.
This is the glue that was missing — notebook output feeds the app
through HERE, never by ad-hoc column names."""

import json
from pathlib import Path
from typing import List, Optional

from src.schemas import SegmentObservation, PAYLOAD_KEYS


def load_scenario(cache_dir: Path, study_date: str, hour: str) -> dict:
    """Load one scenario payload from cache. Raises with clear message
    if the notebook hasn't been run / file missing."""
    f = cache_dir / f"scenario_{study_date}_{hour.replace(':', '')}.json"
    if not f.exists():
        raise FileNotFoundError(
            f"Scenario cache missing: {f.name}\n"
            f"Run 07_scenario_separation_test.ipynb first."
        )
    payload = json.loads(f.read_text())

    # Schema guard — fail loudly at load, not mid-demo
    missing = [k for k in PAYLOAD_KEYS if k not in payload]
    if missing:
        raise ValueError(f"Payload missing keys: {missing} in {f.name}")
    return payload


def build_observations(payload: dict) -> List[SegmentObservation]:
    """Construct SegmentObservation list from cached payload."""
    return [
        SegmentObservation(
            segment_id=s["segment_id"],
            distance_km=s["distance_km"],
            dwell_hours=s["dwell_hours"],
            temperature_c=s["temperature_c"],
        )
        for s in payload["segments"]
    ]


def assess_scenario(engine, payload: dict) -> dict:
    """Full assessment for one scenario — loader + engine in one call."""
    observations = build_observations(payload)
    assessment = engine.assess(observations)
    return {
        "payload": payload,
        "observations": observations,
        "assessment": assessment,
    }