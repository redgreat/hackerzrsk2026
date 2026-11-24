"""运维命令：

python -m app.cli init-db           执行 Alembic 迁移 + 创建 LangGraph checkpoint/store 表
python -m app.cli check-scenarios   校验场景、评分表与试卷模板 YAML
python -m app.cli create-admin --userid admin --password ******   创建或重置管理员账号
python -m app.cli import-recordings [--file data/private/x.json] [--limit N]   导入优质录音（默认经 dbmcp）
python -m app.cli import-transcripts --file ../data/private/x.json   导入已有转写快照和待审核事件
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


def check_scenarios() -> None:
    from app.services.exams import ExamRegistry
    from app.services.scenarios import ScenarioRegistry

    settings = get_settings()
    reg = ScenarioRegistry.load(settings.scenarios_dir)
    for s in reg.scenarios.values():
        print(f"  {s.id} {s.name}（评分表 {s.scoring}，异议 {len(s.persona.objections)} 个）")
    exams = ExamRegistry.load(settings.exams_dir, reg)
    for p in exams.papers.values():
        print(f"  {p.id} {p.name}（{p.kind}，{len(p.sections)} 个部分，及格 {p.pass_score}）")
    print(
        f"校验通过：本地场景定义 {len(reg.scenarios)} 个，本地评分表定义 {len(reg.rubrics)} 个，"
        f"试卷模板 {len(exams.papers)} 套"
    )


async def _with_services(fn):
    """组装录音服务所需依赖（不启动 Web 服务）。"""
    from app.db.session import create_engine, create_session_factory
    from app.services.knowledge import KnowledgeBase
    from app.services.llm import LLMGateway
    from app.services.recordings import RecordingService
    from app.services.scenarios import ScenarioRegistry

    settings = get_settings()
    engine = create_engine(settings)
    sf = create_session_factory(engine)
    try:
        svc = RecordingService(
            settings,
            sf,
            LLMGateway(settings),
            ScenarioRegistry.load(settings.scenarios_dir),
            KnowledgeBase(settings, sf),
        )
        return await fn(settings, sf, svc)
    finally:
        await engine.dispose()


async def _create_admin(userid: str, name: str, password: str) -> None:
    from app.services.users import create_or_reset_admin

    async def run(settings, sf, svc):
        user = await create_or_reset_admin(sf, userid, name, password)
        print(f"管理员已就绪：{user.userid}")

    await _with_services(run)


async def _import_recordings(file: str | None, limit: int | None) -> None:
    from pathlib import Path

    from app.services import recording_source as src

    async def run(settings, sf, svc):
        if file:
            items, source = src.load_file(Path(file), settings.recordings), "file"
        else:
            items, source = await src.fetch_from_dbmcp(settings.recordings, limit), "dbmcp"
        created, skipped = await svc.import_items(items[:limit] if limit else items, source)
        print(f"导入完成：新增 {created} 条，已存在跳过 {skipped} 条")

    await _with_services(run)


def _run(coro):
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    return asyncio.run(coro, loop_factory=loop_factory)


async def _import_transcripts(file: str) -> None:
    from pathlib import Path

    from app.db.session import create_engine, create_session_factory
    from app.services.transcripts import import_file

    engine = create_engine(get_settings())
    try:
        counts = await import_file(create_session_factory(engine), Path(file))
        print(
            f"导入完成：新增快照 {counts['snapshots_created']}，事件 {counts['events_created']}；全部待审核"
        )
    finally:
        await engine.dispose()


async def _clean_training(file: str) -> None:
    from pathlib import Path

    from app.db.session import create_engine, create_session_factory
    from app.services.llm import LLMGateway
    from app.services.training_cleanup import cleanup_file

    settings = get_settings()
    engine = create_engine(settings)
    try:
        result = await cleanup_file(create_session_factory(engine), LLMGateway(settings), Path(file))
        print(f"清洗完成：结果 #{result['id']}，分流 {result['status']}；未启用检索")
    finally:
        await engine.dispose()


def main() -> None:
    setup_logging(get_settings().log_level)
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    parser.add_argument(
        "command",
        choices=[
            "init-db",
            "check-scenarios",
            "create-admin",
            "import-recordings",
            "import-transcripts",
            "clean-training",
        ],
    )
    parser.add_argument("--userid")
    parser.add_argument("--name", default="")
    parser.add_argument("--password")
    parser.add_argument("--file", help="录音/转写 JSON 文件（放 data/private/，不要提交）")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    cmd = args.command
    if cmd == "init-db":
        init_db()
    elif cmd == "create-admin":
        if not args.userid or not args.password:
            parser.error("create-admin 需要 --userid 和 --password")
        _run(_create_admin(args.userid, args.name, args.password))
    elif cmd == "import-recordings":
        _run(_import_recordings(args.file, args.limit))
    elif cmd == "import-transcripts":
        if not args.file:
            parser.error("import-transcripts 需要 --file")
        _run(_import_transcripts(args.file))
    elif cmd == "clean-training":
        if not args.file:
            parser.error("clean-training 需要 --file（已去标识输入）")
        _run(_clean_training(args.file))
    else:
        check_scenarios()


if __name__ == "__main__":
    main()
