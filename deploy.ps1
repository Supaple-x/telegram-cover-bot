# PowerShell Deploy Script for Telegram Cover Bot
# Деплой проекта на сервер

param(
    [switch]$SkipRestart
)

$SERVER_USER = "root"
$SERVER_HOST = "65.109.142.30"
$SERVER_PATH = "/opt/telegram-cover-bot"
$LOCAL_PATH = "C:\Dev\telegram-cover-bot"

Write-Host "🚀 Deploying Telegram Cover Bot to server..." -ForegroundColor Green

# 1. Sync files to server (excluding .git, venv, etc.)
Write-Host "`n📦 Syncing files to server..." -ForegroundColor Yellow
scp -r `
    --exclude='.git' `
    --exclude='venv' `
    --exclude='__pycache__' `
    --exclude='.env' `
    --exclude='logs' `
    --exclude='downloads' `
    --exclude='*.pyc' `
    --exclude='.vscode' `
    "$LOCAL_PATH\*" "${SERVER_USER}@${SERVER_HOST}:${SERVER_PATH}/"

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to sync files!" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Files synced successfully!" -ForegroundColor Green

# 2. Restart service if needed
if (-not $SkipRestart) {
    Write-Host "`n🔄 Restarting bot service..." -ForegroundColor Yellow
    ssh "${SERVER_USER}@${SERVER_HOST}" "systemctl restart telegram-cover-bot"

    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to restart service!" -ForegroundColor Red
        exit 1
    }

    # Wait a moment and check status
    Start-Sleep -Seconds 2
    Write-Host "`n📊 Service status:" -ForegroundColor Yellow
    ssh "${SERVER_USER}@${SERVER_HOST}" "systemctl status telegram-cover-bot --no-pager -l"
}

Write-Host "`n✅ Deployment completed successfully!" -ForegroundColor Green
Write-Host "💡 To skip service restart, use: .\deploy.ps1 -SkipRestart" -ForegroundColor Cyan
