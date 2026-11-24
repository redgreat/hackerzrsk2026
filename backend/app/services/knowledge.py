"""话术知识库（RAG）：数据库话术与录音参考 → knowledge_chunks（pgvector）。

- 开启 embedding：向量相似度检索（cosine）；
- 未开启：按场景过滤 + 字符二元组重合度排序，零成本可用。
知识库内容必须已脱敏（见 doc/05-数据接入与安全.md）。
"""

import hashlib
import logging
import re
import time
from dataclasses import dataclass

from sqlalchemy import delete, func, literal, or_, select, true
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models import KnowledgeChunk
from app.services.llm.usage import UsageRecord, record_usage, token_cost

logger = logging.getLogger(__name__)


@dataclass
class Snippet:
    title: str
    content: str
    score: float


@dataclass
class ParsedChunk:
    source: str
    title: str
    content: str
    tags: list[str]
    scenario_ids: list[str]

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(f"{self.source}|{self.title}|{self.content}".encode()).hexdigest()


def _bigrams(text: str) -> set[str]:
    text = re.sub(r"\s+", "", text)
    return {text[i : i + 2] for i in range(len(text) - 1)}


class KnowledgeBase:
    def __init__(self, settings: Settings, session_factory: async_sessionmaker[AsyncSession] | None):
        self.settings = settings
        self.cfg = settings.embedding
        self.session_factory = session_factory
        self._embedder = None

    @property
    def embedder(self):
        if self._embedder is None and self.cfg.enabled:
            from langchain_openai import OpenAIEmbeddings

            self._embedder = OpenAIEmbeddings(
                model=self.cfg.model,
                base_url=self.cfg.base_url or None,
                api_key=self.cfg.api_key or None,
                dimensions=self.cfg.dimensions,
                check_embedding_ctx_length=False,
            )
        return self._embedder

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        started = time.perf_counter()
        vectors = await self.embedder.aembed_documents(texts)
        tokens = sum(len(t) for t in texts)  # 估算：中文约 1 字 1 token
        record_usage(
            UsageRecord(
                purpose="embedding",
                model=self.cfg.model,
                prompt_tokens=tokens,
                cost_yuan=token_cost(self.settings.llm.pricing.get(self.cfg.model), tokens, 0),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        )
        return vectors

    async def write_chunks(
        self, db: AsyncSession, chunks: list[ParsedChunk], vectors: list, sources: set[str]
    ) -> None:
        if sources:
            await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.source.in_(sources)))
        for c, vec in zip(chunks, vectors, strict=True):
            stmt = insert(KnowledgeChunk).values(
                source=c.source,
                title=c.title,
                content=c.content,
                tags=c.tags,
                scenario_ids=c.scenario_ids,
                content_hash=c.content_hash,
                embedding=vec,
            )
            await db.execute(
                stmt.on_conflict_do_update(
                    index_elements=["content_hash"], set_={"embedding": stmt.excluded.embedding}
                )
            )

    async def replace_source(self, source: str, chunks: list[ParsedChunk]) -> int:
        """在新索引准备好后事务化替换录音参考，空片段表示撤销。"""
        vectors = (
            await self._embed([f"{c.title}\n{c.content}" for c in chunks])
            if chunks and self.cfg.enabled
            else [None] * len(chunks)
        )
        async with self.session_factory() as db, db.begin():
            await self.write_chunks(db, chunks, vectors, {source})
        return len(chunks)

    async def search(self, query: str, scenario_id: str | None, k: int = 3) -> list[Snippet]:
        if self.session_factory is None or not query.strip():
            return []
        scope = (
            or_(
                func.cardinality(KnowledgeChunk.scenario_ids) == 0,
                literal(scenario_id) == KnowledgeChunk.scenario_ids.any_(),
            )
            if scenario_id
            else true()
        )
        vector = None
        if self.cfg.enabled:
            try:
                [vector] = await self._embed([query])
            except Exception:
                logger.exception("向量服务不可用，使用关键词检索")
        semantic = []
        try:
            async with self.session_factory() as db:
                lexical_query = select(KnowledgeChunk).where(scope).order_by(KnowledgeChunk.id).limit(500)
                if vector is not None:
                    dist = KnowledgeChunk.embedding.cosine_distance(vector)
                    vector_rows = (
                        await db.execute(
                            select(KnowledgeChunk, dist.label("d"))
                            .where(
                                scope,
                                KnowledgeChunk.embedding.is_not(None),
                                ~KnowledgeChunk.source.startswith("script:"),
                            )
                            .order_by(dist)
                            .limit(k)
                        )
                    ).all()
                    semantic = [Snippet(r[0].title, r[0].content, 1 - float(r.d)) for r in vector_rows]
                    lexical_query = lexical_query.where(
                        or_(KnowledgeChunk.embedding.is_(None), KnowledgeChunk.source.startswith("script:"))
                    )
                rows = (await db.scalars(lexical_query)).all()
        except Exception:
            logger.exception("知识库检索失败，降级为无参考话术")
            return []
        q = _bigrams(query)
        scored = [(len(q & _bigrams(r.title + r.content)) / (len(q) or 1), r) for r in rows]
        scored.sort(key=lambda x: x[0], reverse=True)
        lexical = [Snippet(r.title, r.content, s) for s, r in scored[:k] if s > 0]
        return (lexical[:1] + semantic + lexical[1:])[:k]
