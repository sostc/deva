#!/usr/bin/env python3
"""
检查信号流时间戳和属性的脚本
"""

import time
from datetime import datetime
from deva.naja.signal.stream import get_signal_stream

# 获取信号流实例
signal_stream = get_signal_stream()

print("=" * 80)
print("🕒 信号流时间戳检查")
print("=" * 80)

# 获取当前时间
current_time = time.time()
print(f"当前时间: {datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')}")
print()

# 检查信号流缓存
print(f"信号流缓存大小: {len(signal_stream.cache)}")

if signal_stream.cache:
    print("\n最近的信号时间戳:")
    recent_signals = signal_stream.get_recent(limit=20)
    
    # 按时间戳排序（最新的在前）
    recent_signals.sort(key=lambda x: x.ts, reverse=True)
    
    for i, signal in enumerate(recent_signals, 1):
        signal_time = datetime.fromtimestamp(signal.ts)
        time_diff = current_time - signal.ts
        
        print(f"{i}. 时间: {signal_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   策略: {signal.strategy_name}")
        print(f"   ID: {signal.id}")
        print(f"   成功: {signal.success}")
        print(f"   时间差: {time_diff:.2f} 秒")
        print(f"   时间戳: {signal.ts}")
        print("-" * 40)
        
        # 检查时间戳是否合理
        if time_diff > 3600:  # 超过1小时
            print("   ⚠️  时间戳过旧！")
            print("-" * 40)
else:
    print("\n信号流缓存为空!")

print("\n" + "=" * 80)
print("检查完成")
print("=" * 80)
