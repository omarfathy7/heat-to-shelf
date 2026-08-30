from pydantic import BaseModel, Field

from app.domain.value_objects.coordinates import Coordinate


class PlaceInput(BaseModel):
    """API request shape: label plus latitude/longitude pair."""

    label: str = Field(..., min_length=1, max_length=200)
    latitude: float
    longitude: float

    def to_place(self) -> "Place":
        return Place(
            label=self.label,
            coordinate=Coordinate(longitude=self.longitude, latitude=self.latitude),
        )


class Place(BaseModel):
    label: str
    coordinate: Coordinate