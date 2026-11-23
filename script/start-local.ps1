# 本地启动：Docker 运行数据库，后端同时托管构建后的前端。
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    if (!(Test-Path -LiteralPath '.env') -or !(Test-Path -LiteralPath 'backend/.env')) {
        throw '缺少本地配置，请先按 项目说明.md 配置根目录 .env 和 backend/.env。'
    }
    $listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        throw "8000 端口已被进程 PID=$($listener.OwningProcess) 占用。请先检查 http://127.0.0.1:8000，或停止旧服务后重试。"
    }

    docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw '请先启动 Docker Desktop，等待引擎就绪后重试。'
    }
    docker compose -p hackerzrsk2026-local up -d --wait db
    if ($LASTEXITCODE -ne 0) { throw '数据库启动失败。' }

    Push-Location frontend
    try {
        pnpm build
        if ($LASTEXITCODE -ne 0) { throw '前端构建失败。' }
    } finally { Pop-Location }

    Push-Location backend
    try {
        Write-Host '正在启动：http://127.0.0.1:8000（Ctrl+C 停止后端）'
        # 使用 backend 自己的 uv 环境，避免 IDE 激活的根目录环境干扰。
        $previousVirtualEnv = $env:VIRTUAL_ENV
        try {
            Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
            uv run --locked python -m app
            if ($LASTEXITCODE -ne 0) { throw '后端启动失败，请查看上方错误。' }
        } finally {
            $env:VIRTUAL_ENV = $previousVirtualEnv
        }
    } finally { Pop-Location }
} finally { Pop-Location }
