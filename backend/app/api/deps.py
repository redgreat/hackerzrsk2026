from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.container import Container
from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_token
from app.db.models import User

bearer = HTTPBearer(auto_error=False)


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


async def current_user(
    c: ContainerDep, cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> User:
    if cred is None:
        raise Unauthorized("请先登录")
    user_id = decode_token(c.settings, cred.credentials)
    async with c.session_factory() as db:
        user = await db.get(User, user_id)
    if user is None:
        raise Unauthorized("用户不存在")
    return user


UserDep = Annotated[User, Depends(current_user)]


async def admin_user(c: ContainerDep, user: UserDep) -> User:
    if c.settings.admin_userids and user.userid not in c.settings.admin_userids:
        raise Forbidden("仅管理员可查看")
    return user


AdminDep = Annotated[User, Depends(admin_user)]
