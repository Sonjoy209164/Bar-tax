from __future__ import annotations

import hashlib
import secrets
from collections import deque
from math import ceil
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request, Security, status
from fastapi.responses import HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.security import APIKeyHeader

from app.core.settings import get_settings

API_KEY_HEADER_NAME = "X-API-Key"
API_KEY_SCHEME_NAME = "ApiKeyAuth"

_api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, scheme_name=API_KEY_SCHEME_NAME, auto_error=False)


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = {}
        self._lock = Lock()

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def check(self, identity: str, *, limit: int, window_seconds: int) -> None:
        if limit <= 0 or window_seconds <= 0:
            return

        now = monotonic()
        cutoff = now - window_seconds

        with self._lock:
            bucket = self._buckets.setdefault(identity, deque())

            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after_seconds = max(1, ceil(window_seconds - (now - bucket[0])))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "rate_limited",
                        "message": "Too many requests for this API identity. Please retry later.",
                        "retry_after_seconds": retry_after_seconds,
                    },
                )

            bucket.append(now)


_rate_limiter = InMemoryRateLimiter()


def _api_key_identity(api_key: str) -> str:
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]
    return f"key:{digest}"


def _client_identity(request: Request) -> str:
    if request.client and request.client.host:
        return f"ip:{request.client.host}"

    forwarded_for = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded_for:
        return f"ip:{forwarded_for}"

    return "ip:unknown"


def _validate_api_key(provided_key: str | None) -> str | None:
    settings = get_settings()
    accepted_keys = settings.accepted_api_keys()

    if not accepted_keys:
        return None

    if provided_key:
        for expected_key in accepted_keys:
            if secrets.compare_digest(provided_key, expected_key):
                return _api_key_identity(expected_key)

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": "forbidden", "message": "A valid API key is required."},
    )


def _enforce_rate_limit(request: Request, authenticated_identity: str | None) -> None:
    settings = get_settings()

    if settings.api_rate_limit_requests <= 0:
        return

    identity = authenticated_identity or _client_identity(request)
    _rate_limiter.check(
        identity,
        limit=settings.api_rate_limit_requests,
        window_seconds=settings.api_rate_limit_window_seconds,
    )


async def require_api_key(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> None:
    authenticated_identity = _validate_api_key(api_key)
    _enforce_rate_limit(request, authenticated_identity)


def reset_security_state() -> None:
    _rate_limiter.reset()


def build_swagger_html(*, openapi_url: str, title: str) -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url=openapi_url,
        title=title,
        swagger_ui_parameters={"persistAuthorization": True},
    )
