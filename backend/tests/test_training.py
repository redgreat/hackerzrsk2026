"""催收培训模块单测：密码、红线、判分、录音解析与脱敏、Paraformer 客户端、dbmcp 结果解析、题库加载。"""

import uuid

import pytest
from langgraph.types import Command

from app.core.errors import UpstreamError
from app.core.security import hash_password, verify_password
from app.graph import rules
from app.graph.schemas import DimensionScore
from app.services import exam_rules
from app.services import recording_rules as rr
from app.services.dbmcp import parse_rows
from app.services.exam_question_bank import QuestionDraft
from app.services.exams import ExamRegistry
from app.services.recording_source import excellent_calls_sql, normalize_url
from app.services.recordings import check_answer

# ---------- 账号 ----------


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert h.startswith("scrypt$") and "secret123" not in h
    assert verify_password("secret123", h)
    assert not verify_password("secret124", h)
    assert not verify_password("x", None) and not verify_password("x", "garbage")
    assert hash_password("secret123") != h  # 每次随机盐


# ---------- 红线 ----------


def test_red_line_cap_and_merge(registry):
    rubric = registry.rubrics["collection_default"]
    assert rubric.red_lines and rubric.red_line_cap == 59
    dims = [DimensionScore(name=d.name, score=5) for d in rubric.dimensions]
    assert rules.total_score(rubric, dims, 0) == 100
    assert rules.total_score(rubric, dims, 0, red_line_hit=True) == 59
    thoughts = [{"turn": 2, "red_line": rubric.red_lines[0]}, {"turn": 3, "red_line": None}]
    v = rules.red_line_violations(thoughts, [f"第2轮：{rubric.red_lines[0]}", "第4轮：越权承诺减免"])
    assert v == [
        {"turn": 2, "red_line": rubric.red_lines[0]},
        {"turn": None, "red_line": "第4轮：越权承诺减免"},
    ]


def _cfg():
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


async def _run(graph, ctx, payload, cfg):
    async for _ in graph.astream(payload, cfg, context=ctx, stream_mode=["custom", "updates"]):
        pass
    return (await graph.aget_state(cfg)).values


async def test_collection_red_line_caps_report(graph, ctx):
    cfg = _cfg()
    scenario = ctx.scenarios.get("S01").model_copy(update={"scoring": "collection_default"})
    await _run(
        graph,
        ctx,
        {
            "session_id": "s",
            "user_id": "u1",
            "scenario_id": scenario.id,
            "scenario_snapshot": ctx.scenarios.snapshot(scenario),
        },
        cfg,
    )
    v = await _run(
        graph, ctx, Command(resume={"type": "message", "text": "你再不还钱就等着坐牢吧，老赖"}), cfg
    )
    said = v["transcript"][-2]
    assert said["role"] == "user" and said["meta"]["red_line"]
    assert said["trust_delta"] <= -20
    v = await _run(graph, ctx, Command(resume={"type": "end"}), cfg)
    report = v["report"]
    assert report["red_lines"] and report["red_lines"][0]["turn"] == 1
    assert report["total_score"] <= 59


async def test_sales_scenario_has_no_red_lines(graph, ctx):
    cfg = _cfg()
    await _run(graph, ctx, {"session_id": "s", "user_id": "u1", "scenario_id": "S01"}, cfg)
    await _run(graph, ctx, Command(resume={"type": "message", "text": "你这个老赖，滚"}), cfg)
    v = await _run(graph, ctx, Command(resume={"type": "end"}), cfg)
    assert v["report"]["red_lines"] == []


# ---------- 判分 ----------


@pytest.mark.parametrize(
    ("qtype", "answer", "chosen", "credit"),
    [
        ("single", [1], [1], 1.0),
        ("single", [1], [0], 0.0),
        ("single", [1], [], 0.0),
        ("single", [1], [1, 2], 0.0),
        ("judge", [0], [0], 1.0),
        ("multi", [0, 1, 3], [3, 1, 0], 1.0),
        ("multi", [0, 1, 3], [0, 1], 0.5),
        ("multi", [0, 1, 3], [0, 2], 0.0),
        ("multi", [0, 1, 3], None, 0.0),
    ],
)
def test_question_credit(qtype, answer, chosen, credit):
    assert exam_rules.question_credit(qtype, answer, chosen) == credit


def test_grade_weighted_sections():
    sections = [
        {
            "type": "quiz",
            "title": "知识",
            "weight": 40,
            "items": [
                {"key": "q:1", "type": "single", "answer": [0]},
                {"key": "q:2", "type": "multi", "answer": [0, 1]},
            ],
        },
        {"type": "roleplay", "title": "对练", "weight": 60, "items": [{"key": "s:C01"}, {"key": "s:C02"}]},
    ]
    r = exam_rules.grade(sections, {"q:1": [0], "q:2": [1]}, {"s:C01": 80, "s:C02": None})
    assert [s["score"] for s in r["sections"]] == [75.0, 40.0]
    assert r["total"] == round((75 * 40 + 40 * 60) / 100)
    assert r["sections"][0]["items"][1]["credit"] == 0.5


def test_check_answer_helper():
    assert check_answer("multi", [0, 2], [2, 0]) and not check_answer("multi", [0, 2], [0])
    assert check_answer("single", [1], [1]) and not check_answer("judge", [0], [1])


# ---------- 题库与试卷 ----------


def test_exam_registry_loads(settings, registry):
    reg = ExamRegistry.load(settings.exams_dir, registry)
    assert {"E01", "T01", "T02", "T03"} <= set(reg.papers)
    assert [section.count for section in reg.papers["E01"].sections] == [12, 2]


@pytest.mark.parametrize(
    "changes",
    [
        {"correct_index": 4},
        {"options": ["先核实", "立即披露", "重复", "重 复"]},
        {"options": ["A"]},
    ],
)
def test_question_validation(changes):
    raw = {
        "topic": "核实身份",
        "stem": "什么情况下先核实身份？",
        "options": ["先核实", "立即披露", "询问同事", "直接结束"],
        "correct_index": 0,
        "explanation": "保护客户信息。",
    }
    with pytest.raises(ValueError):
        QuestionDraft.model_validate(raw | changes)


def test_paper_with_unknown_scenario_rejected(tmp_path, registry):
    (tmp_path / "questions").mkdir()
    (tmp_path / "papers").mkdir()
    (tmp_path / "papers" / "p.yaml").write_text(
        "id: P\nname: p\nsections:\n  - {type: roleplay, title: t, weight: 1, scenario_ids: [NOPE]}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="不存在的场景"):
        ExamRegistry.load(tmp_path, registry)


# ---------- 录音解析与脱敏 ----------


def test_mask_transcript_text():
    t = rr.mask_transcript_text("请问是李建国先生吗？电话 13812345678，车牌浙A12345，住在解放路100号3栋")
    assert "李先生" in t and "建国" not in t
    assert "[手机号]" in t and "[车牌]" in t and "[地址]" in t


def test_parse_single_channel_diarization_and_agent_detection():
    result = {
        "transcripts": [
            {
                "channel_id": 0,
                "sentences": [
                    {"begin_time": 0, "end_time": 900, "text": "喂？", "speaker_id": 1},
                    {
                        "begin_time": 1000,
                        "end_time": 3000,
                        "text": "您好，我这边是贷后服务中心的，工号 1024。",
                        "speaker_id": 0,
                    },
                    {"begin_time": 3200, "end_time": 4000, "text": "提醒您本期月供还没还。", "speaker_id": 0},
                    {"begin_time": 4500, "end_time": 5000, "text": "  ", "speaker_id": 1},
                    {"begin_time": 9000, "end_time": 9500, "text": "知道了。", "speaker_id": 1},
                ],
            }
        ]
    }
    sentences = rr.parse_paraformer(result)
    assert len(sentences) == 4
    assert rr.detect_agent_speaker(sentences) == 0
    t = rr.build_transcript(sentences)
    assert [x["speaker"] for x in t] == ["customer", "agent", "customer"]
    assert t[1]["text"].endswith("月供还没还。") and t[1]["end_ms"] == 4000  # 相邻同人合并
    assert rr.transcript_prompt_text(t).splitlines()[1].startswith("[1] 坐席：")
    assert rr.duration_seconds(result, t) == 10


def test_parse_multi_channel_uses_channel_as_speaker():
    result = {
        "properties": {"original_duration_in_milliseconds": 12000},
        "transcripts": [
            {"channel_id": 1, "sentences": [{"begin_time": 2000, "end_time": 3000, "text": "是我。"}]},
            {
                "channel_id": 0,
                "sentences": [{"begin_time": 0, "end_time": 1500, "text": "您好请问是王先生吗"}],
            },
        ],
    }
    t = rr.build_transcript(rr.parse_paraformer(result))
    assert [x["speaker"] for x in t] == ["agent", "customer"]
    assert rr.duration_seconds(result, t) == 12


# ---------- 数据来源 ----------


def test_parse_rows_formats():
    assert parse_rows('{"rows": [{"a": 1}], "count": 1}') == [{"a": 1}]
    assert parse_rows('{"columns": ["a", "b"], "rows": [[1, 2]]}') == [{"a": 1, "b": 2}]
    assert parse_rows('[{"a": 1}]') == [{"a": 1}]
    with pytest.raises(UpstreamError):
        parse_rows('{"foo": 1}')


def test_excellent_calls_sql_covers_all_shards():
    sql = excellent_calls_sql(10, limit=50)
    assert sql.count("JOIN recall_record_") == 10 and "recall_record_9" in sql
    assert sql.count("a.deleted = 0") == 10
    assert sql.rstrip().endswith("LIMIT 50") and "callCenterPath" in sql
    assert normalize_url("rec/1.mp3", "https://cc.example.com/") == "https://cc.example.com/rec/1.mp3"
    assert normalize_url("https://oss/1.mp3", "https://cc") == "https://oss/1.mp3"
