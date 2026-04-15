from __future__ import annotations

import secrets

from fastapi import HTTPException, Security, status
from fastapi.responses import HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.security import APIKeyHeader

from app.core.settings import get_settings

API_KEY_HEADER_NAME = "X-API-Key"
API_KEY_SCHEME_NAME = "ApiKeyAuth"

_api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, scheme_name=API_KEY_SCHEME_NAME, auto_error=False)


def _validate_api_key(provided_key: str | None) -> None:
    settings = get_settings()
    expected_key = settings.api_access_key
    if not expected_key:
        return
    if provided_key and secrets.compare_digest(provided_key, expected_key):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": "forbidden", "message": "A valid API key is required."},
    )


async def require_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    _validate_api_key(api_key)


def build_swagger_html(*, openapi_url: str, title: str) -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url=openapi_url,
        title=title,
        swagger_ui_parameters={"persistAuthorization": True},
    )
