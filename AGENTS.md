# AGENTS.md

本文件为 AI 编码助手（及新加入的同事）提供项目上下文。修改项目方向时请同步更新本文件和 `doc/` 下的对应文档。

## 项目一句话

**AI 客户陪练**：在企业微信里打开即用的销售/客服话术陪练工具——AI 扮演"难缠客户"与员工对练，练完由 AI 教练打分、点评并给出优秀话术示范，用于降低新人带教成本、提升一线沟通能力。

参赛背景：中瑞数科《"AI赋能·人人会用"比赛活动通知》（NO. C-HR-2026/11/01），初赛作品截止 **2026-11-25 24:00**。

## 文档索引

| 文档 | 内容 |
|---|---|
| [doc/README.md](doc/README.md) | 文档目录 |
| [doc/01-overview.md](doc/01-overview.md) | 项目背景、目标、比赛要求与评审维度、价值主张 |
| [doc/02-product.md](doc/02-product.md) | 用户角色、核心功能、用户流程、MVP 范围 |
| [doc/03-architecture.md](doc/03-architecture.md) | 技术架构、LangGraph 流程设计、企业微信接入、部署 |
| [doc/04-scenario-and-scoring.md](doc/04-scenario-and-scoring.md) | 场景配置规范（YAML）、客户画像、评分表 |
| [doc/05-data-and-security.md](doc/05-data-and-security.md) | 参考项目/客户信息接入规划、脱敏与保密规则 |
| [doc/06-milestones-and-delivery.md](doc/06-milestones-and-delivery.md) | 里程碑、比赛交付物、视频脚本、成本测算 |
| [doc/07-open-questions.md](doc/07-open-questions.md) | 待决事项清单 |

## 技术栈

- 后端：Python 3.13（uv 管理，最低 3.12）、FastAPI（原生 SSE）、SQLAlchemy 2 async + Alembic、LangChain 1.x、LangGraph 1.x
- 数据库：PostgreSQL 16+ + pgvector。业务表、LangGraph checkpoint（AsyncPostgresSaver）、长期记忆（AsyncPostgresStore）、话术向量库都放在同一个库
- 模型：OpenAI 兼容接口，厂商待定（见 `doc/07-open-questions.md`）；`LLM__PROVIDER=stub` 是离线规则模型，开发和测试不需要密钥
- 语音：ASR/TTS 走 OpenAI 兼容 `/audio/*` 接口，或关闭（关闭时前端退化为浏览器朗读、隐藏按住说话）
- 前端：Vue 3 + Vite + TypeScript + Vant 4 + ECharts，企业微信 OAuth 免登（开发环境用开发登录）
- 配置：场景、客户画像、评分表均为 YAML（`scenarios/`），话术知识库为 Markdown（`knowledge/`）
- 依赖供应链：后端 `pyproject.toml` 用 `[tool.uv] exclude-newer` 锁定解析日期；前端 `pnpm-workspace.yaml` 设 `minimumReleaseAge`（7 天）。升级依赖时手动推进这两个设置，不要删除

## 目录结构

```
hackerzr2026/
├── AGENTS.md
├── README.md                 # 快速开始、测试、部署
├── Dockerfile / docker-compose.yml
├── doc/                      # 项目文档
├── backend/
│   ├── app/
│   │   ├── __main__.py       # 启动入口 python -m app（处理 Windows 事件循环）
│   │   ├── cli.py            # init-db / ingest-knowledge / check-scenarios
│   │   ├── main.py           # create_app + lifespan（组装依赖容器）
│   │   ├── api/              # HTTP 路由：auth / scenarios / sessions(SSE) / speech / stats / health
│   │   ├── graph/            # LangGraph：state、schemas（结构化输出）、rules（纯规则）、nodes、builder
│   │   ├── prompts/          # 提示词模板（customer / evaluator / coach / hint），场景差异从 YAML 注入
│   │   ├── services/         # llm（网关+Stub+计量）、practice（会话编排）、scenarios、knowledge(RAG)、
│   │   │                     # memory（长期记忆）、guard（脱敏）、speech、wecom、stats、users
│   │   ├── db/               # SQLAlchemy 模型与会话
│   │   └── core/             # 配置、错误、JWT、日志、依赖容器
│   ├── migrations/           # Alembic 迁移（alembic.ini 必须保持纯 ASCII）
│   └── tests/
├── scenarios/                # 场景 YAML；rubrics/ 为评分表
├── knowledge/                # 话术知识库（已脱敏）
├── frontend/                 # H5：src/views、src/api、src/composables、src/components
└── data/
    └── private/              # 本地敏感数据（已加入 .gitignore，禁止提交）
```

## 关键实现约定

- 陪练图流程：`init_scenario → wait_input(interrupt) → evaluate_turn → customer_reply → check_end`，旁路 `hint`，结束进入 `coach_report`。员工的输入通过 `Command(resume={"type": "message"|"hint"|"end"})` 传入。
- 信任值上下限、成交/挂断判定、总分计算都在 `graph/rules.py`，属于纯函数，修改后同步更新 `tests/test_rules.py`。
- 所有模型调用必须走 `services/llm/gateway.py`（脱敏、结构化输出重试、token/费用计量）；不得在节点里直接实例化 ChatOpenAI。
- 计量记录写入 `usage_scope()`，由 `PracticeService` 统一落库 `model_usage` 并累加到会话成本；不记录对话内容。
- 客户回复的流式片段通过 `runtime.stream_writer` 推送，再经 SSE 下发。图运行放在后台任务中，客户端断开不会中断报告生成。会话锁目前是单进程实现，多实例部署时需改为分布式锁。
- 练习结束前，接口不得下发客户内心独白、信任值、隐藏需求和异议。
- 新增场景只需新增 YAML；新增评分表放 `scenarios/rubrics/`。改完执行 `python -m app.cli check-scenarios` 校验。

## 开发约定

- 场景/画像/评分表等**业务内容一律放 YAML 配置**，不要硬编码在 Python 里，保证可复制性（评审维度之一）。
- "客户"角色与"教练"评分角色**分离为不同节点/Agent**：客户 Agent 温度偏高求真实，教练 Agent 温度低 + 结构化输出求稳定。
- 客户 Agent 必须受隐藏状态（信任值、未解决异议）约束，避免"三句话被说服"。
- 模型调用统一经过一个封装层，便于切换厂商与统计 token 成本（成本数据是比赛汇报的重点）。
- 密钥只放 `.env`（已在 .gitignore），不得写入代码、文档或日志。
- 文档与注释使用中文；代码标识符使用英文。

## 数据安全红线（必须遵守）

- **禁止**将真实客户名称、联系方式、合同金额、通话录音等提交到仓库；真实数据只能放 `data/private/`。
- 进入提示词、知识库、演示视频的数据必须先脱敏，规则见 `doc/05-data-and-security.md`。
- 比赛通知明确要求：作品中不得包含涉密信息、客户数据或未经授权的第三方内容。

## 常用命令

后端（在 `backend/` 下执行）：

```bash
uv sync                                        # 安装依赖
uv run python -m app.cli init-db               # 迁移 + LangGraph checkpoint/store 建表（显式执行，启动时不自动改库）
uv run python -m app.cli ingest-knowledge      # 导入 knowledge/*.md
uv run python -m app.cli check-scenarios       # 校验场景/评分表 YAML
uv run python -m app --reload                  # 启动开发服务 :8000（不要直接用 uvicorn 命令启动，Windows 下 psycopg 异步需要 SelectorEventLoop）
uv run ruff check app tests migrations && uv run ruff format app tests migrations
uv run pytest                                  # 单测（Stub 模型 + 内存检查点，无需数据库）
TEST_DATABASE_URL=postgresql+psycopg://user:pass@host:port/ai_coach_test uv run pytest   # 加跑 HTTP 全链路集成测试（会清空该库）
```

前端（在 `frontend/` 下执行）：

```bash
pnpm install
pnpm dev                                       # :5173，/api 代理到 127.0.0.1:8000（可用 API_TARGET 覆盖）
pnpm build                                     # vue-tsc 类型检查 + 构建到 dist/（后端会自动托管）
```

注意事项：
- Windows 控制台为 GBK 编码，运行脚本时设置 `PYTHONIOENCODING=utf-8`；在 Git Bash 里用 curl 发送中文 JSON 会乱码，请改用 Python/httpx 测试。
- pytest-asyncio 的 fixture 和测试都使用 session 级事件循环（见 pyproject）。如果改成函数级，连接池会挂在另一个循环上导致超时。

发布与部署：
- 本地（Windows）：`.\script\release.ps1 [vX.Y.Z]` 只负责打标签并推送，触发 GitHub Actions 构建 GHCR 镜像。
- 服务器：`./script/redeploy.sh [--tag vX.Y.Z] [--migrate]` 只负责服务器上拉取与重启，不依赖本地环境。
- 不要把两者的逻辑混在一起。

企业微信与管理后台：
- 应用对话：`app/api/wecom.py`（回调）→ `app/services/wecom_chat.py`（指令与会话编排，复用 `PracticeService`）→ `app/services/wecom.py`（发送）。回调必须快速应答，耗时逻辑放后台任务。
- 管理后台 API：`app/api/admin.py` → `app/services/admin.py`，只读，统一 `AdminDep`。前端在 `frontend/src/views/admin/`，使用 Element Plus（H5 仍用 Vant）。
- 新增对话指令时同步 `parse_command` 与 `tests/test_wecom.py`。
