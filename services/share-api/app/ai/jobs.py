"""Procesamiento de la cola del índice en segundo plano, tras responder la solicitud."""

from __future__ import annotations

import logging

from app.ai.index_service import IndexService
from app.container import Components
from app.core.config import Settings

logger = logging.getLogger("share_api.ai")


def process_pending(components: Components, settings: Settings, limit: int = 10) -> None:
    if not settings.ai_enabled:
        return
    try:
        with components.session_factory() as db:
            IndexService(db, settings, components.source, components.embedder).run_pending(limit)
    except Exception:  # el job programado lo reintentará
        logger.exception("no se pudo procesar la cola del índice")
