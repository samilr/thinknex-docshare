import pytest
from pydantic import SecretStr

from app.core.config import Settings

BASE = {
    "database_url": "postgresql+psycopg://x/y",
    "jwt_secret": SecretStr("j" * 32),
    "otp_secret": SecretStr("o" * 32),
    "dms_api_key": SecretStr("k"),
}


@pytest.mark.parametrize(
    ("app_env", "storage", "email", "base_url"),
    [
        ("local", "s3", "smtp", "http://localhost:8080"),
        ("hybrid", "gcs", "smtp", "http://localhost:8080"),
        ("gcp", "gcs", "none", "http://localhost:8000"),
    ],
)
def test_profile_defaults(app_env: str, storage: str, email: str, base_url: str) -> None:
    s = Settings(**BASE, app_env=app_env)  # type: ignore[arg-type]
    assert (s.storage_backend, s.email_provider, s.public_base_url) == (storage, email, base_url)


def test_explicit_values_win_over_profile() -> None:
    s = Settings(**BASE, app_env="gcp", storage_backend="s3", email_provider="smtp")  # type: ignore[arg-type]
    assert (s.storage_backend, s.email_provider) == ("s3", "smtp")


def test_gcp_uses_resend_when_key_present() -> None:
    s = Settings(**BASE, app_env="gcp", resend_api_key=SecretStr("re_x"))  # type: ignore[arg-type]
    assert s.email_provider == "resend"


def test_profile_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "hybrid")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x/y")
    monkeypatch.setenv("JWT_SECRET", "j" * 32)
    monkeypatch.setenv("OTP_SECRET", "o" * 32)
    monkeypatch.setenv("DMS_API_KEY", "k")
    s = Settings()  # type: ignore[call-arg]
    assert (s.app_env, s.storage_backend) == ("hybrid", "gcs")
