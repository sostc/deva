#!/usr/bin/env python3
"""
实时监控注意力系统日志

运行此脚本可以查看注意力系统的详细日志输出
"""

import subprocess
import sys

def watch_logs():
    """监控注意力系统日志"""
    print("=" * 70)
    print("注意力系统日志监控")
    print("=" * 70)
    print("\n正在监控以下日志模式:")
    print("  - [Orchestrator]  数据源处理日志")
    print("  - [AttentionSnapshot] 快照记录日志")
    print("  - [AttentionChange] 变化检测日志")
    print("\n按 Ctrl+C 停止监控\n")
    print("=" * 70)
    
    # 使用 ps 找到 naja 进程，然后跟踪其日志
    # 由于 naja 输出到 stdout，我们需要重启它并捕获日志
    
    # 先检查 naja 是否在运行
    result = subprocess.run(
        ["ps", "aux"], 
        capture_output=True, 
        text=True
    )
    
    if "python -m deva.naja" not in result.stdout:
        print("❌ naja 未在运行，请先启动 naja")
        print("   命令: python -m deva.naja --attention")
        return
    
    print("✅ naja 正在运行")
    print("\n注意：由于 naja 已经运行，你需要查看其终端输出")
    print("或者重启 naja 以查看新的日志输出\n")
    
    # 显示如何查看日志
    print("查看日志的方法:")
    print("1. 查看 naja 启动日志:")
    print("   tail -f /tmp/naja_startup.log")
    print("")
    print("2. 或者直接查看当前运行的 naja 输出:")
    print("   找到 naja 运行的终端窗口查看输出")
    print("")
    print("3. 重启 naja 并捕获日志:")
    print("   pkill -f 'python -m deva.naja'")
    print("   python -m deva.naja --attention 2>&1 | tee /tmp/naja_attention.log")

if __name__ == "__main__":
    watch_logs()
