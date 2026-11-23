"""陪练、语音和录音分析共用的调用费用落库。由调用方管理事务。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ModelUsage, PracticeSession
from app.services.llm.usage import UsageScope


def add_usage(db: AsyncSession, sess: PracticeSession | None, user_id: int | None, usage: UsageScope) -> None:
    for r in usage.records:
        db.add(
            ModelUsage(
                session_id=sess.id if sess else None,
                user_id=user_id,
                purpose=r.purpose,
                model=r.model,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                audio_seconds=r.audio_seconds,
                tts_chars=r.tts_chars,
                cost_yuan=r.cost_yuan,
                latency_ms=r.latency_ms,
            )
        )
    if sess is not None:
        sess.prompt_tokens += usage.prompt_tokens
        sess.completion_tokens += usage.completion_tokens
        sess.cost_yuan += usage.cost_yuan
