"""Composición de dependencias (composition root). Los tests reemplazan piezas con fakes."""

import os
from dataclasses import dataclass, field

from sqlalchemy.orm import Session, sessionmaker

from app.adapters.channels.base import ChannelAdapter, ChannelRegistry
from app.adapters.channels.email_resend import ResendEmailChannel
from app.adapters.channels.email_smtp import SmtpEmailChannel
from app.adapters.channels.mock_messaging import MockMessagingChannel
from app.adapters.document_source import DocumentSource, HttpDocumentSource
from app.adapters.storage import BlobStorage, GcsBlobStorage, S3BlobStorage
from app.ai.llm import ClaudeLlm, Llm
from app.ai.providers import Embedder, FakeEmbedder, VertexEmbedder
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
    embedder: Embedder = field(default_factory=FakeEmbedder)
    llm: Llm | None = None


def _secret(value: object) -> str | None:
    getter = getattr(value, "get_secret_value", None)
    return getter() if getter else None


def build_storage(settings: Settings) -> BlobStorage:
    if settings.storage_backend == "gcs":
        return GcsBlobStorage(settings.snapshot_bucket)
    storage = S3BlobStorage(
        bucket=settings.snapshot_bucket,
        endpoint_url=settings.s3_endpoint_url,
        access_key=_secret(settings.s3_access_key),
        secret_key=_secret(settings.s3_secret_key),
        region=settings.s3_region,
    )
    storage.ensure_bucket()
    return storage


def build_email_channel(settings: Settings) -> ChannelAdapter:
    if settings.email_provider == "resend":
        key = _secret(settings.resend_api_key)
        if not key:
            raise RuntimeError("EMAIL_PROVIDER=resend requiere RESEND_API_KEY")
        return ResendEmailChannel(key, settings.email_from)
    if settings.email_provider == "smtp":
        return SmtpEmailChannel(settings.smtp_host, settings.smtp_port, settings.email_from)
    return MockMessagingChannel("email-simulado")


def build_channels(settings: Settings) -> ChannelRegistry:
    return ChannelRegistry(
        {
            Channel.EMAIL: build_email_channel(settings),
            Channel.WHATSAPP: MockMessagingChannel("whatsapp-mock"),
            Channel.SMS: MockMessagingChannel("sms-mock"),
        }
    )


def build_checker(settings: Settings) -> SensitivityChecker:
    classifier = None
    if settings.sensitivity_llm_enabled:
        classifier = ClaudeSensitivityClassifier(
            api_key=_secret(settings.anthropic_api_key),
            model=settings.sensitivity_llm_model,
            timeout=settings.sensitivity_llm_timeout_seconds,
        )
    return SensitivityChecker(classifier, settings.sensitivity_llm_max_chars)


def build_embedder(settings: Settings) -> Embedder:
    project = settings.vertex_project or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if settings.embeddings_provider == "vertex":
        if not project:
            raise RuntimeError("EMBEDDINGS_PROVIDER=vertex requiere VERTEX_PROJECT")
        return VertexEmbedder(
            project=project, location=settings.vertex_location, model=settings.embeddings_model
        )
    return FakeEmbedder()


def build_llm(settings: Settings) -> Llm | None:
    key = _secret(settings.anthropic_api_key) or os.environ.get("ANTHROPIC_API_KEY")
    if not settings.ai_enabled or not key:
        return None
    return ClaudeLlm(api_key=key, timeout=settings.ai_timeout_seconds)


def build_components(settings: Settings) -> Components:
    return Components(
        session_factory=session_factory(settings.database_url),
        source=HttpDocumentSource(
            settings.dms_base_url,
            settings.dms_api_key.get_secret_value(),
            settings.dms_timeout_seconds,
            audience=settings.dms_audience,
        ),
        storage=build_storage(settings),
        channels=build_channels(settings),
        checker=build_checker(settings),
        embedder=build_embedder(settings),
        llm=build_llm(settings),
    )
