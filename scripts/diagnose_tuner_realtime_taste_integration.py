#!/usr/bin/env python
"""诊断脚本：验证 RealtimeTaste 与 BanditTuner 集成"""
import os
import sys
import time

os.environ['NAJA_LAB_MODE'] = '1'

print("=" * 70)
print("诊断：RealtimeTaste 与 BanditTuner 集成")
print("=" * 70)

from deva.naja.bandit.tuner import get_bandit_tuner, BanditTuner

print("\n[1] 获取 BanditTuner 实例...")
tuner = get_bandit_tuner()
print(f"    tuner id: {id(tuner)}")

print("\n[2] 检查 RealtimeTaste 初始化...")
print(f"    tuner._realtime_taste: {tuner._realtime_taste}")
print(f"    类型: {type(tuner._realtime_taste).__name__}")

print("\n[3] 启动 Tuner...")
tuner.start()
time.sleep(0.1)

print("\n[4] 检查状态...")
status = tuner.get_status()
print(f"    running: {status.get('running')}")
print(f"    realtime_taste_enabled: {status.get('realtime_taste_enabled')}")

print("\n[5] 模拟开仓信号...")
from deva.naja.strategy.result_store import StrategyResult

test_result = StrategyResult(
    id="integration_test_001",
    strategy_id="TestStrategy",
    strategy_name="集成测试策略",
    ts=time.time(),
    success=True,
    input_preview="测试信号",
    output_preview="置信度: 0.8",
    output_full={
        'signal_type': 'BUY',
        'stock_code': '000001',
        'price': 10.0,
        'confidence': 0.8,
    },
    process_time_ms=0,
    error="",
    metadata={'source': 'diagnostic'}
)
tuner.on_signal(test_result)
time.sleep(0.1)

print("\n[6] 检查持仓同步到 RealtimeTaste...")
taste = tuner._realtime_taste
if taste:
    positions = taste.get_positions_summary()
    print(f"    RealtimeTaste 持仓数: {len(positions)}")
    for pos in positions:
        print(f"    持仓: {pos.get('symbol')} @ {pos.get('entry_price')}")

print("\n[7] 模拟价格更新（盈利场景）...")
for i in range(3):
    price = 10.0 + (i + 1) * 0.2
    print(f"    更新价格: {price}")
    tuner.on_price_update("000001", price)
    time.sleep(0.05)

print("\n[8] 检查舌识建议...")
taste_state = taste.get_state()
print(f"    舌识状态: {taste_state}")

print("\n[9] 检查持仓摘要...")
positions = taste.get_positions_summary()
for pos in positions:
    print(f"    {pos.get('symbol')}: pnl={pos.get('current_pnl'):.2%}, trend={pos.get('pnl_trend'):.2%}")

print("\n[10] 停止 Tuner...")
tuner.stop()

print("\n" + "=" * 70)
print("诊断完成")
print("=" * 70)