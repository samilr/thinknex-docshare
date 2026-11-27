"""Usuarios iniciales (idempotente).

- ADMIN de arranque desde BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD (todos los ambientes).
- Usuarios demo ficticios solo con DEMO_USERS_ENABLED=true (ambientes de demostración).

Nunca sobrescribe la contraseña de un usuario que ya la tiene.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password
from app.db.models import User
from app.domain.enums import Role

DEMO_USERS = [
    ("ana@thinknex.example", "Ana Rojas", [Role.SHARER]),
    ("bruno@thinknex.example", "Bruno Díaz", [Role.SHARER]),
    ("carla@thinknex.example", "Carla Muñoz", [Role.AUDITOR]),
]


def _ensure(session: Session, email: str, name: str, roles: list[Role], password: str) -> None:
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        session.add(
            User(
                email=email,
                name=name,
                roles=[r.value for r in roles],
                password_hash=hash_password(password),
                password_changed_at=datetime.now(UTC),
            )
        )
    elif user.password_hash is None:
        user.password_hash = hash_password(password)
        user.password_changed_at = datetime.now(UTC)


def seed_users(session: Session, settings: Settings) -> None:
    if settings.bootstrap_admin_email and settings.bootstrap_admin_password:
        _ensure(
            session,
            settings.bootstrap_admin_email.lower(),
            settings.bootstrap_admin_name,
            [Role.ADMIN],
            settings.bootstrap_admin_password.get_secret_value(),
        )
    if settings.demo_users_enabled and settings.demo_users_password:
        for email, name, roles in DEMO_USERS:
            _ensure(session, email, name, roles, settings.demo_users_password.get_secret_value())
    session.commit()
