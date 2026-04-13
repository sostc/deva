#!/bin/bash

# Naja 安装脚本
# 用于自动安装 deva naja 及其依赖

set -e

echo "===================================="
echo "Naja 安装脚本"
echo "===================================="

# 检查 Python 版本
echo "检查 Python 版本..."
python3 --version

# 检查 pip
echo "检查 pip..."
pip3 --version

# 创建虚拟环境（可选）
echo "创建虚拟环境..."
python3 -m venv naja-env
source naja-env/bin/activate

# 安装依赖
echo "安装依赖..."
pip3 install --upgrade pip
pip3 install requests

# 安装 deva naja
echo "安装 deva naja..."
git clone https://github.com/sostc/deva.git || echo "deva 目录已存在"
cd deva
pip3 install -e .

# 安装 river 库（处理版本兼容性）
echo "安装 river 库..."
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
pip3 install river

# 返回技能目录
cd ..

echo "===================================="
echo "安装完成！"
echo "===================================="
echo ""
echo "使用说明："
echo "1. 启动 Naja 系统："
echo "   python -m deva.naja --port 8080"
echo ""
echo "2. 使用 naja-api 技能："
echo "   python skills/naja-api/scripts/api_client.py system-status"
echo ""
echo "3. 监控系统状态："
echo "   bash skills/naja-api/scripts/monitor_system.sh"
echo ""
echo "4. 监控市场热点："
echo "   bash skills/naja-api/scripts/monitor_market.sh"
echo ""
echo "5. 导出认知系统数据："
echo "   bash skills/naja-api/scripts/export_cognition.sh"
echo ""
echo "===================================="
echo "Naja 系统已安装完成，技能已就绪！"
echo "===================================="
