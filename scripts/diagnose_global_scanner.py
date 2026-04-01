#!/usr/bin/env python
"""诊断脚本：验证 GlobalMarketScanner 异步任务管理修复"""
import os
import sys
import time

os.environ['NAJA_RADAR_DEBUG'] = 'true'

print("=" * 70)
print("诊断：GlobalMarketScanner 异步任务管理")
print("=" * 70)

from deva.naja.radar.engine import RadarEngine

print("\n[1] 获取 RadarEngine 实例...")
engine = RadarEngine()
print(f"    engine id: {id(engine)}")

print("\n[2] 启动 GlobalMarketScanner...")
result = engine.start_global_market_scanner(
    fetch_interval=5,
    alert_threshold_volatility=2.0,
    alert_threshold_single=3.0
)
print(f"    启动结果: {result}")

time.sleep(3)

print("\n[3] 检查 GlobalMarketScanner 状态...")
if engine._global_scanner:
    print(f"    scanner: {engine._global_scanner}")
    print(f"    scanner._running: {engine._global_scanner._running}")
else:
    print("    scanner: None")

print("\n[4] 获取统计信息...")
stats = engine.get_global_market_scanner_stats()
print(f"    统计: {stats}")

print("\n[5] 停止 GlobalMarketScanner...")
engine.stop_global_market_scanner()
time.sleep(1)
print(f"    停止后 scanner: {engine._global_scanner}")

print("\n" + "=" * 70)
print("诊断完成")
print("=" * 70)