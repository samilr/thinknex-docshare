"""Endpoints públicos del destinatario. El token del enlace es la credencial inicial."""

import html
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import AccessServiceDep, ContextDep
from app.core.errors import LinkUnavailableError
from app.schemas import DownloadTokenResponse, OtpSentResponse, OtpVerifyRequest

router = APIRouter(prefix="/s", tags=["destinatario (público)"])
_bearer = HTTPBearer(auto_error=False)
_PAGE = (Path(__file__).parent / "access_page.html").read_text(encoding="utf-8")
_UNAVAILABLE = (
    "<!doctype html><html lang=es><meta charset=utf-8><title>Enlace no disponible</title>"
    "<body style='font-family:system-ui;max-width:30rem;margin:3rem auto'>"
    "<h1>Enlace no disponible</h1><p>El enlace no es válido, venció o fue revocado. "
    "Solicita a quien te lo envió que lo comparta nuevamente.</p></body></html>"
)


def _csp(nonce: str) -> str:
    return (
        f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
        "connect-src 'self'; img-src 'self' blob:; base-uri 'none'; form-action 'none'; "
        "frame-ancestors 'none'"
    )


@router.get("/{token}", response_class=HTMLResponse, include_in_schema=True)
def landing(token: str, service: AccessServiceDep, ctx: ContextDep) -> HTMLResponse:
    """Página mínima del destinatario. GET no consume accesos (seguro ante previsualizadores)."""
    try:
        info = service.open_link(token, ctx)
    except LinkUnavailableError:
        return HTMLResponse(_UNAVAILABLE, status_code=404)
    nonce = secrets.token_urlsafe(16)
    page = _PAGE
    for key, value in {
        "{nonce}": nonce,
        "{shared_by}": html.escape(info.shared_by),
        "{destination}": html.escape(info.otp_destination),
        "{channel}": html.escape(info.channel),
        "{expires_at}": f"{info.expires_at:%Y-%m-%d %H:%M}",
    }.items():
        page = page.replace(key, value)
    return HTMLResponse(page, headers={"Content-Security-Policy": _csp(nonce)})


@router.post("/{token}/otp", response_model=OtpSentResponse)
def request_otp(token: str, service: AccessServiceDep, ctx: ContextDep) -> OtpSentResponse:
    issued = service.request_otp(token, ctx)
    return OtpSentResponse(sent_to=issued.sent_to, expires_in_seconds=issued.expires_in_seconds)


@router.post("/{token}/verify", response_model=DownloadTokenResponse)
def verify_otp(
    token: str, body: OtpVerifyRequest, service: AccessServiceDep, ctx: ContextDep
) -> DownloadTokenResponse:
    grant = service.verify(token, body.code, ctx)
    return DownloadTokenResponse(
        access_token=grant.access_token,
        expires_in=grant.expires_in,
        remaining_accesses=grant.remaining_accesses,
    )


@router.get("/{token}/download", response_class=Response)
def download(
    token: str,
    service: AccessServiceDep,
    ctx: ContextDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Response:
    """Entrega el documento con marca de agua. Requiere el token obtenido al verificar el OTP."""
    payload = service.download(token, credentials.credentials if credentials else "", ctx)
    return Response(
        content=payload.content,
        media_type=payload.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{payload.filename}"'},
    )
