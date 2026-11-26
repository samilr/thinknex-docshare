"""Administración de usuarios (rol ADMIN)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import any_, func, literal, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.security import generate_temporary_password, hash_password
from app.db.models import User
from app.domain.enums import ActorType, AuditEventType, Role
from app.services import audit_service
from app.services.auth_service import AuthService
from app.services.context import RequestContext


@dataclass(frozen=True)
class UserPage:
    items: list[User]
    total: int


@dataclass
class UserService:
    db: Session
    auth: AuthService

    def _audit(
        self,
        event: AuditEventType,
        admin: User,
        target: User,
        ctx: RequestContext,
        **details: object,
    ) -> None:
        audit_service.record(
            self.db,
            event_type=event,
            actor_type=ActorType.USER,
            actor_id=admin.id,
            ctx=ctx,
            details={"target_user_id": str(target.id), "target_email": target.email, **details},
        )

    def _get(self, user_id: uuid.UUID) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise NotFoundError("Usuario no encontrado")
        return user

    def _active_admins_excluding(self, user_id: uuid.UUID) -> int:
        return (
            self.db.scalar(
                select(func.count(User.id)).where(
                    User.is_active.is_(True),
                    literal(Role.ADMIN.value) == any_(User.roles),
                    User.id != user_id,
                )
            )
            or 0
        )

    def search(self, *, q: str | None, limit: int, offset: int) -> UserPage:
        stmt = select(User)
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(func.lower(User.email).like(like), func.lower(User.name).like(like))
            )
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = list(self.db.scalars(stmt.order_by(User.email).limit(limit).offset(offset)))
        return UserPage(items, total)

    def create(
        self, admin: User, *, email: str, name: str, roles: list[Role], ctx: RequestContext
    ) -> tuple[User, str]:
        email = email.strip().lower()
        if self.db.scalar(select(User.id).where(User.email == email)):
            raise ConflictError("Ya existe un usuario con ese email")
        temporary = generate_temporary_password()
        user = User(
            email=email,
            name=name.strip(),
            roles=sorted({r.value for r in roles}),
            password_hash=hash_password(temporary),
            must_change_password=True,
            password_changed_at=datetime.now(UTC),
        )
        self.db.add(user)
        self.db.flush()
        self._audit(AuditEventType.USER_CREATED, admin, user, ctx, roles=user.roles)
        return user, temporary

    def update(
        self,
        admin: User,
        user_id: uuid.UUID,
        *,
        name: str | None,
        roles: list[Role] | None,
        is_active: bool | None,
        ctx: RequestContext,
    ) -> User:
        user = self._get(user_id)
        changes: dict[str, object] = {}
        if roles is not None:
            new_roles = sorted({r.value for r in roles})
            if not new_roles:
                raise ValidationFailedError("El usuario debe tener al menos un rol")
            losing_admin = Role.ADMIN.value in user.roles and Role.ADMIN.value not in new_roles
            if losing_admin and user.id == admin.id:
                raise ConflictError("No puede quitarse a sí mismo el rol ADMIN")
            if losing_admin and self._active_admins_excluding(user.id) == 0:
                raise ConflictError("Debe quedar al menos un ADMIN activo")
            if new_roles != sorted(user.roles):
                changes["roles"] = {"from": sorted(user.roles), "to": new_roles}
                user.roles = new_roles
        if name is not None and name.strip() != user.name:
            changes["name"] = {"from": user.name, "to": name.strip()}
            user.name = name.strip()
        if is_active is not None and is_active != user.is_active:
            if not is_active and user.id == admin.id:
                raise ConflictError("No puede desactivarse a sí mismo")
            if (
                not is_active
                and Role.ADMIN.value in user.roles
                and self._active_admins_excluding(user.id) == 0
            ):
                raise ConflictError("Debe quedar al menos un ADMIN activo")
            user.is_active = is_active
            if not is_active:
                self.auth.revoke_all_sessions(user)
            self._audit(
                AuditEventType.USER_ENABLED if is_active else AuditEventType.USER_DISABLED,
                admin,
                user,
                ctx,
            )
        if changes:
            self._audit(AuditEventType.USER_UPDATED, admin, user, ctx, changes=changes)
        self.db.flush()
        return user

    def reset_password(self, admin: User, user_id: uuid.UUID, ctx: RequestContext) -> str:
        user = self._get(user_id)
        temporary = generate_temporary_password()
        user.password_hash = hash_password(temporary)
        user.must_change_password = True
        user.failed_login_attempts = 0
        user.locked_until = None
        user.password_changed_at = datetime.now(UTC)
        self.auth.revoke_all_sessions(user)
        self._audit(AuditEventType.PASSWORD_RESET, admin, user, ctx)
        return temporary
