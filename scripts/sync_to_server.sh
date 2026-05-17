#!/bin/bash
#
# 同步 deva/naja 代码到服务器
# 使用方式: ./sync_to_server.sh [可选的文件路径]
# 如果不指定路径，同步整个 deva/naja 目录

SERVER="root@secsay.com"
REMOTE_PATH="/usr/local/lib/python3.10/site-packages/deva/naja/"
LOCAL_PATH="deva/naja/"

echo "=== 同步代码到服务器 ==="
echo "本地路径: $LOCAL_PATH"
echo "远程路径: $REMOTE_PATH"
echo ""

if [ -n "$1" ]; then
    # 同步指定文件
    echo "同步指定文件: $1"
    scp "$1" "$SERVER:$REMOTE_PATH${1#$LOCAL_PATH}"
else
    # 同步整个 naja 目录
    echo "同步整个 naja 目录..."
    rsync -av --delete \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='*.pyo' \
        --exclude='.git' \
        --exclude='*.log' \
        "$LOCAL_PATH" "$SERVER:$REMOTE_PATH../"
fi

echo ""
echo "=== 同步完成 ==="

# 询问是否重启服务
read -p "是否重启服务器上的 Naja 服务? (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "重启 Naja 服务..."
    ssh "$SERVER" "kill \$(cat /root/naja.pid) 2>/dev/null; sleep 1; cd /root && python3 -m deva.naja --port 8080 --host 0.0.0.0 > /root/.naja/logs/naja_console.log 2>&1 & echo \$! > /root/naja.pid"
    echo "服务已重启"
fi