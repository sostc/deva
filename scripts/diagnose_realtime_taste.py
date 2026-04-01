#!/usr/bin/env python
"""诊断脚本：验证 RealtimeTaste 实时舌识系统"""
import os
import sys
import time

os.environ['NAJA_LAB_MODE'] = '1'

print("=" * 70)
print("诊断：实时舌识系统 (RealtimeTaste)")
print("=" * 70)

from deva.naja.senses.realtime_taste import RealtimeTaste, TasteSignal, FreshnessLevel

print("\n[1] 创建 RealtimeTaste 实例...")
taste = RealtimeTaste()
print(f"    实例创建成功")

print("\n[2] 注册持仓...")
taste.register_position("000001", entry_price=10.0, quantity=10000, entry_time=time.time())
print(f"    持仓注册成功")
state = taste.get_state()
print(f"    当前持仓数: {state.get('position_count')}")

print("\n[3] 模拟价格更新（盈利场景）...")
for i in range(5):
    price = 10.0 + (i + 1) * 0.1  # 逐渐上涨
    taste.update_price("000001", price)
    time.sleep(0.01)

signal = taste.taste_position("000001", 10.5)
if signal:
    print(f"    floating_pnl: {signal.floating_pnl:.2%}")
    print(f"    freshness: {signal.freshness:.2%}")
    print(f"    emotional_intensity: {signal.emotional_intensity:.2%}")
    print(f"    should_adjust: {signal.should_adjust}")
    if signal.adjust_reason:
        print(f"    adjust_reason: {signal.adjust_reason}")

print("\n[4] 模拟价格下跌（回吐场景）...")
for i in range(3):
    price = 10.5 - (i + 1) * 0.15  # 逐渐下跌
    taste.update_price("000001", price)
    time.sleep(0.01)

signal = taste.taste_position("000001", 10.0)
if signal:
    print(f"    floating_pnl: {signal.floating_pnl:.2%}")
    print(f"    freshness: {signal.freshness:.2%}")
    print(f"    pnl_trend: {signal.floating_pnl:.2%}")
    print(f"    should_adjust: {signal.should_adjust}")
    if signal.adjust_reason:
        print(f"    adjust_reason: {signal.adjust_reason}")

print("\n[5] 测试机会成本计算...")
taste.set_benchmark(0.08)  # 基准收益 8%
signal = taste.taste_position("000001", 10.5)
if signal:
    print(f"    floating_pnl: {signal.floating_pnl:.2%}")
    print(f"    benchmark: 8%")
    print(f"    opportunity_cost: {signal.opportunity_cost:.2%}")

print("\n[6] 测试多持仓尝受...")
taste.register_position("000002", entry_price=20.0, quantity=5000, entry_time=time.time())
prices = {"000001": 10.5, "000002": 21.0}
results = taste.taste_all(prices)
print(f"    尝受持仓数: {len(results)}")
for symbol, sig in results.items():
    print(f"    {symbol}: pnl={sig.floating_pnl:.2%}, freshness={sig.freshness:.2%}")

print("\n[7] 测试平仓...")
taste.close_position("000001")
state = taste.get_state()
print(f"    平仓后持仓数: {state.get('position_count')}")

print("\n[8] 获取持仓摘要...")
summary = taste.get_positions_summary()
print(f"    剩余持仓数: {len(summary)}")
for s in summary:
    print(f"    {s.get('symbol')}: entry={s.get('entry_price')}, current_pnl={s.get('current_pnl'):.2%}")

print("\n" + "=" * 70)
print("诊断完成")
print("=" * 70)