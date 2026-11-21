"""dbmcp（公司数据库 MCP 服务）最小客户端：SSE 传输 + JSON-RPC，只用于只读查询导入优质录音。

协议：GET /mcp/sse 拿到 endpoint → POST initialize / notifications/initialized / tools/call，
响应经 SSE 流按 id 回传。访问密钥只从配置读取（RECORDINGS__DBMCP_KEY），不打印。
"""

import asyncio
import contextlib
import json
import logging

import httpx

from app.core.errors import FeatureDisabled, UpstreamError

logger = logging.getLogger(__name__)


class DbMcpClient:
    def __init__(self, url: str, key: str | None, timeout: float = 120):
        if not key:
            raise FeatureDisabled("未配置 RECORDINGS__DBMCP_KEY")
        self.url = url
        self.headers = {"X-Access-Key": key}
        self.timeout = timeout

    async def call_tool(self, name: str, arguments: dict) -> str:
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, read=None)) as client:
            endpoint: asyncio.Future[str] = asyncio.get_running_loop().create_future()
            pending: dict[int, asyncio.Future[dict]] = {}

            async def reader() -> None:
                async with client.stream("GET", self.url, headers=self.headers) as resp:
                    if resp.status_code >= 400:
                        endpoint.set_exception(UpstreamError(f"dbmcp 连接失败（{resp.status_code}）"))
                        return
                    event = None
                    async for line in resp.aiter_lines():
                        if line.startswith("event:"):
                            event = line[6:].strip()
                        elif line.startswith("data:"):
                            data = line[5:].strip()
                            if event == "endpoint" and not endpoint.done():
                                endpoint.set_result(data)
                            elif data.startswith("{"):
                                msg = json.loads(data)
                                fut = pending.pop(msg.get("id"), None)
                                if fut and not fut.done():
                                    fut.set_result(msg)

            task = asyncio.create_task(reader())
            try:
                post_url = await asyncio.wait_for(endpoint, 30)

                async def rpc(i: int | None, method: str, params: dict) -> dict | None:
                    body = {"jsonrpc": "2.0", "method": method, "params": params}
                    fut = None
                    if i is not None:
                        body["id"] = i
                        fut = pending[i] = asyncio.get_running_loop().create_future()
                    resp = await client.post(post_url, json=body, headers=self.headers)
                    if resp.status_code >= 400:
                        raise UpstreamError(f"dbmcp 请求失败（{resp.status_code}）：{resp.text[:200]}")
                    return await asyncio.wait_for(fut, self.timeout) if fut else None

                await rpc(
                    1,
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "ai-coach", "version": "1"},
                    },
                )
                await rpc(None, "notifications/initialized", {})
                res = await rpc(2, "tools/call", {"name": name, "arguments": arguments})
            finally:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        if "error" in res:
            raise UpstreamError(f"dbmcp 调用失败：{res['error'].get('message')}")
        result = res["result"]
        text = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        if result.get("isError"):
            raise UpstreamError(f"dbmcp 查询报错：{text[:300]}")
        return text

    async def query(self, connection_id: int, sql: str) -> list[dict]:
        return parse_rows(await self.call_tool("execute_query", {"connection_id": connection_id, "sql": sql}))


def parse_rows(text: str) -> list[dict]:
    """兼容常见返回格式：行数组 / {"rows": [...]} / {"columns": [...], "rows": [[...]]} / {"data": [...]}。"""
    data = json.loads(text)
    if isinstance(data, dict):
        for key in ("rows", "data", "results", "records"):
            if key in data:
                rows = data[key]
                if rows and isinstance(rows[0], list) and "columns" in data:
                    cols = [c if isinstance(c, str) else c.get("name") for c in data["columns"]]
                    return [dict(zip(cols, r, strict=False)) for r in rows]
                return rows
        raise UpstreamError(f"无法识别的查询结果格式：{list(data)[:5]}")
    return data
