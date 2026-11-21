from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import ContainerDep, UserDep, is_admin
from app.core.errors import FeatureDisabled, Forbidden
from app.core.security import create_token
from app.services import users as svc
from app.services.users import upsert_user, user_dict

router = APIRouter(prefix="/auth", tags=["auth"])


class WeComLoginIn(BaseModel):
    code: str


class RegisterIn(BaseModel):
    userid: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=64)
    department: str = Field("", max_length=128)
    password: str = Field(min_length=6, max_length=64)


class PasswordLoginIn(BaseModel):
    userid: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=64)


class ChangePasswordIn(BaseModel):
    old_password: str = Field("", max_length=64)
    new_password: str = Field(min_length=6, max_length=64)


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
        "password_enabled": c.settings.auth.password_enabled,
        "register_enabled": c.settings.auth.password_enabled and c.settings.auth.register_enabled,
        "require_approval": c.settings.auth.require_approval,
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


@router.post("/register")
async def register(body: RegisterIn, c: ContainerDep) -> dict:
    a = c.settings.auth
    if not (a.password_enabled and a.register_enabled):
        raise FeatureDisabled("暂未开放注册")
    user = await svc.register(
        c.session_factory,
        body.userid.strip(),
        body.name.strip(),
        body.department.strip(),
        body.password,
        a.require_approval,
    )
    if user.status != "active":
        return {"status": user.status, "message": svc.STATUS_MESSAGES[user.status]}
    return {"status": user.status, **_login_result(c, user)}


@router.post("/login")
async def password_login(body: PasswordLoginIn, c: ContainerDep) -> dict:
    if not c.settings.auth.password_enabled:
        raise FeatureDisabled("账号密码登录未开启")
    user = await svc.password_login(c.session_factory, body.userid.strip(), body.password)
    return _login_result(c, user)


@router.post("/password")
async def change_password(body: ChangePasswordIn, c: ContainerDep, user: UserDep) -> dict:
    await svc.change_password(c.session_factory, user.id, body.old_password, body.new_password)
    return {"ok": True}


@router.post("/dev")
async def dev_login(body: DevLoginIn, c: ContainerDep) -> dict:
    if not c.settings.dev_login_enabled or c.settings.app_env == "prod":
        raise Forbidden("开发登录已关闭")
    user = await upsert_user(c.session_factory, body.userid, body.name, body.department, "dev")
    return _login_result(c, user)


@router.get("/me")
async def me(c: ContainerDep, user: UserDep) -> dict:
    return user_dict(user, is_admin(c.settings, user))
