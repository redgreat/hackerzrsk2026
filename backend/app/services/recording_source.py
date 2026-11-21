"""优质录音来源：瑟维斯贷后（dbmcp 连接 51）或本地 JSON 文件。

只取录音地址与必要的非身份字段；客户姓名、手机号等一律不取。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import RecordingSettings
from app.services.dbmcp import DbMcpClient

# recall_record_x 分 20 张表：recall_record_x_0 .. recall_record_x_19
URL_EXPR = """CASE
           WHEN c.source IN (0, 3, 4) THEN c.callCenterPath
           WHEN c.source = 6 AND c.callCenterPath IS NOT NULL THEN c.callCenterPath
           ELSE c.url
       END"""


@dataclass
class RecordingItem:
    source_key: str
    audio_url: str
    title: str = ""
    duration_seconds: int | None = None
    meta: dict = field(default_factory=dict)


def excellent_calls_sql(shard_count: int, limit: int | None = None) -> str:
    shards = "\n    UNION ALL\n    ".join(
        f"SELECT b.callId FROM recall_excellent_call a JOIN recall_record_x_{i} b ON a.recordId = b.id"
        for i in range(shard_count)
    )
    sql = f"""SELECT c.id AS call_id, {URL_EXPR} AS url
FROM recall_call_record c
WHERE c.id IN (
    {shards}
)
ORDER BY c.id DESC"""
    return sql + (f"\nLIMIT {int(limit)}" if limit else "")


def _item(row: dict, source: str) -> RecordingItem | None:
    url = (row.get("url") or row.get("audio_url") or "").strip()
    if not url:
        return None
    key = str(row.get("call_id") or row.get("source_key") or url)
    meta = {k: v for k, v in row.items() if k in ("call_time", "stage", "reason", "remark") and v is not None}
    return RecordingItem(
        source_key=f"{source}:{key}",
        audio_url=url,
        title=str(row.get("title") or ""),
        duration_seconds=int(row["duration"]) if row.get("duration") else None,
        meta=meta,
    )


def normalize_url(url: str, base: str | None) -> str:
    if url.startswith(("http://", "https://")) or not base:
        return url
    return f"{base.rstrip('/')}/{url.lstrip('/')}"


async def fetch_from_dbmcp(cfg: RecordingSettings, limit: int | None = None) -> list[RecordingItem]:
    rows = await DbMcpClient(cfg.dbmcp_url, cfg.dbmcp_key).query(
        cfg.connection_id, excellent_calls_sql(cfg.shard_count, limit)
    )
    items = [i for r in rows if (i := _item(r, f"db{cfg.connection_id}"))]
    for i in items:
        i.audio_url = normalize_url(i.audio_url, cfg.audio_base_url)
    return items


def load_file(path: Path, cfg: RecordingSettings) -> list[RecordingItem]:
    """JSON 数组：[{"call_id"|"source_key", "url", "title"?, "duration"?}]。"""
    rows = json.loads(path.read_text(encoding="utf-8"))
    items = [i for r in rows if (i := _item(r, "file"))]
    for i in items:
        i.audio_url = normalize_url(i.audio_url, cfg.audio_base_url)
    return items
