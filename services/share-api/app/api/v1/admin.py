"""Administración de la plataforma (rol ADMIN): usuarios, bandeja simulada y retención."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select

from app.api.deps import AdminDep, ComponentsDep, ContextDep, DbDep, SettingsDep, UserServiceDep
from app.db.models import SimulatedMessage, User
from app.domain.enums import Role
from app.services import retention_service

router = APIRouter(prefix="/admin", tags=["admin"])


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    roles: list[str]
    is_active: bool
    must_change_password: bool
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class UserPageOut(BaseModel):
    items: list[UserOut]
    total: int
    limit: int
    offset: int


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    roles: list[Role] = Field(min_length=1)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    roles: list[Role] | None = Field(default=None, min_length=1)
    is_active: bool | None = None


class TemporaryPasswordOut(BaseModel):
    user: UserOut
    temporary_password: str = Field(description="Se muestra UNA sola vez; obliga a cambiarla")


class InboxMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    share_id: uuid.UUID | None
    channel: str
    kind: str
    to_address: str
    subject: str
    body: str
    delivered_real: bool


class InboxPageOut(BaseModel):
    items: list[InboxMessageOut]
    total: int


@router.get("/users", response_model=UserPageOut)
def list_users(
    _: AdminDep,
    service: UserServiceDep,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserPageOut:
    page = service.search(q=q, limit=limit, offset=offset)
    return UserPageOut(
        items=[UserOut.model_validate(u) for u in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.post("/users", response_model=TemporaryPasswordOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate, admin: AdminDep, service: UserServiceDep, ctx: ContextDep
) -> TemporaryPasswordOut:
    user, temporary = service.create(
        admin, email=str(body.email), name=body.name, roles=body.roles, ctx=ctx
    )
    return TemporaryPasswordOut(user=UserOut.model_validate(user), temporary_password=temporary)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID, body: UserUpdate, admin: AdminDep, service: UserServiceDep, ctx: ContextDep
) -> UserOut:
    user = service.update(
        admin, user_id, name=body.name, roles=body.roles, is_active=body.is_active, ctx=ctx
    )
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/reset-password", response_model=TemporaryPasswordOut)
def reset_password(
    user_id: uuid.UUID, admin: AdminDep, service: UserServiceDep, ctx: ContextDep, db: DbDep
) -> TemporaryPasswordOut:
    temporary = service.reset_password(admin, user_id, ctx)
    return TemporaryPasswordOut(
        user=UserOut.model_validate(db.get(User, user_id)), temporary_password=temporary
    )


@router.get("/inbox", response_model=InboxPageOut)
def inbox(
    _: AdminDep,
    db: DbDep,
    settings: SettingsDep,
    share_id: uuid.UUID | None = None,
    to: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> InboxPageOut:
    """Bandeja simulada (SOLO DEMO): mensajes con enlace/OTP tal como los recibe el destinatario."""
    if not settings.simulated_inbox_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bandeja simulada deshabilitada")
    stmt = select(SimulatedMessage)
    if share_id:
        stmt = stmt.where(SimulatedMessage.share_id == share_id)
    if to:
        stmt = stmt.where(SimulatedMessage.to_address.ilike(f"%{to}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(SimulatedMessage.created_at.desc()).limit(limit))
    return InboxPageOut(items=[InboxMessageOut.model_validate(r) for r in rows], total=total)


@router.post("/retention/run")
def run_retention(
    _: AdminDep, db: DbDep, components: ComponentsDep, settings: SettingsDep
) -> dict[str, int]:
    """Ejecuta la retención ahora (en producción corre como job programado)."""
    result = retention_service.run(
        db,
        components.storage,
        settings.snapshot_grace_hours,
        inbox_ttl_days=settings.simulated_inbox_ttl_days,
    )
    return result.__dict__
