from fastapi import APIRouter

from app.api.deps import AnyRoleDep, DbDep, SettingsDep
from app.domain.enums import Role
from app.services import stats_service
from app.services.stats_service import Stats

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=Stats)
def get_stats(user: AnyRoleDep, db: DbDep, settings: SettingsDep) -> Stats:
    """KPIs del dashboard: globales para ADMIN/AUDITOR, propios para SHARER."""
    global_view = user.has_any(Role.ADMIN, Role.AUDITOR)
    return stats_service.compute(
        db, owner_id=None if global_view else user.id, timezone=settings.business_timezone
    )
