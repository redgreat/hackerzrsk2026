"""启动入口：python -m app [--host 0.0.0.0] [--port 8000] [--reload]

Windows 下 psycopg 异步驱动需要 SelectorEventLoop，这里统一处理。
"""

import argparse
import asyncio
import sys

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    if args.reload:
        # reload 模式下 uvicorn 在子进程中使用 SelectorEventLoop
        uvicorn.run("app.main:create_app", factory=True, host=args.host, port=args.port, reload=True)
        return
    config = uvicorn.Config(
        "app.main:create_app", factory=True, host=args.host, port=args.port, proxy_headers=True
    )
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(uvicorn.Server(config).serve(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
