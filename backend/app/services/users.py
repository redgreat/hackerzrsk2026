from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import User


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


def user_dict(user: User) -> dict:
    return {"id": user.id, "userid": user.userid, "name": user.name, "department": user.department}
