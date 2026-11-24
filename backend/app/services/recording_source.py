"""优质录音来源：瑟维斯贷后（dbmcp 连接 51）或本地 JSON 文件。

只取录音地址与必要的非身份字段；客户姓名、手机号等一律不取。
"""

import json
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

from app.core.config import RecordingSettings
from app.services.dbmcp import DbMcpClient
from app.services.transcripts import Case

# recall_record 分库分表：主库 sw_dhtcenter 中 recall_record_0 .. recall_record_9
# （从库 sw_dhtcenter_slave 另有镜像 10 张，合称 20 张表；查询只查主库）
# source=3 的 callCenterPath 是华为云 OBS 地址（403 不可读），改用 c.url 里的
# amp-prod 相对路径，经 audio_base_url 拼成阿里云 OSS 地址
URL_EXPR = """CASE
           WHEN c.source IN (0, 4) THEN c.callCenterPath
           WHEN c.source = 3 THEN c.url
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
        f"SELECT b.callId FROM recall_excellent_call a JOIN recall_record_{i} b ON a.recordId = b.id AND a.deleted = 0"
        for i in range(shard_count)
    )
    sql = f"""SELECT c.id AS call_id, {URL_EXPR} AS url
FROM recall_call_record c
WHERE c.id IN (
    {shards}
)
ORDER BY c.id DESC"""
    return sql + (f"\nLIMIT {int(limit)}" if limit else "")


def recording_transcripts_sql(shard_count: int, limit: int, call_id: int | None) -> str:
    match = f" AND b.callId={int(call_id)}" if call_id is not None else ""
    tables = [f"recall_record_{i}" for i in range(shard_count)] + ["recall_record_his_bak"]
    shards = "\nUNION ALL\n".join(
        f"SELECT b.callId AS call_id, e.recordId AS record_id FROM recall_excellent_call e "
        f"JOIN {table} b ON b.id=e.recordId WHERE e.deleted=0{match}"
        for table in tables
    )
    return f"""WITH candidates AS ({shards}),
selected AS (SELECT DISTINCT call_id FROM candidates WHERE call_id > 0 ORDER BY call_id DESC LIMIT {int(limit)}),
audits AS (
    SELECT a.call_id, MAX(d.id) AS audit_id FROM selected s
    JOIN candidates a ON a.call_id=s.call_id
    JOIN ai_audit_task_execute_detail d ON d.recordId=a.record_id
    WHERE d.deleted=0 AND d.success=1 AND d.characters IS NOT NULL
      AND CHAR_LENGTH(TRIM(d.characters)) > 2
    GROUP BY a.call_id
)
SELECT c.id AS call_id, {URL_EXPR} AS url,
       c.url AS alternate_url, d.characters
FROM selected s JOIN recall_call_record c ON c.id=s.call_id
LEFT JOIN audits a ON a.call_id=s.call_id
LEFT JOIN ai_audit_task_execute_detail d ON d.id=a.audit_id
ORDER BY c.id DESC"""


def transcript_case(call_id: int, raw: str | list | None) -> Case | None:
    lines = json.loads(raw) if isinstance(raw, str) else raw
    if not lines:
        return None
    segments = [
        {
            "seq": index,
            "channel": line.get("ChannelId") or 0,
            "start_raw": line["BeginTime"],
            "end_raw": line["EndTime"],
            "text": line.get("Text") or "",
        }
        for index, line in enumerate(lines, 1)
    ]
    if not any(segment["text"].strip() for segment in segments):
        return None
    digest = sha256(json.dumps(segments, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return Case.model_validate(
        {
            "case_key": f"recall-ai:{call_id}",
            "source_sha256": digest,
            "source_file": "DBMCP AI 质检",
            "source_labels": "",
            "segments": segments,
            "speaker_mapping": {},
            "speaker_mapping_status": "待人工核对",
            "time_unit": "原始时间值",
        }
    )


async def fetch_recordings_with_transcripts(
    cfg: RecordingSettings, limit: int, call_id: int | None
) -> list[dict]:
    return await DbMcpClient(cfg.dbmcp_url, cfg.dbmcp_key).query(
        cfg.connection_id, recording_transcripts_sql(cfg.shard_count, limit, call_id)
    )


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
