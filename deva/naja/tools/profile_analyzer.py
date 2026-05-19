"""
Naja 性能分析脚本

使用 cProfile 对 Naja 系统进行专业性能分析
"""

import cProfile
import pstats
import io
import sys
import time
import os
from datetime import datetime

# 添加 deva 目录到路径
deva_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, deva_root)


def run_performance_analysis():
    """运行性能分析"""
    print("=" * 70)
    print("NAJA 系统性能分析")
    print("=" * 70)
    print(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 创建性能分析器
    profiler = cProfile.Profile()

    print("启动 Naja 系统...")
    print("-" * 70)

    # 启动性能分析
    profiler.enable()

    try:
        # 导入 Naja 核心模块进行初始化
        print("[1/5] 导入 SR 注册表...")
        from deva.naja.register import SR, ensure_trading_clocks

        print("[2/5] 初始化事件总线...")
        from deva.naja.events import get_event_bus

        print("[3/5] 初始化市场热点系统...")
        from deva.naja.market_hotspot.integration.market_hotspot_integration import get_market_hotspot_integration

        print("[4/5] 初始化数据获取器...")
        from deva.naja.market_hotspot.data.realtime_fetcher import get_realtime_data_fetcher

        print("[5/5] 初始化注意力系统...")
        from deva.naja.attention import get_attention_os

        print()
        print("✓ Naja 系统初始化完成")
        print()

        # 模拟运行一段时间
        print("模拟运行 3 秒...")
        time.sleep(3)

        print("✓ 模拟运行完成")

    except Exception as e:
        print(f"初始化过程出错: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 停止性能分析
        profiler.disable()

    # 分析性能数据
    print()
    print("=" * 70)
    print("性能分析结果")
    print("=" * 70)

    # 创建统计对象
    s = pstats.Stats(profiler)

    # 输出到缓冲区
    buffer = io.StringIO()
    ps = pstats.Stats(profiler, stream=buffer)

    # 1. 输出最耗时的函数 (按累计时间排序)
    print()
    print("【TOP 30 最耗时函数】(按累计时间排序)")
    print("-" * 70)
    buffer_tracing = io.StringIO()
    ps_tracing = pstats.Stats(profiler, stream=buffer_tracing)
    ps_tracing.sort_stats('cumulative')
    ps_tracing.print_stats(30)
    print(buffer_tracing.getvalue())

    # 2. 输出最常调用的函数 (按调用次数排序)
    print()
    print("【TOP 30 最常调用函数】(按调用次数排序)")
    print("-" * 70)
    buffer_calls = io.StringIO()
    ps_calls = pstats.Stats(profiler, stream=buffer_calls)
    ps_calls.sort_stats('ncalls')
    ps_calls.print_stats(30)
    print(buffer_calls.getvalue())

    # 3. 输出 Naja 模块特定的函数
    print()
    print("【NAJA 模块热点函数】")
    print("-" * 70)
    naja_stats = []
    for func, (cc, nc, tt, ct, callers) in profiler.stats.items():
        filename, line, func_name = func
        if 'deva/naja' in filename or 'naja' in filename:
            naja_stats.append({
                'func': f"{func_name} ({os.path.basename(filename)}:{line})",
                'ncalls': nc,
                'tottime': tt,
                'cumtime': ct,
                'filename': os.path.basename(filename)
            })

    # 按累计时间排序
    naja_stats.sort(key=lambda x: x['cumtime'], reverse=True)

    print(f"{'函数':<50} {'调用次数':>10} {'累计时间(s)':>12} {'总时间(s)':>12}")
    print("-" * 90)
    for stat in naja_stats[:30]:
        print(f"{stat['func']:<50} {stat['ncalls']:>10} {stat['cumtime']:>12.3f} {stat['tottime']:>12.3f}")

    # 4. 输出调用关系 (哪些函数调用了热点函数)
    print()
    print("【热点函数调用链分析】")
    print("-" * 70)

    # 找出累计时间最长的函数
    hot_functions = naja_stats[:10]

    for hot in hot_functions:
        func_name = hot['func'].split(' (')[0]
        print(f"\n📊 {func_name}")
        print(f"   累计时间: {hot['cumtime']:.3f}s | 调用次数: {hot['ncalls']}")

        # 找出谁调用了这个函数
        callers = []
        for func, stats in profiler.stats.items():
            filename, line, name = func
            if name == func_name:
                for caller, caller_stats in stats[4].items():
                    callers.append({
                        'name': caller[2],
                        'file': os.path.basename(caller[0]),
                        'line': caller[1],
                        'ncalls': caller_stats[0]
                    })

        if callers:
            callers.sort(key=lambda x: x['ncalls'], reverse=True)
            print(f"   调用者:")
            for c in callers[:5]:
                print(f"      - {c['name']} ({c['file']}:{c['line']}) x{c['ncalls']}")

    # 5. 统计信息汇总
    print()
    print("=" * 70)
    print("【性能统计汇总】")
    print("=" * 70)

    total_time = sum(stats[2] for stats in profiler.stats.values())
    print(f"总函数调用次数: {sum(stats[1] for stats in profiler.stats.values()):,}")
    print(f"总执行时间: {total_time:.3f} 秒")
    print(f"函数总数: {len(profiler.stats):,}")

    # 过滤 Naja 模块统计
    naja_total_time = sum(stat[2] for stat in profiler.stats.items()
                         if 'naja' in str(stat[0][0]))
    naja_total_calls = sum(stat[1] for stat in profiler.stats.items()
                          if 'naja' in str(stat[0][0]))

    print(f"\nNaja 模块:")
    print(f"  - 函数调用次数: {naja_total_calls:,}")
    print(f"  - 执行时间: {naja_total_time:.3f} 秒")
    print(f"  - 占比: {naja_total_time/total_time*100:.1f}%")

    # 6. 保存详细报告
    report_file = f"/tmp/naja_profile_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w') as f:
        f.write("=" * 70 + "\n")
        f.write("NAJA 系统性能分析报告\n")
        f.write("=" * 70 + "\n")
        f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("【TOP 50 最耗时函数】\n")
        f.write("-" * 70 + "\n")
        ps_tracing.print_stats(50, stream=f)

        f.write("\n【NAJA 模块全部函数】\n")
        f.write("-" * 70 + "\n")
        for stat in naja_stats:
            f.write(f"{stat['func']}: ncalls={stat['ncalls']}, cumtime={stat['cumtime']:.3f}s\n")

    print(f"\n📄 详细报告已保存到: {report_file}")

    return profiler, naja_stats


if __name__ == "__main__":
    profiler, naja_stats = run_performance_analysis()
