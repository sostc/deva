#!/usr/bin/env python3
"""
测试注意力系统性能监控集成

运行此脚本验证性能监控是否正确接入注意力系统
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

import time
import numpy as np

print("="*60)
print("🔍 注意力系统性能监控集成测试")
print("="*60)

# 测试 1: 导入检查
print("\n📦 测试1: 模块导入检查")
try:
    from deva.naja.performance import (
        get_performance_monitor,
        ComponentType,
        record_component_execution
    )
    print("   ✅ 性能监控模块导入成功")
except Exception as e:
    print(f"   ❌ 性能监控模块导入失败: {e}")
    sys.exit(1)

try:
    from naja_attention_system import AttentionSystem, AttentionSystemConfig
    print("   ✅ 注意力系统模块导入成功")
except Exception as e:
    print(f"   ❌ 注意力系统模块导入失败: {e}")
    sys.exit(1)

try:
    from naja_attention_strategies import get_strategy_manager
    print("   ✅ 注意力策略管理器导入成功")
except Exception as e:
    print(f"   ❌ 注意力策略管理器导入失败: {e}")
    sys.exit(1)

try:
    from deva.naja.attention_orchestrator import get_orchestrator
    print("   ✅ 注意力调度中心导入成功")
except Exception as e:
    print(f"   ❌ 注意力调度中心导入失败: {e}")
    sys.exit(1)

# 测试 2: 初始化性能监控
print("\n🚀 测试2: 初始化性能监控")
try:
    monitor = get_performance_monitor()
    monitor.start_monitoring()
    print("   ✅ 性能监控已启动")
except Exception as e:
    print(f"   ❌ 性能监控启动失败: {e}")
    sys.exit(1)

# 测试 3: 初始化注意力系统
print("\n🎯 测试3: 初始化注意力系统")
try:
    config = AttentionSystemConfig()
    attention_system = AttentionSystem(config)

    # 模拟板块和股票映射
    from naja_attention_system.sector_attention import SectorConfig
    sectors = [
        SectorConfig(sector_id="tech", name="科技"),
        SectorConfig(sector_id="finance", name="金融"),
    ]
    symbol_sector_map = {
        "000001": ["finance"],
        "000002": ["tech"],
        "000063": ["tech"],
    }

    attention_system.initialize(sectors, symbol_sector_map)
    print("   ✅ 注意力系统初始化成功")
except Exception as e:
    print(f"   ❌ 注意力系统初始化失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试 4: 处理快照并记录性能
print("\n📊 测试4: 处理快照并记录性能")
try:
    # 模拟市场数据
    n_symbols = 3
    symbols = np.array(["000001", "000002", "000063"])
    returns = np.array([1.5, -0.5, 2.0])
    volumes = np.array([1000000, 2000000, 1500000])
    prices = np.array([10.5, 20.0, 15.5])
    sector_ids = np.array([0, 1, 1])
    timestamp = time.time()

    # 处理多次以产生性能数据
    for i in range(10):
        result = attention_system.process_snapshot(
            symbols=symbols,
            returns=returns + np.random.randn(n_symbols) * 0.5,
            volumes=volumes,
            prices=prices,
            sector_ids=sector_ids,
            timestamp=timestamp + i
        )

    print(f"   ✅ 已处理 10 次快照")
    print(f"   📈 平均延迟: {result.get('latency_ms', 0):.2f} ms")
except Exception as e:
    print(f"   ❌ 快照处理失败: {e}")
    import traceback
    traceback.print_exc()

# 测试 5: 检查性能监控数据
print("\n📈 测试5: 检查性能监控数据")
time.sleep(0.5)  # 等待数据写入
try:
    metrics = monitor.get_metrics_by_type(ComponentType.STRATEGY)
    attention_metrics = {k: v for k, v in metrics.items() if 'attention' in k.lower()}

    if attention_metrics:
        print(f"   ✅ 找到 {len(attention_metrics)} 个注意力相关性能指标:")
        for key, metric in attention_metrics.items():
            print(f"      • {key}:")
            print(f"        - 平均执行时间: {metric.get('avg_execution_time_ms', 0):.2f} ms")
            print(f"        - 调用次数: {metric.get('call_count', 0)}")
    else:
        print("   ⚠️ 未找到注意力相关性能指标")
        print("   📋 所有可用指标:")
        for key in list(metrics.keys())[:5]:
            print(f"      • {key}")
except Exception as e:
    print(f"   ❌ 检查性能数据失败: {e}")
    import traceback
    traceback.print_exc()

# 测试 6: 生成性能报告
print("\n📋 测试6: 生成性能报告")
try:
    report = monitor.get_full_report()
    print(f"   ✅ 性能报告生成成功")
    print(f"   📊 报告摘要:")
    print(f"      - 总组件数: {report['summary']['total_components']}")
    print(f"      - 慢组件数: {report['summary']['slow_components']}")
    print(f"      - 按类型分布: {report['summary']['by_type']}")
except Exception as e:
    print(f"   ❌ 生成报告失败: {e}")

# 测试 7: 策略管理器性能监控
print("\n🎮 测试7: 策略管理器性能监控")
try:
    manager = get_strategy_manager()
    if not manager.strategies:
        manager.initialize_default_strategies()
    if not manager.is_running:
        manager.start()

    # 模拟数据处理
    try:
        import pandas as pd
        mock_data = pd.DataFrame({
            'code': ['000001', '000002', '000063'],
            'name': ['平安银行', '万科A', '中兴通讯'],
            'now': [10.5, 20.0, 15.5],
            'close': [10.3, 20.2, 15.3],
            'volume': [1000000, 2000000, 1500000],
            'amount': [10000000, 40000000, 23250000],
        })

        context = {
            'global_attention': 0.6,
            'timestamp': time.time()
        }

        # 处理多次
        for i in range(5):
            signals = manager.process_data(mock_data, context)

        print(f"   ✅ 策略管理器已处理 5 次数据")
    except ImportError:
        print("   ⚠️ pandas 未安装，跳过策略管理器测试")
except Exception as e:
    print(f"   ❌ 策略管理器测试失败: {e}")
    import traceback
    traceback.print_exc()

# 最终检查
print("\n" + "="*60)
print("📊 最终性能监控数据检查")
print("="*60)
time.sleep(0.5)

try:
    all_metrics = monitor.get_metrics_by_type()
    attention_related = {k: v for k, v in all_metrics.items()
                        if any(x in k.lower() for x in ['attention', 'strategy', 'orchestrator'])}

    if attention_related:
        print(f"\n✅ 成功监控到 {len(attention_related)} 个注意力相关组件:")
        for key, metric in sorted(attention_related.items()):
            avg_time = metric.get('avg_execution_time_ms', 0)
            call_count = metric.get('call_count', 0)
            print(f"   • {key}")
            print(f"     平均: {avg_time:.2f}ms | 调用: {call_count}次")
    else:
        print("\n⚠️ 未找到注意力相关性能数据")

    # 慢组件报告
    slow_summary = monitor.get_slow_components_summary()
    if slow_summary['total_slow'] > 0:
        print(f"\n⚠️ 发现 {slow_summary['total_slow']} 个慢组件:")
        for comp_type, comps in slow_summary['by_type'].items():
            print(f"   • {comp_type}: {len(comps)} 个")
    else:
        print("\n✅ 未发现性能瓶颈")

except Exception as e:
    print(f"\n❌ 最终检查失败: {e}")

print("\n" + "="*60)
print("🎉 测试完成!")
print("="*60)

# 停止监控
monitor.stop_monitoring()
print("\n✅ 性能监控已停止")
