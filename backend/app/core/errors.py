from enum import Enum


class ErrorCode(str, Enum):
    INVALID_COORDINATES = "INVALID_COORDINATES"
    INVALID_TIME_WINDOW = "INVALID_TIME_WINDOW"
    PRODUCT_PROFILE_UNAVAILABLE = "PRODUCT_PROFILE_UNAVAILABLE"
    ROUTING_PROVIDER_FAILED = "ROUTING_PROVIDER_FAILED"
    FORTYGUARD_PROVIDER_FAILED = "FORTYGUARD_PROVIDER_FAILED"
    FORTYGUARD_RESPONSE_INVALID = "FORTYGUARD_RESPONSE_INVALID"
    THERMAL_DATA_MISSING = "THERMAL_DATA_MISSING"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    SHIPMENT_NOT_FOUND = "SHIPMENT_NOT_FOUND"
    RECOMMENDATION_UNAVAILABLE = "RECOMMENDATION_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 400,
        details: dict | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


def error_envelope(
    code: ErrorCode,
    message: str,
    request_id: str,
    details: dict | None = None,
) -> dict:
    return {
        "error": {
            "code": code.value,
            "message": message,
            "request_id": request_id,
            "details": details or {},
        }
    }