from pydantic import BaseModel, Field, field_validator

from app.core.errors import AppError, ErrorCode

MAX_LATITUDE = 90.0
MAX_LONGITUDE = 180.0


class Coordinate(BaseModel):
    longitude: float = Field(..., description="WGS84 longitude, -180..180")
    latitude: float = Field(..., description="WGS84 latitude, -90..90")

    @field_validator("longitude")
    @classmethod
    def _check_longitude(cls, value: float) -> float:
        if not (-MAX_LONGITUDE <= value <= MAX_LONGITUDE):
            raise AppError(
                ErrorCode.INVALID_COORDINATES,
                f"longitude out of range: {value}",
                details={"field": "longitude", "value": value},
            )
        return value

    @field_validator("latitude")
    @classmethod
    def _check_latitude(cls, value: float) -> float:
        if not (-MAX_LATITUDE <= value <= MAX_LATITUDE):
            raise AppError(
                ErrorCode.INVALID_COORDINATES,
                f"latitude out of range: {value}",
                details={"field": "latitude", "value": value},
            )
        return value

    def as_tuple(self) -> tuple[float, float]:
        return (self.longitude, self.latitude)

    def as_geojson(self) -> dict:
        return {"type": "Point", "coordinates": [self.longitude, self.latitude]}