"""Procesa la cola del índice de IA. Uso: ``python -m app.ai.worker [--backfill]``.

En GCP corre como Cloud Run Job programado; en local, ``make ai-index``.
"""

from __future__ import annotations

import argparse
import logging

from app.ai.index_service import IndexService
from app.container import build_components
from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger("share_api.ai")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backfill", action="store_true", help="Encola todos los documentos")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings.log_level)
    if not settings.ai_enabled:
        logger.info("AI_ENABLED=false: no hay nada que indexar")
        return
    components = build_components(settings)
    with components.session_factory() as db:
        service = IndexService(db, settings, components.source, components.embedder)
        if args.backfill:
            logger.info("backfill", extra={"extra_fields": {"queued": service.enqueue_all()}})
        total = 0
        while processed := service.run_pending(limit=50):
            total += processed
        logger.info("índice sincronizado", extra={"extra_fields": {"processed": total}})


if __name__ == "__main__":
    main()
