import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.api import api_router
from app.core.config import Settings, get_settings
from app.core.container import Container
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging
from app.db.session import create_engine, create_session_factory
from app.graph.builder import build_practice_graph
from app.graph.state import PracticeContext
from app.services.knowledge import KnowledgeBase
from app.services.llm import LLMGateway
from app.services.practice import PracticeService
from app.services.scenarios import ScenarioRegistry
from app.services.speech import SpeechService
from app.services.wecom import WeComClient

logger = logging.getLogger(__name__)


def create_checkpoint_pool(settings: Settings) -> AsyncConnectionPool:
    return AsyncConnectionPool(
        settings.psycopg_conninfo,
        max_size=settings.db_pool_size,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=False,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    settings.validate_for_runtime()
    engine = create_engine(settings)
    sf = create_session_factory(engine)
    pool = create_checkpoint_pool(settings)
    await pool.open()
    try:
        scenarios = ScenarioRegistry.load(settings.scenarios_dir)
        llm = LLMGateway(settings)
        knowledge = KnowledgeBase(settings, sf)
        store = AsyncPostgresStore(pool)
        graph = build_practice_graph(AsyncPostgresSaver(pool), store)
        practice = PracticeService(
            graph, PracticeContext(llm=llm, scenarios=scenarios, knowledge=knowledge), sf
        )
        app.state.container = Container(
            settings=settings,
            engine=engine,
            session_factory=sf,
            scenarios=scenarios,
            llm=llm,
            knowledge=knowledge,
            speech=SpeechService(settings),
            wecom=WeComClient(settings.wecom),
            practice=practice,
        )
        logger.info("服务启动：模型=%s，场景 %d 个", settings.llm.provider, len(scenarios.scenarios))
        yield
        await practice.shutdown()
    finally:
        await pool.close()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(
        title="AI 客户陪练",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.app_env != "prod" else None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(api_router)

    dist = settings.frontend_dist
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            file = (dist / path).resolve()
            if path and file.is_file() and dist.resolve() in file.parents:
                return FileResponse(file)
            return FileResponse(dist / "index.html")

    return app
