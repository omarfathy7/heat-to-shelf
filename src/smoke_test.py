"""End-to-end integration smoke test.
Run from project root: python src/smoke_test.py

Verifies: notebook → cache → loader → RiskEngine → correct numbers.
Also runs the full 10-scenario sweep.

Citation: Wine 25°C/28°C (FDA FSMA + wine industry standards)
"""

import sys
from pathlib import Path

# ── Path setup ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.risk_engine import RiskEngine, CargoProfile, RiskLevel
from src.cargo_profiles import WINE_PROFILE
from src.loader import load_scenario, build_observations

CACHE = PROJECT_ROOT / "cache"
STUDY_DATE = "2026-08-19"

# ── Engine with REAL citation ──
engine = RiskEngine(CargoProfile(
    name=WINE_PROFILE.name,
    warning_threshold_c=WINE_PROFILE.warning_threshold_c,
    critical_threshold_c=WINE_PROFILE.critical_threshold_c,
    source_name=WINE_PROFILE.source_name,
    source_url=WINE_PROFILE.source_url,
))

# ── Validated numbers (3 key scenarios) ──
EXPECTED = {
    "06:00": (0.0, "SAFE", False, 0),
    "12:00": (44.1, "HIGH", False, 15),
    "16:00": (83.5, "CRITICAL", True, 95),
}

ALL_10 = ["04:00", "06:00", "08:00", "10:00", "12:00",
          "14:00", "16:00", "18:00", "20:00", "22:00"]

print(f"Cargo: {WINE_PROFILE.name}")
print(f"Thresholds: warning {WINE_PROFILE.warning_threshold_c}°C / "
      f"critical {WINE_PROFILE.critical_threshold_c}°C")
print(f"Source: {WINE_PROFILE.source_name[:60]}...")
print()
print(f"{'hour':<8}{'score':>7}{'level':>10}{'override':>10}{'segments':>10}")
print("-" * 45)

# ── 3 key scenarios — strict verification ──
all_ok = True
for hour in ["06:00", "12:00", "16:00"]:
    payload = load_scenario(CACHE, STUDY_DATE, hour)
    obs = build_observations(payload)
    assert len(obs) == 150, f"Expected 150 segments, got {len(obs)}"

    a = engine.assess(obs)
    print(f"{hour:<8}{a.risk_score:>7}{a.risk_level.value:>10}"
          f"{str(a.critical_override_triggered):>10}"
          f"{a.segments_above_warning:>10}")

    exp_score, exp_level, exp_override, exp_segments = EXPECTED[hour]
    if (abs(a.risk_score - exp_score) > 0.1
            or a.risk_level.value != exp_level
            or a.critical_override_triggered != exp_override
            or a.segments_above_warning != exp_segments):
        print(f"  ❌ MISMATCH: expected {EXPECTED[hour]}, got "
              f"({a.risk_score}, {a.risk_level.value}, "
              f"{a.critical_override_triggered}, {a.segments_above_warning})")
        all_ok = False

# ── Full 10-scenario sweep ──
print(f"\n{'='*60}")
print("FULL 10-SCENARIO SWEEP")
print(f"{'='*60}")
print(f"{'hour':<8}{'score':>7}{'level':>10}{'override':>10}"
      f"{'exp_min':>8}{'segs':>8}")
print("-" * 55)

for hour in ALL_10:
    try:
        payload = load_scenario(CACHE, STUDY_DATE, hour)
        obs = build_observations(payload)
        a = engine.assess(obs)
        print(f"{hour:<8}{a.risk_score:>7}{a.risk_level.value:>10}"
              f"{str(a.critical_override_triggered):>10}"
              f"{a.exposure_hours*60:>8.1f}"
              f"{a.segments_above_warning:>8}")
    except FileNotFoundError:
        print(f"{hour:<8}  --- NOT CACHED ---")

# ── Verdict ──
print(f"\n{'='*60}")
if all_ok:
    print("✅ INTEGRATION OK — all 3 key scenarios match validated numbers")
    print(f"✅ CITATION: {WINE_PROFILE.name} — FDA FSMA + wine industry")
    print(f"✅ 10-SCENARIO SWEEP complete")
else:
    print("⚠️ Numbers differ — check if thresholds changed")

# ── Summary: safe vs danger windows ──
safe_hours = []
danger_hours = []
critical_hours = []
for hour in ALL_10:
    try:
        payload = load_scenario(CACHE, STUDY_DATE, hour)
        a = engine.assess(build_observations(payload))
        if a.risk_level == RiskLevel.SAFE:
            safe_hours.append(hour)
        elif a.critical_override_triggered:
            critical_hours.append(hour)
        else:
            danger_hours.append(hour)
    except FileNotFoundError:
        pass

print(f"\nSafe window:     {safe_hours}")
print(f"Danger window:   {danger_hours}")
print(f"Critical window: {critical_hours} 🚨")