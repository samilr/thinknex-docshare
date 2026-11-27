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
from app.services.auth_service import AuthService
from app.services.context import RequestContext
from app.services.library_service import LibraryService
from app.services.policy_service import PolicyService
from app.services.share_service import ShareService
from app.services.user_service import UserService

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


# scope="function": el commit ocurre antes de enviar la respuesta. Con el scope por defecto
# FastAPI cierra la dependencia DESPUÉS de responder, así que un cliente podía leer antes del commit
# (o recibir 2xx aunque el commit fallara).
DbDep = Annotated[Session, Depends(get_db, scope="function")]


def get_request_context(request: Request) -> RequestContext:
    return RequestContext(
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )


ContextDep = Annotated[RequestContext, Depends(get_request_context)]


def get_session_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: DbDep, settings: SettingsDep
) -> User:
    """Usuario autenticado y activo. Usuario y roles se leen SIEMPRE desde la BD."""
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
    if user is None or not user.is_active:
        raise unauthorized
    return user


SessionUserDep = Annotated[User, Depends(get_session_user)]


def get_current_user(user: SessionUserDep) -> User:
    """Como ``get_session_user`` pero exige haber cambiado la contraseña temporal."""
    if user.must_change_password:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Debe cambiar su contraseña antes de continuar",
            headers={"X-Error-Code": "password_change_required"},
        )
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[[User], User]:
    """Autoriza si el usuario tiene al menos uno de los roles indicados."""

    def _check(user: CurrentUserDep) -> User:
        if not user.has_any(*(r.value for r in roles)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Rol insuficiente")
        return user

    return _check


SharerDep = Annotated[User, Depends(require_roles(Role.SHARER))]
AuditorDep = Annotated[User, Depends(require_roles(Role.AUDITOR))]
AdminDep = Annotated[User, Depends(require_roles(Role.ADMIN))]
OversightDep = Annotated[User, Depends(require_roles(Role.ADMIN, Role.AUDITOR))]
AnyRoleDep = Annotated[User, Depends(require_roles(Role.ADMIN, Role.SHARER, Role.AUDITOR))]
RevokerDep = Annotated[User, Depends(require_roles(Role.SHARER, Role.ADMIN))]
SharingDep = Annotated[User, Depends(require_roles(Role.SHARER, Role.ADMIN))]
# Biblioteca: quienes comparten y el ADMIN (que administra archivos aunque no comparta).
LibraryUserDep = Annotated[User, Depends(require_roles(Role.SHARER, Role.ADMIN))]


def get_auth_service(db: DbDep, settings: SettingsDep) -> AuthService:
    return AuthService(db, settings)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_user_service(db: DbDep, auth: AuthServiceDep) -> UserService:
    return UserService(db, auth)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def get_share_service(db: DbDep, settings: SettingsDep, c: ComponentsDep) -> ShareService:
    return ShareService(db, settings, c.source, c.storage, c.channels, c.checker)


def get_access_service(db: DbDep, settings: SettingsDep, c: ComponentsDep) -> AccessService:
    return AccessService(db, settings, c.storage, c.channels, c.source)


def get_library_service(db: DbDep, settings: SettingsDep, c: ComponentsDep) -> LibraryService:
    return LibraryService(db, settings, c.source)


def get_policy_service(db: DbDep) -> PolicyService:
    return PolicyService(db)


ShareServiceDep = Annotated[ShareService, Depends(get_share_service)]
PolicyServiceDep = Annotated[PolicyService, Depends(get_policy_service)]
LibraryServiceDep = Annotated[LibraryService, Depends(get_library_service)]
AccessServiceDep = Annotated[AccessService, Depends(get_access_service)]
