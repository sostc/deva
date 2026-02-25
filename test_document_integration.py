#!/usr/bin/env python
# coding: utf-8
"""
文档集成测试脚本

运行此脚本启动 Deva admin UI，然后在浏览器中访问文档 tab 查看集成效果。
"""

from deva import Deva

def main():
    print("=" * 60)
    print("Deva 文档集成测试")
    print("=" * 60)
    print()
    print("正在启动 Deva Admin UI...")
    print()
    print("访问地址：http://127.0.0.1:9999")
    print("然后点击导航菜单中的【文档】选项卡")
    print()
    print("文档中心包含以下内容:")
    print("  - 快速开始")
    print("  - 安装指南")
    print("  - 使用指南")
    print("  - 最佳实践")
    print("  - 故障排查")
    print("  - API 参考")
    print("  - 术语表")
    print("  - 示例文档")
    print("  - 文档优化报告")
    print("  - 各模块 API 文档")
    print()
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    
    # 启动 admin UI
    from deva.admin import admin
    admin()

if __name__ == '__main__':
    main()
