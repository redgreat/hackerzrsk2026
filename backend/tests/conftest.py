import asyncio
import shutil
import sys
from importlib import import_module
from pathlib import Path

import pytest
import yaml
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from sqlalchemy.dialects.postgresql import insert

from app.core.config import Settings
from app.db.models import RubricVersion
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
    default = import_module("migrations.versions.0008_rubric_versions").DEFAULT
    (root / "rubrics" / "collection_default.yaml").write_text(
        yaml.safe_dump(default, allow_unicode=True), encoding="utf-8"
    )
    return root


@pytest.fixture(scope="session")
def settings(test_scenarios_dir: Path) -> Settings:
    return Settings(
        _env_file=None, app_env="test", llm={"provider": "stub"}, scenarios_dir=test_scenarios_dir
    )


@pytest.fixture(scope="session")
def registry(settings: Settings) -> ScenarioRegistry:
    return ScenarioRegistry.load(settings.scenarios_dir)


@pytest.fixture(scope="session")
def seed_test_rubrics(registry: ScenarioRegistry):
    def seed(conn):
        for rubric in registry.rubrics.values():
            conn.execute(
                insert(RubricVersion)
                .values(rubric_id=rubric.id, version=1, content=rubric.model_dump(mode="json"))
                .on_conflict_do_nothing()
            )

    return seed


@pytest.fixture
def ctx(settings: Settings, registry: ScenarioRegistry) -> PracticeContext:
    return PracticeContext(llm=LLMGateway(settings), scenarios=registry, knowledge=None)


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def graph(store: InMemoryStore):
    return build_practice_graph(InMemorySaver(), store)
