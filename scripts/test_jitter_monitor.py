#!/usr/bin/env python3
"""
抖动监测测试脚本

用于验证性能监控中的抖动检测功能是否正常工作。
直接导入模块进行测试，不依赖完整的naja系统。

使用方法:
    python scripts/test_jitter_monitor.py
"""

import sys
import time
import threading
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from deva.naja.performance import (
    get_performance_monitor,
    record_component_execution,
    record_data_arrival,
    ComponentType,
    NajaPerformanceMonitor,
)


def simulate_data_arrivals(datasource_id: str, interval_ms: float, count: int):
    """模拟数据源按固定间隔发送数据"""
    print(f"\n📡 模拟数据源 '{datasource_id}' 发送 {count} 次数据，间隔 {interval_ms}ms")
    print("   (理想情况下，不应该有抖动)")

    for i in range(count):
        record_data_arrival(
            datasource_id=datasource_id,
            expected_interval_ms=interval_ms,
        )
        time.sleep(interval_ms / 1000)


def simulate_strategy_executions(strategy_id: str, interval_ms: float, count: int):
    """模拟策略按固定间隔执行"""
    print(f"\n🎯 模拟策略 '{strategy_id}' 执行 {count} 次，间隔 {interval_ms}ms")
    print("   (理想情况下，不应该有抖动)")

    for i in range(count):
        record_component_execution(
            component_id=f"strategy_{strategy_id}",
            component_name=f"策略: {strategy_id}",
            component_type=ComponentType.STRATEGY,
            execution_time_ms=10.0 + (hash(str(i)) % 5),  # 模拟10-15ms的执行时间
            success=True,
            expected_interval_ms=interval_ms,
        )
        time.sleep(interval_ms / 1000)


def simulate_jittered_data_arrivals(datasource_id: str, expected_interval_ms: float, count: int):
    """模拟有抖动的数据到达"""
    print(f"\n⚠️  模拟数据源 '{datasource_id}' 发送 {count} 次数据，有抖动")
    print(f"   期望间隔: {expected_interval_ms}ms，实际间隔随机 500ms - {expected_interval_ms*2}ms")

    for i in range(count):
        record_data_arrival(
            datasource_id=datasource_id,
            expected_interval_ms=expected_interval_ms,
        )
        # 模拟抖动：随机间隔
        import random
        actual_interval_ms = random.randint(500, int(expected_interval_ms * 2))
        time.sleep(actual_interval_ms / 1000)


def print_jitter_report():
    """打印抖动监测报告"""
    monitor = get_performance_monitor()

    print("\n" + "=" * 70)
    print("                         抖动监测报告")
    print("=" * 70)

    has_jitter_data = False

    with monitor._metrics_lock:
        for key, metrics in monitor._metrics.items():
            component_type, component_id = key

            # 检查是否有抖动数据
            if (hasattr(metrics, 'expected_interval_ms') and
                metrics.expected_interval_ms > 0 and
                len(metrics.call_intervals_ms) >= 3):

                has_jitter_data = True
                stats = {
                    'expected_interval_ms': metrics.expected_interval_ms,
                    'avg_interval_ms': metrics.avg_call_interval_ms,
                    'std_interval_ms': metrics.std_call_interval_ms,
                    'jitter_ratio': metrics.jitter_ratio,
                    'jitter_status': metrics.jitter_status,
                    'calls_per_minute': metrics.calls_per_minute,
                }

                print(f"\n📊 {metrics.component_name}")
                print(f"   类型: {component_type.value}")
                print(f"   期望间隔: {stats['expected_interval_ms']:.0f}ms")
                print(f"   平均间隔: {stats['avg_interval_ms']:.1f}ms")
                print(f"   标准差: {stats['std_interval_ms']:.1f}ms")

                jitter_pct = stats['jitter_ratio'] * 100
                if stats['jitter_status'] == 'stable':
                    status_icon = "✅"
                elif stats['jitter_status'] == 'minor_jitter':
                    status_icon = "🟡"
                elif stats['jitter_status'] == 'moderate_jitter':
                    status_icon = "⚠️"
                else:
                    status_icon = "🔴"

                print(f"   抖动率: {jitter_pct:.1f}% {status_icon} ({stats['jitter_status']})")
                print(f"   调用次数: {metrics.call_count}")

                # 与期望间隔的偏差
                deviation = abs(stats['avg_interval_ms'] - stats['expected_interval_ms'])
                deviation_pct = (deviation / stats['expected_interval_ms'] * 100) if stats['expected_interval_ms'] > 0 else 0
                print(f"   与期望偏差: {deviation:.1f}ms ({deviation_pct:.1f}%)")

    if not has_jitter_data:
        print("\n⚠️  还没有收集到足够的抖动数据，请先运行模拟")

    print("\n" + "=" * 70)


def main():
    print("""
╔═══════════════════════════════════════════════════════════════════════╗
║                    抖动监测功能测试脚本                               ║
║                                                                       ║
║  测试内容:                                                            ║
║  1. 模拟稳定的数据源到达 (5000ms间隔)                                  ║
║  2. 模拟稳定的策略执行 (5000ms间隔)                                    ║
║  3. 模拟有抖动的数据源到达 (随机间隔)                                  ║
║  4. 打印抖动监测报告                                                   ║
╚═══════════════════════════════════════════════════════════════════════╝
    """)

    # 重置性能监控器
    monitor = get_performance_monitor()
    monitor.reset_metrics()

    # 测试1: 模拟稳定的数据源
    simulate_data_arrivals("test_stable_datasource", 5000, 10)

    # 测试2: 模拟稳定的策略执行
    simulate_strategy_executions("stable_strategy", 5000, 10)

    # 测试3: 模拟有抖动的数据源
    simulate_jittered_data_arrivals("test_jittered_datasource", 5000, 10)

    # 打印报告
    print_jitter_report()

    print("""
✅ 测试完成！

抖动状态判定标准:
  - stable (< 15%): 稳定，理想状态
  - minor_jitter (15-30%): 轻微抖动，可能需要关注
  - moderate_jitter (30-50%): 中度抖动，建议检查
  - severe_jitter (> 50%): 严重抖动，需要处理
""")


if __name__ == "__main__":
    main()