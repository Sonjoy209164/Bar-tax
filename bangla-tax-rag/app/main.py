from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_eval import router as eval_router
from app.api.routes_agentic import router as agentic_router
from app.api.routes_health import router as health_router
from app.api.routes_ingest import router as ingest_router
from app.api.routes_query import router as query_router
from app.core.logging import configure_logging, get_logger
from app.core.settings import get_settings

configure_logging()
settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info(
        "FastAPI app started",
        extra={
            "environment": settings.app_env,
            "retrieval_mode": settings.retrieval_mode,
            "sparse_index_dir": settings.sparse_index_dir,
        },
    )
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(eval_router)
app.include_router(agentic_router)
