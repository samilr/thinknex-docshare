import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.catalog import Catalog, load_seed_entries
from app.config import Settings, get_settings
from app.routes import router
from app.seed import seed
from app.storage import BlobStore, S3BlobStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _build_store(settings: Settings) -> BlobStore:
    store = S3BlobStore(
        bucket=settings.dms_bucket,
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key.get_secret_value() if settings.s3_access_key else None,
        secret_key=settings.s3_secret_key.get_secret_value() if settings.s3_secret_key else None,
        region=settings.s3_region,
    )
    store.ensure_bucket()
    return store


def create_app(settings: Settings | None = None, store: BlobStore | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        blob_store = store or _build_store(settings)
        entries = load_seed_entries(settings.seed_catalog_path)
        if settings.dms_auto_seed:
            seed(blob_store, entries)
        catalog = Catalog(blob_store)
        catalog.load(entries)
        app.state.catalog = catalog
        yield

    app = FastAPI(
        title="Document API (DMS simulado)",
        version="0.1.0",
        description="Simula el sistema documental existente. Solo datos ficticios.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.include_router(router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
