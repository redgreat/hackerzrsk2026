# 08 催收新人培训系统（贷后呼叫中心）

> 分支：`feat/collection-training`。在现有"AI 客户陪练"基础上扩展，面向瑟维斯贷后呼叫中心新人，
> 只走 H5（浏览器直接打开），不依赖企业微信。

## 1. 目标

新人入职后，不需要老员工一对一带教，就可以在一个 H5 里完成：

| 能力 | 说明 |
|---|---|
| 听优质录音 | 从贷后系统"优秀录音"导入，AI 转写、标注亮点话术、合规点评；支持点句跳转播放 |
| AI 对练（自测） | AI 扮演逾期客户（忘还、困难、拖延、情绪激动、第三方接听……），练完 AI 教练打分并给出改进话术 |
| 考试 | 试卷 = 合规/话术选择题 + 听录音答题 + AI 情景对练（禁用提示），设及格线、限时、限次，成绩留档 |
| 指导意见 | 每次对练/考试后给出维度评分、亮点、改进建议、逐轮推荐话术；红线违规单独列出并封顶分数 |
| 账号 | 开放注册（工号+姓名+密码）→ 管理员审核通过后可用 |
| 管理后台 | 账号审核、录音管理（转写/分析/发布）、录音题目审核、考试成绩 |

## 2. 数据来源评估：贷后优秀录音

来源：本地录音清单（JSON，只含录音地址等必要字段）。应用不连接任何业务库，清单由人工从业务系统导出。

```sql
-- 优秀录音 → 催收记录（主库 recall_record_0..9 共 10 张分表；从库 sw_dhtcenter_slave 另有镜像 10 张）→ 通话记录 → 录音地址
select CASE WHEN c.source in (0,3,4) THEN c.callCenterPath
            WHEN c.source = 6 AND c.callCenterPath IS NOT NULL THEN c.callCenterPath
            ELSE c.url END AS url
from recall_call_record c
where c.id in (select b.callId from recall_excellent_call a left join recall_record_x b on a.recordId = b.id);
```

是否符合本项目需求：

- **符合**：优秀录音是"销冠话术"的一手素材，正好用于 ①新人收听学习 ②提炼话术进知识库（RAG，供教练点评引用）
  ③生成听录音答题 ④归纳典型客户类型，编写对练场景 YAML。
- **前提**：录音需要转文字才能做 AI 分析。采用阿里云百炼 Paraformer 录音文件识别（直接传 OSS URL，支持双声道/说话人分离）。
  OSS 地址必须能被百炼拉取（公网可读或带签名）；内网地址需另行处理。
- **合规**：录音含真实客户信息，**只在系统内部播放，不入仓库**；转写文本落库前做脱敏（手机号、身份证、银行卡、车牌等），
  AI 分析结果不得包含客户姓名；录音默认"未发布"，管理员审核后员工才能看到。演示视频只能用虚构/脱敏素材。

导入方式：`python -m app.cli import-recordings [--limit N]`，从标准输入读取 URL，每行一条：`录音URL<TAB>标题(可选)`，相对路径按 `recordings.audio_base_url` 拼接。URL 只写入 PG，服务器上不保存清单文件。
具体字段待白名单开通后核对表结构，SQL 集中在 `app/services/recording_source.py`。

## 3. 架构

```
           H5（Vue3 + Vant）                     管理后台（Element Plus）
  练习 | 录音 | 考试 | 我的                 账号审核 | 录音管理 | 题目审核 | 成绩
            │                                        │
            └──────────── FastAPI /api ──────────────┘
   auth(密码/注册)  recordings  exams  sessions(复用陪练图)  training-admin
            │             │         │
            │   RecordingService     ExamService ──→ PracticeService(mode=exam，禁用提示)
            │     ├ 来源：文件清单
            │     ├ 转写：Paraformer（stub 可离线）
            │     └ 分析：LLMGateway(purpose=analyst) → 亮点/合规/题目
            └── PostgreSQL：users(+密码/状态/角色) recordings recording_questions exam_attempts
```

新增配置（写在 `config/config.yml`，均有默认值，可不配）：

```
RECORDINGS__ASR_PROVIDER=stub|dashscope|none
RECORDINGS__DASHSCOPE_API_KEY=...
RECORDINGS__DBMCP_URL=https://mcp.lunz.cn/mcp/sse
RECORDINGS__DBMCP_KEY=...
RECORDINGS__CONNECTION_ID=51
AUTH__PASSWORD_ENABLED=true
AUTH__REQUIRE_APPROVAL=true
```

## 4. 业务内容（全部 YAML，可复制）

- `scenarios/C0x_*.yaml`：催收对练场景（虚构）。
  C01 忘记还款的首逾客户 / C02 资金困难求延期 / C03 一拖再拖不给准话 / C04 情绪激动扬言投诉 /
  C05 质疑金额称已还款 / C06 家属代接（第三方保密）
- `scenarios/rubrics/collection_default.yaml`：催收评分表，含 `red_lines`（威胁恐吓、辱骂、向第三方透露欠款、
  冒充公检法、越权承诺减免等）。触发红线 → 客户可能直接挂断，总分封顶 `red_line_cap`（默认 59）。
- `exams/questions/*.yaml`：合规/话术题库（单选、多选、判断）。
- `exams/papers/*.yaml`：试卷，`kind: exam | self_test`，由若干 section 组成：
  - `quiz`：指定题目或按标签随机抽题
  - `listening`：从已发布录音的已审核题目中随机抽题（先听录音再答题）
  - `roleplay`：指定对练场景（考试中禁用求助提示）

## 5. 评分规则

- 选择题：单选/判断全对得分；多选全对得分、漏选得一半、错选 0 分。
- 各 section 先折算为百分制，再按 `weight` 加权得总分；`total >= pass_score` 为通过。
- 对练 section 取各场景教练报告 `total_score` 的平均；交卷时未完成的场景计 0 分，报告生成中的需等待。
- 考试：限时（截止后自动按已保存答案判分）、限次（`max_attempts`）；交卷后才显示答案解析（`show_answers`）。
- 自测：不限次，交卷即看解析。

规则均为纯函数（`app/services/exam_rules.py`），有单测。

## 6. 里程碑与验收

| 阶段 | 内容 | 验证 |
|---|---|---|
| P1 | 账号注册审核、密码登录 | 单测 + HTTP 集成测试 |
| P2 | 催收场景/评分表/红线、对练考试模式 | `check-scenarios` + 图测试 |
| P3 | 录音导入、转写（stub/Paraformer）、AI 分析、题目生成、发布 | 单测（解析/脱敏/角色识别）+ 集成测试 |
| P4 | 题库/试卷、考试与自测流程、判分 | 规则单测 + 集成测试全流程 |
| P5 | H5 页面（录音、考试、登录注册）+ 管理后台页面 | `pnpm build`（类型检查）+ 本地联调 |
| P6 | 真实录音清单导入、Paraformer 密钥 | 人工验收 |

验收清单（最终由业务方确认）：

- [ ] 新人可自助注册，管理员审核后能登录
- [ ] 录音库可播放、看转写、看 AI 亮点与点评，点句跳转
- [ ] 6 个催收场景可对练，报告含维度分、红线、推荐话术
- [ ] 自测试卷可反复做，交卷看解析
- [ ] 正式考试限时限次、禁用提示，成绩在后台可查
- [ ] 真实录音导入、转写、发布（依赖外部权限）
