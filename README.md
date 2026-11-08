# hackerzr2026
公司组织的AI大赛

参赛作品 **AI 客户陪练**：在企业微信里打开即用的销售/客服话术陪练工具。AI 扮演带隐藏情绪和异议的“难缠客户”和员工对练，练完由 AI 教练按评分表打分，给出逐轮点评、推荐话术，并复盘客户的“内心独白”。

项目背景和设计见 [doc/](doc/README.md)，AI 助手协作约定见 [AGENTS.md](AGENTS.md)。

## 技术栈

| 层 | 选型 |
|---|---|
| 智能体 | LangGraph 1.x（StateGraph + interrupt 人机交互 + PostgreSQL checkpoint/store）、LangChain 1.x |
| 后端 | Python 3.13、FastAPI（原生 SSE 流式）、SQLAlchemy 2 async、Alembic、uv |
| 数据库 | PostgreSQL 16+ + pgvector（业务表、会话检查点、长期记忆、话术向量库同库） |
| 模型 | OpenAI 兼容接口（DeepSeek / 通义千问 / 豆包 / 私有部署均可），内置离线 Stub 模型 |
| 前端 | Vue 3 + Vite + TypeScript + Vant 4（移动端）+ ECharts，企业微信 OAuth 免登 |

## 目录

```
backend/        FastAPI + LangGraph 服务（app/、migrations/、tests/）
frontend/       H5 对练页面
scenarios/      场景 YAML；scenarios/rubrics/ 为评分表 YAML
knowledge/      话术知识库 Markdown（RAG，内容必须已脱敏）
doc/            项目文档
```

## 本地运行

前置：Python 3.12+、[uv](https://docs.astral.sh/uv/)、Node 20+、pnpm、一个装了 pgvector 的 PostgreSQL。

```bash
# 1. 后端
cd backend
cp .env.example .env              # 按需修改 DATABASE_URL；默认 LLM__PROVIDER=stub，不需要密钥
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

接入真实模型：在 `backend/.env` 中设置 `LLM__PROVIDER=openai`，以及 `LLM__BASE_URL`、`LLM__API_KEY`、`LLM__MODEL`、`LLM__PRICING`。

## 测试

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
| 企业微信应用对话 | `/api/wecom/callback` | 员工在企业微信应用里直接发文字/语音练习（主入口，无需打开网页） |
| H5 网页 | `/`（企业微信内自动免登，电脑端扫码登录） | 对练界面、评分报告（应用对话里会附报告链接） |

**应用对话**的工作方式：回调只做验签解密并转入后台，模型调用完成后通过应用消息接口主动回复（企微要求 5 秒内应答）。支持的指令：`菜单`、`1`/`S01`（开始练习）、练习中直接发消息、`求助`、`结束`（生成报告）、`报告`（最近一次）。语音消息依赖企微返回的识别文字，未开启识别时会提示员工改用文字。

配置步骤（在企业微信管理后台完成）：

1. 应用管理 → 自建应用 → **接收消息** → 设置 API 接收：URL 填 `https://<域名>/api/wecom/callback`，生成 Token 和 EncodingAESKey，写入 `backend/.env` 的 `WECOM__TOKEN`、`WECOM__ENCODING_AES_KEY`。
2. 同一页面开启语音识别（企微会随语音消息返回识别文字；具体菜单位置以企微后台为准）。
3. 应用的 **OAuth 可信域名 / 网页授权回调域名** 配置为 `<域名>`，同时设置 `WECOM__PUBLIC_BASE_URL=https://<域名>`（报告链接使用）。扫码登录与企微内免登都依赖它。
4. `WECOM__CORP_ID`、`WECOM__AGENT_ID`、`WECOM__SECRET` 填应用的 CorpID、AgentID、Secret。
5. 管理员工号写入 `ADMIN_USERIDS`（JSON 数组）。生产环境未配置时任何人都无法进入管理后台。

## 管理后台（网页版）

`/admin`，仅管理员可访问（需要 `is_admin`，见上）。电脑浏览器打开，用企业微信扫码登录。

- 数据概览：完成练习、参与人数、平均分、成功推进率、单次成本与人工带教对比、近 7/30/90 天趋势
- 练习记录：按员工、场景、结果筛选；详情含完整对话、客户内心独白、评分报告、模型调用明细
- 员工：按工号/姓名/部门搜索，查看练习次数、平均分、累计成本
- 模型用量：每次模型与语音调用的 Token、费用、耗时
- 场景配置、话术知识库：只读展示（内容仍由 YAML 与 Markdown 维护）

管理后台所有接口只读；对话内容与客户内心独白仅对管理员开放，请按公司保密制度使用。

## 发布与部署

镜像由 GitHub Actions 构建并推送到 GHCR（`ghcr.io/redgreat/hackerzrsk2026`），不使用阿里云。流程：

1. 本地（Windows）执行 `.\script\release.ps1`，自动计算下一个版本号并打标签推送；也可指定版本：`.\script\release.ps1 v0.1.1`
2. Actions（`.github/workflows/build-deploy.yml`）自动构建镜像，推送 `:v0.1.0` 和 `:latest`
3. 服务器上部署：

```bash
# 首次部署：准备配置
echo "POSTGRES_PASSWORD=<强密码>" > .env          # 根目录，供 compose 使用
cp backend/.env.example backend/.env             # 设置 APP_ENV=prod、JWT_SECRET（≥32位）、真实模型与企业微信配置
# 若镜像为私有：docker login ghcr.io -u <GitHub 用户名> -p <PAT(read:packages)>

./script/redeploy.sh --migrate --tag v0.1.0      # 拉取、迁移、启动、健康检查
./script/redeploy.sh                             # 之后升级到 latest
./script/redeploy.sh --tag v0.1.1 --migrate      # 有新迁移时加 --migrate
```

首次部署后还需要导入话术知识库：`docker compose run --rm app python -m app.cli ingest-knowledge`。

服务只监听 `127.0.0.1:8000`，企业微信要求 HTTPS 可信域名，需要在前面加一层反向代理（Nginx/Caddy）并配置证书，把 `/` 转发到 `127.0.0.1:8000`（SSE 接口需关闭缓冲）。

本地构建镜像（不推送）：`docker build -t hackerzrsk2026:local .`
