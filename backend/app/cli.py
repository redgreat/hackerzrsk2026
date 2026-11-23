"""运维命令：

python -m app.cli init-db           执行 Alembic 迁移 + 创建 LangGraph checkpoint/store 表
python -m app.cli ingest-knowledge  将 knowledge/*.md 导入话术知识库
python -m app.cli check-scenarios   校验全部场景 / 评分表 / 题库 / 试卷 YAML
python -m app.cli create-admin --userid admin --password ******   创建或重置管理员账号
python -m app.cli import-recordings [--limit N] < urls.txt   从标准输入导入优质录音 URL（每行一条，不落盘）
python -m app.cli process-recordings [--limit N]   转写 + AI 分析待处理录音
"""

import argparse
import asyncio
import sys

from app.core.config import BACKEND_DIR, get_settings
from app.core.errors import AppError
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
    seed = get_settings().seed_admin
    if seed:
        _run(_seed_admin(seed.userid, seed.name, seed.password))
    print("数据库初始化完成")


async def _seed_admin(userid: str, name: str, password: str) -> None:
    from app.db.session import create_engine, create_session_factory
    from app.services.users import seed_admin_if_missing

    engine = create_engine(get_settings())
    try:
        created = await seed_admin_if_missing(create_session_factory(engine), userid, name, password)
        print(f"管理员 {userid}：{'已创建' if created else '已存在，未修改'}")
    finally:
        await engine.dispose()


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
        f"校验通过：场景 {len(reg.scenarios)} 个，评分表 {len(reg.rubrics)} 个，"
        f"题目 {len(exams.questions)} 道，试卷 {len(exams.papers)} 套"
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


async def _import_recordings(text: str, limit: int | None) -> None:
    from app.services import recording_source as src

    async def run(settings, sf, svc):
        try:
            items = src.parse_lines(text, settings.recordings)
        except AppError as exc:
            raise SystemExit(f"导入失败：{exc.message}") from None
        created, skipped = await svc.import_items(items[:limit] if limit else items, "url")
        print(f"导入完成：新增 {created} 条，已存在跳过 {skipped} 条")

    await _with_services(run)


async def _process_recordings(limit: int) -> None:
    async def run(settings, sf, svc):
        results = await svc.process_pending(limit)
        ok = sum(r["status"] == "ready" for r in results)
        for r in results:
            if r["status"] != "ready":
                print(f"  #{r['id']} 失败：{r['error']}")
        print(f"处理完成：成功 {ok} 条，失败 {len(results) - ok} 条（成功的录音需在管理后台审核发布）")

    await _with_services(run)


def _run(coro):
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    return asyncio.run(coro, loop_factory=loop_factory)


def main() -> None:
    setup_logging(get_settings().log_level)
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    parser.add_argument(
        "command",
        choices=[
            "init-db",
            "ingest-knowledge",
            "check-scenarios",
            "create-admin",
            "import-recordings",
            "process-recordings",
        ],
    )
    parser.add_argument("--userid")
    parser.add_argument("--name", default="")
    parser.add_argument("--password")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    cmd = args.command
    if cmd == "init-db":
        init_db()
    elif cmd == "ingest-knowledge":
        print(f"已导入 {_run(_ingest())} 个知识片段")
    elif cmd == "create-admin":
        if not args.userid or not args.password:
            parser.error("create-admin 需要 --userid 和 --password")
        _run(_create_admin(args.userid, args.name, args.password))
    elif cmd == "import-recordings":
        _run(_import_recordings(sys.stdin.read(), args.limit))
    elif cmd == "process-recordings":
        _run(_process_recordings(args.limit or 20))
    else:
        check_scenarios()


if __name__ == "__main__":
    main()
