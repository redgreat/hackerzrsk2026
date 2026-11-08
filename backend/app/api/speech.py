import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import ContainerDep, UserDep
from app.core.errors import AppError
from app.services.llm import usage_scope

router = APIRouter(prefix="/speech", tags=["speech"])
MAX_AUDIO_BYTES = 5 * 1024 * 1024


class TTSIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    session_id: uuid.UUID | None = None


@router.get("/config")
async def speech_config(c: ContainerDep) -> dict:
    return {"asr_enabled": c.speech.asr_enabled, "tts_enabled": c.speech.tts_enabled}


@router.post("/asr")
async def asr(
    c: ContainerDep,
    user: UserDep,
    file: Annotated[UploadFile, File()],
    duration_ms: Annotated[int, Form()] = 0,
    session_id: Annotated[uuid.UUID | None, Form()] = None,
) -> dict:
    audio = await file.read()
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise AppError("录音为空或超过 5MB")
    with usage_scope() as usage:
        text = await c.speech.transcribe(
            audio, file.filename or "audio.webm", file.content_type or "audio/webm", duration_ms
        )
    await c.practice.record_usage(session_id, user, usage)
    return {"text": text}


@router.post("/tts")
async def tts(body: TTSIn, c: ContainerDep, user: UserDep) -> Response:
    with usage_scope() as usage:
        audio = await c.speech.synthesize(body.text)
    await c.practice.record_usage(body.session_id, user, usage)
    return Response(content=audio, media_type="audio/mpeg")
