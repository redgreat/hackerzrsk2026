import asyncio
import sys

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from app.core.config import Settings
from app.graph.builder import build_practice_graph
from app.graph.state import PracticeContext
from app.services.llm import LLMGateway
from app.services.scenarios import ScenarioRegistry


def pytest_asyncio_loop_factories(config, item):
    # psycopg 异步驱动在 Windows 上需要 SelectorEventLoop
    if sys.platform == "win32":
        return {"selector": asyncio.SelectorEventLoop}
    return None


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(_env_file=None, app_env="test", llm={"provider": "stub"})


@pytest.fixture(scope="session")
def registry(settings: Settings) -> ScenarioRegistry:
    return ScenarioRegistry.load(settings.scenarios_dir)


@pytest.fixture
def ctx(settings: Settings, registry: ScenarioRegistry) -> PracticeContext:
    return PracticeContext(llm=LLMGateway(settings), scenarios=registry, knowledge=None)


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def graph(store: InMemoryStore):
    return build_practice_graph(InMemorySaver(), store)
