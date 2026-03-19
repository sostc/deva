#!/usr/bin/env python3
"""
测试注意力系统和策略的完整流程

验证: realtime_tick_5s 数据源 -> 注意力系统 -> 策略执行
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

import time
import pandas as pd
import numpy as np

print("="*60)
print("🧪 测试注意力策略系统流程")
print("="*60)

# 1. 初始化注意力系统
print("\n1️⃣ 初始化注意力系统...")
from deva.naja.attention_integration import initialize_attention_system
from deva.naja.attention_orchestrator import initialize_orchestrator

attention_system = initialize_attention_system()
orchestrator = initialize_orchestrator()
print("   ✅ 注意力系统已初始化")

# 2. 初始化策略系统
print("\n2️⃣ 初始化策略系统...")
from naja_attention_strategies import setup_attention_strategies

manager = setup_attention_strategies()
print("   ✅ 策略系统已初始化")

# 3. 检查策略状态
print("\n3️⃣ 检查策略状态...")
stats = manager.get_all_stats()
print(f"   总策略数: {stats['total_strategies']}")
print(f"   活跃策略: {stats['active_strategies']}")
for strategy_id, strategy_stats in stats['strategy_stats'].items():
    status = "🟢" if strategy_stats['enabled'] else "🔴"
    print(f"   {status} {strategy_stats['name']}")

# 4. 模拟 realtime_tick_5s 数据
print("\n4️⃣ 模拟 realtime_tick_5s 数据...")

# 创建模拟数据（类似 realtime_tick_5s 的格式）
np.random.seed(42)
n_symbols = 100

mock_data = pd.DataFrame({
    'code': [f'SZ{str(i).zfill(6)}' for i in range(1, n_symbols + 1)],
    'now': np.random.uniform(10, 100, n_symbols),
    'close': np.random.uniform(10, 100, n_symbols),
    'open': np.random.uniform(10, 100, n_symbols),
    'high': np.random.uniform(10, 100, n_symbols),
    'low': np.random.uniform(10, 100, n_symbols),
    'volume': np.random.randint(100000, 10000000, n_symbols),
    'p_change': np.random.uniform(-5, 5, n_symbols),
})

print(f"   模拟数据: {len(mock_data)} 只股票")
print(f"   数据列: {list(mock_data.columns)}")

# 5. 测试数据流
print("\n5️⃣ 测试数据流...")
print("   发送数据到注意力调度中心...")

# 模拟数据源 emit 数据
orchestrator.process_datasource_data('realtime_tick_5s', mock_data)
print("   ✅ 数据已发送")

# 6. 检查注意力系统状态
print("\n6️⃣ 检查注意力系统状态...")
from deva.naja.attention_integration import get_attention_integration

integration = get_attention_integration()
report = integration.get_attention_report()

print(f"   全局注意力: {report.get('global_attention', 0):.3f}")
print(f"   处理快照数: {report.get('processed_snapshots', 0)}")

freq_summary = report.get('frequency_summary', {})
print(f"   高频股票: {freq_summary.get('high_frequency', 0)} 只")
print(f"   中频股票: {freq_summary.get('medium_frequency', 0)} 只")
print(f"   低频股票: {freq_summary.get('low_frequency', 0)} 只")

# 7. 检查策略执行结果
print("\n7️⃣ 检查策略执行结果...")
time.sleep(0.5)  # 等待策略执行

stats = manager.get_all_stats()
print(f"   总信号数: {stats['total_signals_generated']}")

# 获取最近信号
recent_signals = manager.get_recent_signals(n=10)
if recent_signals:
    print(f"   最近信号:")
    for signal in recent_signals[-5:]:
        print(f"     - {signal.symbol}: {signal.signal_type} (置信度: {signal.confidence:.2f})")
else:
    print("   暂无信号（可能需要更多数据或市场变化）")

# 8. 模拟多轮数据（模拟实时数据流）
print("\n8️⃣ 模拟多轮实时数据...")
print("   发送 10 轮模拟数据...")

for i in range(10):
    # 更新价格（模拟涨跌）
    mock_data['p_change'] = np.random.uniform(-5, 5, n_symbols)
    mock_data['now'] = mock_data['now'] * (1 + mock_data['p_change'] / 100)
    mock_data['volume'] = np.random.randint(100000, 10000000, n_symbols)
    
    # 发送到注意力系统
    orchestrator.process_datasource_data('realtime_tick_5s', mock_data)
    
    # 显示进度
    if (i + 1) % 5 == 0:
        print(f"     已发送 {i + 1}/10 轮")
    
    time.sleep(0.1)

print("   ✅ 数据发送完成")

# 9. 最终统计
print("\n9️⃣ 最终统计...")
stats = manager.get_all_stats()
print(f"   总信号数: {stats['total_signals_generated']}")

# 各策略统计
print("\n   各策略执行统计:")
for strategy_id, strategy_stats in stats['strategy_stats'].items():
    print(f"     - {strategy_stats['name']}:")
    print(f"       执行次数: {strategy_stats['execution_count']}")
    print(f"       跳过次数: {strategy_stats['skip_count']}")
    print(f"       信号数量: {strategy_stats['signal_count']}")

# 获取最近信号
recent_signals = manager.get_recent_signals(n=20)
if recent_signals:
    print(f"\n   最近信号 ({len(recent_signals)} 个):")
    for signal in recent_signals[-10:]:
        emoji = "🚀" if signal.signal_type == 'buy' else "💨" if signal.signal_type == 'sell' else "👀"
        print(f"     {emoji} {signal.symbol}: {signal.signal_type} | 置信度: {signal.confidence:.2f} | {signal.reason[:50]}...")

print("\n" + "="*60)
print("✅ 测试完成!")
print("="*60)
print("\n💡 说明:")
print("   - 注意力系统已自动跟随数据源启动")
print("   - 策略根据注意力水平自动调整执行频率")
print("   - 只有高注意力股票才会触发个股策略")
print("   - 板块轮动策略监控板块权重变化")
print("="*60)
