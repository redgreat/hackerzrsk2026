"""管理后台：账号审核与管理（H5 开放注册 → 管理员审核）。"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import AdminDep, ContainerDep
from app.services import users as svc

router = APIRouter(prefix="/admin/accounts", tags=["admin-accounts"])


class ReviewIn(BaseModel):
    action: Literal["approve", "reject", "disable", "enable"]


class RoleIn(BaseModel):
    role: Literal["user", "admin"]


class ResetPasswordIn(BaseModel):
    password: str = Field(min_length=6, max_length=64)


@router.get("")
async def list_accounts(
    c: ContainerDep,
    _: AdminDep,
    status: str | None = None,
    q: str | None = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    return await svc.list_accounts(c.session_factory, status, q, page, size)


@router.post("/{uid}/review")
async def review(uid: int, body: ReviewIn, c: ContainerDep, admin: AdminDep) -> dict:
    return await svc.review_account(c.session_factory, admin, uid, body.action)


@router.post("/{uid}/role")
async def set_role(uid: int, body: RoleIn, c: ContainerDep, admin: AdminDep) -> dict:
    return await svc.set_role(c.session_factory, admin, uid, body.role)


@router.post("/{uid}/password")
async def reset_password(uid: int, body: ResetPasswordIn, c: ContainerDep, _: AdminDep) -> dict:
    await svc.reset_password(c.session_factory, uid, body.password)
    return {"ok": True}
