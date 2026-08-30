import asyncio
import logging
import time

import httpx

from app.core.config import settings
from app.core.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


class FortyGuardClient:
    """HTTP client for FortyGuard with timeout, retry, rate-limit handling.

    Credentials live server-side only. Every response passes through record-
    keeping for request type, duration, status, retries, and usage metadata.
    Raw provider errors are mapped to sanitized application errors.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        backoff_seconds: float | None = None,
        max_staleness_minutes: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or settings.fortyguard_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.fortyguard_api_key
        self.timeout = timeout if timeout is not None else settings.fortyguard_timeout_seconds
        self.max_retries = max_retries if max_retries is not None else settings.fortyguard_max_retries
        self.backoff = backoff_seconds if backoff_seconds is not None else settings.fortyguard_retry_backoff_seconds
        self.max_staleness_minutes = (
            max_staleness_minutes if max_staleness_minutes is not None else settings.fortyguard_max_staleness_minutes
        )
        self._transport = transport

    def configured(self) -> bool:
        return bool(self.api_key)

    async def _client(self) -> httpx.AsyncClient:
        if self._transport is not None:
            return httpx.AsyncClient(timeout=self.timeout, transport=self._transport)
        return httpx.AsyncClient(timeout=self.timeout)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def get_json(self, provider: str, path: str, params: dict) -> tuple[dict, dict]:
        """Return (json_body, request_metadata) or raise a sanitized AppError."""
        meta: dict = {
            "provider": provider,
            "path": path,
            "duration_ms": 0.0,
            "status": None,
            "retries": 0,
            "rate_limited": False,
            "usage": None,
        }
        if not self.configured():
            raise AppError(
                ErrorCode.FORTYGUARD_PROVIDER_FAILED,
                f"{provider} not configured",
                status_code=503,
            )

        client = await self._client()
        start = time.perf_counter()
        try:
            attempt = 0
            while True:
                try:
                    resp = await client.get(f"{self.base_url}{path}", params=params, headers=self._headers())
                except httpx.TimeoutException as exc:
                    if attempt < self.max_retries:
                        attempt += 1
                        meta["retries"] = attempt
                        await asyncio.sleep(self.backoff * (2 ** (attempt - 1)))
                        continue
                    raise AppError(
                        ErrorCode.FORTYGUARD_PROVIDER_FAILED,
                        f"{provider} request timed out",
                        status_code=504,
                    ) from exc
                except httpx.HTTPError as exc:
                    raise AppError(
                        ErrorCode.FORTYGUARD_PROVIDER_FAILED,
                        f"{provider} unreachable",
                        status_code=503,
                    ) from exc

                meta["status"] = resp.status_code
                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    meta["rate_limited"] = resp.status_code == 429
                    if attempt < self.max_retries:
                        attempt += 1
                        meta["retries"] = attempt
                        await asyncio.sleep(self.backoff * (2 ** (attempt - 1)))
                        continue
                break

            if resp.status_code >= 400:
                logger.warning(
                    "provider_http_error",
                    extra={"provider": provider, "path": path, "status": resp.status_code},
                )
                raise AppError(
                    ErrorCode.FORTYGUARD_PROVIDER_FAILED,
                    f"{provider} returned status {resp.status_code}",
                    status_code=502,
                )

            try:
                body = resp.json()
            except ValueError as exc:
                raise AppError(
                    ErrorCode.FORTYGUARD_RESPONSE_INVALID,
                    f"{provider} returned non-JSON body",
                    status_code=502,
                ) from exc

            meta["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
            meta["usage"] = {
                "quota_remaining": resp.headers.get("x-ratelimit-remaining"),
                "quota_limit": resp.headers.get("x-ratelimit-limit"),
            }
            logger.info(
                "provider_request",
                extra={
                    "provider": provider,
                    "path": path,
                    "status": resp.status_code,
                    "duration_ms": meta["duration_ms"],
                    "retries": meta["retries"],
                },
            )
            return body, meta
        finally:
            await client.aclose()