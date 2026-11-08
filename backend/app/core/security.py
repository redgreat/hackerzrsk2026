from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import Settings
from app.core.errors import Unauthorized

ALGORITHM = "HS256"


def create_token(settings: Settings, user_id: int, userid: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "uid": userid,
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(settings: Settings, token: str) -> int:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise Unauthorized("登录已失效，请重新进入") from exc
    return int(payload["sub"])
