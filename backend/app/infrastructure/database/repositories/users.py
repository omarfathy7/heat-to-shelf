from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: UUID) -> User | None:
        return self.session.get(User, user_id)

    def get_or_create(self, email: str) -> User:
        user = self.session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            user = User(email=email)
            self.session.add(user)
            self.session.flush()
        return user