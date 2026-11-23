"""优质录音来源：直接的录音 URL 列表（不连接任何业务库，也不在服务器上存文件）。

每行一条：`录音URL[<TAB>标题]`。相对路径按 recordings.audio_base_url 拼接。
"""

from dataclasses import dataclass, field
from hashlib import sha256

from app.core.config import RecordingSettings
from app.core.errors import AppError


@dataclass
class RecordingItem:
    source_key: str
    audio_url: str
    title: str = ""
    duration_seconds: int | None = None
    meta: dict = field(default_factory=dict)


def normalize_url(url: str, base: str | None) -> str:
    if url.startswith(("http://", "https://")) or not base:
        return url
    return f"{base.rstrip('/')}/{url.lstrip('/')}"


def parse_lines(text: str, cfg: RecordingSettings) -> list[RecordingItem]:
    items: list[RecordingItem] = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        url, _, title = line.partition("\t")
        url = url.strip()
        if not url:
            continue
        if " " in url:
            raise AppError(f"第 {n} 行 URL 含空格：{url[:60]}")
        full = normalize_url(url, cfg.audio_base_url)
        items.append(
            RecordingItem(
                source_key=f"url:{sha256(full.encode()).hexdigest()}", audio_url=full, title=title.strip()
            )
        )
    if not items:
        raise AppError("没有可导入的录音 URL")
    return items
