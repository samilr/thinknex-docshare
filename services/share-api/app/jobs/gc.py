"""Job de retención. Uso: ``python -m app.jobs.gc`` (en producción: CronJob / scheduler)."""

import json

from app.container import build_storage
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import session_factory
from app.services import retention_service


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    factory = session_factory(settings.database_url)
    with factory() as db, db.begin():
        result = retention_service.run(
            db,
            build_storage(settings),
            settings.snapshot_grace_hours,
            inbox_ttl_days=settings.simulated_inbox_ttl_days,
        )
    print(json.dumps(result.__dict__))


if __name__ == "__main__":
    main()
