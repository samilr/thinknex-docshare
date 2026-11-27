import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app.config import Settings, get_settings
from app.db import build_engine, ensure_database, migrate
from app.routes import router
from app.seed import load_catalog, seed
from app.storage import BlobStore, GcsBlobStore, S3BlobStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _build_store(settings: Settings) -> BlobStore:
    if settings.storage_backend == "gcs":
        return GcsBlobStore(settings.dms_bucket)
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
        if settings.dms_create_database:
            ensure_database(settings.database_url)
        engine = build_engine(settings.database_url)
        migrate(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        blob_store = store or _build_store(settings)
        if settings.dms_auto_seed:
            with factory() as db:
                seed(db, blob_store, load_catalog(settings.seed_catalog_path))
        app.state.session_factory = factory
        app.state.store = blob_store
        yield
        engine.dispose()

    app = FastAPI(
        title="Document API (DMS simulado)",
        version="0.2.0",
        description=(
            "Simula el sistema documental de la organización: bibliotecas, carpetas, documentos "
            "y versiones. Solo datos ficticios. Acceso servicio a servicio (X-API-Key)."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.include_router(router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
