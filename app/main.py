from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.infrastructure.database import dispose_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await dispose_database()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    register_exception_handlers(application)
    application.include_router(api_router, prefix=settings.api_prefix)
    return application


app = create_app()

