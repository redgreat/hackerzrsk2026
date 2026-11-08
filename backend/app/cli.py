"""运维命令：

python -m app.cli init-db           执行 Alembic 迁移 + 创建 LangGraph checkpoint/store 表
python -m app.cli ingest-knowledge  将 knowledge/*.md 导入话术知识库
python -m app.cli check-scenarios   校验全部场景 / 评分表 YAML
"""

import argparse
import asyncio
import sys

from app.core.config import BACKEND_DIR, get_settings
from app.core.logging import setup_logging


async def _setup_langgraph() -> None:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.store.postgres.aio import AsyncPostgresStore

    from app.main import create_checkpoint_pool

    pool = create_checkpoint_pool(get_settings())
    await pool.open()
    try:
        await AsyncPostgresSaver(pool).setup()
        await AsyncPostgresStore(pool).setup()
    finally:
        await pool.close()


def init_db() -> None:
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    _run(_setup_langgraph())
    print("数据库初始化完成")


async def _ingest() -> int:
    from app.db.session import create_engine, create_session_factory
    from app.services.knowledge import KnowledgeBase
    from app.services.llm import usage_scope

    settings = get_settings()
    engine = create_engine(settings)
    try:
        with usage_scope() as usage:
            n = await KnowledgeBase(settings, create_session_factory(engine)).ingest_dir(
                settings.knowledge_dir
            )
        print(
            f"embedding 费用约 {usage.cost_yuan:.4f} 元"
            if usage.records
            else "未启用 embedding，使用关键词检索"
        )
        return n
    finally:
        await engine.dispose()


def check_scenarios() -> None:
    from app.services.scenarios import ScenarioRegistry

    reg = ScenarioRegistry.load(get_settings().scenarios_dir)
    for s in reg.scenarios.values():
        print(f"  {s.id} {s.name}（评分表 {s.scoring}，异议 {len(s.persona.objections)} 个）")
    print(f"校验通过：场景 {len(reg.scenarios)} 个，评分表 {len(reg.rubrics)} 个")


def _run(coro):
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    return asyncio.run(coro, loop_factory=loop_factory)


def main() -> None:
    setup_logging(get_settings().log_level)
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    parser.add_argument("command", choices=["init-db", "ingest-knowledge", "check-scenarios"])
    cmd = parser.parse_args().command
    if cmd == "init-db":
        init_db()
    elif cmd == "ingest-knowledge":
        print(f"已导入 {_run(_ingest())} 个知识片段")
    else:
        check_scenarios()


if __name__ == "__main__":
    main()
