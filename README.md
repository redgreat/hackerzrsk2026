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

## 发布与部署

镜像由 GitHub Actions 构建并推送到 GHCR（`ghcr.io/redgreat/hackerzrsk2026`），不使用阿里云。流程：

1. 本地打版本标签并推送：`git tag v0.1.0 && git push origin v0.1.0`
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
