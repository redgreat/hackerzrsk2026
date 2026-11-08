from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import ContainerDep, UserDep, is_admin
from app.core.errors import Forbidden
from app.core.security import create_token
from app.services.users import upsert_user, user_dict

router = APIRouter(prefix="/auth", tags=["auth"])


class WeComLoginIn(BaseModel):
    code: str


class DevLoginIn(BaseModel):
    userid: str = Field(min_length=1, max_length=64)
    name: str = Field("", max_length=64)
    department: str = Field("", max_length=128)


@router.get("/config")
async def auth_config(c: ContainerDep, redirect_uri: str | None = None) -> dict:
    """前端据此决定登录方式：企微内置浏览器走 OAuth 免登，电脑浏览器走扫码登录。"""
    enabled = c.settings.wecom.enabled and redirect_uri is not None
    return {
        "wecom_enabled": c.settings.wecom.enabled,
        "oauth_url": c.wecom.oauth_url(redirect_uri) if enabled else None,
        "qr_url": c.wecom.qr_login_url(redirect_uri) if enabled else None,
        "dev_login_enabled": c.settings.dev_login_enabled and c.settings.app_env != "prod",
    }


def _login_result(c, user) -> dict:
    return {
        "token": create_token(c.settings, user.id, user.userid),
        "user": user_dict(user, is_admin(c.settings, user)),
    }


@router.post("/wecom")
async def wecom_login(body: WeComLoginIn, c: ContainerDep) -> dict:
    wu = await c.wecom.user_by_code(body.code)
    user = await upsert_user(c.session_factory, wu.userid, wu.name, wu.department, "wecom")
    return _login_result(c, user)


@router.post("/dev")
async def dev_login(body: DevLoginIn, c: ContainerDep) -> dict:
    if not c.settings.dev_login_enabled or c.settings.app_env == "prod":
        raise Forbidden("开发登录已关闭")
    user = await upsert_user(c.session_factory, body.userid, body.name, body.department, "dev")
    return _login_result(c, user)


@router.get("/me")
async def me(c: ContainerDep, user: UserDep) -> dict:
    return user_dict(user, is_admin(c.settings, user))
