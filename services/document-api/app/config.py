from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"


class Settings(BaseSettings):
    """Configuración del DMS simulado. Todo valor sensible llega por variables de entorno."""

    model_config = SettingsConfigDict(extra="ignore")

    dms_api_key: SecretStr
    storage_backend: Literal["s3", "gcs"] = "s3"
    s3_endpoint_url: str | None = None
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None
    s3_region: str = "us-east-1"
    dms_bucket: str = "dms-documents"
    dms_auto_seed: bool = True
    seed_catalog_path: Path = SEED_DIR / "catalog.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
