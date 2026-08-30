from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import Product, ProductProfile


class ProductRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_enabled_with_profiles(self) -> list[tuple[Product, list[ProductProfile]]]:
        """Enabled products and their active, in-effect, approved profiles."""
        now = func.now()
        products = (
            self.session.execute(
                select(Product).where(Product.active.is_(True)).order_by(Product.name)
            )
            .scalars()
            .all()
        )
        result: list[tuple[Product, list[ProductProfile]]] = []
        for product in products:
            profiles = (
                self.session.execute(
                    select(ProductProfile)
                    .where(
                        ProductProfile.product_id == product.id,
                        ProductProfile.active.is_(True),
                        ProductProfile.effective_from <= now,
                        (ProductProfile.effective_to.is_(None) | (ProductProfile.effective_to >= now)),
                    )
                    .order_by(ProductProfile.version.desc())
                )
                .scalars()
                .all()
            )
            result.append((product, profiles))
        return result


class ProductProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, profile_id) -> ProductProfile | None:
        return self.session.get(ProductProfile, profile_id)

    def get_active_for_product(self, product_id: object) -> ProductProfile | None:
        now = func.now()
        return self.session.execute(
            select(ProductProfile)
            .where(
                ProductProfile.product_id == product_id,
                ProductProfile.active.is_(True),
                ProductProfile.effective_from <= now,
                (ProductProfile.effective_to.is_(None) | (ProductProfile.effective_to >= now)),
            )
            .order_by(ProductProfile.version.desc())
            .limit(1)
        ).scalar_one_or_none()