"""Threshold status classification — pure, deterministic, thresholds from profile.

Application semantics only: reports modeled exposure status, not spoilage.
Band mapping (all temperatures in Celsius):
  temp < min_temp_c                     -> warning     (cold excursion)
  min_temp_c <= temp <= max_temp_c      -> safe
  max_temp_c < temp <= warning_threshold -> warning
  warning_threshold < temp <= critical_threshold -> high
  temp > critical_threshold             -> critical
  missing temperature                   -> unknown
"""

from app.domain.value_objects.thermal_observation import ThresholdStatus


def classify_threshold(
    temperature_c: float | None,
    *,
    min_temp_c: float,
    max_temp_c: float,
    warning_threshold_c: float,
    critical_threshold_c: float,
) -> ThresholdStatus:
    if temperature_c is None:
        return ThresholdStatus.UNKNOWN
    if temperature_c < min_temp_c:
        return ThresholdStatus.WARNING
    if temperature_c <= max_temp_c:
        return ThresholdStatus.SAFE
    if temperature_c <= warning_threshold_c:
        return ThresholdStatus.WARNING
    if temperature_c <= critical_threshold_c:
        return ThresholdStatus.HIGH
    return ThresholdStatus.CRITICAL