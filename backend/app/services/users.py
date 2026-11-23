import asyncio
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError, Conflict, Forbidden, NotFound, Unauthorized
from app.core.security import hash_password, verify_password
from app.db.models import User

STATUS_MESSAGES = {
    "pending": "账号正在等待管理员审核，审核通过后即可登录",
    "rejected": "注册申请未通过，请联系管理员",
    "disabled": "账号已停用，请联系管理员",
}
MIN_PASSWORD = 6


async def upsert_user(
    sf: async_sessionmaker[AsyncSession], userid: str, name: str, department: str, source: str
) -> User:
    async with sf() as db, db.begin():
        user = (await db.execute(select(User).where(User.userid == userid))).scalar_one_or_none()
        if user is None:
            user = User(userid=userid, name=name or userid, department=department, source=source)
            db.add(user)
        else:
            user.name = name or user.name
            user.department = department or user.department
        user.last_login_at = datetime.now(UTC)
    return user


def check_status(user: User) -> None:
    if user.status != "active":
        raise Forbidden(STATUS_MESSAGES.get(user.status, "账号不可用"))


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise AppError(f"密码至少 {MIN_PASSWORD} 位")


async def register(
    sf: async_sessionmaker[AsyncSession],
    userid: str,
    name: str,
    department: str,
    password: str,
    require_approval: bool,
) -> User:
    _check_password(password)
    pwd = await asyncio.to_thread(hash_password, password)
    async with sf() as db, db.begin():
        if (await db.execute(select(User.id).where(User.userid == userid))).first():
            raise Conflict("该工号已注册，如忘记密码请联系管理员重置")
        user = User(
            userid=userid,
            name=name,
            department=department,
            source="register",
            password_hash=pwd,
            status="pending" if require_approval else "active",
        )
        db.add(user)
    return user


async def password_login(sf: async_sessionmaker[AsyncSession], userid: str, password: str) -> User:
    async with sf() as db, db.begin():
        user = (await db.execute(select(User).where(User.userid == userid))).scalar_one_or_none()
        ok = user is not None and await asyncio.to_thread(verify_password, password, user.password_hash)
        if not ok:
            raise Unauthorized("工号或密码错误")
        check_status(user)
        user.last_login_at = datetime.now(UTC)
    return user


async def change_password(sf: async_sessionmaker[AsyncSession], user_id: int, old: str, new: str) -> None:
    _check_password(new)
    async with sf() as db, db.begin():
        user = await db.get(User, user_id)
        if user.password_hash and not await asyncio.to_thread(verify_password, old, user.password_hash):
            raise AppError("原密码错误")
        user.password_hash = await asyncio.to_thread(hash_password, new)


async def seed_admin_if_missing(
    sf: async_sessionmaker[AsyncSession], userid: str, name: str, password: str
) -> bool:
    """工号不存在时创建管理员账号，返回是否新建。"""
    async with sf() as db:
        exists = (await db.execute(select(User.id).where(User.userid == userid))).first() is not None
    if exists:
        return False
    await create_or_reset_admin(sf, userid, name, password)
    return True


async def create_or_reset_admin(
    sf: async_sessionmaker[AsyncSession], userid: str, name: str, password: str
) -> User:
    _check_password(password)
    pwd = await asyncio.to_thread(hash_password, password)
    async with sf() as db, db.begin():
        user = (await db.execute(select(User).where(User.userid == userid))).scalar_one_or_none()
        if user is None:
            user = User(userid=userid, name=name or userid, department="管理", source="register")
            db.add(user)
        user.password_hash, user.status, user.role = pwd, "active", "admin"
    return user


# ---------- 管理员：账号审核 ----------

ACTIONS = {"approve": "active", "reject": "rejected", "disable": "disabled", "enable": "active"}


async def list_accounts(
    sf: async_sessionmaker[AsyncSession], status: str | None, q: str | None, page: int, size: int
) -> dict:
    size = max(1, min(size, 100))
    cond = []
    if status:
        cond.append(User.status == status)
    if q:
        cond.append(User.userid.ilike(f"%{q}%") | User.name.ilike(f"%{q}%") | User.department.ilike(f"%{q}%"))
    async with sf() as db:
        total = (await db.execute(select(func.count()).select_from(User).where(*cond))).scalar_one()
        rows = (
            (
                await db.execute(
                    select(User)
                    .where(*cond)
                    .order_by(User.created_at.desc())
                    .offset((max(page, 1) - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        pending = (await db.execute(select(func.count()).where(User.status == "pending"))).scalar_one()
    return {"total": total, "pending": pending, "items": [account_dict(u) for u in rows]}


async def review_account(sf: async_sessionmaker[AsyncSession], admin: User, uid: int, action: str) -> dict:
    if action not in ACTIONS:
        raise AppError(f"不支持的操作：{action}")
    async with sf() as db, db.begin():
        user = await db.get(User, uid, with_for_update=True)
        if user is None:
            raise NotFound("账号不存在")
        if user.id == admin.id and action in ("reject", "disable"):
            raise AppError("不能停用自己的账号")
        user.status = ACTIONS[action]
        user.reviewed_by, user.reviewed_at = admin.id, datetime.now(UTC)
    return account_dict(user)


async def set_role(sf: async_sessionmaker[AsyncSession], admin: User, uid: int, role: str) -> dict:
    if role not in ("user", "admin"):
        raise AppError("角色只能是 user 或 admin")
    if uid == admin.id and role != "admin":
        raise AppError("不能取消自己的管理员身份")
    async with sf() as db, db.begin():
        user = await db.get(User, uid, with_for_update=True)
        if user is None:
            raise NotFound("账号不存在")
        user.role = role
    return account_dict(user)


async def reset_password(sf: async_sessionmaker[AsyncSession], uid: int, password: str) -> None:
    _check_password(password)
    pwd = await asyncio.to_thread(hash_password, password)
    async with sf() as db, db.begin():
        user = await db.get(User, uid, with_for_update=True)
        if user is None:
            raise NotFound("账号不存在")
        user.password_hash = pwd


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def account_dict(u: User) -> dict:
    return {
        "id": u.id,
        "userid": u.userid,
        "name": u.name,
        "department": u.department,
        "source": u.source,
        "status": u.status,
        "role": u.role,
        "has_password": bool(u.password_hash),
        "created_at": _iso(u.created_at),
        "reviewed_at": _iso(u.reviewed_at),
        "last_login_at": _iso(u.last_login_at),
    }


def user_dict(user: User, is_admin: bool = False) -> dict:
    return {
        "id": user.id,
        "userid": user.userid,
        "name": user.name,
        "department": user.department,
        "is_admin": is_admin,
    }
