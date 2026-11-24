"""将项目话术原稿迁入数据库，并保留录音检索资料。"""

import hashlib
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_knowledge_scripts"
down_revision = "0008_rubric_versions"
branch_labels = None
depends_on = None

SEED = [
    (
        "客户服务话术.md",
        "贷后核实与还款流程 / 先核实对象",
        "按机构规定完成身份核实后，再沟通具体账户情况。身份无法确认时，说明核实要求，提供可自行核验的官方联系方式。涉及第三方时避免披露债务信息。",
        ["贷后", "身份核实", "还款核对"],
    ),
    (
        "客户服务话术.md",
        "贷后核实与还款流程 / 核对付款状态",
        "客户表示已经付款时，先确认交易是否成功、付款渠道和待核实事项。发现支付端和系统记录不一致时，引导通过官方渠道提交核查所需信息，核查完成前避免要求重复付款或保证到账。",
        ["贷后", "身份核实", "还款核对"],
    ),
    (
        "客户服务话术.md",
        "贷后核实与还款流程 / 结束前确认行动",
        "简短复述已确认的事实和当前待核实事项。与客户确认下一步由谁做、通过什么官方渠道完成。客户尚未确认的计划按待核实记录。",
        ["贷后", "身份核实", "还款核对"],
    ),
    (
        "投诉处理话术.md",
        "贷后异议与合规沟通 / 接住情绪再问事实",
        "先用一句话确认客户的担忧，再问一个能推进处理的问题。避免争辩，按本机构流程说明目前能核查什么。",
        ["贷后", "情绪安抚", "合规表达"],
    ),
    (
        "投诉处理话术.md",
        "贷后异议与合规沟通 / 说明申请和审核边界",
        "客户提出困难或减免诉求时，先了解现状，再说明可咨询的官方渠道和申请流程。明确申请、审核和结果是不同阶段，按实际权限解释可办理事项。",
        ["贷后", "情绪安抚", "合规表达"],
    ),
    (
        "投诉处理话术.md",
        "贷后异议与合规沟通 / 分步说明解决方案",
        "先给出客户当下可以做的一步，再根据核实结果解释后续选项。确认客户已理解，并准确记录双方确认的安排。",
        ["贷后", "情绪安抚", "合规表达"],
    ),
]


def upgrade() -> None:
    scripts = op.create_table(
        "knowledge_scripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String(64)), nullable=False),
        sa.Column("scenario_ids", postgresql.ARRAY(sa.String(32)), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
    )
    db = op.get_bind()
    originals = {item[0] for item in SEED}
    bundled = [(source, title, content, tags, []) for source, title, content, tags in SEED]
    other = [
        tuple(row)
        for row in db.execute(
            sa.text(
                "SELECT source, title, content, tags, scenario_ids FROM knowledge_chunks WHERE source LIKE '%.md'"
            )
        )
        if row.source not in originals
    ]
    for original, title, content, tags, scenario_ids in bundled + other:
        script_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{original}|{title}|{content}")
        source = f"script:{script_id}"
        fingerprint = hashlib.sha256(f"{source}|{title}|{content}".encode()).hexdigest()
        category = title.split(" / ", 1)[0][:64] or "通用话术"
        db.execute(
            scripts.insert().values(
                id=script_id,
                category=category,
                title=title,
                content=content,
                enabled=True,
                tags=tags,
                scenario_ids=scenario_ids,
            )
        )
        found = db.execute(
            sa.text(
                "UPDATE knowledge_chunks SET source=:source, content_hash=:fingerprint "
                "WHERE source=:original AND title=:title AND content=:content "
                "AND id=(SELECT min(id) FROM knowledge_chunks "
                "WHERE source=:original AND title=:title AND content=:content)"
            ),
            dict(source=source, fingerprint=fingerprint, original=original, title=title, content=content),
        )
        if not found.rowcount:
            db.execute(
                sa.text(
                    "INSERT INTO knowledge_chunks (source,title,content,tags,scenario_ids,content_hash) "
                    "VALUES (:source,:title,:content,:tags,:scenario_ids,:fingerprint)"
                ),
                dict(
                    source=source,
                    title=title,
                    content=content,
                    tags=tags,
                    scenario_ids=scenario_ids,
                    fingerprint=fingerprint,
                ),
            )
    db.execute(sa.text("DELETE FROM knowledge_chunks WHERE source LIKE '%.md'"))


def downgrade() -> None:
    # 降级保留可检索内容，并把来源改回可被升级脚本识别的格式。
    op.execute("UPDATE knowledge_chunks SET source = source || '.md' WHERE source LIKE 'script:%'")
    op.drop_table("knowledge_scripts")
