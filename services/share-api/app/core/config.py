from functools import lru_cache
from typing import Any, Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["local", "hybrid", "gcp"]

# Valores por defecto de cada perfil. Solo se aplican a lo que NO se definió explícitamente:
# una variable de entorno concreta siempre gana sobre el perfil.
PROFILE_DEFAULTS: dict[str, dict[str, Any]] = {
    # Todo en Docker en localhost: Postgres, SeaweedFS (S3) y Mailpit locales.
    "local": {
        "storage_backend": "s3",
        "email_provider": "smtp",
        "public_base_url": "http://localhost:8080",
    },
    # Contenedores en localhost conectados a la infraestructura real de GCP.
    "hybrid": {
        "storage_backend": "gcs",
        "email_provider": "smtp",
        "public_base_url": "http://localhost:8080",
    },
    # Todo en Cloud Run. PUBLIC_BASE_URL la define Terraform.
    "gcp": {"storage_backend": "gcs", "email_provider": "none"},
}


class Settings(BaseSettings):
    """Configuración de share-api. Los secretos solo llegan por variables de entorno."""

    model_config = SettingsConfigDict(extra="ignore")

    # Perfil de ejecución (APP_ENV): local | hybrid | gcp
    app_env: AppEnv = "local"
    log_level: str = "INFO"
    public_base_url: str = "http://localhost:8000"
    # Zona horaria del negocio para agrupar indicadores por día
    business_timezone: str = "America/Santiago"

    database_url: str

    # Autenticación de usuarios internos
    jwt_secret: SecretStr
    jwt_ttl_minutes: int = 15
    refresh_ttl_days: int = 7
    cookie_secure: bool = True
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    password_min_length: int = 10
    internal_email_domains: list[str] = Field(default_factory=lambda: ["thinknex.example"])

    # Usuarios iniciales: un ADMIN siempre; usuarios demo solo si se habilita
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: SecretStr | None = None
    bootstrap_admin_name: str = "Administrador"
    demo_users_enabled: bool = False
    demo_users_password: SecretStr | None = None

    # Acceso del destinatario
    otp_secret: SecretStr
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5
    otp_max_sends: int = 5
    access_token_ttl_minutes: int = 30  # sesión del destinatario en el visor

    # Políticas de share
    default_expiry_hours: int = 72
    max_expiry_hours: int = 168
    default_max_accesses: int = 3
    max_accesses_limit: int = 100
    snapshot_grace_hours: int = 24

    # Sistema documental (DMS)
    dms_base_url: str = "http://localhost:8001"
    dms_api_key: SecretStr
    dms_timeout_seconds: float = 10.0
    max_upload_mb: int = 20
    # Si se define, se agrega un ID token de Google (Cloud Run con invoker IAM) además de la key
    dms_audience: str | None = None

    # Almacenamiento de snapshots: s3 (S3/SeaweedFS local) o gcs (Cloud Storage con ADC)
    storage_backend: Literal["s3", "gcs"] = "s3"
    s3_endpoint_url: str | None = None
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None
    s3_region: str = "us-east-1"
    snapshot_bucket: str = "share-snapshots"

    # Canales. EMAIL_PROVIDER: smtp (Mailpit local) | resend (email real) | none (solo simulado)
    email_provider: Literal["smtp", "resend", "none"] = "smtp"
    email_from: str = "ThinkNex Docs (demo) <no-reply@thinknex.example>"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    resend_api_key: SecretStr | None = None
    # Bandeja simulada (SOLO DEMO): guarda cada mensaje, con enlace/OTP, visible para ADMIN
    simulated_inbox_enabled: bool = False
    simulated_inbox_ttl_days: int = 7

    # Chequeo de sensibilidad asistido por LLM (opcional)
    sensitivity_llm_enabled: bool = False
    anthropic_api_key: SecretStr | None = None
    sensitivity_llm_model: str = "claude-haiku-5-5"
    sensitivity_llm_max_chars: int = 8000
    sensitivity_llm_timeout_seconds: float = 20.0

    @model_validator(mode="before")
    @classmethod
    def _apply_profile(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        profile = str(data.get("app_env") or "local")
        if profile == "gcp" and data.get("resend_api_key"):
            data.setdefault("email_provider", "resend")
        for field, value in PROFILE_DEFAULTS.get(profile, {}).items():
            data.setdefault(field, value)
        return data

    @model_validator(mode="after")
    def _strong_secrets(self) -> Self:
        for name in ("jwt_secret", "otp_secret"):
            if len(getattr(self, name).get_secret_value()) < 32:
                raise ValueError(f"{name.upper()} debe tener al menos 32 caracteres")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
