from datetime import datetime, timedelta, timezone

import pytest

from app.core.errors import AppError, ErrorCode
from app.domain.value_objects.time_window import TimeWindow


def utc(hour: int = 0, day: int = 21) -> datetime:
    return datetime(2026, 8, day, hour, tzinfo=timezone.utc)


class TestTimeWindow:
    def test_valid_window(self) -> None:
        tw = TimeWindow(start_utc=utc(6), end_utc=utc(12))
        assert tw.duration_seconds() == 6 * 3600

    def test_naive_timestamp_rejected(self) -> None:
        with pytest.raises(AppError) as exc:
            TimeWindow(start_utc=datetime(2026, 8, 21, 6), end_utc=utc(12))
        assert exc.value.code == ErrorCode.INVALID_TIME_WINDOW

    def test_reversed_window_rejected(self) -> None:
        with pytest.raises(AppError) as exc:
            TimeWindow(start_utc=utc(12), end_utc=utc(6))
        assert exc.value.code == ErrorCode.INVALID_TIME_WINDOW

    def test_equal_timestamps_rejected(self) -> None:
        with pytest.raises(AppError) as exc:
            TimeWindow(start_utc=utc(6), end_utc=utc(6))
        assert exc.value.code == ErrorCode.INVALID_TIME_WINDOW

    def test_contains(self) -> None:
        tw = TimeWindow(start_utc=utc(6), end_utc=utc(12))
        assert tw.contains(utc(9))
        assert not tw.contains(utc(13))

    def test_offset_aware_is_normalized_to_utc(self) -> None:
        tz = timezone(timedelta(hours=-7))
        tw = TimeWindow(
            start_utc=datetime(2026, 8, 21, 6, tzinfo=tz),
            end_utc=datetime(2026, 8, 21, 12, tzinfo=tz),
        )
        assert tw.duration_seconds() == 6 * 3600