#!/usr/bin/env bash
# ==========================================
# AI 客户陪练 - 从 GHCR 拉取镜像并重新部署
# 用法:
#   ./script/redeploy.sh                 # 部署 latest
#   ./script/redeploy.sh --tag v0.1.0    # 部署指定版本
#   ./script/redeploy.sh --migrate       # 部署前执行数据库迁移（首次部署或有新迁移时使用）
# ==========================================

set -euo pipefail

IMAGE="ghcr.io/redgreat/hackerzrsk2026"
TAG="latest"
MIGRATE=false
HEALTH_URL="http://127.0.0.1:8000/api/health"

info()  { echo -e "\033[34m➤ $*\033[0m"; }
ok()    { echo -e "\033[32m✔ $*\033[0m"; }
warn()  { echo -e "\033[33m⚠ $*\033[0m"; }
die()   { echo -e "\033[31m✖ $*\033[0m" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)     TAG="${2:?--tag 需要版本号}"; shift 2 ;;
    --migrate) MIGRATE=true; shift ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) die "未知参数: $1" ;;
  esac
done

# 脚本位于 <项目根>/script/，固定到项目根执行，与所在路径无关
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

command -v docker >/dev/null 2>&1 || die "未找到 docker"
docker compose version >/dev/null 2>&1 || die "未找到 docker compose（需要 Compose v2）"
[[ -f .env ]] || die "缺少根目录 .env（需要 POSTGRES_PASSWORD）"
[[ -f backend/.env ]] || die "缺少 backend/.env（参考 backend/.env.example 创建）"

export APP_IMAGE="${IMAGE}:${TAG}"
echo "=========================================="
echo " 部署镜像: ${APP_IMAGE}"
echo "=========================================="

info "1. 拉取镜像（私有镜像需先执行 docker login ghcr.io）..."
if ! docker compose pull app; then
  die "拉取失败：请确认标签 ${TAG} 已由 CI 构建，或已登录 ghcr.io"
fi

info "2. 启动数据库..."
docker compose up -d db

if $MIGRATE; then
  info "3. 执行数据库迁移（幂等）..."
  docker compose run --rm app python -m app.cli init-db
else
  info "3. 跳过数据库迁移（如有新迁移请加 --migrate）"
fi

info "4. 重建并启动应用容器..."
docker compose up -d --no-deps --force-recreate app

info "5. 等待健康检查 ${HEALTH_URL} ..."
healthy=false
for _ in $(seq 1 30); do
  if curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then healthy=true; break; fi
  sleep 2
done
if $healthy; then
  ok "服务健康：$(curl -fsS "${HEALTH_URL}")"
else
  warn "健康检查超时，最近日志如下："
  docker compose logs --tail=80 app || true
  die "部署完成但服务不健康"
fi

info "6. 清理悬挂镜像（仅 dangling，不影响其它镜像）..."
docker image prune -f >/dev/null

docker compose ps
ok "部署完成：${APP_IMAGE}"
