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
print("       - 查看当前模型配置状态")
print("       - 配置 Kimi/DeepSeek/Qwen/GPT 模型")
print("       - 测试模型连接")
print()
print("     💻 代码生成 Tab:")
print("       - 生成量化策略代码")
print("       - 生成数据源代码")
print("       - 生成任务代码")
print()
print("     💬 智能对话 Tab:")
print("       - 与 AI 进行对话")
print("       - 测试多轮对话")
print()
print("     🎯 功能演示 Tab:")
print("       - 文章摘要生成")
print("       - 链接提取")
print("       - 数据分析")
print("       - 新闻翻译")
print()
print("=" * 60)
print("按 Ctrl+C 停止服务")
print("=" * 60)
print()

# 启动 Admin UI
from deva.admin import admin

if __name__ == '__main__':
    admin()
