"""运维配置：后台可改的非敏感配置项（覆盖 config.yml 的值，持久化到 app_settings 表）。

边界：
- 只允许白名单内的键；密钥、数据库连接、JWT、管理员工号、录音相关配置不在此列，仍只放 config.yml。
- 启动时先记录 config.yml 中的原始值（用于“恢复默认”），再应用覆盖。
- 保存后即时生效：Settings 对象是进程内共享的；修改 llm.* 时清空模型客户端缓存，下次调用使用新配置。
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError, NotFound
from app.db.models import AppSetting

logger = logging.getLogger(__name__)
BASE: dict[str, Any] = {}


@dataclass(frozen=True)
class Item:
    key: str
    label: str
    group: str
    kind: str  # bool / int / float / str / choice
    choices: tuple[str, ...] = ()
    lo: float | None = None
    hi: float | None = None
    hint: str = ""


ITEMS: list[Item] = [
    Item("mask_pii", "进入模型前脱敏", "隐私", "bool", hint="手机号、邮箱、证件号等在发送给模型前替换"),
    Item(
        "manual_coaching_cost_yuan",
        "人工带教单次成本（元）",
        "统计",
        "float",
        lo=0,
        hi=100000,
        hint="用于效果与成本对比",
    ),
    Item("auth.password_enabled", "允许账号密码登录", "登录与注册", "bool"),
    Item("auth.register_enabled", "允许新人注册", "登录与注册", "bool"),
    Item("auth.require_approval", "新注册需管理员审核", "登录与注册", "bool"),
    Item("llm.model", "文本模型名称", "大模型", "str", hint="需与 config.yml 中 llm.base_url 对应的厂商一致"),
    Item("llm.timeout_seconds", "模型调用超时（秒）", "大模型", "float", lo=1, hi=600),
    Item("llm.max_retries", "模型调用重试次数", "大模型", "int", lo=0, hi=5),
    Item("speech.asr_provider", "语音识别（按住说话）", "语音", "choice", choices=("none", "openai", "stub")),
    Item("speech.tts_provider", "语音合成（播放回复）", "语音", "choice", choices=("none", "openai", "stub")),
    Item(
        "embedding.enabled",
        "知识库向量检索",
        "知识库",
        "bool",
        hint="开启需 config.yml 中已配置 embedding 的地址与密钥",
    ),
]
BY_KEY = {i.key: i for i in ITEMS}
LLM_KEYS = {k for k in BY_KEY if k.startswith("llm.")}


def _resolve(settings: Settings, key: str) -> tuple[Any, str]:
    obj: Any = settings
    parts = key.split(".")
    for p in parts[:-1]:
        obj = getattr(obj, p)
    return obj, parts[-1]


def get_value(settings: Settings, key: str) -> Any:
    obj, attr = _resolve(settings, key)
    return getattr(obj, attr)


def set_value(settings: Settings, key: str, value: Any) -> None:
    obj, attr = _resolve(settings, key)
    setattr(obj, attr, value)


def coerce(item: Item, raw: Any) -> Any:
    try:
        match item.kind:
            case "bool":
                if not isinstance(raw, bool):
                    raise ValueError("需要布尔值")
                return raw
            case "choice":
                if raw not in item.choices:
                    raise ValueError(f"可选值：{', '.join(item.choices)}")
                return raw
            case "int":
                v: float = int(raw)
            case "float":
                v = float(raw)
            case _:
                s = str(raw).strip()
                if not s or len(s) > 128:
                    raise ValueError("长度 1~128")
                return s
    except (TypeError, ValueError) as exc:
        raise AppError(f"{item.label}：{exc}") from None
    if (item.lo is not None and v < item.lo) or (item.hi is not None and v > item.hi):
        raise AppError(f"{item.label}：范围 {item.lo}~{item.hi}")
    return int(v) if item.kind == "int" else v


def _reload_clients(key: str) -> None:
    if key in LLM_KEYS:
        from app.services.llm import LLMGateway

        LLMGateway.chat_model.cache_clear()  # 进程级网关的按用途模型缓存


def remember_base(settings: Settings) -> None:
    for item in ITEMS:
        BASE.setdefault(item.key, get_value(settings, item.key))


async def apply_overrides(sf: async_sessionmaker[AsyncSession], settings: Settings) -> int:
    """启动时调用。表不存在（未执行迁移）时只记录告警，不影响启动。"""
    remember_base(settings)
    try:
        async with sf() as db:
            rows = (await db.execute(select(AppSetting))).scalars().all()
    except Exception:
        logger.warning("运维配置表不可用，使用 config.yml 的值（请执行 init-db 迁移）")
        return 0
    applied = 0
    for row in rows:
        item = BY_KEY.get(row.key)
        if item is None:
            continue
        set_value(settings, row.key, coerce(item, row.value["v"]))
        applied += 1
    return applied


async def list_items(sf: async_sessionmaker[AsyncSession], settings: Settings) -> list[dict]:
    async with sf() as db:
        rows = {r.key: r for r in (await db.execute(select(AppSetting))).scalars().all()}
    out = []
    for item in ITEMS:
        row = rows.get(item.key)
        out.append(
            {
                "key": item.key,
                "label": item.label,
                "group": item.group,
                "kind": item.kind,
                "choices": list(item.choices),
                "min": item.lo,
                "max": item.hi,
                "hint": item.hint,
                "value": get_value(settings, item.key),
                "default": BASE.get(item.key),
                "overridden": row is not None,
                "updated_by": row.updated_by if row else None,
                "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
            }
        )
    return out


async def save(sf: async_sessionmaker[AsyncSession], settings: Settings, key: str, raw: Any, by: str) -> Any:
    item = BY_KEY.get(key)
    if item is None:
        raise NotFound("该配置项不允许在后台修改")
    value = coerce(item, raw)
    async with sf() as db, db.begin():
        stmt = insert(AppSetting).values(
            key=key, value={"v": value}, updated_by=by, updated_at=datetime.now(UTC)
        )
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=["key"],
                set_={"value": stmt.excluded.value, "updated_by": by, "updated_at": stmt.excluded.updated_at},
            )
        )
    set_value(settings, key, value)
    _reload_clients(key)
    logger.warning("运维配置变更 %s=%s by=%s", key, value, by)
    return value


async def reset(sf: async_sessionmaker[AsyncSession], settings: Settings, key: str, by: str) -> Any:
    if key not in BY_KEY:
        raise NotFound("该配置项不允许在后台修改")
    async with sf() as db, db.begin():
        await db.execute(delete(AppSetting).where(AppSetting.key == key))
    set_value(settings, key, BASE[key])
    _reload_clients(key)
    logger.warning("运维配置恢复默认 %s by=%s", key, by)
    return BASE[key]
