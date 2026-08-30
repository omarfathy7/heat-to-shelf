from datetime import datetime

from pydantic import BaseModel, field_validator

from app.core.errors import AppError, ErrorCode


class TimeWindow(BaseModel):
    # Always UTC-aware.
    start_utc: datetime
    end_utc: datetime

    @field_validator("start_utc", "end_utc")
    @classmethod
    def _tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise AppError(
                ErrorCode.INVALID_TIME_WINDOW,
                "timestamps must be timezone-aware; use UTC",
            )
        return value

    @field_validator("end_utc")
    @classmethod
    def _ordered(cls, value: datetime, info) -> datetime:
        start = info.data.get("start_utc")
        if start is not None and value <= start:
            raise AppError(
                ErrorCode.INVALID_TIME_WINDOW,
                "end_utc must be after start_utc",
            )
        return value

    def duration_seconds(self) -> float:
        return (self.end_utc - self.start_utc).total_seconds()

    def contains(self, moment: datetime) -> bool:
        return self.start_utc <= moment <= self.end_utc