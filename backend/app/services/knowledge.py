"""话术知识库（RAG）：knowledge/*.md → knowledge_chunks（pgvector）。

- 开启 embedding：向量相似度检索（cosine）；
- 未开启：按场景过滤 + 字符二元组重合度排序，零成本可用。
知识文件内容必须已脱敏（见 doc/05-data-and-security.md）。
"""

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import func, literal, or_, select, true
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models import KnowledgeChunk
from app.services.guard import mask_pii
from app.services.llm.usage import UsageRecord, record_usage, token_cost

logger = logging.getLogger(__name__)
FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


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


def parse_markdown(path: Path, root: Path) -> list[ParsedChunk]:
    """按二级标题切块；front matter 支持 title / tags / scenarios。"""
    text = path.read_text(encoding="utf-8")
    meta: dict = {}
    if m := FRONT_MATTER.match(text):
        meta = yaml.safe_load(m.group(1)) or {}
        text = text[m.end() :]
    doc_title = meta.get("title", path.stem)
    chunks = []
    for block in re.split(r"(?m)^##\s+", text):
        block = block.strip()
        if not block or block.startswith("# "):
            continue
        heading, _, body = block.partition("\n")
        if body.strip():
            chunks.append(
                ParsedChunk(
                    source=path.relative_to(root).as_posix(),
                    title=f"{doc_title} / {heading.strip()}",
                    content=mask_pii(body.strip()),
                    tags=list(meta.get("tags", [])),
                    scenario_ids=list(meta.get("scenarios", [])),
                )
            )
    return chunks


def parse_dir(root: Path) -> list[ParsedChunk]:
    return [
        c
        for f in sorted(root.rglob("*.md"))
        if f.name.lower() != "readme.md"
        for c in parse_markdown(f, root)
    ]


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

    async def ingest_dir(self, root: Path) -> int:
        chunks = await asyncio.to_thread(parse_dir, root)
        if not chunks:
            return 0
        vectors = (
            await self._embed([f"{c.title}\n{c.content}" for c in chunks])
            if self.cfg.enabled
            else [None] * len(chunks)
        )
        async with self.session_factory() as db, db.begin():
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
        try:
            async with self.session_factory() as db:
                if self.cfg.enabled:
                    [vec] = await self._embed([query])
                    dist = KnowledgeChunk.embedding.cosine_distance(vec)
                    rows = (
                        await db.execute(
                            select(KnowledgeChunk, dist.label("d"))
                            .where(scope, KnowledgeChunk.embedding.is_not(None))
                            .order_by(dist)
                            .limit(k)
                        )
                    ).all()
                    return [Snippet(r[0].title, r[0].content, 1 - float(r.d)) for r in rows]
                rows = (await db.execute(select(KnowledgeChunk).where(scope).limit(500))).scalars().all()
        except Exception:
            logger.exception("知识库检索失败，降级为无参考话术")
            return []
        q = _bigrams(query)
        scored = [(len(q & _bigrams(r.title + r.content)) / (len(q) or 1), r) for r in rows]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [Snippet(r.title, r.content, s) for s, r in scored[:k] if s > 0]
