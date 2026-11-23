# hackerzr2026
公司组织的AI大赛

参赛作品 **AI 客户话术陪练**：面向客服、服务、销售等客户沟通岗位的语音陪练工具。员工从企业微信工作台进入 H5，选择场景后直接开口；AI 扮演带情绪、诉求和隐藏顾虑的客户，结束后按业务评分表给出逐轮点评和推荐话术。公司已采购并授权使用的成熟话术可在脱敏、筛选后进入知识库，成为求助提示和复盘建议的经验依据。

项目背景和设计见 [doc/](doc/README.md)，AI 助手协作约定见 [AGENTS.md](AGENTS.md)。

## 技术栈

| 层 | 选型 |
|---|---|
| 智能体 | LangGraph 1.x（StateGraph + interrupt 人机交互 + PostgreSQL checkpoint/store）、LangChain 1.x |
| 后端 | Python 3.13、FastAPI（原生 SSE 流式）、SQLAlchemy 2 async、Alembic、uv |
| 数据库 | PostgreSQL 16+ + pgvector（业务表、会话检查点、长期记忆、话术向量库同库） |
| 模型 | OpenAI 兼容接口（DeepSeek / 通义千问 / 豆包 / 私有部署均可），内置离线 Stub 模型 |
| 前端 | Vue 3 + Vite + TypeScript + Vant 4（移动端）+ ECharts，企业微信 OAuth 免登 / 注册+密码登录 |
| 语音转写 | 录音文件转写支持阿里云百炼 Paraformer（`RECORDINGS__ASR_PROVIDER=dashscope`）或离线 Stub |

## 目录

```
backend/        FastAPI + LangGraph 服务（app/、migrations/、tests/）
frontend/       H5 页面（练习 / 优秀录音 / 考试 / 管理后台）
scenarios/      场景 YAML；scenarios/collection/ 为催收场景；scenarios/rubrics/ 为评分表
exams/          题库与试卷 YAML（questions/ 题库，papers/ 试卷定义）
knowledge/      话术知识库 Markdown（RAG，内容必须已脱敏）
doc/            项目文档
```

## 本地运行

前置：Python 3.12+、[uv](https://docs.astral.sh/uv/)、Node 20+、pnpm、一个装了 pgvector 的 PostgreSQL。

```bash
# 1. 后端
cd backend
cp ../config/config.yml.example ../config/config.yml   # 按需修改；本地开发可直接用 llm.provider: stub，不需要密钥
uv sync
uv run python -m app.cli init-db           # 执行迁移，并创建 LangGraph checkpoint/store 表
uv run python -m app.cli ingest-knowledge  # 导入话术知识库
uv run python -m app --reload              # http://127.0.0.1:8000/api/docs

# 2. 前端（另开终端）
cd frontend
pnpm install
pnpm dev                                   # http://localhost:5173，/api 代理到 8000
```

执行 `pnpm build` 后，后端会直接托管 `frontend/dist`，访问 http://127.0.0.1:8000 即可。

接入真实模型：在 `config/config.yml` 中设置 `llm.provider: openai`，以及 `llm.base_url`、`llm.api_key`、`llm.model`、`llm.pricing`。

## 测试

真实语音试用需要可连接的 PostgreSQL（可使用已有远程实例），以及实际可用的模型和语音服务。在 `config/config.yml` 中配置 `database_url`，将 `llm.provider`、`speech.asr_provider` 和 `speech.tts_provider` 设为 `openai` 并填写各自兼容接口地址、密钥和模型名。`stub` 仅用于联调，不能用来评价真实对话或识别效果。

无需本地 Docker：连接准备好的数据库后，在 `backend/` 执行 `uv run python -m app.cli init-db` 和 `uv run python -m app.cli ingest-knowledge`，再按上面的后端、前端命令启动。数据库初始化会修改所配置的库，请确认目标库属于本项目。手机和企微内置浏览器须通过 HTTPS 访问，首次录音允许麦克风权限；自动播放受限时可点击回复旁的播放按钮。录音单轮最长 60 秒，松手后提交识别。

```bash
cd backend
uv run ruff check app tests migrations
uv run pytest                                     # 图/规则/服务单测，使用 Stub 模型 + 内存检查点
TEST_DATABASE_URL=postgresql+psycopg://...ai_coach_test uv run pytest   # 额外跑 HTTP 全链路集成测试（会清空测试库）

cd frontend && pnpm build                          # 类型检查 + 构建
```

## 企业微信接入

两种入口，共用同一套陪练引擎：

| 入口 | 位置 | 用途 |
|---|---|---|
| H5 网页 | `/`（企业微信内自动免登，电脑端扫码登录） | **主入口**；按住说话、ASR、客户回复 TTS、完整报告 |
| 企业微信应用对话 | `/api/wecom/callback` | 轻量补充；场景菜单、文字或单条短语音练习、提醒、报告链接 |

**应用对话**不是实时语音通话：员工每次发送一条语音消息，企微返回识别文字后系统再异步生成文字回复。它适合入口、提醒和碎片化短练习；连续语音、自动播放和完整报告使用 H5。回调只做验签解密并转入后台，模型调用完成后通过应用消息接口主动回复（企微要求快速应答）。支持的指令：`菜单`、`1`/`S01`（开始练习）、练习中直接发消息、`求助`、`结束`（生成报告）、`报告`（最近一次）。

配置步骤（在企业微信管理后台完成）：

1. 应用管理 → 自建应用 → **接收消息** → 设置 API 接收：URL 填 `https://<域名>/api/wecom/callback`，生成 Token 和 EncodingAESKey，写入 `config/config.yml` 的 `wecom.token`、`wecom.encoding_aes_key`。
2. 同一页面开启语音识别（企微会随语音消息返回识别文字；具体菜单位置以企微后台为准）。
3. 应用的 **OAuth 可信域名 / 网页授权回调域名** 配置为 `<域名>`，同时设置 `WECOM__PUBLIC_BASE_URL=https://<域名>`（报告链接使用）。扫码登录与企微内免登都依赖它。
4. `WECOM__CORP_ID`、`WECOM__AGENT_ID`、`WECOM__SECRET` 填应用的 CorpID、AgentID、Secret。
5. 管理员工号写入 `ADMIN_USERIDS`（JSON 数组）。生产环境未配置时任何人都无法进入管理后台。

## 管理后台（网页版）

`/admin`，仅管理员可访问（需要 `is_admin`，见上）。电脑浏览器打开，用企业微信扫码登录。

- 数据概览：完成练习、参与人数、平均分、目标达成率、单次成本与人工带教对比、近 7/30/90 天趋势
- 练习记录：按员工、场景、结果筛选；详情含完整对话、客户内心独白、评分报告、模型调用明细
- 员工：按工号/姓名/部门搜索，查看练习次数、平均分、累计成本
- 模型用量：每次模型与语音调用的 Token、费用、耗时
- 场景配置、话术知识库：只读展示（内容仍由 YAML 与 Markdown 维护）

管理后台所有接口只读；对话内容与客户内心独白仅对管理员开放，请按公司保密制度使用。

## 催收培训考试系统（H5）

面向贷后/催收新人的培训考核模块，详见 [doc/08-collection-training.md](doc/08-collection-training.md)。与陪练共用同一套引擎，新增能力：

- **账号体系**：开放注册 + 管理员审核（`/admin/accounts`），密码登录；审核未通过不能登录
- **优秀录音**：H5「录音」页按客户类型检索、边听边看逐句转写（点句跳听）、AI 生成的亮点话术点评与合规提醒、答题自测
- **录音加工**：`uv run python -m app.cli import-recordings`（dbmcp 查询或本地清单）→ `process-recordings`（转写 + AI 分析 + 出题）→ 管理后台审核发布
- **题库试卷**：`exams/` 下 YAML 定义，支持选择题、听录音题、情景对练三种题型；`python -m app.cli check-scenarios` 一并校验
- **考试与自测**：H5「考试」页支持自测（不限次、交卷给解析）与正式考试（限时、限次、对练中禁用求助、红线违规总分封顶）

环境变量：`RECORDINGS__ASR_PROVIDER`（stub/dashscope）、`DBMCP__*`（数据源查询）、`DASHSCOPE_API_KEY`（Paraformer）。录音文件、转写稿等真实数据只放 `data/private/`，不入库到 git。

## 发布与部署

镜像由 GitHub Actions 构建并推送到 Quay（`quay.io/zrsk/hackerzrsk2026`）。需要在 GitHub 仓库的 Settings → Secrets 中配置 `QUAY_USERNAME`、`QUAY_PASSWORD`。流程：

1. 本地（Windows）执行 `.\script\release.ps1`，自动计算下一个版本号并打标签推送；也可指定版本：`.\script\release.ps1 v0.1.1`
2. Actions（`.github/workflows/build-deploy.yml`）自动构建镜像，推送 `:<版本>` 和 `:latest`
3. 服务器上部署：

```bash
# 首次部署：准备配置（服务器上的 config/ 目录即配置来源，不需要 .env）
cp config/config.yml.example config/config.yml   # 填写 database_url（云上 PostgreSQL）、jwt_secret、app_env: prod、llm、wecom 等
# 若镜像为私有：export QUAY_USERNAME=... QUAY_PASSWORD=...（脚本会自动 docker login quay.io），或手动 docker login quay.io

./script/redeploy.sh --migrate --tag v0.2.1      # 拉取、迁移、启动、健康检查
./script/redeploy.sh                             # 之后升级到 latest
./script/redeploy.sh --tag v0.2.2 --migrate      # 有新迁移时加 --migrate
```

首次部署后还需要导入话术知识库：`docker compose run --rm app python -m app.cli ingest-knowledge`。
数据库使用云上 PostgreSQL（需提前安装 pgvector 扩展），部署文件不包含数据库容器。

服务只监听 `127.0.0.1:8000`，企业微信要求 HTTPS 可信域名，需要在前面加一层反向代理（Nginx/Caddy）并配置证书，把 `/` 转发到 `127.0.0.1:8000`（SSE 接口需关闭缓冲）。

本地构建镜像（不推送）：`docker build -t hackerzrsk2026:local .`
