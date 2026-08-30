import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadinessResponse(BaseModel):
    status: str
    db: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness — never blocks on external dependencies."""
    return HealthResponse(status="ok", version=settings.app_version)


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(db: Session = Depends(get_db)) -> ReadinessResponse:
    """Readiness — verifies PostgreSQL connectivity only."""
    try:
        db.execute(text("SELECT 1"))
        return ReadinessResponse(status="ready", db="up")
    except Exception:
        logger.warning("database_unavailable")
        raise HTTPException(status_code=503, detail={"status": "not_ready", "db": "down"})