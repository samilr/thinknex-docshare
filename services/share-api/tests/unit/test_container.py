import pytest
from pydantic import SecretStr

from app.adapters.channels.email_resend import ResendEmailChannel
from app.adapters.channels.email_smtp import SmtpEmailChannel
from app.adapters.channels.mock_messaging import MockMessagingChannel
from app.container import build_email_channel
from app.core.config import Settings


def settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+psycopg://x/y",
        "jwt_secret": SecretStr("j" * 32),
        "otp_secret": SecretStr("o" * 32),
        "dms_api_key": SecretStr("k"),
    }
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


def test_email_provider_selection() -> None:
    assert isinstance(build_email_channel(settings(email_provider="smtp")), SmtpEmailChannel)
    assert isinstance(build_email_channel(settings(email_provider="none")), MockMessagingChannel)
    resend = settings(email_provider="resend", resend_api_key=SecretStr("re_test"))
    assert isinstance(build_email_channel(resend), ResendEmailChannel)


def test_resend_requires_key() -> None:
    with pytest.raises(RuntimeError, match="RESEND_API_KEY"):
        build_email_channel(settings(email_provider="resend"))


def test_weak_secrets_are_rejected() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        settings(jwt_secret=SecretStr("corto"))
