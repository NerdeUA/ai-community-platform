import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.logging_handler import OpenSearchHandler
from app.middleware.trace import TraceMiddleware
from app.routers import health
from app.routers.admin import assets as admin_assets
from app.routers.admin import settings as admin_settings
from app.routers.admin import sources as admin_sources
from app.routers.api import analyze as api_analyze
from app.routers.api import manifest as api_manifest
from app.routers.web import dashboard as web_dashboard

logging.basicConfig(level=logging.INFO)
_os_handler = OpenSearchHandler(settings.opensearch_url)
logging.getLogger().addHandler(_os_handler)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.scheduler import start_scheduler, stop_scheduler

    try:
        start_scheduler()
        logger.info("ti-analyst started")
    except Exception as exc:
        logger.warning("Scheduler could not start: %s", exc)

    yield

    try:
        stop_scheduler()
    except Exception:
        pass
    logger.info("ti-analyst stopped")


app = FastAPI(title="ti-analyst", version="0.1.0", lifespan=lifespan)
app.add_middleware(TraceMiddleware)

app.include_router(health.router)
app.include_router(api_manifest.router)
app.include_router(api_analyze.router)
app.include_router(admin_sources.router)
app.include_router(admin_assets.router)
app.include_router(admin_settings.router)
app.include_router(web_dashboard.router)
