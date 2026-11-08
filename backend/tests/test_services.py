import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.core.config import ModelPrice, Settings
from app.core.errors import UpstreamError
from app.services.guard import mask_pii
from app.services.knowledge import parse_markdown
from app.services.llm import LLMGateway, usage_scope
from app.services.llm.usage import token_cost
from app.services.scenarios import ScenarioRegistry


def test_all_scenarios_valid(registry: ScenarioRegistry):
    assert {"S01", "S02", "S03"} <= set(registry.scenarios)
    for s in registry.scenarios.values():
        assert registry.rubric_for(s).dimensions
        assert s.key_objection_ids, f"{s.id} 至少需要一个关键异议"


def test_mask_pii():
    text = "联系我 13812345678 或 a.b@corp.com，身份证 11010119900307123X，座机 021-12345678"
    masked = mask_pii(text)
    for raw in ["13812345678", "a.b@corp.com", "11010119900307123X", "021-12345678"]:
        assert raw not in masked


def test_token_cost():
    assert float(token_cost(ModelPrice(input=2, output=8), 1_000_000, 500_000)) == 6.0
    assert token_cost(None, 100, 100) == 0


def test_parse_knowledge(settings: Settings):
    root = settings.knowledge_dir
    chunks = parse_markdown(root / "sales_objections.md", root)
    assert len(chunks) >= 3
    assert chunks[0].scenario_ids == ["S01", "S02"]
    assert "/" in chunks[0].title


async def test_gateway_masks_pii_and_records_usage(settings: Settings):
    gw = LLMGateway(settings)
    with usage_scope() as usage:
        await gw.text("hint", [HumanMessage(content="客户电话 13812345678")])
    assert usage.records[0].purpose == "hint"
    assert "13812345678" not in gw._prepare([HumanMessage(content="13812345678")])[0].content


class _Strict(BaseModel):
    must_exist: int


async def test_structured_output_failure_raises(settings: Settings):
    gw = LLMGateway(settings)
    with pytest.raises(UpstreamError):
        await gw.structured("hint", [SystemMessage(content="x")], _Strict)
