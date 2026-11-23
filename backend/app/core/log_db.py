"""把 WARNING 及以上日志与 4xx/5xx 请求写入 app_logs 表。

写库在后台线程中完成，日志调用不会阻塞请求；队列满时丢弃，避免影响业务。
不记录请求体、对话内容与密钥。
"""

import logging
import queue
import threading
import traceback

import psycopg

ACCESS_LOGGER = "http.access"
_SKIP_PREFIXES = ("psycopg", "sqlalchemy", "httpx", "httpcore")
_queue: queue.Queue = queue.Queue(maxsize=2000)
_installed = False


class DbLogHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(_SKIP_PREFIXES):
            return
        try:
            row = {
                "level": record.levelname,
                "logger": record.name[:128],
                "message": record.getMessage()[:4000],
                "exc": "".join(traceback.format_exception(*record.exc_info))[:8000]
                if record.exc_info
                else None,
                "method": getattr(record, "method", None),
                "path": (getattr(record, "path", None) or "")[:256] or None,
                "status": getattr(record, "status", None),
            }
            _queue.put_nowait(row)
        except Exception:
            pass  # 队列满或格式化失败时静默丢弃


def _writer(conninfo: str) -> None:
    conn = None
    while True:
        row = _queue.get()
        try:
            if conn is None or conn.closed:
                conn = psycopg.connect(conninfo, autocommit=True)
            conn.execute(
                "INSERT INTO app_logs (level, logger, message, exc, method, path, status) "
                "VALUES (%(level)s, %(logger)s, %(message)s, %(exc)s, %(method)s, %(path)s, %(status)s)",
                row,
            )
        except Exception:
            if conn is not None:
                conn.close()
            conn = None  # 写库失败不影响应用，下次重连


def install(conninfo: str) -> None:
    """注册到根 logger，重复调用只生效一次。"""
    global _installed
    if _installed:
        return
    _installed = True
    logging.getLogger().addHandler(DbLogHandler())
    threading.Thread(target=_writer, args=(conninfo,), daemon=True, name="app-log-writer").start()
