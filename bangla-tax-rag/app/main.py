from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from app.api.routes_eval import router as eval_router
from app.api.routes_agentic import router as agentic_router
from app.api.routes_health import router as health_router
from app.api.routes_ingest import router as ingest_router
from app.api.routes_inventory import router as inventory_router
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


app.include_router(health_router)
app.include_router(ingest_router, dependencies=[Depends(require_api_key)])
app.include_router(inventory_router, dependencies=[Depends(require_api_key)])
app.include_router(query_router, dependencies=[Depends(require_api_key)])
app.include_router(eval_router, dependencies=[Depends(require_api_key)])
app.include_router(agentic_router, dependencies=[Depends(require_api_key)])
