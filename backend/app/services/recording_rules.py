"""优质录音纯规则：转写结果解析、坐席/客户角色识别、转写脱敏（不依赖网络与数据库，便于单测）。"""

import re

from app.services.guard import mask_pii

AGENT_OPENING = re.compile(
    r"(我是|这边是|这里是).{0,12}(公司|金融|客服|贷后|工号)|工号|来电是|提醒您|您的(账单|还款|月供)"
)
_NAME_TITLE = re.compile(r"([\u4e00-\u9fa5])[\u4e00-\u9fa5]{1,2}(先生|女士|小姐|总)")
_PLATE = re.compile(r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-Z0-9]{5,6}")
_ADDRESS = re.compile(r"[\u4e00-\u9fa5]{2,}(路|街|巷)\d+号(\d+(栋|幢|单元|室))*")
_MERGE_GAP_MS = 1500


def mask_transcript_text(text: str) -> str:
    """在通用脱敏基础上，处理姓名+称谓、车牌、详细门牌地址。"""
    text = mask_pii(text)
    text = _NAME_TITLE.sub(lambda m: f"{m.group(1)}{m.group(2)}", text)
    text = _PLATE.sub("[车牌]", text)
    return _ADDRESS.sub("[地址]", text)


def parse_paraformer(result: dict) -> list[dict]:
    """解析 Paraformer 识别结果 JSON。

    多声道（呼叫中心双轨录音）时以 channel_id 作为说话人；单声道时使用说话人分离的 speaker_id。
    """
    transcripts = result.get("transcripts") or []
    multi_channel = len(transcripts) > 1
    sentences = []
    for t in transcripts:
        for s in t.get("sentences") or []:
            text = (s.get("text") or "").strip()
            if not text:
                continue
            speaker = t.get("channel_id", 0) if multi_channel else s.get("speaker_id", 0)
            sentences.append(
                {
                    "begin_ms": int(s.get("begin_time", 0)),
                    "end_ms": int(s.get("end_time", 0)),
                    "speaker_raw": int(speaker or 0),
                    "text": text,
                }
            )
    sentences.sort(key=lambda s: (s["begin_ms"], s["end_ms"]))
    return sentences


def detect_agent_speaker(sentences: list[dict]) -> int:
    """坐席识别：优先看谁说了自报家门/提醒还款的话；否则取第一个开口的人（外呼通常坐席先说）。"""
    for s in sentences[:8]:
        if AGENT_OPENING.search(s["text"]):
            return s["speaker_raw"]
    return sentences[0]["speaker_raw"] if sentences else 0


def build_transcript(sentences: list[dict]) -> list[dict]:
    """标注角色、脱敏，并合并同一说话人间隔很短的相邻句子。"""
    agent = detect_agent_speaker(sentences)
    out: list[dict] = []
    for s in sentences:
        role = "agent" if s["speaker_raw"] == agent else "customer"
        text = mask_transcript_text(s["text"])
        prev = out[-1] if out else None
        if prev and prev["speaker"] == role and s["begin_ms"] - prev["end_ms"] <= _MERGE_GAP_MS:
            prev["text"] += text
            prev["end_ms"] = max(prev["end_ms"], s["end_ms"])
        else:
            out.append({"begin_ms": s["begin_ms"], "end_ms": s["end_ms"], "speaker": role, "text": text})
    return out


def transcript_prompt_text(transcript: list[dict]) -> str:
    role = {"agent": "坐席", "customer": "客户"}
    return "\n".join(
        f"[{i}] {role.get(t['speaker'], t['speaker'])}：{t['text']}" for i, t in enumerate(transcript)
    )


def duration_seconds(result: dict, transcript: list[dict]) -> int | None:
    ms = (result.get("properties") or {}).get("original_duration_in_milliseconds")
    if ms is None and transcript:
        ms = transcript[-1]["end_ms"]
    return round(ms / 1000) if ms is not None else None
