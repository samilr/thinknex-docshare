"""Autenticación de usuarios internos: login, refresh rotativo, logout y cambio de contraseña.

- Contraseñas con argon2id; usuario inexistente igual ejecuta argon2 (sin oráculo de tiempo).
- Bloqueo temporal tras N intentos fallidos.
- Access token JWT de corta vida + refresh token opaco rotativo (solo su hash en BD). Si se
  presenta un refresh ya rotado, se asume robo y se revoca toda la familia (sesión).
- Todo queda en la auditoría.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import DomainError, ForbiddenError, NotFoundError, ValidationFailedError
from app.core.security import (
    create_user_token,
    generate_share_token,
    hash_password,
    hash_token,
    mask_email,
    password_needs_rehash,
    verify_password,
)
from app.db.models import RefreshToken, User
from app.domain.enums import ActorType, AuditEventType
from app.services import audit_service
from app.services.context import RequestContext


class AuthenticationError(DomainError):
    status_code = 401
    code = "invalid_credentials"
    title = "Credenciales inválidas"


class SessionExpiredError(DomainError):
    status_code = 401
    code = "session_expired"
    title = "La sesión expiró; vuelva a iniciar sesión"


@dataclass(frozen=True)
class IssuedSession:
    user: User
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_id: uuid.UUID
    impersonator: User | None = None


IMPERSONATION_MAX_HOURS = 8


def validate_password_policy(password: str, *, email: str, min_length: int) -> None:
    if len(password) < min_length:
        raise ValidationFailedError(f"La contraseña debe tener al menos {min_length} caracteres")
    if password.lower() in {email.lower(), email.split("@")[0].lower()}:
        raise ValidationFailedError("La contraseña no puede ser igual al usuario")
    if password.isdigit() or password.isalpha():
        raise ValidationFailedError("La contraseña debe combinar letras con números o símbolos")


@dataclass
class AuthService:
    db: Session
    settings: Settings

    # ------------------------------------------------------------------ helpers
    def _audit(
        self,
        event: AuditEventType,
        ctx: RequestContext,
        user: User | None = None,
        **details: object,
    ) -> None:
        audit_service.record(
            self.db,
            event_type=event,
            actor_type=ActorType.USER,
            actor_id=user.id if user else None,
            ctx=ctx,
            details=dict(details),
        )

    def _issue(
        self,
        user: User,
        ctx: RequestContext,
        family_id: uuid.UUID | None,
        impersonator: User | None = None,
        expires_at: datetime | None = None,
    ) -> IssuedSession:
        plain = generate_share_token()
        token = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=hash_token(plain),
            family_id=family_id or uuid.uuid4(),
            expires_at=expires_at
            or datetime.now(UTC) + timedelta(days=self.settings.refresh_ttl_days),
            impersonator_id=impersonator.id if impersonator else None,
            ip=ctx.ip,
            user_agent=(ctx.user_agent or "")[:512] or None,
        )
        self.db.add(token)
        self.db.flush()
        access = create_user_token(
            user.id,
            list(user.roles),
            self.settings.jwt_secret.get_secret_value(),
            self.settings.jwt_ttl_minutes,
            impersonator_id=impersonator.id if impersonator else None,
        )
        return IssuedSession(
            user, access, self.settings.jwt_ttl_minutes * 60, plain, token.id, impersonator
        )

    def _current_token(self, refresh_token: str | None) -> RefreshToken | None:
        if not refresh_token:
            return None
        return self.db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token))
        )

    def _revoke_family(self, family_id: uuid.UUID) -> None:
        self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )

    def revoke_all_sessions(self, user: User) -> None:
        self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )

    # ------------------------------------------------------------------ casos de uso
    def login(self, email: str, password: str, ctx: RequestContext) -> IssuedSession:
        now = datetime.now(UTC)
        user = self.db.scalar(select(User).where(User.email == email.strip().lower()))

        if user is None or not user.is_active or user.password_hash is None:
            verify_password(password, None)  # mismo costo que un usuario real
            reason = "UNKNOWN_USER" if user is None else "INACTIVE"
            self._audit(
                AuditEventType.USER_LOGIN_FAILED, ctx, user, reason=reason, email=mask_email(email)
            )
            self.db.commit()
            raise AuthenticationError("Usuario o contraseña inválidos")

        if user.locked_until and user.locked_until > now:
            verify_password(password, None)
            self._audit(AuditEventType.USER_LOGIN_FAILED, ctx, user, reason="LOCKED")
            self.db.commit()
            raise AuthenticationError("Usuario o contraseña inválidos")

        if not verify_password(password, user.password_hash):
            user.failed_login_attempts += 1
            self._audit(
                AuditEventType.USER_LOGIN_FAILED,
                ctx,
                user,
                reason="WRONG_PASSWORD",
                attempts=user.failed_login_attempts,
            )
            if user.failed_login_attempts >= self.settings.login_max_attempts:
                user.locked_until = now + timedelta(minutes=self.settings.login_lockout_minutes)
                user.failed_login_attempts = 0
                self._audit(
                    AuditEventType.USER_LOCKED,
                    ctx,
                    user,
                    minutes=self.settings.login_lockout_minutes,
                )
            self.db.commit()
            raise AuthenticationError("Usuario o contraseña inválidos")

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        session = self._issue(user, ctx, family_id=None)
        self._audit(AuditEventType.USER_LOGIN, ctx, user)
        return session

    def refresh(self, refresh_token: str | None, ctx: RequestContext) -> IssuedSession:
        if not refresh_token:
            raise SessionExpiredError()
        now = datetime.now(UTC)
        token = self.db.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(refresh_token))
            .with_for_update()
        )
        if token is None:
            raise SessionExpiredError()
        user = self.db.get(User, token.user_id)
        if token.revoked_at is not None or token.replaced_by is not None:
            if token.replaced_by is not None:  # token ya rotado presentado de nuevo: posible robo
                self._revoke_family(token.family_id)
                self._audit(
                    AuditEventType.TOKEN_REUSE_DETECTED, ctx, user, family=str(token.family_id)
                )
                self.db.commit()
            raise SessionExpiredError()
        if token.expires_at <= now or user is None or not user.is_active:
            raise SessionExpiredError()
        impersonator = self.db.get(User, token.impersonator_id) if token.impersonator_id else None
        if token.impersonator_id and (
            impersonator is None or not impersonator.is_active or "ADMIN" not in impersonator.roles
        ):
            self._revoke_family(token.family_id)
            raise SessionExpiredError()

        session = self._issue(
            user,
            ctx,
            family_id=token.family_id,
            impersonator=impersonator,
            expires_at=token.expires_at if impersonator else None,
        )
        token.revoked_at = now
        token.replaced_by = session.refresh_id
        return session

    def logout(self, refresh_token: str | None, ctx: RequestContext) -> None:
        if not refresh_token:
            return
        token = self.db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token))
        )
        if token is None:
            return
        self._revoke_family(token.family_id)
        self._audit(AuditEventType.USER_LOGOUT, ctx, self.db.get(User, token.user_id))

    def impersonate(
        self, admin: User, target_id: uuid.UUID, refresh_token: str | None, ctx: RequestContext
    ) -> IssuedSession:
        """El ADMIN pasa a actuar como otro usuario. Su sesión actual se cierra y la nueva sesión
        recuerda quién está detrás; todo lo que haga queda auditado con ``impersonated_by``."""
        target = self.db.get(User, target_id)
        if target is None or not target.is_active:
            raise NotFoundError("Usuario no encontrado o inactivo")
        if target.id == admin.id:
            raise ValidationFailedError("Ya estás usando tu propia cuenta")
        if "ADMIN" in target.roles:
            raise ForbiddenError("No es posible actuar como otro administrador")
        current = self._current_token(refresh_token)
        if current is not None and current.user_id == admin.id:
            self._revoke_family(current.family_id)
        session = self._issue(
            target,
            ctx,
            family_id=None,
            impersonator=admin,
            expires_at=datetime.now(UTC) + timedelta(hours=IMPERSONATION_MAX_HOURS),
        )
        self._audit(
            AuditEventType.IMPERSONATION_STARTED,
            ctx,
            admin,
            target_id=str(target.id),
            target_email=target.email,
        )
        return session

    def stop_impersonation(self, refresh_token: str | None, ctx: RequestContext) -> IssuedSession:
        """Vuelve a la cuenta del ADMIN: cierra la sesión suplantada y abre una propia."""
        token = self._current_token(refresh_token)
        if token is None or token.impersonator_id is None or token.revoked_at is not None:
            raise SessionExpiredError()
        admin = self.db.get(User, token.impersonator_id)
        target = self.db.get(User, token.user_id)
        self._revoke_family(token.family_id)
        if admin is None or not admin.is_active or "ADMIN" not in admin.roles:
            raise SessionExpiredError()
        self._audit(
            AuditEventType.IMPERSONATION_ENDED,
            ctx,
            admin,
            target_id=str(token.user_id),
            target_email=target.email if target else None,
        )
        return self._issue(admin, ctx, family_id=None)

    def change_password(
        self, user: User, current: str, new: str, ctx: RequestContext
    ) -> IssuedSession:
        if not verify_password(current, user.password_hash):
            raise AuthenticationError("La contraseña actual no es correcta")
        if current == new:
            raise ValidationFailedError("La nueva contraseña debe ser distinta de la actual")
        validate_password_policy(
            new, email=user.email, min_length=self.settings.password_min_length
        )
        user.password_hash = hash_password(new)
        user.password_changed_at = datetime.now(UTC)
        user.must_change_password = False
        self.revoke_all_sessions(user)  # cierra sesiones en otros dispositivos
        self._audit(AuditEventType.PASSWORD_CHANGED, ctx, user)
        return self._issue(user, ctx, family_id=None)
