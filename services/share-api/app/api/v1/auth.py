"""Autenticación de usuarios internos.

El access token (JWT, 15 min) viaja en el body y el cliente lo guarda solo en memoria. El
refresh token (opaco, rotativo) viaja en una cookie httpOnly + Secure + SameSite=Strict limitada
a /api/v1/auth. El frontend se sirve en el mismo origen, así que no hace falta CORS.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import AuthServiceDep, ContextDep, SessionUserDep, SettingsDep
from app.core.config import Settings
from app.db.models import User
from app.services.auth_service import IssuedSession

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
REFRESH_PATH = "/api/v1/auth"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class MeOut(BaseModel):
    id: str
    email: str
    name: str
    roles: list[str]
    must_change_password: bool
    last_login_at: datetime | None


class SessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    user: MeOut


def me_out(user: User) -> MeOut:
    return MeOut(
        id=str(user.id),
        email=user.email,
        name=user.name,
        roles=list(user.roles),
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
    )


def _session_response(session: IssuedSession, response: Response, settings: Settings) -> SessionOut:
    response.set_cookie(
        REFRESH_COOKIE,
        session.refresh_token,
        max_age=settings.refresh_ttl_days * 86400,
        path=REFRESH_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return SessionOut(
        access_token=session.access_token, expires_in=session.expires_in, user=me_out(session.user)
    )


def require_fetch_header(
    x_requested_with: Annotated[str | None, Header()] = None,
) -> None:
    """Defensa CSRF adicional a SameSite: un formulario de otro sitio no puede fijar headers."""
    if x_requested_with != "fetch":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Falta el header X-Requested-With")


@router.post("/login", response_model=SessionOut)
def login(
    body: LoginRequest,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
    ctx: ContextDep,
) -> SessionOut:
    return _session_response(service.login(body.email, body.password, ctx), response, settings)


@router.post("/token", include_in_schema=True, summary="Login OAuth2 (para Swagger)")
def token(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: AuthServiceDep,
    ctx: ContextDep,
) -> dict[str, str | int]:
    session = service.login(form.username, form.password, ctx)
    return {
        "access_token": session.access_token,
        "token_type": "bearer",
        "expires_in": session.expires_in,
    }


@router.post("/refresh", response_model=SessionOut, dependencies=[Depends(require_fetch_header)])
def refresh(
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
    ctx: ContextDep,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> SessionOut:
    return _session_response(service.refresh(refresh_token, ctx), response, settings)


@router.post(
    "/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_fetch_header)]
)
def logout(
    response: Response,
    service: AuthServiceDep,
    ctx: ContextDep,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> Response:
    service.logout(refresh_token, ctx)
    response.status_code = status.HTTP_204_NO_CONTENT
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)
    return response


@router.get("/me", response_model=MeOut)
def me(user: SessionUserDep) -> MeOut:
    return me_out(user)


@router.post("/change-password", response_model=SessionOut)
def change_password(
    body: ChangePasswordRequest,
    user: SessionUserDep,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
    ctx: ContextDep,
) -> SessionOut:
    session = service.change_password(user, body.current_password, body.new_password, ctx)
    return _session_response(session, response, settings)
