"""Composición de dependencias (composition root). Los tests reemplazan piezas con fakes."""

from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.adapters.channels.base import ChannelAdapter, ChannelRegistry, DevOutbox, RecordingChannel
from app.adapters.channels.email_smtp import SmtpEmailChannel
from app.adapters.channels.mock_messaging import MockMessagingChannel
from app.adapters.document_source import DocumentSource, HttpDocumentSource
from app.adapters.storage import BlobStorage, S3BlobStorage
from app.core.config import Settings
from app.db.session import session_factory
from app.domain.enums import Channel
from app.sensitivity.checker import SensitivityChecker
from app.sensitivity.llm_classifier import ClaudeSensitivityClassifier


@dataclass
class Components:
    session_factory: sessionmaker[Session]
    source: DocumentSource
    storage: BlobStorage
    channels: ChannelRegistry
    checker: SensitivityChecker
    outbox: DevOutbox | None


def build_storage(settings: Settings) -> S3BlobStorage:
    storage = S3BlobStorage(
        bucket=settings.snapshot_bucket,
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key.get_secret_value() if settings.s3_access_key else None,
        secret_key=settings.s3_secret_key.get_secret_value() if settings.s3_secret_key else None,
        region=settings.s3_region,
    )
    storage.ensure_bucket()
    return storage


def build_channels(settings: Settings, outbox: DevOutbox | None) -> ChannelRegistry:
    adapters: dict[Channel, ChannelAdapter] = {
        Channel.EMAIL: SmtpEmailChannel(settings.smtp_host, settings.smtp_port, settings.smtp_from),
        Channel.WHATSAPP: MockMessagingChannel("whatsapp-mock"),
        Channel.SMS: MockMessagingChannel("sms-mock"),
    }
    if outbox is not None:
        adapters = {ch: RecordingChannel(a, outbox) for ch, a in adapters.items()}
    return ChannelRegistry(adapters)


def build_checker(settings: Settings) -> SensitivityChecker:
    classifier = None
    if settings.sensitivity_llm_enabled:
        classifier = ClaudeSensitivityClassifier(
            api_key=(
                settings.anthropic_api_key.get_secret_value()
                if settings.anthropic_api_key
                else None
            ),
            model=settings.sensitivity_llm_model,
            timeout=settings.sensitivity_llm_timeout_seconds,
        )
    return SensitivityChecker(classifier, settings.sensitivity_llm_max_chars)


def build_components(settings: Settings) -> Components:
    outbox = DevOutbox() if settings.env == "dev" else None
    return Components(
        session_factory=session_factory(settings.database_url),
        source=HttpDocumentSource(
            settings.dms_base_url,
            settings.dms_api_key.get_secret_value(),
            settings.dms_timeout_seconds,
        ),
        storage=build_storage(settings),
        channels=build_channels(settings, outbox),
        checker=build_checker(settings),
        outbox=outbox,
    )
