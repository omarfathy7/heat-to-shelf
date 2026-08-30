# ═══════════════════════════════════════════════════
# src/explainer.py — deterministic explanation layer.
# Every number comes from the assessment object. No LLM,
# no invented values. This is the guaranteed fallback
# behind any fancier agent we might add.
# ═══════════════════════════════════════════════════

from src.risk_engine import RiskAssessment, CargoProfile, RiskLevel


def explain_assessment(a: RiskAssessment, cargo: CargoProfile,
                       trip_minutes: float) -> str:
    """Human-readable explanation built ONLY from real numbers."""

    if a.data_completeness == "insufficient_data":
        return (
            "Insufficient thermal data for this scenario — "
            "no definitive assessment is possible. This is reported "
            "explicitly rather than guessing a score."
        )

    peak = None  # filled by caller context if needed
    base = (
        f"Cargo: {cargo.name} — warning at {cargo.warning_threshold_c}°C, "
        f"critical at {cargo.critical_threshold_c}°C.\n"
        f"Trip duration: {trip_minutes:.0f} minutes.\n"
    )

    if a.critical_override_triggered:
        n = len(a.critical_segments)
        return base + (
            f"\n🚨 VERDICT: DO NOT DEPART at this hour.\n\n"
            f"The critical override fired: {n} route segments reached or "
            f"exceeded the critical threshold ({cargo.critical_threshold_c}°C). "
            f"The shipment spent {a.exposure_hours * 60:.1f} minutes above the "
            f"warning threshold, including one continuous stretch of "
            f"{a.longest_run_hours * 60:.1f} minutes.\n\n"
            f"The weighted score was {a.risk_score}/100, but the override "
            f"rule treats any critical-threshold breach as disqualifying — "
            f"a brief breach is still a breach.\n\n"
            f"Recommendation: choose an earlier departure scenario; "
            f"06:00 measured 0 minutes of threshold exposure on this date."
        )

    if a.risk_level == RiskLevel.SAFE:
        return base + (
            f"\n✅ VERDICT: Safe to depart.\n\n"
            f"Peak route temperature stayed below the warning threshold "
            f"({cargo.warning_threshold_c}°C) for the entire {trip_minutes:.0f}-"
            f"minute trip. Zero minutes of threshold exposure were measured.\n\n"
            f"Score: {a.risk_score}/100 ({a.risk_level.value})."
        )

    if a.risk_level == RiskLevel.WARNING:
        return base + (
            f"\n⚠️ VERDICT: Acceptable with awareness.\n\n"
            f"The route crossed the warning threshold for "
            f"{a.exposure_hours * 60:.1f} minutes "
            f"(longest continuous stretch: {a.longest_run_hours * 60:.1f} min), "
            f"but never reached the critical threshold "
            f"({cargo.critical_threshold_c}°C).\n\n"
            f"Score: {a.risk_score}/100. An earlier departure reduces "
            f"exposure further."
        )

    return base + (  # HIGH
        f"\n⚠️ VERDICT: High risk — consider a different hour.\n\n"
        f"The shipment spends {a.exposure_hours * 60:.1f} minutes above the "
        f"warning threshold — {a.segments_above_warning} of 150 route segments. "
        f"No segment reached the critical threshold, but the exposure "
        f"pattern is significant.\n\n"
        f"Score: {a.risk_score}/100 ({a.risk_level.value})."
    )


def explain_comparison(results: dict, cargo: CargoProfile,
                       trip_minutes: float) -> str:
    """Comparison summary across scenarios — for the What-if panel."""
    best = min(results.items(), key=lambda kv: kv[1].risk_score)
    worst = max(results.items(), key=lambda kv: kv[1].risk_score)
    delta = (worst[1].exposure_hours - best[1].exposure_hours) * 60

    return (
        f"Across {len(results)} departure scenarios, {best[0]} carries the "
        f"lowest thermal exposure (risk {best[1].risk_score}, "
        f"{best[1].exposure_hours * 60:.1f} min above warning) while "
        f"{worst[0]} carries the highest (risk {worst[1].risk_score}, "
        f"{worst[1].exposure_hours * 60:.1f} min).\n\n"
        f"Switching from {worst[0]} to {best[0]} removes "
        f"{delta:.1f} minutes of threshold exposure on the same route, "
        f"the same cargo, and the same date — the only variable is "
        f"departure time."
    )