"""Indicadores para el dashboard. ADMIN/AUDITOR ven todo; SHARER solo lo propio."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Document, Share, User
from app.domain.enums import AuditEventType, ShareStatus


class DailyCount(BaseModel):
    day: date
    count: int


class TopDocument(BaseModel):
    source_id: str
    title: str
    shares: int


class Stats(BaseModel):
    scope: str
    shares_total: int
    shares_by_status: dict[str, int]
    shares_by_channel: dict[str, int]
    accesses_by_day: list[DailyCount]
    blocked_attempts_30d: int
    denied_accesses_30d: int
    sensitive_acknowledged: int
    top_documents: list[TopDocument]
    users_active: int | None = None


def compute(db: Session, *, owner_id: uuid.UUID | None, days: int = 7) -> Stats:
    def own(stmt: Any) -> Any:  # Select con columnas variables
        return stmt.where(Share.shared_by == owner_id) if owner_id else stmt

    def event_filter(event_type: AuditEventType, since: datetime) -> list[ColumnElement[bool]]:
        conditions = [AuditEvent.event_type == event_type.value, AuditEvent.occurred_at >= since]
        if owner_id:
            conditions.append(AuditEvent.share_id.in_(own(select(Share.id))))
        return conditions

    # Estado efectivo: un ACTIVE vencido se cuenta como EXPIRED (vencimiento perezoso).
    status = case(
        (
            (Share.status == ShareStatus.ACTIVE.value) & (Share.expires_at <= func.now()),
            ShareStatus.EXPIRED.value,
        ),
        else_=Share.status,
    )
    by_status = {
        str(k): int(v)
        for k, v in db.execute(own(select(status, func.count(Share.id)).group_by(status)))
    }
    by_channel = {
        str(k): int(v)
        for k, v in db.execute(
            own(select(Share.channel, func.count(Share.id)).group_by(Share.channel))
        )
    }
    acknowledged = db.scalar(
        own(select(func.count(Share.id)).where(Share.sensitivity_decision == "WARN"))
    )

    now = datetime.now(UTC)
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    day = func.date_trunc("day", AuditEvent.occurred_at)
    per_day = {
        row[0].date(): int(row[1])
        for row in db.execute(
            select(day, func.count(AuditEvent.id))
            .where(*event_filter(AuditEventType.DOCUMENT_ACCESSED, start))
            .group_by(day)
        )
    }
    accesses_by_day = [
        DailyCount(day=d, count=per_day.get(d, 0))
        for d in ((start + timedelta(days=i)).date() for i in range(days))
    ]

    month_ago = now - timedelta(days=30)
    blocked_filter = [
        AuditEvent.event_type == AuditEventType.SHARE_BLOCKED.value,
        AuditEvent.occurred_at >= month_ago,
    ]
    if owner_id:  # un intento bloqueado no tiene share: se atribuye por actor
        blocked_filter.append(AuditEvent.actor_id == str(owner_id))
    blocked = db.scalar(select(func.count(AuditEvent.id)).where(*blocked_filter))
    denied = db.scalar(
        select(func.count(AuditEvent.id)).where(
            *event_filter(AuditEventType.ACCESS_DENIED, month_ago)
        )
    )

    top = db.execute(
        own(
            select(Document.source_id, Document.title, func.count(Share.id))
            .join(Share, Share.document_id == Document.id)
            .group_by(Document.source_id, Document.title)
            .order_by(func.count(Share.id).desc())
            .limit(5)
        )
    )
    users_active = None
    if owner_id is None:
        users_active = int(
            db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0
        )
    return Stats(
        scope="mine" if owner_id else "all",
        shares_total=sum(by_status.values()),
        shares_by_status=by_status,
        shares_by_channel=by_channel,
        accesses_by_day=accesses_by_day,
        blocked_attempts_30d=int(blocked or 0),
        denied_accesses_30d=int(denied or 0),
        sensitive_acknowledged=int(acknowledged or 0),
        top_documents=[TopDocument(source_id=s, title=t, shares=int(n)) for s, t, n in top],
        users_active=users_active,
    )
