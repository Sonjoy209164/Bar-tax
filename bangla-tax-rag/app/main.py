from fastapi import FastAPI

from app.api.routes_eval import router as eval_router
from app.api.routes_health import router as health_router
from app.api.routes_ingest import router as ingest_router
from app.api.routes_query import router as query_router
from app.core.logging import configure_logging
from app.core.settings import get_settings

configure_logging()
settings = get_settings()

app = FastAPI(title=settings.app_name)

app.include_router(health_router)
app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(eval_router)
