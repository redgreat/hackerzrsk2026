"""企业微信应用消息回调：在企业微信管理后台「接收消息」中配置 URL 为 https://<域名>/api/wecom/callback。"""

import xml.etree.ElementTree as ET

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import PlainTextResponse

from app.api.deps import ContainerDep
from app.core.errors import FeatureDisabled, Unauthorized
from app.services import wecom_crypto
from app.services.wecom_chat import parse_incoming

router = APIRouter(prefix="/wecom", tags=["wecom"])


def _require_chat(c) -> None:
    if not c.settings.wecom.chat_enabled:
        raise FeatureDisabled("企业微信应用对话未配置（需 WECOM__TOKEN、WECOM__ENCODING_AES_KEY）")


@router.get("/callback", response_class=PlainTextResponse)
async def verify_url(
    c: ContainerDep, msg_signature: str = "", timestamp: str = "", nonce: str = "", echostr: str = ""
) -> str:
    _require_chat(c)
    w = c.settings.wecom
    try:
        return wecom_crypto.verify_url(
            w.token, w.encoding_aes_key, w.corp_id, msg_signature, timestamp, nonce, echostr
        )
    except ValueError as exc:
        raise Unauthorized(f"回调验证失败：{exc}") from exc


@router.post("/callback", response_class=PlainTextResponse)
async def receive(
    c: ContainerDep,
    request: Request,
    background: BackgroundTasks,
    msg_signature: str = "",
    timestamp: str = "",
    nonce: str = "",
) -> str:
    _require_chat(c)
    w = c.settings.wecom
    # 企微要求 5 秒内应答：这里只做验签解密，耗时的模型调用放到后台任务
    envelope = ET.fromstring((await request.body()).decode("utf-8"))
    encrypted = envelope.findtext("Encrypt", "")
    if not encrypted or not wecom_crypto.verify_signature(
        w.token, msg_signature, timestamp, nonce, encrypted
    ):
        raise Unauthorized("回调签名校验失败")
    try:
        xml = wecom_crypto.decrypt(w.encoding_aes_key, encrypted, w.corp_id)
    except ValueError as exc:
        raise Unauthorized(f"回调解密失败：{exc}") from exc
    msg = parse_incoming(xml)
    if msg is not None:
        background.add_task(c.wecom_bot.handle, msg)
    return "success"
