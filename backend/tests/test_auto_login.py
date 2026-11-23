"""自动登录只向显式启用该功能的开发环境开放。"""

from types import SimpleNamespace

import pytest

from app.api.auth import auth_config, dev_login
from app.core.config import Settings
from app.core.errors import Forbidden


@pytest.mark.parametrize(
    "env,enabled,automatic,expected",
    [
        ("dev", True, True, True),
        ("dev", True, False, False),
        ("dev", False, True, False),
        ("test", True, True, False),
        ("prod", True, True, False),
    ],
)
async def test_auto_login_config(env, enabled, automatic, expected):
    settings = Settings(_env_file=None, app_env=env, dev_login_enabled=enabled, dev_auto_login=automatic)
    container = SimpleNamespace(settings=settings)
    assert (await auth_config(container))["dev_auto_login"] is expected
    if env == "prod" or not enabled:
        with pytest.raises(Forbidden):
            await dev_login(None, container)
