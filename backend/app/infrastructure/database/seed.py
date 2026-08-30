"""Seed the single approved, sourced Fresh Produce profile.

Per plan section 2 and 5, thresholds must come from a credible source supplied
by the product member; a profile is not enabled until its source is confirmed.
We therefore seed the product and profile with `active=False` and placeholder
source metadata so nothing is presented as live, approved guidance.
"""

from datetime import datetime, timezone

from app.infrastructure.database.models import Product, ProductProfile
from app.infrastructure.database.session import SessionLocal

PENDING_SOURCE_NAME = "PENDING_PRODUCT_REVIEW"
PENDING_SOURCE_URL = "pending://fresh-produce-profile"

PRODUCT = {
    "name": "Fresh Produce",
    "category": "Perishables",
}

PROFILE_V1 = {
    "version": 1,
    "min_temp_c": 0.0,
    "max_temp_c": 4.0,
    "warning_threshold_c": 8.0,
    "critical_threshold_c": 12.0,
    "exposure_rules": {
        "duration": {
            "description": "continuous time within the journey, in minutes",
            "max_minutes": 1440,
        },
        "exceedance": {
            "description": "consecutive minutes above threshold per segment",
            "max_minutes": 60,
        },
        "persistence": {
            "description": "longest uninterrupted run above critical threshold",
            "max_minutes": 30,
        },
    },
    "source_name": PENDING_SOURCE_NAME,
    "source_url": PENDING_SOURCE_URL,
    "source_published_at": None,
    "effective_from": datetime(2024, 1, 1, tzinfo=timezone.utc),
    "active": False,
}


def seed() -> None:
    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.name == PRODUCT["name"]).first()
        if product is None:
            product = Product(**PRODUCT)
            db.add(product)
            db.flush()

        profile = (
            db.query(ProductProfile)
            .filter(
                ProductProfile.product_id == product.id,
                ProductProfile.version == PROFILE_V1["version"],
            )
            .first()
        )
        if profile is None:
            db.add(ProductProfile(product_id=product.id, **PROFILE_V1))
            db.commit()
            print(f"Seeded Fresh Produce profile v{PROFILE_V1['version']} (inactive, awaiting source review)")
        else:
            print("Fresh Produce profile already present; nothing to do.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()