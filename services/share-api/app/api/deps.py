import uuid
from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.container import Components
from app.core.config import Settings
from app.core.security import InvalidTokenError, decode_user_token
from app.db.models import User
from app.db.session import session_scope
from app.domain.enums import Role
from app.services.access_service import AccessService
from app.services.context import RequestContext
from app.services.share_service import ShareService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_components(request: Request) -> Components:
    components: Components = request.app.state.components
    return components


SettingsDep = Annotated[Settings, Depends(get_settings)]
ComponentsDep = Annotated[Components, Depends(get_components)]


def get_db(components: ComponentsDep) -> Iterator[Session]:
    yield from session_scope(components.session_factory)


DbDep = Annotated[Session, Depends(get_db)]


def get_request_context(request: Request) -> RequestContext:
    return RequestContext(
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )


ContextDep = Annotated[RequestContext, Depends(get_request_context)]


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: DbDep, settings: SettingsDep
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o vencidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = decode_user_token(token, settings.jwt_secret.get_secret_value())
        user = db.get(User, uuid.UUID(claims["sub"]))
    except (InvalidTokenError, ValueError):
        raise unauthorized from None
    if user is None:
        raise unauthorized
    return user


def require_role(*roles: Role) -> Callable[[User], User]:
    def _check(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in {r.value for r in roles}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Rol insuficiente")
        return user

    return _check


SharerDep = Annotated[User, Depends(require_role(Role.SHARER))]
AuditorDep = Annotated[User, Depends(require_role(Role.AUDITOR))]


def get_share_service(db: DbDep, settings: SettingsDep, c: ComponentsDep) -> ShareService:
    return ShareService(db, settings, c.source, c.storage, c.channels, c.checker)


def get_access_service(db: DbDep, settings: SettingsDep, c: ComponentsDep) -> AccessService:
    return AccessService(db, settings, c.storage, c.channels)


ShareServiceDep = Annotated[ShareService, Depends(get_share_service)]
AccessServiceDep = Annotated[AccessService, Depends(get_access_service)]
