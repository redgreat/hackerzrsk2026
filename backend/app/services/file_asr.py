"""录音文件转写：阿里云百炼 Paraformer 录音文件识别（异步任务：提交 → 轮询 → 下载结果 JSON）。

provider:
- dashscope：直接把 OSS 录音地址交给百炼拉取（地址需公网可读或带签名）
- stub：离线生成一段示例催收对话，用于开发、测试
- none：关闭
"""

import asyncio
import logging
import time
from decimal import Decimal

import httpx

from app.core.config import RecordingSettings
from app.core.errors import FeatureDisabled, UpstreamError
from app.services.llm.usage import UsageRecord, record_usage

logger = logging.getLogger(__name__)

STUB_DIALOG = [
    (0, "您好，请问是李建国先生吗？我这边是车贷贷后服务中心的，工号 1024。"),
    (1, "是我，什么事？"),
    (
        0,
        "李先生您好，打扰您一分钟。系统显示您这期月供还款日已经过了三天，还没有扣款成功，想跟您确认一下情况。",
    ),
    (1, "啊？我还以为扣了，最近换了张卡，可能忘了转钱。"),
    (
        0,
        "理解的，换卡确实容易忽略。您之前一直都按时还款，记录特别好，所以我们第一时间提醒您，尽量不影响您的征信。",
    ),
    (1, "会影响征信吗？晚几天应该没事吧？"),
    (
        0,
        "逾期时间越长，对征信记录的影响越大。如果今天能处理好，影响就能降到最低。您看今天几点前方便把钱转到扣款卡里？",
    ),
    (1, "那我下午三点前转进去吧。"),
    (
        0,
        "好的，跟您确认一下：今天下午三点前把本期月供存入尾号 [银行卡号] 的扣款卡，我们会在四点后再发起扣款。您手机号 13812345678 能收到短信提醒吗？",
    ),
    (1, "可以，收到了。"),
    (0, "好的，感谢您的配合，祝您生活愉快，再见。"),
]


def stub_result(url: str) -> dict:
    sentences, t = [], 200
    for i, (speaker, text) in enumerate(STUB_DIALOG):
        dur = 250 * len(text)
        sentences.append(
            {"begin_time": t, "end_time": t + dur, "text": text, "sentence_id": i + 1, "speaker_id": speaker}
        )
        t += dur + 600
    return {
        "file_url": url,
        "properties": {"original_duration_in_milliseconds": t},
        "transcripts": [{"channel_id": 0, "sentences": sentences}],
    }


class FileASR:
    def __init__(self, cfg: RecordingSettings, transport: httpx.AsyncBaseTransport | None = None):
        self.cfg = cfg
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return self.cfg.asr_provider != "none"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.cfg.dashscope_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {self.cfg.dashscope_api_key}"},
            timeout=60,
            transport=self._transport,
        )

    def _parameters(self) -> dict:
        params: dict = {"language_hints": ["zh"]}
        if self.cfg.channel_ids:
            params["channel_id"] = self.cfg.channel_ids
        else:
            params.update(diarization_enabled=True, speaker_count=2)
        return params

    async def submit(self, url: str) -> str:
        async with self._client() as client:
            resp = await client.post(
                "/api/v1/services/audio/asr/transcription",
                headers={"X-DashScope-Async": "enable"},
                json={
                    "model": self.cfg.asr_model,
                    "input": {"file_urls": [url]},
                    "parameters": self._parameters(),
                },
            )
        if resp.status_code >= 400:
            raise UpstreamError(f"提交转写任务失败（{resp.status_code}）：{resp.text[:200]}")
        return resp.json()["output"]["task_id"]

    async def wait(self, task_id: str) -> dict:
        deadline = time.monotonic() + self.cfg.poll_timeout_seconds
        async with self._client() as client:
            while True:
                resp = await client.get(f"/api/v1/tasks/{task_id}")
                if resp.status_code >= 400:
                    raise UpstreamError(f"查询转写任务失败（{resp.status_code}）")
                output = resp.json()["output"]
                status = output.get("task_status")
                if status == "SUCCEEDED":
                    sub = (output.get("results") or [{}])[0]
                    if sub.get("subtask_status") != "SUCCEEDED":
                        raise UpstreamError(f"转写失败：{sub.get('code')} {sub.get('message', '')}".strip())
                    result = await client.get(sub["transcription_url"])
                    return result.json()
                if status in ("FAILED", "CANCELED", "UNKNOWN"):
                    raise UpstreamError(f"转写失败：{output.get('code')} {output.get('message', '')}".strip())
                if time.monotonic() > deadline:
                    raise UpstreamError("转写超时，请稍后重试")
                await asyncio.sleep(self.cfg.poll_interval_seconds)

    async def transcribe(self, url: str, task_id: str | None = None, on_submitted=None) -> dict:
        """返回 Paraformer 识别结果 JSON；task_id 不为空时续查已提交的任务。"""
        if not self.enabled:
            raise FeatureDisabled("录音转写未开启（RECORDINGS__ASR_PROVIDER）")
        started = time.perf_counter()
        if self.cfg.asr_provider == "stub":
            result = stub_result(url)
        else:
            if not task_id:
                task_id = await self.submit(url)
                if on_submitted:
                    await on_submitted(task_id)
            result = await self.wait(task_id)
        ms = (result.get("properties") or {}).get("original_duration_in_milliseconds") or 0
        seconds = Decimal(ms) / 1000
        record_usage(
            UsageRecord(
                purpose="asr",
                model=self.cfg.asr_model if self.cfg.asr_provider != "stub" else "stub",
                audio_seconds=seconds,
                cost_yuan=Decimal(0)
                if self.cfg.asr_provider == "stub"
                else seconds / 60 * Decimal(str(self.cfg.asr_price_per_minute)),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        )
        return result
