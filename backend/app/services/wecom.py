"""企业微信自建应用：网页授权（OAuth2 snsapi_base）换取成员身份。"""

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from app.core.config import WeComSettings
from app.core.errors import FeatureDisabled, Unauthorized, UpstreamError

TEXT_MAX_BYTES = 2000


def split_text(text: str, limit: int = TEXT_MAX_BYTES) -> list[str]:
    """按 UTF-8 字节数切分，不切断字符。"""
    chunks, cur = [], ""
    for ch in text:
        if cur and len((cur + ch).encode("utf-8")) > limit:
            chunks.append(cur)
            cur = ""
        cur += ch
    return chunks + ([cur] if cur or not chunks else [])


@dataclass
class WeComUser:
    userid: str
    name: str = ""
    department: str = ""


class WeComClient:
    def __init__(self, cfg: WeComSettings):
        self.cfg = cfg
        self._token: str | None = None
        self._token_expire_at = 0.0
        self._lock = asyncio.Lock()

    def oauth_url(self, redirect_uri: str, state: str = "coach") -> str:
        if not self.cfg.enabled:
            raise FeatureDisabled("企业微信未配置")
        return (
            "https://open.weixin.qq.com/connect/oauth2/authorize"
            f"?appid={self.cfg.corp_id}&redirect_uri={quote(redirect_uri, safe='')}"
            f"&response_type=code&scope=snsapi_base&state={state}&agentid={self.cfg.agent_id}#wechat_redirect"
        )

    def qr_login_url(self, redirect_uri: str, state: str = "coach") -> str:
        """电脑浏览器扫码登录（企微自建应用 CorpApp），回调带 code 到 redirect_uri。"""
        if not self.cfg.enabled:
            raise FeatureDisabled("企业微信未配置")
        return (
            "https://login.work.weixin.qq.com/wwlogin/sso/login"
            f"?login_type=CorpApp&appid={self.cfg.corp_id}&agentid={self.cfg.agent_id}"
            f"&redirect_uri={quote(redirect_uri, safe='')}&state={state}"
        )

    async def _get(self, path: str, **params) -> dict:
        async with httpx.AsyncClient(base_url=self.cfg.api_base, timeout=10) as client:
            resp = await client.get(path, params=params)
        data = resp.json()
        if data.get("errcode", 0) != 0:
            raise UpstreamError(f"企业微信接口错误：{data.get('errcode')} {data.get('errmsg')}")
        return data

    async def access_token(self) -> str:
        async with self._lock:
            if self._token and time.time() < self._token_expire_at:
                return self._token
            data = await self._get("/cgi-bin/gettoken", corpid=self.cfg.corp_id, corpsecret=self.cfg.secret)
            self._token = data["access_token"]
            self._token_expire_at = time.time() + int(data.get("expires_in", 7200)) - 300
            return self._token

    async def _post(self, path: str, body: dict) -> dict:
        token = await self.access_token()
        async with httpx.AsyncClient(base_url=self.cfg.api_base, timeout=10) as client:
            resp = await client.post(path, params={"access_token": token}, json=body)
        data = resp.json()
        if data.get("errcode", 0) != 0:
            raise UpstreamError(f"企业微信发送失败：{data.get('errcode')} {data.get('errmsg')}")
        return data

    async def send_text(self, userid: str, text: str) -> None:
        """向成员发送应用文本消息（单条上限 2048 字节，超长自动分段）。"""
        for chunk in split_text(text):
            await self._post(
                "/cgi-bin/message/send",
                {
                    "touser": userid,
                    "msgtype": "text",
                    "agentid": int(self.cfg.agent_id),
                    "text": {"content": chunk},
                },
            )

    async def send_link_card(self, userid: str, title: str, desc: str, url: str) -> None:
        await self._post(
            "/cgi-bin/message/send",
            {
                "touser": userid,
                "msgtype": "textcard",
                "agentid": int(self.cfg.agent_id),
                "textcard": {
                    "title": title[:128],
                    "description": desc[:512],
                    "url": url,
                    "btntxt": "查看详情",
                },
            },
        )

    async def user_by_code(self, code: str) -> WeComUser:
        if not self.cfg.enabled:
            raise FeatureDisabled("企业微信未配置")
        data = await self._get("/cgi-bin/auth/getuserinfo", access_token=await self.access_token(), code=code)
        userid = data.get("userid") or data.get("UserId")
        if not userid:
            raise Unauthorized("仅限企业成员使用")
        user = WeComUser(userid=userid)
        try:
            detail = await self._get(
                "/cgi-bin/user/get", access_token=await self.access_token(), userid=userid
            )
            user.name = detail.get("name", "")
            user.department = ",".join(str(d) for d in detail.get("department", []))
        except UpstreamError:
            pass  # 读取成员详情需要通讯录权限，缺权限时只用 userid
        return user
