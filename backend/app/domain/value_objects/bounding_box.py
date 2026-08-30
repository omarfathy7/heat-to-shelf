from pydantic import BaseModel, model_validator

from app.core.errors import AppError, ErrorCode


class BoundingBox(BaseModel):
    """Longitude/latitude envelope in WGS84 (SRID 4326)."""

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    @model_validator(mode="after")
    def _ordered(self) -> "BoundingBox":
        if self.min_lon >= self.max_lon or self.min_lat >= self.max_lat:
            raise AppError(
                ErrorCode.INVALID_COORDINATES,
                "bounding box min values must be less than max values",
            )
        return self

    def center(self) -> tuple[float, float]:
        return (
            (self.min_lon + self.max_lon) / 2.0,
            (self.min_lat + self.max_lat) / 2.0,
        )