import asyncio
import shutil
import sys
from pathlib import Path

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
def test_scenarios_dir(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("scenarios")
    shutil.copytree(Path(__file__).parent / "fixtures" / "scenarios", root, dirs_exist_ok=True)
    source = Settings(_env_file=None).scenarios_dir / "rubrics" / "collection_default.yaml"
    shutil.copyfile(source, root / "rubrics" / source.name)
    return root


@pytest.fixture(scope="session")
def settings(test_scenarios_dir: Path) -> Settings:
    return Settings(_env_file=None, app_env="test", llm={"provider": "stub"}, scenarios_dir=test_scenarios_dir)


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
