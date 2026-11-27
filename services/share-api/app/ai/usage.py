"""Registro del consumo de modelos y presupuesto diario por usuario."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.llm import Usage
from app.core.errors import TooManyRequestsError
from app.db.models import AiUsage


def record(db: Session, user_id: uuid.UUID | None, feature: str, usage: Usage) -> None:
    db.add(
        AiUsage(
            user_id=user_id,
            feature=feature,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            latency_ms=usage.latency_ms,
        )
    )


def spent_today(db: Session, user_id: uuid.UUID) -> int:
    since = datetime.now(UTC) - timedelta(hours=24)
    total = db.scalar(
        select(func.coalesce(func.sum(AiUsage.input_tokens + AiUsage.output_tokens), 0)).where(
            AiUsage.user_id == user_id, AiUsage.created_at >= since
        )
    )
    return int(total or 0)


def ensure_budget(db: Session, user_id: uuid.UUID, budget: int) -> None:
    if spent_today(db, user_id) >= budget:
        raise TooManyRequestsError(
            "Alcanzaste el límite diario de uso de IA. Vuelve a intentarlo mañana."
        )
