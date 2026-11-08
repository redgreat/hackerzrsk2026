from app.graph import rules
from app.graph.schemas import CoachOutput, DimensionScore, TurnEvaluation


def _ev(delta, resolved=(), hangup=False):
    return TurnEvaluation(
        trust_delta=delta, resolved_objection_ids=list(resolved), inner_thought="x", hangup=hangup
    )


def test_delta_is_clamped(registry):
    s = registry.get("S01")
    o = rules.apply_evaluation(s, 30, ["price", "risk", "service"], 1, _ev(80))
    assert o.delta == s.state_rules.max_gain_per_turn
    o = rules.apply_evaluation(s, 30, ["price"], 1, _ev(-80))
    assert o.status == "hangup" and o.trust_after == 5


def test_unknown_objection_ids_ignored(registry):
    s = registry.get("S01")
    o = rules.apply_evaluation(s, 30, ["price", "risk"], 1, _ev(5, ["foo", "price"]))
    assert o.resolved == ["price"] and o.open_objections == ["risk"]


def test_no_deal_while_key_objection_open(registry):
    s = registry.get("S01")
    o = rules.apply_evaluation(s, 70, ["price", "service"], 6, _ev(15))
    assert o.status == "ongoing"
    assert o.trust_after == s.state_rules.deal_threshold - 1


def test_no_deal_before_min_turns(registry):
    s = registry.get("S01")
    o = rules.apply_evaluation(s, 70, ["service"], 2, _ev(15))
    assert o.status == "ongoing"
    o = rules.apply_evaluation(s, 70, ["service"], 4, _ev(15))
    assert o.status == "deal"


def test_max_turns_and_hangup_flag(registry):
    s = registry.get("S01")
    assert rules.apply_evaluation(s, 40, ["price"], s.max_turns, _ev(0)).status == "max_turns"
    assert rules.apply_evaluation(s, 40, ["price"], 1, _ev(0, hangup=True)).status == "hangup"


def test_total_score_with_hint_penalty(registry):
    rubric = registry.rubrics["sales_default"]
    out = CoachOutput(
        summary="s", dimension_scores=[DimensionScore(name=d.name, score=5) for d in rubric.dimensions]
    )
    dims = rules.normalize_dimensions(rubric, out)
    assert rules.total_score(rubric, dims, 0) == 100
    assert rules.total_score(rubric, dims, 2) == 96
    assert rules.total_score(rubric, dims, 50) == 90


def test_missing_dimension_filled(registry):
    rubric = registry.rubrics["sales_default"]
    dims = rules.normalize_dimensions(rubric, CoachOutput(summary="s", dimension_scores=[]))
    assert [d.name for d in dims] == [d.name for d in rubric.dimensions]
    assert all(d.score == 3 for d in dims)
