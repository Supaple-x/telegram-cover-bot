#!/bin/bash
# Bash Deploy Script for Telegram Cover Bot
# Деплой проекта на сервер

set -e

SERVER_USER="root"
SERVER_HOST="65.109.142.30"
SERVER_PATH="/opt/telegram-cover-bot"

SKIP_RESTART=false
if [[ "$1" == "--skip-restart" ]]; then
    SKIP_RESTART=true
fi

echo "🚀 Deploying Telegram Cover Bot to server..."

# 1. Sync files to server
echo ""
echo "📦 Syncing files to server..."
rsync -avz --progress \
    --exclude='.git' \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='.env' \
    --exclude='logs' \
    --exclude='downloads' \
    --exclude='*.pyc' \
    --exclude='.vscode' \
    ./ "${SERVER_USER}@${SERVER_HOST}:${SERVER_PATH}/"

echo "✅ Files synced successfully!"

# 2. Restart service if needed
if [ "$SKIP_RESTART" = false ]; then
    echo ""
    echo "🔄 Restarting bot service..."
    ssh "${SERVER_USER}@${SERVER_HOST}" "systemctl restart telegram-cover-bot"

    # Wait and check status
    sleep 2
    echo ""
    echo "📊 Service status:"
    ssh "${SERVER_USER}@${SERVER_HOST}" "systemctl status telegram-cover-bot --no-pager -l"
fi

echo ""
echo "✅ Deployment completed successfully!"
echo "💡 To skip service restart, use: ./deploy.sh --skip-restart"
