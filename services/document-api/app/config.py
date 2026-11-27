from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"

AppEnv = Literal["local", "hybrid", "gcp"]

# Valores por defecto por perfil; una variable explícita siempre gana.
PROFILE_DEFAULTS: dict[str, dict[str, Any]] = {
    "local": {"storage_backend": "s3", "dms_create_database": True},
    "hybrid": {"storage_backend": "gcs", "dms_create_database": False},
    "gcp": {"storage_backend": "gcs", "dms_create_database": False},
}


class Settings(BaseSettings):
    """Configuración del DMS simulado. Todo valor sensible llega por variables de entorno."""

    model_config = SettingsConfigDict(extra="ignore")

    # Perfil de ejecución (APP_ENV): local | hybrid | gcp
    app_env: AppEnv = "local"
    dms_api_key: SecretStr
    storage_backend: Literal["s3", "gcs"] = "s3"
    s3_endpoint_url: str | None = None
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None
    s3_region: str = "us-east-1"
    dms_bucket: str = "dms-documents"
    dms_auto_seed: bool = True
    # Persistencia de metadata (Postgres en ambientes reales; SQLite en memoria en tests)
    database_url: str = "sqlite+pysqlite:///:memory:"
    # Solo local: crea la base si no existe (en la nube la crea Terraform)
    dms_create_database: bool = False
    max_upload_mb: int = 20
    seed_catalog_path: Path = SEED_DIR / "catalog.json"

    @model_validator(mode="before")
    @classmethod
    def _apply_profile(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field, value in PROFILE_DEFAULTS.get(
                str(data.get("app_env") or "local"), {}
            ).items():
                data.setdefault(field, value)
        return data


@lru_cache
def get_settings() -> Settings:
    return Settings()
