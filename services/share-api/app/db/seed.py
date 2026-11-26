"""Usuarios internos ficticios para la demo (idempotente)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User
from app.domain.enums import Role

DEMO_USERS = [
    ("ana@demo-corp.example", "Ana Rojas", Role.SHARER),
    ("bruno@demo-corp.example", "Bruno Díaz", Role.SHARER),
    ("carla@demo-corp.example", "Carla Muñoz", Role.AUDITOR),
]


def seed_users(session: Session) -> None:
    existing = set(session.scalars(select(User.email)))
    for email, name, role in DEMO_USERS:
        if email not in existing:
            session.add(User(email=email, name=name, role=role.value))
    session.commit()
