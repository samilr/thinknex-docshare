from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import ComponentsDep, SettingsDep

router = APIRouter(tags=["health"])
VERSION = "0.3.0"


class MetaOut(BaseModel):
    app_env: str
    version: str


@router.get("/health")
def health(settings: SettingsDep) -> dict[str, str]:
    return {"status": "ok", "app_env": settings.app_env}


@router.get("/api/v1/meta", response_model=MetaOut)
def meta(settings: SettingsDep) -> MetaOut:
    """Perfil de ejecución (local | hybrid | gcp): el portal lo muestra en el encabezado."""
    return MetaOut(app_env=settings.app_env, version=VERSION)


@router.get("/ready")
def ready(components: ComponentsDep, settings: SettingsDep) -> JSONResponse:
    checks: dict[str, bool] = {}
    try:
        with components.session_factory() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False
    checks["storage"] = components.storage.ping()
    checks["document_source"] = components.source.ping()
    ok = all(checks.values())
    return JSONResponse(
        {"ready": ok, "app_env": settings.app_env, "checks": checks},
        status_code=200 if ok else 503,
    )
