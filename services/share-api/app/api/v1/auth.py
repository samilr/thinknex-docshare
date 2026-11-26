import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import DbDep, SettingsDep
from app.core.security import create_user_token
from app.db.models import User
from app.schemas import TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbDep, settings: SettingsDep
) -> TokenResponse:
    """Login de DESARROLLO (usuarios ficticios + contraseña compartida desde el entorno).

    En producción esto se reemplaza por el IdP corporativo (OIDC/SAML); el resto de la API solo
    depende de recibir un JWT con ``sub`` y ``role``.
    """
    expected = settings.dev_login_password
    if settings.env == "prod" or expected is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Login de desarrollo deshabilitado")
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    password_ok = secrets.compare_digest(form.password, expected.get_secret_value())
    if user is None or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña inválidos")
    token = create_user_token(
        user.id, user.role, settings.jwt_secret.get_secret_value(), settings.jwt_ttl_minutes
    )
    return TokenResponse(access_token=token, expires_in=settings.jwt_ttl_minutes * 60)
