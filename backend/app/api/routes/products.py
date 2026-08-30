from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_db
from app.domain.entities.product import ProductProfile
from app.infrastructure.database.repositories.products import ProductRepository

router = APIRouter(tags=["products"])


class ProfileOut(BaseModel):
    id: UUID
    version: int
    min_temp_c: float
    max_temp_c: float
    warning_threshold_c: float
    critical_threshold_c: float
    source_name: str
    source_url: str
    source_published_at: datetime | None = None


class ProductOut(BaseModel):
    id: UUID
    name: str
    category: str
    profiles: list[ProfileOut]


@router.get("/products", response_model=list[ProductOut])
async def list_products(db=Depends(get_db)) -> list[ProductOut]:
    repo = ProductRepository(db)
    result: list[ProductOut] = []
    for product, profiles in repo.list_enabled_with_profiles():
        approved = [p for p in profiles if ProductProfile.model_validate(p, from_attributes=True).is_approved()]
        result.append(
            ProductOut(
                id=product.id,
                name=product.name,
                category=product.category,
                profiles=[
                    ProfileOut(
                        id=p.id,
                        version=p.version,
                        min_temp_c=p.min_temp_c,
                        max_temp_c=p.max_temp_c,
                        warning_threshold_c=p.warning_threshold_c,
                        critical_threshold_c=p.critical_threshold_c,
                        source_name=p.source_name,
                        source_url=p.source_url,
                        source_published_at=p.source_published_at,
                    )
                    for p in approved
                ],
            )
        )
    return result