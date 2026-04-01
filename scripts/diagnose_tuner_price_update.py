#!/usr/bin/env python
"""诊断脚本：验证 BanditTuner.on_price_update 链路"""
import os
import sys
import time

os.environ['NAJA_LAB_MODE'] = '1'
os.environ['NAJA_TUNE_MODE'] = '1'

print("=" * 70)
print("诊断：BanditTuner.on_price_update 链路验证")
print("=" * 70)

from deva.naja.bandit.tuner import get_bandit_tuner

print("\n[1] 获取 BanditTuner 实例...")
tuner = get_bandit_tuner()
print(f"    tuner id: {id(tuner)}")
print(f"    tuner._running: {tuner._running}")
print(f"    tuner._portfolio: {tuner._portfolio}")

print("\n[2] 调用 tuner.start()...")
tuner.start()
print(f"    tuner._running: {tuner._running}")
print(f"    tuner._portfolio: {tuner._portfolio}")

print("\n[3] 获取 Portfolio...")
portfolio = tuner._get_portfolio()
print(f"    portfolio: {portfolio}")
if portfolio:
    print(f"    portfolio._total_capital: {portfolio._total_capital}")
    print(f"    portfolio._positions: {portfolio._positions}")

print("\n[4] 模拟开仓...")
from deva.naja.strategy.result_store import StrategyResult
test_result = StrategyResult(
    id="test_signal_001",
    strategy_id="DiagnosticTest",
    strategy_name="诊断测试",
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
print(f"    发送信号: {test_result.output_full}")
tuner.on_signal(test_result)
time.sleep(0.1)

print(f"\n[5] 检查持仓...")
if portfolio:
    positions = portfolio.get_all_positions(status="OPEN")
    print(f"    开仓数量: {len(positions)}")
    for pos in positions:
        print(f"    持仓: {pos.stock_code} @ {pos.entry_price}, 数量={pos.quantity}, 止损={pos.stop_loss}%, 止盈={pos.take_profit}%")

print(f"\n[6] 模拟价格更新 (触发止盈/止损检查)...")
print(f"    当前持仓数量: {len(positions) if portfolio else 0}")
if positions:
    pos = list(positions)[0]
    stock_code = pos.stock_code
    print(f"\n    测试场景A: 价格下跌触发止损")
    print(f"    持仓成本: {pos.entry_price}, 止损线: {pos.stop_loss}%")
    new_price = pos.entry_price * 0.94  # 下跌6%，应该触发止损
    print(f"    新价格: {new_price} (下跌6%)")
    tuner.on_price_update(stock_code, new_price)
    time.sleep(0.1)

    positions_after = portfolio.get_all_positions(status="OPEN")
    positions_closed = portfolio.get_all_positions(status="CLOSED")
    print(f"    更新后 - 开仓数: {len(positions_after)}, 平仓数: {len(positions_closed)}")
    for p in positions_closed:
        print(f"    平仓记录: {p.stock_code} @ {p.exit_price}, 原因={p.close_reason}, P&L={p.profit_loss:.2f}")
else:
    print("    没有持仓，跳过价格更新测试")

print("\n[7] 直接测试 on_price_update 的 _running 检查...")
print(f"    当前 tuner._running: {tuner._running}")

# 测试在不启动的情况下调用
print("\n[8] 测试未启动时调用 on_price_update...")
tuner2 = get_bandit_tuner()
print(f"    tuner2._running: {tuner2._running}")
tuner2.on_price_update("000002", 20.0)  # 应该被静默跳过
print("    调用完成（应该无输出，因为 _running=False）")

print("\n" + "=" * 70)
print("诊断完成")
print("=" * 70)