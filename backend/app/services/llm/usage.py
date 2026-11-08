"""调用计量：每次模型/语音调用写入当前 UsageScope，由业务层统一落库。

只记录 token、时长、费用，不记录任何对话内容。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from decimal import Decimal

from app.core.config import ModelPrice

MILLION = Decimal(1_000_000)


@dataclass
class UsageRecord:
    purpose: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_yuan: Decimal = Decimal(0)
    latency_ms: int = 0
    audio_seconds: Decimal = Decimal(0)
    tts_chars: int = 0


@dataclass
class UsageScope:
    records: list[UsageRecord] = field(default_factory=list)

    @property
    def prompt_tokens(self) -> int:
        return sum(r.prompt_tokens for r in self.records)

    @property
    def completion_tokens(self) -> int:
        return sum(r.completion_tokens for r in self.records)

    @property
    def cost_yuan(self) -> Decimal:
        return sum((r.cost_yuan for r in self.records), Decimal(0))


_current: ContextVar[UsageScope | None] = ContextVar("usage_scope", default=None)


@contextmanager
def usage_scope() -> Iterator[UsageScope]:
    scope = UsageScope()
    token = _current.set(scope)
    try:
        yield scope
    finally:
        _current.reset(token)


def record_usage(record: UsageRecord) -> None:
    scope = _current.get()
    if scope is not None:
        scope.records.append(record)


def token_cost(price: ModelPrice | None, prompt_tokens: int, completion_tokens: int) -> Decimal:
    if price is None:
        return Decimal(0)
    return (
        Decimal(str(price.input)) * prompt_tokens + Decimal(str(price.output)) * completion_tokens
    ) / MILLION
