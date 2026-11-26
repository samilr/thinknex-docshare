import uuid
from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.adapters.document_source import SourceDocument
from app.domain.enums import Channel, Classification, Decision, ShareStatus
from app.sensitivity.checker import SensitivityReport


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class RecipientIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, pattern=r"^\+?[0-9 ]{8,16}$")

    @model_validator(mode="after")
    def _has_contact(self) -> Self:
        if not self.email and not self.phone:
            raise ValueError("Se requiere email o teléfono del destinatario")
        return self


class ShareRequest(BaseModel):
    document_id: str = Field(min_length=1, max_length=100, examples=["doc-003"])
    recipient: RecipientIn
    channel: Channel
    reason: str = Field(min_length=3, max_length=500, examples=["Envío de informe al auditor"])
    expires_in_hours: int | None = Field(default=None, ge=1)
    max_accesses: int | None = Field(default=None, ge=1)
    acknowledge_sensitive: bool = False

    @model_validator(mode="after")
    def _contact_matches_channel(self) -> Self:
        if self.channel is Channel.EMAIL and not self.recipient.email:
            raise ValueError("El canal EMAIL requiere recipient.email")
        if self.channel in (Channel.WHATSAPP, Channel.SMS) and not self.recipient.phone:
            raise ValueError(f"El canal {self.channel.value} requiere recipient.phone")
        return self


class PrecheckRequest(BaseModel):
    document_id: str
    recipient: RecipientIn


class PrecheckResponse(BaseModel):
    document: SourceDocument
    report: SensitivityReport


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: str
    source_version: int
    title: str
    sha256: str
    classification: Classification


class RecipientOut(BaseModel):
    name: str
    contact: str
    is_external: bool


class ShareOut(BaseModel):
    id: uuid.UUID
    document: DocumentOut
    recipient: RecipientOut
    shared_by: str
    channel: Channel
    reason: str
    status: ShareStatus
    created_at: datetime
    expires_at: datetime
    max_accesses: int
    access_count: int
    sensitivity_decision: Decision
    sensitivity_report: dict[str, Any]
    notification_status: str | None = None
    revoked_at: datetime | None = None


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    event_type: str
    actor_type: str
    actor_id: str | None
    actor: str | None = None
    share_id: uuid.UUID | None
    document_id: uuid.UUID | None
    channel: str | None
    ip: str | None
    user_agent: str | None
    details: dict[str, Any] = Field(serialization_alias="metadata")
    hash: str


class AuditPage(BaseModel):
    items: list[AuditEventOut]
    total: int
    limit: int
    offset: int


class ChainVerificationOut(BaseModel):
    valid: bool
    events_checked: int
    first_broken_event_id: int | None
    last_hash: str


class OtpVerifyRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class OtpSentResponse(BaseModel):
    sent_to: str
    expires_in_seconds: int


class DownloadTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    remaining_accesses: int
