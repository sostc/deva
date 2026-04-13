#!/bin/bash

# Naja 安装脚本
# 用于自动检测并安装 deva naja 及其依赖

set -e

echo "===================================="
echo "Naja 安装脚本"
echo "===================================="

# ── 1. 检查 Python 版本 ──
echo ""
echo "[1/5] 检查 Python 版本..."
python3 --version || { echo "错误: 需要 Python 3.7+"; exit 1; }

# ── 2. 检测 deva 是否已安装 ──
echo ""
echo "[2/5] 检测 deva 是否已安装..."
DEVA_INSTALLED=false

if python3 -c "import deva" 2>/dev/null; then
    DEVA_INSTALLED=true
    echo "  ✅ deva 已安装"
    # 检查 naja 模块
    if python3 -c "from deva.naja import __main__" 2>/dev/null; then
        echo "  ✅ deva.naja 模块可用"
    else
        echo "  ⚠️ deva 已安装但 naja 模块不可用，将重新安装"
        DEVA_INSTALLED=false
    fi

    # deva 已安装，检查是否有更新
    if [ "$DEVA_INSTALLED" = true ]; then
        echo "  🔄 检查 deva 更新..."
        DEVADIR=""
        for d in deva ../deva /workspace/deva; do
            if [ -d "$d/.git" ]; then
                DEVADIR="$d"
                break
            fi
        done
        if [ -n "$DEVADIR" ]; then
            cd "$DEVADIR"
            # 获取当前 commit hash
            OLD_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
            # 异步拉取更新（超时10秒）
            UPDATE_OUTPUT=$(timeout 10 git pull --ff-only 2>&1) || true
            NEW_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
            cd - > /dev/null
            if [ "$OLD_HASH" != "$NEW_HASH" ]; then
                echo "  ✅ deva 已更新 ($OLD_HASH → $NEW_HASH)"
                echo "  📝 更新内容:"
                echo "$UPDATE_OUTPUT" | grep -E "^ [a-z]" | head -5 | sed 's/^/    /'
                # 重新安装以应用更新
                echo "  🔄 重新安装 deva..."
                cd "$DEVADIR"
                pip3 install --break-system-packages -e . 2>&1 | tail -1
                cd - > /dev/null
                echo "  ✅ 重新安装完成"
            else
                echo "  ✅ deva 已是最新 ($OLD_HASH)"
            fi
        else
            echo "  ⚠️ 未找到 deva git 目录，跳过更新检查"
        fi
    fi
fi

if [ "$DEVA_INSTALLED" = false ]; then
    echo "  ❌ deva 未安装，开始安装..."
    echo ""
    echo "  安装 deva 依赖..."
    pip3 install --break-system-packages aiohttp requests pyyaml or \
    pip3 install aiohttp requests pyyaml

    echo ""
    echo "  克隆 deva 仓库..."
    if [ -d "deva" ] || [ -d "../deva" ]; then
        echo "  ⚠️ deva 目录已存在，跳过克隆"
        DEVADIR=$(ls -d deva ../deva 2>/dev/null | head -1)
    else
        git clone https://github.com/sostc/deva.git
        DEVADIR="deva"
    fi

    echo ""
    echo "  安装 deva（pip install -e .）..."
    cd "$DEVADIR"
    pip3 install --break-system-packages -e . 2>&1 | tail -3
    cd - > /dev/null

    # 安装 river 库（处理版本兼容性）
    echo ""
    echo "  安装 river 库..."
    export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
    pip3 install --break-system-packages river 2>&1 | tail -3

    echo ""
    echo "  ✅ deva 安装完成"
fi

# ── 3. 验证安装 ──
echo ""
echo "[3/5] 验证安装..."
python3 -c "
import deva
print('  ✅ import deva 成功')
" || { echo "  ❌ import deva 失败"; exit 1; }

python3 -c "
from deva.naja.register import SR
print('  ✅ deva.naja 模块加载成功')
" || { echo "  ❌ deva.naja 模块加载失败"; exit 1; }

# ── 4. 检测 naja 是否已在运行 ──
echo ""
echo "[4/5] 检测 naja 运行状态..."
NAJA_RUNNING=false
if curl -s http://localhost:8080/api/health > /dev/null 2>&1; then
    NAJA_RUNNING=true
    echo "  ✅ naja 已在端口 8080 运行"
fi

if [ "$NAJA_RUNNING" = false ]; then
    echo "  ❌ naja 未运行"
    echo ""
    echo "  ⚡ 正在启动 naja 系统（后台运行）..."
    echo "  命令: python -m deva.naja --port 8080"
    echo ""

    # 确定工作目录
    if [ -d "deva" ]; then
        WORKDIR="deva"
    elif [ -d "../deva" ]; then
        WORKDIR="../deva"
    else
        WORKDIR="."
    fi

    cd "$WORKDIR"
    nohup python3 -m deva.naja --port 8080 > /tmp/naja.log 2>&1 &
    NAJA_PID=$!
    cd - > /dev/null

    echo "  PID: $NAJA_PID"
    echo "  日志: /tmp/naja.log"
    echo ""
    echo "  ⏳ 等待 naja 启动（15秒）..."

    # 等待启动
    for i in $(seq 1 15); do
        sleep 1
        if curl -s http://localhost:8080/api/health > /dev/null 2>&1; then
            echo "  ✅ naja 启动成功！（耗时 ${i} 秒）"
            NAJA_RUNNING=true
            break
        fi
        echo "  ... 等待中 (${i}/15)"
    done

    if [ "$NAJA_RUNNING" = false ]; then
        echo "  ⚠️ naja 启动超时，请检查日志: tail -50 /tmp/naja.log"
        echo "  提示: naja 可能需要更长时间初始化，请稍后手动检查"
    fi
fi

# ── 5. 最终验证 ──
echo ""
echo "[5/5] 最终验证..."
if curl -s http://localhost:8080/api/system/status > /dev/null 2>&1; then
    HEALTH=$(curl -s http://localhost:8080/api/system/status 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('overall','未知'))" 2>/dev/null || echo "未知")
    echo "  ✅ 系统状态: $HEALTH"
else
    echo "  ⚠️ API 暂时不可用（系统可能仍在初始化中）"
fi

echo ""
echo "===================================="
echo "安装完成！"
echo "===================================="
echo ""
echo "📋 安装摘要:"
echo "  - deva: $([ "$DEVA_INSTALLED" = true ] && echo '已安装（跳过）' || echo '新安装')"
echo "  - naja: $([ "$NAJA_RUNNING" = true ] && echo '运行中 (http://localhost:8080)' || echo '未运行')"
echo ""
echo "📌 常用命令:"
echo "  检查状态:  curl -s http://localhost:8080/api/system/status | python3 -m json.tool"
echo "  认知记忆:  curl -s http://localhost:8080/api/cognition/memory | python3 -m json.tool"
echo "  知识库:    curl -s http://localhost:8080/api/knowledge/list | python3 -m json.tool"
echo "  Manas:     curl -s http://localhost:8080/api/attention/manas/state | python3 -m json.tool"
echo "  停止 naja: lsof -ti:8080 | xargs kill"
echo "  查看日志:  tail -f /tmp/naja.log"
echo ""
echo "===================================="
