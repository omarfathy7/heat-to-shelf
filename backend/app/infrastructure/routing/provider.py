from typing import Protocol

from app.core.config import settings
from app.domain.interfaces.providers import RoutingProvider
from app.infrastructure.routing.fixture import FixtureRoutingProvider
from app.infrastructure.routing.http import HttpRoutingProvider


def get_routing_provider() -> RoutingProvider:
    name = settings.routing_provider.lower()
    if name == "fixture":
        return FixtureRoutingProvider()
    if name == "http":
        return HttpRoutingProvider(
            base_url=settings.routing_base_url,
            api_key=settings.routing_api_key,
            timeout=settings.routing_timeout_seconds,
        )
    raise ValueError(f"unknown routing provider: {name}")