import base64
import hashlib
import hmac
import secrets
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


# ---------- 密码（标准库 scrypt，无额外依赖） ----------

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    b64 = base64.urlsafe_b64encode
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    try:
        algo, n, r, p, salt, digest = (stored or "").split("$")
        if algo != "scrypt":
            return False
        expected = base64.urlsafe_b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(),
            salt=base64.urlsafe_b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)
