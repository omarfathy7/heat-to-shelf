from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.infrastructure.database.repositories.users import UserRepository
from app.infrastructure.database.session import get_db


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> CurrentUser:
    """Simple MVP user boundary: identity from a header, defaulting to a demo user."""
    email = (request.headers.get("X-User-Email") or settings.default_user_email).strip().lower()
    if not email:
        raise AppError(ErrorCode.INTERNAL_ERROR, "missing user identity")
    user = UserRepository(db).get_or_create(email)
    return CurrentUser(id=user.id, email=user.email)