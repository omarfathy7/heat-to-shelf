from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.errors import AppError, ErrorCode


class Product(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    category: str
    active: bool


class ProductProfile(BaseModel):
    """Versioned, sourced cargo rules. Never overwrite a used profile."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    version: int
    min_temp_c: float
    max_temp_c: float
    warning_threshold_c: float
    critical_threshold_c: float
    exposure_rules: dict[str, Any]
    source_name: str
    source_url: str
    source_published_at: datetime | None = None
    effective_from: datetime
    effective_to: datetime | None = None
    active: bool = Field(default=True)

    @model_validator(mode="after")
    def _thresholds_ordered(self) -> "ProductProfile":
        if self.critical_threshold_c < self.warning_threshold_c:
            raise AppError(
                ErrorCode.PRODUCT_PROFILE_UNAVAILABLE,
                "critical_threshold_c must be >= warning_threshold_c",
            )
        return self

    @model_validator(mode="after")
    def _exposure_rules_complete(self) -> "ProductProfile":
        required = {"duration", "exceedance", "persistence"}
        missing = required - set(self.exposure_rules)
        if missing:
            raise AppError(
                ErrorCode.PRODUCT_PROFILE_UNAVAILABLE,
                f"exposure_rules missing required keys: {sorted(missing)}",
            )
        return self

    def is_approved(self) -> bool:
        """A profile is approved only when a real source is present and enabled."""
        if not self.active:
            return False
        if self.source_published_at is None:
            return False
        if self.source_url.startswith("pending:"):
            return False
        return True