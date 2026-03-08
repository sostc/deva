#!/usr/bin/env python3
"""
测试信号流更新的脚本
"""

import time
from deva.naja.signal.stream import get_signal_stream
from deva.naja.strategy.result_store import StrategyResult, get_result_store

print("=" * 80)
print("🔍 测试信号流更新")
print("=" * 80)

# 清空信号流缓存
signal_stream = get_signal_stream()
signal_stream.clear()
print("信号流缓存已清空")
print(f"信号流缓存大小: {len(signal_stream.cache)}")
print(f"信号流 is_cache: {signal_stream.is_cache}")
print(f"信号流 cache_max_len: {getattr(signal_stream, 'cache_max_len', 'N/A')}")
print(f"信号流 cache_max_age_seconds: {getattr(signal_stream, 'cache_max_age_seconds', 'N/A')}")

# 直接测试 signal_stream.update 方法
print("\n直接测试 signal_stream.update 方法...")
test_result = StrategyResult(
    id="test_id_123",
    strategy_id="test_strategy_123",
    strategy_name="测试策略",
    ts=time.time(),
    success=True,
    input_preview="test input",
    output_preview="test output",
    output_full={"test": "data"},
    process_time_ms=10.5,
    error="",
    metadata={}
)

print("创建测试结果:")
print(f"  策略: {test_result.strategy_name}")
print(f"  时间: {time.ctime(test_result.ts)}")
print(f"  成功: {test_result.success}")

# 直接调用 update 方法
print("\n调用 signal_stream.update...")
signal_stream.update(test_result)

# 检查信号流
time.sleep(1)  # 等待信号流更新
print("\n检查信号流:")
print(f"信号流缓存大小: {len(signal_stream.cache)}")
print(f"信号流缓存内容: {list(signal_stream.cache.keys())}")

if signal_stream.cache:
    recent_signals = signal_stream.get_recent(limit=5)
    print("\n最近的信号:")
    for i, signal in enumerate(recent_signals, 1):
        print(f"{i}. 策略: {signal.strategy_name}")
        print(f"   时间: {time.ctime(signal.ts)}")
        print(f"   成功: {signal.success}")
        print(f"   输出预览: {signal.output_preview}")
        print("-" * 40)
else:
    print("信号流缓存为空!")

# 测试通过 store.save 方法
print("\n" + "=" * 80)
print("测试通过 store.save 方法...")
print("=" * 80)

# 清空信号流缓存
signal_stream.clear()
print("信号流缓存已清空")
print(f"信号流缓存大小: {len(signal_stream.cache)}")

# 获取结果存储
store = get_result_store()

# 保存结果（现在应该先发送到信号流，然后再保存）
print("\n保存结果...")
store.save(
    strategy_id=test_result.strategy_id,
    strategy_name=test_result.strategy_name,
    success=test_result.success,
    input_data="test input data",
    output_data={"test": "data"},
    process_time_ms=test_result.process_time_ms,
    error=test_result.error,
    persist=False
)

# 检查信号流
time.sleep(1)  # 等待信号流更新
print("\n检查信号流:")
print(f"信号流缓存大小: {len(signal_stream.cache)}")

if signal_stream.cache:
    recent_signals = signal_stream.get_recent(limit=5)
    print("\n最近的信号:")
    for i, signal in enumerate(recent_signals, 1):
        print(f"{i}. 策略: {signal.strategy_name}")
        print(f"   时间: {time.ctime(signal.ts)}")
        print(f"   成功: {signal.success}")
        print(f"   输出预览: {signal.output_preview}")
        print("-" * 40)
else:
    print("信号流缓存为空!")

print("\n" + "=" * 80)
print("测试完成")
print("=" * 80)
