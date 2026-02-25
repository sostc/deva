#!/usr/bin/env python
# coding: utf-8
"""
测试 AI 功能中心

运行此脚本启动 Admin UI，然后在浏览器中访问 AI Tab 测试功能。

使用方法：
    python test_ai_center.py
"""

print("=" * 60)
print("Deva AI 功能中心测试")
print("=" * 60)
print()
print("正在启动 Deva Admin UI...")
print()
print("访问地址：http://127.0.0.1:9999")
print()
print("测试步骤：")
print("  1. 在浏览器中访问上述地址")
print("  2. 登录 Admin UI（如果需要）")
print("  3. 点击导航栏的 🤖 AI 菜单")
print("  4. 测试以下功能：")
print()
print("     🤖 模型配置 Tab:")
print("       - 配置 DeepSeek/Kimi/Sambanova/Qwen 模型")
print("       - 测试模型连接")
print("       - 查看配置指南")
print()
print("     💬 智能对话 Tab:")
print("       - 与 AI 进行多轮对话")
print("       - 测试问题解答")
print()
print("     💻 代码生成 Tab:")
print("       - 生成 Python 代码")
print("       - 生成 Deva 策略")
print("       - 生成 Deva 数据源")
print("       - 生成 Deva 任务")
print()
print("     📝 文本处理 Tab:")
print("       - 文章摘要生成")
print("       - 文本翻译")
print("       - 文本润色")
print("       - 文本分析")
print()
print("=" * 60)
print("按 Ctrl+C 停止服务")
print("=" * 60)
print()

# 启动 Admin UI
from deva.admin import admin

if __name__ == '__main__':
    admin()
