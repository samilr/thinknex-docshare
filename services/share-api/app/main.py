from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.api.public import access
from app.api.v1 import admin, audit, auth, documents, library, policies, shares, stats
from app.container import Components, build_components
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import RequestContextMiddleware, configure_logging
from app.db.seed import seed_users

DESCRIPTION = """
Compartición **segura y auditable** de documentos del sistema documental.

* El documento nunca viaja por el canal: el destinatario recibe un enlace y valida un OTP.
* Cada acción queda en una auditoría append-only encadenada por hash (`/api/v1/audit/verify`).
* Antes de compartir se evalúa la sensibilidad (reglas + IA opcional).

**Acceso:** botón `Authorize` con un usuario de la plataforma. En ambientes demo existen
`ana@thinknex.example` (SHARER), `carla@thinknex.example` (AUDITOR) y el ADMIN de arranque.
"""


def create_app(settings: Settings | None = None, components: Components | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.components = components or build_components(settings)
        with app.state.components.session_factory() as db:
            seed_users(db, settings)
        yield

    app = FastAPI(
        title="Share API — compartición segura de documentos",
        version="0.1.0",
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(access.router)
    for router in (
        auth.router,
        documents.router,
        library.router,
        shares.router,
        audit.router,
        stats.router,
        admin.router,
        policies.router,
    ):
        app.include_router(router, prefix="/api/v1")
    return app
