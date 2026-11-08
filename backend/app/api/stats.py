from fastapi import APIRouter

from app.api.deps import AdminDep, ContainerDep, UserDep
from app.services import stats

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/me")
async def my_stats(c: ContainerDep, user: UserDep) -> dict:
    return await stats.my_stats(c.session_factory, user)


@router.get("/overview")
async def overview(c: ContainerDep, _: AdminDep) -> dict:
    return await stats.overview(c.session_factory, c.settings.manual_coaching_cost_yuan)
