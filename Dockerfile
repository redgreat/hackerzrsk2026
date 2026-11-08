# 多阶段构建：前端 H5 → Python 运行时（FastAPI 同时托管 H5 静态文件）

FROM node:24-alpine AS web
WORKDIR /web
RUN npm install -g pnpm@12
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.13-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 APP_ENV=prod
WORKDIR /srv/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
COPY scenarios /srv/scenarios
COPY knowledge /srv/knowledge
COPY --from=web /web/dist /srv/frontend/dist
ENV PATH="/srv/backend/.venv/bin:$PATH"
RUN useradd --system --no-create-home coach
USER coach
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["python", "-m", "app", "--host", "0.0.0.0", "--port", "8000"]
