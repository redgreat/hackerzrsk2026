"""共享费用落库兼容陪练会话和未关联会话的录音分析。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from app.db.usage import add_usage
from app.services.llm.usage import UsageRecord, UsageScope


def test_recording_usage_without_session_or_user():
    db = Mock()
    usage = UsageScope(records=[UsageRecord(purpose="analyst", model="stub", cost_yuan=Decimal("0.1"))])
    add_usage(db, None, None, usage)
    row = db.add.call_args.args[0]
    assert row.session_id is None and row.user_id is None
    assert row.purpose == "analyst" and row.cost_yuan == Decimal("0.1")


def test_practice_usage_accumulates_session_cost():
    db = Mock()
    session = SimpleNamespace(id="session", prompt_tokens=10, completion_tokens=5, cost_yuan=Decimal("0.2"))
    usage = UsageScope(
        records=[
            UsageRecord(
                purpose="coach", model="stub", prompt_tokens=3, completion_tokens=2, cost_yuan=Decimal("0.1")
            )
        ]
    )
    add_usage(db, session, 1, usage)
    assert (session.prompt_tokens, session.completion_tokens, session.cost_yuan) == (13, 7, Decimal("0.3"))
    row = db.add.call_args.args[0]
    assert row.session_id == session.id and row.user_id == 1
