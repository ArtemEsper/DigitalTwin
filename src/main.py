import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.admin import router as admin_router
from src.api.health import router as health_router
from src.api.memory import router as memory_router
from src.api.slack import router as slack_router
from src.config import settings

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Digital Twin API starting (env=%s)", settings.APP_ENV)
    yield
    logger.info("Digital Twin API shutting down")


app = FastAPI(
    title="Digital Twin API",
    version="0.1.0",
    description=(
        "Memory-grounded conversational agent representing a person. "
        "All memory writes require admin approval."
    ),
    lifespan=lifespan,
    # Disable automatic schema exposure in non-development environments
    docs_url="/docs" if settings.APP_ENV == "development" else None,
    redoc_url="/redoc" if settings.APP_ENV == "development" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.APP_ENV == "development" else [],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(health_router, tags=["health"])
app.include_router(memory_router, prefix="/api/v1/memory", tags=["memory"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(slack_router, prefix="/api/v1/slack", tags=["slack"])
