#!/usr/bin/env python
"""诊断脚本：验证 SignalDispatcher 路由稳定性"""
import os
import sys
import time

os.environ['NAJA_LAB_MODE'] = '1'

print("=" * 70)
print("诊断：Signal OutputController 路由稳定性")
print("=" * 70)

from deva.naja.signal.dispatcher import get_dispatcher, SignalDispatcher
from deva.naja.strategy.output_controller import get_output_controller, OutputConfig
from deva.naja.strategy.result_store import StrategyResult

print("\n[1] 获取 SignalDispatcher 实例...")
dispatcher = get_dispatcher()
print(f"    dispatcher id: {id(dispatcher)}")

print("\n[2] 获取 OutputController 实例...")
controller = get_output_controller()
print(f"    controller id: {id(controller)}")
print(f"    dispatcher 和 controller 是同一实例: {dispatcher is controller}")

print("\n[3] 检查默认配置...")
config = controller.get_config("test_strategy")
print(f"    默认配置: signal={config.signal}, radar={config.radar}, memory={config.memory}, bandit={config.bandit}")

print("\n[4] 更新配置并验证...")
controller.update_targets("test_strategy", radar=True, bandit=True, memory=False)
config = controller.get_config("test_strategy")
print(f"    更新后: signal={config.signal}, radar={config.radar}, memory={config.memory}, bandit={config.bandit}")

print("\n[5] 模拟信号分发...")
test_result = StrategyResult(
    id="dispatch_test_001",
    strategy_id="test_strategy",
    strategy_name="测试策略",
    ts=time.time(),
    success=True,
    input_preview="测试输入",
    output_preview="置信度: 0.7",
    output_full={
        'signal_type': 'BUY',
        'stock_code': '000001',
        'price': 10.0,
        'confidence': 0.7,
        'score': 0.75,
    },
    process_time_ms=0,
    error="",
    metadata={'source': 'diagnostic'}
)

print(f"    发送信号: strategy_id={test_result.strategy_id}")
print(f"    应该发送到: radar={controller.should_send_to('test_strategy', 'radar')}, bandit={controller.should_send_to('test_strategy', 'bandit')}")

try:
    dispatcher.dispatch(test_result)
    print("    dispatch() 调用成功")
except Exception as e:
    print(f"    dispatch() 失败: {e}")

print("\n[6] 测试配置持久化...")
controller2 = get_output_controller()
config2 = controller2.get_config("test_strategy")
print(f"    新实例读取: radar={config2.radar}, bandit={config2.bandit}")
print(f"    配置已持久化: {config.radar == config2.radar and config.bandit == config2.bandit}")

print("\n[7] 测试不存在的策略配置...")
config3 = controller.get_config("nonexistent_strategy")
print(f"    不存在策略默认配置: signal={config3.signal}, radar={config3.radar}, bandit={config3.bandit}")

print("\n" + "=" * 70)
print("诊断完成")
print("=" * 70)