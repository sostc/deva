#!/usr/bin/env python3
"""
检查信号流状态的脚本
"""

import time
from deva.naja.signal.stream import get_signal_stream
from deva.naja.strategy.result_store import StrategyResult

# 获取信号流实例
signal_stream = get_signal_stream()

print("=" * 80)
print("🔍 信号流状态检查")
print("=" * 80)

# 检查信号流缓存
print(f"信号流缓存大小: {len(signal_stream.cache)}")

if signal_stream.cache:
    print("\n最近的信号:")
    recent_signals = signal_stream.get_recent(limit=10)
    for i, signal in enumerate(recent_signals, 1):
        print(f"{i}. ID: {signal.id}")
        print(f"   策略: {signal.strategy_name}")
        print(f"   时间: {time.ctime(signal.ts)}")
        print(f"   成功: {signal.success}")
        print(f"   输出预览: {signal.output_preview[:50]}...")
        print("-" * 40)
else:
    print("\n信号流缓存为空!")

print("\n" + "=" * 80)
print("检查完成")
print("=" * 80)
