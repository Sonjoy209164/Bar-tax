from fastapi import APIRouter, Depends

from app.core.schemas import ConfigResponse, HealthResponse
from app.core.security import require_api_key
from app.core.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="bangla-tax-rag")


@router.get("/config", response_model=ConfigResponse, dependencies=[Depends(require_api_key)])
async def read_runtime_config() -> ConfigResponse:
    settings = get_settings()
    return ConfigResponse(**settings.non_secret_config())
