#!/usr/bin/env bash
# ==========================================
# AI 客户陪练 - 从 quay.io 拉取镜像并重新部署（服务器端使用，与本地发布脚本无关）
# 用法:
#   ./script/redeploy.sh                 # 部署 latest
#   ./script/redeploy.sh --tag v0.2.1    # 部署指定版本
#   ./script/redeploy.sh --no-migrate    # 跳过数据库迁移（默认每次部署都执行，已迁移的库是幂等的）
# 可选：若环境中设置了 QUAY_USERNAME / QUAY_PASSWORD，脚本会先执行 docker login quay.io
# ==========================================

set -euo pipefail

IMAGE="quay.io/zrsk/hackerzrsk2026"
TAG="latest"
MIGRATE=true
HEALTH_URL="http://127.0.0.1:8000/api/health"

info()  { echo -e "\033[34m➤ $*\033[0m"; }
ok()    { echo -e "\033[32m✔ $*\033[0m"; }
warn()  { echo -e "\033[33m⚠ $*\033[0m"; }
die()   { echo -e "\033[31m✖ $*\033[0m" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)     TAG="${2:?--tag 需要版本号}"; shift 2 ;;
    --migrate) MIGRATE=true; shift ;;
    --no-migrate) MIGRATE=false; shift ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) die "未知参数: $1" ;;
  esac
done

# 部署目录自动定位：脚本同级有 docker-compose.yml 则它就是部署目录（服务器上脚本与 compose 同放）；
# 否则取上一级（仓库中脚本位于 <项目根>/script/）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/docker-compose.yml" ]]; then
  ROOT_DIR="${SCRIPT_DIR}"
else
  ROOT_DIR="$(dirname "${SCRIPT_DIR}")"
fi
cd "${ROOT_DIR}"
echo "部署目录: ${ROOT_DIR}"

command -v docker >/dev/null 2>&1 || die "未找到 docker（podman 环境请设置 alias docker=podman）"
docker compose version >/dev/null 2>&1 || die "未找到 docker compose（需要 Compose v2）"
[[ -f config/config.yml ]] || die "缺少 config/config.yml（参考 config/config.yml.example 创建）"

if [[ -n "${QUAY_USERNAME:-}" && -n "${QUAY_PASSWORD:-}" ]]; then
  info "登录 quay.io ..."
  printf '%s' "${QUAY_PASSWORD}" | docker login quay.io -u "${QUAY_USERNAME}" --password-stdin >/dev/null
fi

echo "=========================================="
echo " 部署镜像: ${IMAGE}:${TAG}"
echo "=========================================="

info "1. 拉取镜像 ${IMAGE}:${TAG} ..."
if ! docker pull "${IMAGE}:${TAG}"; then
  die "拉取失败：请确认标签 ${TAG} 已由 CI 构建，且镜像仓可访问（私有仓需先 docker login quay.io）"
fi
# compose 文件中的镜像可能固定为 :latest，这里把所选版本标记为 latest，保证 up 时运行的就是该版本
docker tag "${IMAGE}:${TAG}" "${IMAGE}:latest"

if $MIGRATE; then
  info "2. 执行数据库迁移（幂等）..."
  docker compose run --rm app python -m app.cli init-db
else
  info "2. 跳过数据库迁移（--no-migrate）"
fi

info "3. 重建并启动应用容器..."
docker compose up -d --force-recreate app

info "4. 等待健康检查 ${HEALTH_URL} ..."
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

info "5. 清理悬挂镜像（仅 dangling，不影响其它镜像）..."
docker image prune -f >/dev/null

docker compose ps
ok "部署完成：${IMAGE}:${TAG}"
