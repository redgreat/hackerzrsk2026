"""企业微信应用对话通道：文字 / 语音（企微识别结果）→ 陪练会话 → 文字回复。

企微回调要求 5 秒内应答，因此回调只做验签解密并投递到后台任务；回复通过应用消息接口主动推送。
同一用户的消息串行处理，避免并发打乱对练顺序。
"""

import asyncio
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import WeComSettings
from app.core.errors import AppError
from app.db.models import PracticeSession, User
from app.services.practice import PracticeService
from app.services.scenarios import ScenarioRegistry
from app.services.users import upsert_user
from app.services.wecom import WeComClient

logger = logging.getLogger(__name__)
OUTCOME_TEXT = {"deal": "成功推进", "hangup": "客户挂断", "max_turns": "轮数用完", "user_end": "主动结束"}
DEDUP_TTL = 600

HELP_TEXT = (
    "AI 客户陪练\n"
    "· 回复场景编号（如 1 或 S01）开始练习\n"
    "· 练习中直接发文字或语音和客户对话\n"
    "· 回复「求助」获取一条话术提示\n"
    "· 回复「结束」生成评分报告\n"
    "· 回复「菜单」查看场景列表"
)


@dataclass
class Incoming:
    userid: str
    kind: str  # text / voice / enter
    content: str = ""
    msg_id: str = ""


def parse_incoming(xml: str) -> Incoming | None:
    root = ET.fromstring(xml)
    msg_type = root.findtext("MsgType", "")
    userid = root.findtext("FromUserName", "")
    msg_id = root.findtext("MsgId", "")
    if msg_type == "text":
        return Incoming(userid, "text", root.findtext("Content", "").strip(), msg_id)
    if msg_type == "voice":
        # 应用开启「接收语音识别结果」后，企微会随消息返回 Recognition 文本
        return Incoming(userid, "voice", root.findtext("Recognition", "").strip(), msg_id)
    if msg_type == "event" and root.findtext("Event", "") == "enter_agent":
        return Incoming(userid, "enter")
    return None


def parse_command(text: str, ongoing: bool, scenario_ids: list[str]) -> tuple[str, str | None]:
    """返回 (命令, 参数)。练习进行中，除求助/结束/帮助/菜单外的内容一律视为对话。"""
    t = text.strip()
    if t.lower() in {"帮助", "help", "?", "？"}:
        return "help", None
    if t in {"菜单", "场景", "列表"}:
        return "menu", None
    if t in {"求助", "提示"}:
        return ("hint", None) if ongoing else ("help", None)
    if t in {"结束", "结束练习", "报告", "生成报告"}:
        return "end", None
    if ongoing:
        return "message", t
    m = re.fullmatch(r"(?:开始|练习|start)?\s*(S\d{2}|\d{1,2})", t, re.IGNORECASE)
    if m:
        key = m.group(1).upper()
        if key.isdigit():
            idx = int(key) - 1
            if 0 <= idx < len(scenario_ids):
                return "start", scenario_ids[idx]
        elif key in scenario_ids:
            return "start", key
    return "unknown", None


class WeComChatBot:
    def __init__(
        self,
        cfg: WeComSettings,
        wecom: WeComClient,
        practice: PracticeService,
        scenarios: ScenarioRegistry,
        session_factory: async_sessionmaker[AsyncSession],
    ):
        self.cfg = cfg
        self.wecom = wecom
        self.practice = practice
        self.scenarios = scenarios
        self.sf = session_factory
        self._seen: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _duplicate(self, msg_id: str) -> bool:
        now = time.time()
        self._seen = {k: v for k, v in self._seen.items() if now - v < DEDUP_TTL}
        if msg_id in self._seen:
            return True
        self._seen[msg_id] = now
        return False

    async def handle(self, msg: Incoming) -> None:
        if msg.msg_id and self._duplicate(msg.msg_id):
            return
        async with self._locks.setdefault(msg.userid, asyncio.Lock()):
            try:
                user = await upsert_user(self.sf, msg.userid, "", "", "wecom")
                await self._dispatch(user, msg)
            except AppError as exc:
                await self._say(msg.userid, exc.message)
            except Exception:
                logger.exception("企微对话处理失败 user=%s", msg.userid)
                await self._say(msg.userid, "AI 服务开小差了，请稍后再试。")

    async def _say(self, userid: str, text: str) -> None:
        await self.wecom.send_text(userid, text)

    async def _dispatch(self, user: User, msg: Incoming) -> None:
        if msg.kind == "enter":
            return await self._say(msg.userid, HELP_TEXT)
        if msg.kind == "voice" and not msg.content:
            return await self._say(
                msg.userid,
                "没有识别到语音内容。请在企业微信应用设置中开启「接收语音识别结果」，或直接发送文字。",
            )
        if not msg.content:
            return await self._say(msg.userid, HELP_TEXT)

        active = await self.practice.active_session(user)
        scenario_ids = [s.id for s in self.scenarios.list()]
        cmd, arg = parse_command(msg.content, active is not None, scenario_ids)
        if cmd == "help":
            await self._say(msg.userid, HELP_TEXT)
        elif cmd == "menu" or cmd == "unknown":
            await self._say(msg.userid, self._menu(None if cmd == "menu" else "没有识别这条指令。"))
        elif cmd == "start":
            await self._start(user, arg)
        elif cmd == "hint":
            hint = await self.practice.hint(active.id, user)
            await self._say(msg.userid, f"教练提示：{hint}")
        elif cmd == "end":
            if active is None:
                return await self._last_report(user)
            await self.practice.end(active.id, user)
            await self._send_report(user, active.id, active.scenario_id, "本次练习已结束。")
        else:
            await self._chat(user, active, msg.content)

    def _menu(self, prefix: str | None) -> str:
        lines = [prefix] if prefix else []
        lines.append("请选择练习场景（回复编号或场景代号开始）：")
        for i, s in enumerate(self.scenarios.list(), 1):
            lines.append(f"{i}. {s.name}（{s.id}，难度 {s.difficulty}，约 {s.estimated_minutes} 分钟）")
        return "\n".join(lines)

    async def _start(self, user: User, scenario_id: str) -> None:
        scenario = self.scenarios.get(scenario_id)
        detail = await self.practice.start(user, scenario.id)
        first = detail["messages"][0] if detail["messages"] else None
        opening = (
            first["content"] if first and first["role"] == "customer" else "请先开口，和客户打个招呼吧。"
        )
        await self._say(
            user.userid,
            f"【{scenario.name}】\n"
            f"客户：{scenario.persona.name}（{scenario.persona.role}）\n"
            f"目标：{scenario.goal}\n\n"
            f"{scenario.persona.name}：{opening}\n\n"
            "直接回复文字或语音对话；回复「求助」获取提示，回复「结束」生成报告。",
        )

    async def _chat(self, user: User, active: PracticeSession, text: str) -> None:
        parts: list[str] = []
        status = "ongoing"
        errors: list[str] = []
        events = await self.practice.open_message_stream(active.id, user, text)
        async for ev in events:
            if ev["type"] == "token":
                parts.append(ev["text"])
            elif ev["type"] == "error":
                errors.append(ev["message"])
            elif ev["type"] == "done":
                status = ev["status"]
        if errors:
            return await self._say(user.userid, errors[0])
        reply = "".join(parts).strip()
        persona = self.scenarios.get(active.scenario_id).persona.name
        if reply:
            await self._say(user.userid, f"{persona}：{reply}")
        if status != "ongoing":
            await self._send_report(
                user, active.id, active.scenario_id, f"练习结束（{OUTCOME_TEXT.get(status, status)}）。"
            )

    async def _last_report(self, user: User) -> None:
        last = await self.practice.last_reported_session(user)
        if last is None:
            return await self._say(user.userid, "还没有完成的练习。" + "\n" + self._menu(None))
        await self._send_report(user, last.id, last.scenario_id, "这是你最近一次练习的报告。")

    async def _send_report(self, user: User, sid, scenario_id: str, header: str) -> None:
        report = await self.practice.report(sid, user)
        if report is None:
            return await self._say(user.userid, f"{header}\n报告生成中，稍后回复「报告」可查看。")
        lines = [
            header,
            f"本次得分：{report['total_score']} 分（{OUTCOME_TEXT.get(report['outcome'], report['outcome'])}，"
            f"{report['turns']} 轮，求助 {report['hints_used']} 次）",
            f"总评：{report['summary']}",
        ]
        if report["highlights"]:
            lines.append("亮点：" + "；".join(report["highlights"][:2]))
        if report["improvements"]:
            lines.append("改进：" + "；".join(report["improvements"][:2]))
        await self._say(user.userid, "\n".join(lines))
        if self.cfg.public_base_url:
            scenario = self.scenarios.get(scenario_id)
            await self.wecom.send_link_card(
                user.userid,
                f"评分报告 · {scenario.name}",
                f"总分 {report['total_score']}，点击查看逐轮点评、推荐话术与客户内心独白",
                f"{self.cfg.public_base_url.rstrip('/')}/report/{sid}",
            )
