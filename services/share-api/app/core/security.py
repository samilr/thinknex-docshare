"""Primitivas criptográficas: JWT, tokens de enlace, OTP y enmascarado de datos de contacto."""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

ALGORITHM = "HS256"
USER_TOKEN = "user"  # noqa: S105 - tipo de token, no un secreto
DOWNLOAD_TOKEN = "download"  # noqa: S105


class InvalidTokenError(Exception):
    pass


# --------------------------------------------------------------------------- contraseñas
_hasher = PasswordHasher()  # argon2id con parámetros recomendados por la librería (RFC 9106)
_DUMMY_HASH = _hasher.hash("contraseña-ficticia-para-igualar-tiempos")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Compara en tiempo ~constante; sin hash (usuario inexistente) igual ejecuta argon2."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def generate_temporary_password() -> str:
    return secrets.token_urlsafe(12)


def _encode(claims: dict[str, Any], secret: str, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {**claims, "iat": now, "exp": now + ttl, "jti": uuid.uuid4().hex}
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def _decode(token: str, secret: str, expected_type: str) -> dict[str, Any]:
    try:
        claims: dict[str, Any] = jwt.decode(
            token, secret, algorithms=[ALGORITHM], options={"require": ["exp", "sub", "typ"]}
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if claims.get("typ") != expected_type:
        raise InvalidTokenError("tipo de token inesperado")
    return claims


def create_user_token(user_id: uuid.UUID, roles: list[str], secret: str, ttl_minutes: int) -> str:
    """Access token de corta vida. Los roles viajan como información para el cliente; la API
    siempre vuelve a leer usuario y roles desde la BD (una desactivación aplica de inmediato)."""
    return _encode(
        {"sub": str(user_id), "roles": roles, "typ": USER_TOKEN},
        secret,
        timedelta(minutes=ttl_minutes),
    )


def decode_user_token(token: str, secret: str) -> dict[str, Any]:
    return _decode(token, secret, USER_TOKEN)


def create_download_token(share_id: uuid.UUID, secret: str, ttl_minutes: int) -> str:
    return _encode(
        {"sub": str(share_id), "typ": DOWNLOAD_TOKEN}, secret, timedelta(minutes=ttl_minutes)
    )


def decode_download_token(token: str, secret: str) -> dict[str, Any]:
    return _decode(token, secret, DOWNLOAD_TOKEN)


def generate_share_token() -> str:
    """Token de enlace de 256 bits. Solo se entrega al destinatario; en BD se guarda su hash."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_otp() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def otp_mac(code: str, share_id: uuid.UUID, secret: str) -> str:
    """HMAC del OTP ligado al share: un volcado de la BD no permite reutilizar códigos."""
    return hmac.new(secret.encode(), f"{share_id}:{code}".encode(), hashlib.sha256).hexdigest()


def verify_otp(code: str, share_id: uuid.UUID, secret: str, expected_mac: str) -> bool:
    return hmac.compare_digest(otp_mac(code, share_id, secret), expected_mac)


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def mask_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    return f"***{digits[-4:]}" if len(digits) >= 4 else "***"
