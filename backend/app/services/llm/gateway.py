"""模型封装层：所有大模型调用的唯一出口。

- 按用途（customer/evaluator/coach/hint）选择模型与温度，便于切换厂商；
- 进入模型前统一做敏感信息脱敏；
- 结构化输出采用 JSON 模式 + Pydantic 校验 + 一次纠错重试，兼容各家 OpenAI 兼容接口；
- 每次调用记录 token 与估算费用（成本统计是比赛汇报重点）。
"""

import json
import logging
import time
from collections.abc import AsyncIterator, Sequence
from functools import cache

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from app.core.config import Purpose, Settings
from app.core.errors import UpstreamError
from app.services.guard import mask_pii
from app.services.llm.stub import StubChatModel
from app.services.llm.usage import UsageRecord, record_usage, token_cost

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("输出中没有 JSON 对象")
    return text[start : end + 1]


class LLMGateway:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cfg = settings.llm

    def model_name(self, purpose: Purpose) -> str:
        if self.cfg.provider == "stub":
            return "stub"
        return self.cfg.for_purpose(purpose).model or self.cfg.model

    @cache  # noqa: B019 - 网关为进程级单例
    def chat_model(self, purpose: Purpose) -> BaseChatModel:
        pc = self.cfg.for_purpose(purpose)
        if self.cfg.provider == "stub":
            return StubChatModel(purpose=purpose)
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self.model_name(purpose),
            base_url=self.cfg.base_url or None,
            api_key=self.cfg.api_key or None,
            temperature=pc.temperature,
            timeout=self.cfg.timeout_seconds,
            max_retries=self.cfg.max_retries,
            stream_usage=True,
            # 国内厂商普遍只识别 max_tokens（不识别 max_completion_tokens），经 extra_body 直传
            extra_body={
                **({"max_tokens": pc.max_tokens} if pc.max_tokens else {}),
                **(self.cfg.extra_body or {}),
            },
        )

    def _prepare(self, messages: Sequence[BaseMessage]) -> list[BaseMessage]:
        if not self.settings.mask_pii:
            return list(messages)
        return [
            m.model_copy(update={"content": mask_pii(m.content)}) if isinstance(m.content, str) else m
            for m in messages
        ]

    def _record(self, purpose: Purpose, msg: AIMessage | AIMessageChunk | None, started: float) -> None:
        usage = (msg.usage_metadata if msg is not None else None) or {}
        model = self.model_name(purpose)
        pt, ct = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        record_usage(
            UsageRecord(
                purpose=purpose,
                model=model,
                prompt_tokens=pt,
                completion_tokens=ct,
                cost_yuan=token_cost(self.cfg.pricing.get(model), pt, ct),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        )

    async def stream_text(self, purpose: Purpose, messages: Sequence[BaseMessage]) -> AsyncIterator[str]:
        started = time.perf_counter()
        full: AIMessageChunk | None = None
        try:
            async for chunk in self.chat_model(purpose).astream(self._prepare(messages)):
                full = chunk if full is None else full + chunk
                if isinstance(chunk.content, str) and chunk.content:
                    yield chunk.content
        except Exception as exc:
            logger.exception("模型流式调用失败 purpose=%s", purpose)
            raise UpstreamError("AI 服务暂时不可用，请稍后重试") from exc
        finally:
            self._record(purpose, full, started)

    async def text(self, purpose: Purpose, messages: Sequence[BaseMessage]) -> str:
        return await self._invoke(purpose, self._prepare(messages))

    async def _invoke(self, purpose: Purpose, messages: list[BaseMessage], **bind) -> str:
        started = time.perf_counter()
        model = self.chat_model(purpose)
        msg = None
        try:
            msg = await (model.bind(**bind) if bind else model).ainvoke(messages)
        except Exception as exc:
            logger.exception("模型调用失败 purpose=%s", purpose)
            raise UpstreamError("AI 服务暂时不可用，请稍后重试") from exc
        finally:
            self._record(purpose, msg, started)
        return msg.content if isinstance(msg.content, str) else str(msg.content)

    async def structured[T: BaseModel](
        self, purpose: Purpose, messages: Sequence[BaseMessage], schema: type[T], retries: int = 1
    ) -> T:
        schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        instruction = SystemMessage(
            content=f"只输出一个 JSON 对象，不要输出任何解释或 Markdown 代码块。JSON 必须符合以下 JSON Schema：\n{schema_text}"
        )
        convo = [*self._prepare(messages), instruction]
        bind = {} if self.cfg.provider == "stub" else {"response_format": {"type": "json_object"}}
        last_err: Exception | None = None
        for _ in range(retries + 1):
            raw = await self._invoke(purpose, convo, **bind)
            try:
                return schema.model_validate_json(_extract_json(raw))
            except (ValueError, ValidationError) as exc:
                last_err = exc
                logger.warning("结构化输出解析失败 purpose=%s: %s", purpose, str(exc)[:200])
                convo = [
                    *convo,
                    AIMessage(content=raw),
                    HumanMessage(content=f"上次输出不符合要求：{str(exc)[:300]}。请重新只输出合法 JSON。"),
                ]
        raise UpstreamError("AI 输出格式异常，请重试") from last_err
