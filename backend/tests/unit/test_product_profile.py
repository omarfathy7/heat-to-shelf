from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.errors import AppError, ErrorCode
from app.domain.entities.product import Product, ProductProfile


def build_profile(**overrides) -> ProductProfile:
    base = dict(
        id=uuid4(),
        product_id=uuid4(),
        version=1,
        min_temp_c=0.0,
        max_temp_c=4.0,
        warning_threshold_c=8.0,
        critical_threshold_c=12.0,
        exposure_rules={
            "duration": {"max_minutes": 1440},
            "exceedance": {"max_minutes": 60},
            "persistence": {"max_minutes": 30},
        },
        source_name="Some Credible Source",
        source_url="https://example.com/source",
        source_published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        effective_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
        active=True,
    )
    base.update(overrides)
    return ProductProfile(**base)


class TestProductProfileValidation:
    def test_valid_profile(self) -> None:
        p = build_profile()
        assert p.version == 1

    def test_critical_below_warning_rejected(self) -> None:
        with pytest.raises(AppError) as exc:
            build_profile(warning_threshold_c=15.0, critical_threshold_c=12.0)
        assert exc.value.code == ErrorCode.PRODUCT_PROFILE_UNAVAILABLE

    def test_exposure_rules_require_duration_exceedance_persistence(self) -> None:
        rules = {"duration": {"max_minutes": 60}}
        with pytest.raises(AppError) as exc:
            build_profile(exposure_rules=rules)
        assert exc.value.code == ErrorCode.PRODUCT_PROFILE_UNAVAILABLE
        assert "exceedance" in exc.value.message and "persistence" in exc.value.message

    def test_threshold_ordering_semantics(self) -> None:
        # max_temp should not exceed warning; keep domain invariant explicit.
        p = build_profile()
        assert p.min_temp_c < p.max_temp_c <= p.warning_threshold_c <= p.critical_threshold_c


class TestProduct:
    def test_product_basic(self) -> None:
        p = Product(id=uuid4(), name="Fresh Produce", category="Perishables", active=True)
        assert p.active is True
        assert p.category == "Perishables"