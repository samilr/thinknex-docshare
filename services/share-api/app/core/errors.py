"""Errores de dominio y su traducción a respuestas RFC 7807 (application/problem+json)."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

PROBLEM_JSON = "application/problem+json"


class DomainError(Exception):
    status_code = 400
    code = "bad_request"
    title = "Solicitud inválida"

    def __init__(self, detail: str | None = None, **extensions: Any) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        self.extensions = extensions


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"
    title = "Recurso no encontrado"


class ForbiddenError(DomainError):
    status_code = 403
    code = "forbidden"
    title = "Operación no permitida"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"
    title = "Conflicto con el estado actual"


class NameConflictError(ConflictError):
    code = "name_conflict"
    title = "Ya existe un archivo con ese nombre en esta ubicación"


class ValidationFailedError(DomainError):
    status_code = 422
    code = "validation_failed"
    title = "Datos inválidos"


class SharingBlockedError(ForbiddenError):
    code = "sharing_blocked"
    title = "La política de seguridad impide compartir este documento"


class SensitiveContentError(ConflictError):
    code = "sensitive_content_requires_ack"
    title = "El documento contiene información sensible y requiere confirmación"


class LinkUnavailableError(DomainError):
    """Respuesta uniforme para enlaces inválidos, vencidos, revocados o agotados.

    No distingue la causa hacia afuera (evita enumeración); la causa real queda en la auditoría.
    """

    status_code = 404
    code = "link_unavailable"
    title = "El enlace no es válido o ya no está disponible"


class InvalidOtpError(DomainError):
    status_code = 401
    code = "invalid_otp"
    title = "Código inválido o vencido"


class TooManyRequestsError(DomainError):
    status_code = 429
    code = "too_many_requests"
    title = "Demasiadas solicitudes"


class UpstreamError(DomainError):
    status_code = 502
    code = "upstream_error"
    title = "Error al comunicarse con el sistema documental"


def problem(
    status: int, code: str, title: str, detail: str, request: Request, **ext: Any
) -> JSONResponse:
    body = {
        "type": f"https://errors.thinknex.example/{code}",
        "code": code,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path if not request.url.path.startswith("/s/") else "/s/***",
        "request_id": getattr(request.state, "request_id", None),
        **ext,
    }
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        return problem(exc.status_code, exc.code, exc.title, exc.detail, request, **exc.extensions)
