from fastapi import APIRouter

from app.api.deps import ContainerDep, UserDep
from app.services import stats

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/me")
async def my_stats(c: ContainerDep, user: UserDep) -> dict:
    return await stats.my_stats(c.session_factory, user)
