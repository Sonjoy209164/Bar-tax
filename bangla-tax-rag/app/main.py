from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_eval import router as eval_router
from app.api.routes_agentic import router as agentic_router
from app.api.routes_feedback import router as feedback_router
from app.api.routes_health import router as health_router
from app.api.routes_ingest import router as ingest_router
from app.api.routes_inventory import router as inventory_router
from app.api.routes_orders import router as orders_router
from app.api.routes_owner import router as owner_router
from app.api.routes_query import router as query_router
from app.core.logging import configure_logging, get_logger
from app.core.security import (
    build_swagger_html,
    require_api_key,
)
from app.core.settings import get_settings

configure_logging()
initial_settings = get_settings()
logger = get_logger(__name__)
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


class SafeFrontendFiles(StaticFiles):
    _DENYLIST = {"config.local.json"}

    async def get_response(self, path: str, scope):  # type: ignore[override]
        normalized = Path(path).as_posix().lstrip("/")
        if normalized in self._DENYLIST:
            return JSONResponse({"detail": {"error": "frontend_asset_not_found"}}, status_code=404)
        return await super().get_response(path, scope)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    logger.info(
        "FastAPI app started",
        extra={
            "environment": settings.app_env,
            "retrieval_mode": settings.retrieval_mode,
            "sparse_index_dir": settings.sparse_index_dir,
        },
    )
    yield


app = FastAPI(title=initial_settings.app_name, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/openapi.json", include_in_schema=False)
async def custom_openapi() -> JSONResponse:
    schema = get_openapi(
        title=app.title,
        version="0.1.0",
        routes=app.routes,
    )
    return JSONResponse(schema)


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    return build_swagger_html(openapi_url="/openapi.json", title=f"{app.title} - Swagger UI")


@app.get("/frontend", include_in_schema=False)
async def frontend_redirect() -> RedirectResponse:
    return RedirectResponse(url="/frontend/", status_code=307)


@app.get("/frontend/runtime-config.json", include_in_schema=False)
async def frontend_runtime_config(request: Request) -> JSONResponse:
    settings = get_settings()
    return JSONResponse(
        {
            "apiBaseUrl": str(request.base_url).rstrip("/"),
            "sameOriginApi": True,
            "apiAuthEnabled": bool(settings.accepted_api_keys()),
            "apiKeyHeader": "X-API-Key",
            "frontendPath": "/frontend/",
        }
    )


app.include_router(health_router)
app.include_router(ingest_router, dependencies=[Depends(require_api_key)])
app.include_router(inventory_router, dependencies=[Depends(require_api_key)])
app.include_router(orders_router, dependencies=[Depends(require_api_key)])
app.include_router(feedback_router, dependencies=[Depends(require_api_key)])
app.include_router(owner_router, dependencies=[Depends(require_api_key)])
app.include_router(query_router, dependencies=[Depends(require_api_key)])
app.include_router(eval_router, dependencies=[Depends(require_api_key)])
app.include_router(agentic_router, dependencies=[Depends(require_api_key)])

if FRONTEND_DIR.exists():
    app.mount(
        "/frontend",
        SafeFrontendFiles(directory=str(FRONTEND_DIR), html=True),
        name="inventory_frontend",
    )
