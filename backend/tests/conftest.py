from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.infrastructure.database.models import Product, ProductProfile
from app.main import app

_test_engine = create_engine(settings.database_url)


@pytest.fixture(autouse=True)
def _unlimited_analysis_rate() -> None:
    """Analysis rate limiting is verified in dedicated tests; keep the rest of
    the suite from tripping the process-global limiter."""
    from app.api import rate_limit

    original = rate_limit._limiter
    rate_limit._limiter = rate_limit.SlidingWindowLimiter(10_000_000, 60)
    yield
    rate_limit._limiter = original


def _db_available() -> bool:
    try:
        with _test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _db_available(), reason="PostGIS database not available")

TEST_SOURCE_URL = "https://example.com/test-source"


@pytest.fixture()
def isolated_db() -> Session:
    """A rolled-back session used by any DB-backed API test.

    Installs a get_db override so the whole request shares one isolated
    transaction that is always rolled back — no test pollution.
    """
    if not _db_available():
        pytest.skip("database not available")
    connection = _test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def approved_profile(isolated_db: Session) -> ProductProfile:
    product = Product(name="Test Produce", category="Perishables", active=True)
    isolated_db.add(product)
    isolated_db.flush()
    profile = ProductProfile(
        product_id=product.id,
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
        source_name="Test Source",
        source_url=TEST_SOURCE_URL,
        source_published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        effective_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
        active=True,
    )
    isolated_db.add(profile)
    isolated_db.flush()
    return profile