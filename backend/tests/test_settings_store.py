import pytest

from app.core.errors import AppError
from app.services import settings_store as ss


def test_coerce_validates_types_and_ranges():
    by = ss.BY_KEY
    assert ss.coerce(by["mask_pii"], True) is True
    with pytest.raises(AppError):
        ss.coerce(by["mask_pii"], "yes")
    with pytest.raises(AppError):
        ss.coerce(by["llm.max_retries"], 99)
    assert ss.coerce(by["llm.max_retries"], 3) == 3
    with pytest.raises(AppError):
        ss.coerce(by["speech.asr_provider"], "bogus")
    with pytest.raises(AppError):
        ss.coerce(by["manual_coaching_cost_yuan"], -1)


def test_whitelist_excludes_secrets():
    keys = set(ss.BY_KEY)
    assert not any(
        k.startswith(("database_url", "jwt", "wecom", "llm.api_key", "admin_userids", "recordings"))
        for k in keys
    )
