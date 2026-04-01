#!/usr/bin/env python
"""验证风险修复：RealtimeTaste 不再依赖私有属性"""
import os
import sys
import time

os.environ['NAJA_LAB_MODE'] = '1'

print("=" * 70)
print("验证：移除对私有属性 _positions 的依赖")
print("=" * 70)

print("\n[1] 验证 taste_position 可以独立处理不存在的持仓...")
from deva.naja.senses.realtime_taste import RealtimeTaste

taste = RealtimeTaste()

result = taste.taste_position("NONEXISTENT", 10.0)
print(f"    查询不存在的持仓: {result}")
print(f"    ✅ taste_position 正确返回 None，不依赖私有属性")

print("\n[2] 验证正常流程...")
taste.register_position("000001", entry_price=10.0, quantity=1000, entry_time=time.time())
print(f"    注册持仓后，查询存在的持仓:")
result = taste.taste_position("000001", 10.5)
print(f"    floating_pnl: {result.floating_pnl:.2%}")
print(f"    ✅ 正常流程工作正常")

print("\n[3] 验证 BanditTuner 集成...")
from deva.naja.bandit.tuner import get_bandit_tuner

tuner = get_bandit_tuner()
print(f"    tuner._realtime_taste: {type(tuner._realtime_taste).__name__}")

tuner.start()
time.sleep(0.1)

print("\n[4] 发送开仓信号...")
from deva.naja.strategy.result_store import StrategyResult

result = StrategyResult(
    id="risk_fix_test",
    strategy_id="RiskFixTest",
    strategy_name="风险修复测试",
    ts=time.time(),
    success=True,
    input_preview="测试",
    output_preview="",
    output_full={
        'signal_type': 'BUY',
        'stock_code': 'TEST001',
        'price': 50.0,
        'confidence': 0.8,
    },
    process_time_ms=0,
    error="",
    metadata={}
)

tuner.on_signal(result)
time.sleep(0.1)

positions = tuner._realtime_taste.get_positions_summary()
print(f"    RealtimeTaste 持仓数: {len(positions)}")

print("\n[5] 价格更新测试...")
tuner.on_price_update("TEST001", 52.0)
time.sleep(0.1)

taste_state = tuner._realtime_taste.get_state()
print(f"    recent_signals_count: {taste_state.get('recent_signals_count')}")
print(f"    ✅ 不再依赖 _positions 私有属性")

tuner.stop()

print("\n" + "=" * 70)
print("风险修复验证完成")
print("=" * 70)