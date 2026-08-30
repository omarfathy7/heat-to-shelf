from typing import Protocol


class AuthProvider(Protocol):
    async def authenticate(self, token: str) -> str | None:
        """Return a user id for a valid token, or None."""