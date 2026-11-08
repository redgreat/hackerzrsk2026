"""语音：ASR（语音转文字）/ TTS（文字转语音）。

provider:
- none：关闭（前端隐藏按住说话；TTS 退化为浏览器 speechSynthesis）
- openai：OpenAI 兼容 /audio/transcriptions、/audio/speech 接口
- stub：开发联调用，ASR 返回固定文本、TTS 返回空音频
"""

import time
from decimal import Decimal

import httpx

from app.core.config import Settings
from app.core.errors import FeatureDisabled, UpstreamError
from app.services.llm.usage import UsageRecord, record_usage


class SpeechService:
    def __init__(self, settings: Settings):
        self.cfg = settings.speech

    @property
    def asr_enabled(self) -> bool:
        return self.cfg.asr_provider != "none"

    @property
    def tts_enabled(self) -> bool:
        return self.cfg.tts_provider != "none"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=(self.cfg.base_url or "").rstrip("/"),
            headers={"Authorization": f"Bearer {self.cfg.api_key}"},
            timeout=60,
        )

    async def transcribe(self, audio: bytes, filename: str, content_type: str, duration_ms: int) -> str:
        if not self.asr_enabled:
            raise FeatureDisabled("语音识别未开启")
        started = time.perf_counter()
        if self.cfg.asr_provider == "stub":
            text = "您好，我想先了解一下您这边目前最关心的是哪些方面？"
        else:
            async with self._client() as client:
                resp = await client.post(
                    "/audio/transcriptions",
                    files={"file": (filename, audio, content_type)},
                    data={"model": self.cfg.asr_model, "language": "zh"},
                )
            if resp.status_code >= 400:
                raise UpstreamError(f"语音识别失败（{resp.status_code}）")
            text = resp.json().get("text", "").strip()
        seconds = Decimal(max(duration_ms, 0)) / 1000
        record_usage(
            UsageRecord(
                purpose="asr",
                model=self.cfg.asr_model,
                audio_seconds=seconds,
                cost_yuan=seconds / 60 * Decimal(str(self.cfg.asr_price_per_minute)),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        )
        return text

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        if not self.tts_enabled:
            raise FeatureDisabled("语音合成未开启")
        started = time.perf_counter()
        if self.cfg.tts_provider == "stub":
            audio = b""
        else:
            async with self._client() as client:
                resp = await client.post(
                    "/audio/speech",
                    json={
                        "model": self.cfg.tts_model,
                        "input": text,
                        "voice": voice or self.cfg.tts_voice,
                        "response_format": "mp3",
                    },
                )
            if resp.status_code >= 400:
                raise UpstreamError(f"语音合成失败（{resp.status_code}）")
            audio = resp.content
        record_usage(
            UsageRecord(
                purpose="tts",
                model=self.cfg.tts_model,
                tts_chars=len(text),
                cost_yuan=Decimal(len(text)) / 10000 * Decimal(str(self.cfg.tts_price_per_10k_chars)),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        )
        return audio
