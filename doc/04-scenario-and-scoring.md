# 04 场景与评分设计

## 1. 设计原则

- 场景 = 客户画像 + 隐藏状态 + 结束规则 + 评分表，全部 YAML 配置。
- 业务专家、培训负责人可以不写代码直接新增/修改场景。
- 评分标准由对应业务专家共同制定，避免用一套销售标准评价所有客户沟通岗位。

## 2. 场景 YAML 规范（草案）

```yaml
id: S01
name: 情绪激动的投诉客户
department: [客服, 服务]
difficulty: 2            # 1~5
max_turns: 15
estimated_minutes: 5

background: |
  （给员工看的场景说明）客户因系统故障影响营业，第一次报障后没有收到反馈，
  再次来电时情绪激动。
goal: 安抚情绪，确认诉求，给出明确处理节点并约定回访。

persona:
  name: 赵女士
  role: 门店店长
  personality: 性子急、情绪激动，但讲道理
  speaking_style: 语速快，最反感推诿和打官腔
  hidden_needs:            # 客户真实关心但不会主动说的
    - 被重视、被道歉
    - 得到明确回复时间
  objections:              # 隐藏异议，被有效化解才会移除
    - id: emotion
      text: 觉得被敷衍
      key: true            # 关键顾虑，未化解不能达成目标
    - id: solution
      text: 没有明确处理方案和时间
      key: true

state_rules:
  initial_trust: 30
  deal_threshold: 75
  hangup_threshold: 5

scoring: service_complaint # 引用评分表 id
```

> 已落地的完整字段以 `backend/app/services/scenarios.py` 为准，示例见 `scenarios/S01_angry_complaint.yaml`。
> 相比上面的草案，新增了这些字段：`summary`、`tags`、`opening`（谁先开口、开场白、给员工的提示）、
> `objections[].resolve_hints`（化解要点，供评估参考）、`state_rules.min_turns_to_deal / max_gain_per_turn / max_loss_per_turn`、
> `deal_line / hangup_line`（结束时的参考台词）、`enabled`。评分表放在 `scenarios/rubrics/*.yaml`，可配置 `hint_penalty` 和 `hint_penalty_max`。

## 3. 隐藏状态规则

| 员工行为 | 信任值影响（示例） |
|---|---|
| 有效挖掘需求、提出好问题 | +5 ~ +10 |
| 针对性化解一个异议 | +10 ~ +20，并移除该异议 |
| 空泛吹嘘、答非所问 | -5 |
| 急于报价/压单、贬低竞品 | -10 |
| 不礼貌或违规承诺 | -20，可能直接挂断 |

具体数值作为 `evaluate_turn` 节点的提示词参考，由模型结合上下文判断，代码层做上下限保护。

## 4. 评分表（草案）

### 4.1 客户服务评分表 `customer_service`（满分 100）

| 维度 | 权重 | 5 分标准 | 1 分标准 |
|---|---|---|---|
| 开场与服务意识 | 15 | 礼貌、主动承担，让客户感到被认真对待 | 机械问候或推诿 |
| 倾听与需求澄清 | 25 | 问清场景、现象和诉求并复述确认 | 没问清楚就猜测 |
| 解答与方案准确性 | 25 | 回答针对、步骤清楚、不编造 | 答非所问或越权承诺 |
| 情绪与预期管理 | 15 | 识别情绪，给出可兑现时间节点 | 争辩或只说“尽快” |
| 表达与合规 | 10 | 口语通俗、保护信息、遵守权限 | 堆术语或违规承诺 |
| 结束与闭环 | 10 | 确认理解，复述下一步与回访 | 草草结束 |

扣分项：每次使用求助提示扣 2 分（最多扣 10 分）。

### 4.2 客服投诉评分表 `service_complaint`（满分 100）

| 维度 | 权重 |
|---|---|
| 情绪安抚与共情 | 30 |
| 问题确认与澄清 | 20 |
| 解决方案与时效承诺 | 25 |
| 合规表达（不推诿、不越权承诺） | 15 |
| 结束与回访确认 | 10 |

## 5. 报告输出结构（教练 Agent JSON）

```json
{
  "total_score": 78,
  "summary": "一句话总评",
  "dimension_scores": [{"name": "需求挖掘", "score": 4, "comment": "..."}],
  "highlights": ["亮点1"],
  "improvements": ["改进点1"],
  "turn_reviews": [
    {"turn": 3, "user_said": "...", "issue": "...", "better_reply": "..."}
  ],
  "trust_curve": [30, 35, 25, 45, 60, 80],
  "outcome": "deal"
}
```

## 6. 待业务确认

- 业务系统成熟话术的授权范围、导出方式、转写质量和更新频率
- 首批客服场景的真实流程、权限边界和常见客户表达（脱敏后）
- 评分维度与权重是否符合公司客服质量标准
