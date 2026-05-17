#!/bin/bash
#
# 通过 Git 更新服务器上的代码
# 使用方式: ./git_update_server.sh

SERVER="root@secsay.com"
REMOTE_PATH="/usr/local/lib/python3.10/site-packages/deva"
REPO_URL="https://github.com/sostc/deva.git"

echo "=== 通过 Git 更新服务器代码 ==="
echo "远程服务器: $SERVER"
echo "远程路径: $REMOTE_PATH"
echo ""

# 检查服务器上是否已初始化 git
ssh "$SERVER" << 'ENDSSH'
cd /usr/local/lib/python3.10/site-packages/deva

# 先备份当前代码
if [ ! -d .git ]; then
    echo "服务器上尚未初始化 git"
    echo "备份当前代码为 deva_backup..."
    cd ..
    cp -r deva deva_backup_$(date +%Y%m%d_%H%M%S)
    cd deva
    
    echo "初始化 git 仓库..."
    git init
    git config --global user.name "Server"
    git config --global user.email "server@secsay.com"
    git remote add origin https://github.com/sostc/deva.git
    
    echo "获取远程代码..."
    git fetch origin
    
    echo "重置到远程 master 分支（保留本地文件）..."
    git reset --mixed origin/master
    
    echo "同步远程文件（保留本地修改）..."
    git checkout origin/master -- .
    
    echo "清理不需要的文件（如 pyc 等）..."
    rm -f deva/naja/__pycache__/*.pyc 2>/dev/null
    rm -f deva/naja/**/__pycache__/*.pyc 2>/dev/null
else
    echo "服务器上已有 git 仓库"
    echo "获取远程更新..."
    git fetch origin
    
    echo "合并远程 master 分支..."
    git merge origin/master --no-edit
fi

echo ""
echo "=== 服务器上的 Git 状态 ==="
git status

echo ""
echo "=== 当前提交 ==="
git log -1 --stat
ENDSSH

echo ""
echo "=== Git 更新完成 ==="
echo ""

# 询问是否重启服务
read -p "是否重启服务器上的 Naja 服务? (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "重启 Naja 服务..."
    ssh "$SERVER" "kill \$(cat /root/naja.pid) 2>/dev/null; sleep 1; cd /root && python3 -m deva.naja --port 8080 --host 0.0.0.0 > /root/.naja/logs/naja_console.log 2>&1 & echo \$! > /root/naja.pid"
    echo "服务已重启"
fi
