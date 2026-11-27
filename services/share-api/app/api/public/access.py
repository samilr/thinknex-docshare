"""API pública del destinatario (visor de ThinkNex Docs). El token del enlace es la credencial
inicial; tras verificar (o abrir un enlace para cualquiera) se usa una sesión Bearer de 30 min."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Path, Response, UploadFile
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.adapters.document_source import UploadedFile
from app.api.deps import AccessServiceDep, ContextDep, SettingsDep
from app.core.errors import LinkUnavailableError, ValidationFailedError
from app.domain.enums import Audience, Permission
from app.schemas import OtpSentResponse, OtpVerifyRequest
from app.sensitivity.detectors import FindingSummary

router = APIRouter(prefix="/api/v1/access", tags=["destinatario (público)"])
_bearer = HTTPBearer(auto_error=False)
NO_STORE = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


class AccessInfoOut(BaseModel):
    shared_by: str
    audience: Audience
    permission: Permission
    requires_code: bool
    destination: str | None
    document_title: str | None
    expires_at: datetime


class AccessSessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    remaining_accesses: int


class DocumentViewOut(BaseModel):
    title: str
    mime_type: str
    kind: str
    version: int
    live: bool
    page_count: int
    permission: Permission
    can_download: bool
    can_edit: bool
    viewer_label: str
    watermark: bool


class VersionPublishedOut(BaseModel):
    version: int
    findings: list[FindingSummary]


def session_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    if credentials is None:
        raise LinkUnavailableError()
    return credentials.credentials


SessionDep = Annotated[str, Depends(session_token)]
TokenPath = Annotated[str, Path(min_length=10, max_length=200)]


@router.get("/{token}", response_model=AccessInfoOut)
def info(token: TokenPath, service: AccessServiceDep, ctx: ContextDep) -> AccessInfoOut:
    """Información previa al acceso. A personas específicas no se les revela el título."""
    return AccessInfoOut(**service.info(token, ctx).__dict__)


@router.post("/{token}/otp", response_model=OtpSentResponse)
def request_otp(token: TokenPath, service: AccessServiceDep, ctx: ContextDep) -> OtpSentResponse:
    issued = service.request_otp(token, ctx)
    return OtpSentResponse(sent_to=issued.sent_to, expires_in_seconds=issued.expires_in_seconds)


@router.post("/{token}/verify", response_model=AccessSessionOut)
def verify(
    token: TokenPath, body: OtpVerifyRequest, service: AccessServiceDep, ctx: ContextDep
) -> AccessSessionOut:
    return AccessSessionOut(**service.verify(token, body.code, ctx).__dict__)


@router.post("/{token}/open", response_model=AccessSessionOut)
def open_link(token: TokenPath, service: AccessServiceDep, ctx: ContextDep) -> AccessSessionOut:
    """Enlace para cualquier persona: inicia la sesión sin código."""
    return AccessSessionOut(**service.open(token, ctx).__dict__)


@router.get("/{token}/document", response_model=DocumentViewOut)
def document(
    token: TokenPath, session: SessionDep, service: AccessServiceDep, ctx: ContextDep
) -> DocumentViewOut:
    return DocumentViewOut(**service.document(token, session, ctx).__dict__)


@router.get("/{token}/pages/{number}", response_class=Response)
def page(
    token: TokenPath,
    number: Annotated[int, Path(ge=1, le=2000)],
    session: SessionDep,
    service: AccessServiceDep,
    ctx: ContextDep,
) -> Response:
    """Página renderizada como PNG con marca de agua (vista protegida)."""
    return Response(
        service.page(token, session, number, ctx), media_type="image/png", headers=NO_STORE
    )


@router.get("/{token}/text", response_class=PlainTextResponse)
def text(
    token: TokenPath, session: SessionDep, service: AccessServiceDep, ctx: ContextDep
) -> PlainTextResponse:
    return PlainTextResponse(service.text(token, session, ctx), headers=NO_STORE)


@router.get("/{token}/download", response_class=Response)
def download(
    token: TokenPath, session: SessionDep, service: AccessServiceDep, ctx: ContextDep
) -> Response:
    """Solo con permiso de descarga o edición. PDF con marca de agua."""
    payload = service.download(token, session, ctx)
    return Response(
        content=payload.content,
        media_type=payload.mime_type,
        headers={**NO_STORE, "Content-Disposition": f'attachment; filename="{payload.filename}"'},
    )


@router.post("/{token}/versions", response_model=VersionPublishedOut, status_code=201)
async def upload_version(
    token: TokenPath,
    session: SessionDep,
    service: AccessServiceDep,
    settings: SettingsDep,
    ctx: ContextDep,
    file: Annotated[UploadFile, File()],
    comment: Annotated[str, Form(max_length=500)] = "",
) -> VersionPublishedOut:
    """Solo con permiso de edición: publica una nueva versión del archivo vivo."""
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValidationFailedError(f"El archivo supera el máximo de {settings.max_upload_mb} MB")
    uploaded = UploadedFile(
        filename=file.filename or "archivo",
        content_type=file.content_type or "application/octet-stream",
        data=data,
    )
    result = service.upload_version(token, session, uploaded, comment, ctx)
    return VersionPublishedOut(version=result.version, findings=result.findings)
