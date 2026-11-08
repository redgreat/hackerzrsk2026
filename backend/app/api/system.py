from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import ContainerDep

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(c: ContainerDep) -> dict:
    async with c.session_factory() as db:
        await db.execute(text("select 1"))
    return {"status": "ok", "llm_provider": c.settings.llm.provider, "scenarios": len(c.scenarios.scenarios)}
