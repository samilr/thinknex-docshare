"""Administración de la política de compartición (reglas en BD) con bitácora en la auditoría.

Cada alta, cambio o baja queda como evento encadenado (POLICY_CREATED / POLICY_UPDATED /
POLICY_DELETED) con quién lo hizo y el estado anterior y posterior de la regla, de modo que
siempre se puede reconstruir qué política estaba vigente cuando se evaluó un envío.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.db.models import PolicyRuleRow, User
from app.domain.enums import ActorType, AuditEventType, Channel, Classification, Decision
from app.sensitivity.policy import PolicyRule, RecipientScope
from app.services import audit_service
from app.services.context import RequestContext

FindingType = Literal["RUT", "EMAIL", "PHONE", "CARD", "BANK_ACCOUNT"]


class PolicyRuleIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    description: str = Field(default="", max_length=500)
    action: Literal["WARN", "BLOCK"]
    message: str = Field(
        min_length=3, max_length=300, description="Motivo que verá quien intenta compartir"
    )
    classifications: list[Classification] = Field(
        default_factory=list, description="Vacío = cualquier clasificación"
    )
    recipient: RecipientScope = RecipientScope.ANY
    finding_types: list[FindingType] = Field(
        default_factory=list, description="Aplica si el documento contiene al menos uno"
    )
    channels: list[Channel] = Field(default_factory=list, description="Vacío = cualquier canal")
    enabled: bool = True

    @field_validator("name", "message", "description")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class PolicyRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    action: Literal["WARN", "BLOCK"]
    message: str
    classifications: list[Classification]
    recipient: RecipientScope
    finding_types: list[FindingType]
    channels: list[Channel]
    enabled: bool
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


_FIELDS = (
    "name",
    "description",
    "action",
    "message",
    "classifications",
    "recipient",
    "finding_types",
    "channels",
    "enabled",
)


def _snapshot(row: PolicyRuleRow) -> dict[str, Any]:
    return {f: getattr(row, f) for f in _FIELDS}


def _values(data: PolicyRuleIn) -> dict[str, Any]:
    raw = data.model_dump(mode="json")
    # Orden estable para que el "antes/después" de la auditoría no muestre cambios ficticios.
    for key in ("classifications", "finding_types", "channels"):
        raw[key] = sorted(set(raw[key]))
    return raw


def active_rules(db: Session) -> list[PolicyRule]:
    rows = db.scalars(
        select(PolicyRuleRow).where(PolicyRuleRow.enabled.is_(True)).order_by(PolicyRuleRow.name)
    )
    return [
        PolicyRule(
            name=r.name,
            action=Decision(r.action),
            message=r.message,
            classifications=frozenset(r.classifications),
            recipient=RecipientScope(r.recipient),
            finding_types=frozenset(r.finding_types),
            channels=frozenset(r.channels),
        )
        for r in rows
    ]


@dataclass
class PolicyService:
    db: Session

    def _audit(
        self, event: AuditEventType, user: User, ctx: RequestContext, **details: Any
    ) -> None:
        audit_service.record(
            self.db,
            event_type=event,
            actor_type=ActorType.USER,
            actor_id=user.id,
            ctx=ctx,
            details=details,
        )

    def _get(self, rule_id: uuid.UUID) -> PolicyRuleRow:
        row = self.db.get(PolicyRuleRow, rule_id)
        if row is None:
            raise NotFoundError("Regla no encontrada")
        return row

    def _ensure_unique(self, name: str, exclude: uuid.UUID | None = None) -> None:
        stmt = select(PolicyRuleRow.id).where(PolicyRuleRow.name.ilike(name))
        if exclude is not None:
            stmt = stmt.where(PolicyRuleRow.id != exclude)
        if self.db.scalar(stmt) is not None:
            raise ConflictError("Ya existe una regla con ese nombre")

    def list(self) -> list[PolicyRuleRow]:
        return list(
            self.db.scalars(
                select(PolicyRuleRow).order_by(PolicyRuleRow.enabled.desc(), PolicyRuleRow.name)
            )
        )

    def create(self, user: User, data: PolicyRuleIn, ctx: RequestContext) -> PolicyRuleRow:
        values = _values(data)
        self._ensure_unique(values["name"])
        row = PolicyRuleRow(**values, created_by=user.email, updated_by=user.email)
        self.db.add(row)
        self.db.flush()
        self._audit(
            AuditEventType.POLICY_CREATED, user, ctx, policy_id=str(row.id), after=_snapshot(row)
        )
        return row

    def update(
        self, user: User, rule_id: uuid.UUID, data: PolicyRuleIn, ctx: RequestContext
    ) -> PolicyRuleRow:
        row = self._get(rule_id)
        values = _values(data)
        self._ensure_unique(values["name"], exclude=row.id)
        before = _snapshot(row)
        changed = [f for f in _FIELDS if before[f] != values[f]]
        if not changed:
            return row
        for field_name in changed:
            setattr(row, field_name, values[field_name])
        row.updated_by = user.email
        self.db.flush()
        self._audit(
            AuditEventType.POLICY_UPDATED,
            user,
            ctx,
            policy_id=str(row.id),
            name=row.name,
            changed=changed,
            before={f: before[f] for f in changed},
            after={f: values[f] for f in changed},
        )
        return row

    def delete(self, user: User, rule_id: uuid.UUID, ctx: RequestContext) -> None:
        row = self._get(rule_id)
        before = _snapshot(row)
        self.db.delete(row)
        self.db.flush()
        self._audit(
            AuditEventType.POLICY_DELETED,
            user,
            ctx,
            policy_id=str(rule_id),
            name=before["name"],
            before=before,
        )
