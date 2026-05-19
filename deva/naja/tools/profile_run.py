#!/usr/bin/env python3
"""
Naja 性能分析脚本 v3

使用 cProfile 对 Naja 系统进行专业性能分析
"""

import cProfile
import pstats
import sys
import time
import os
from datetime import datetime

# 添加路径
deva_root = '/Users/spark/pycharmproject/deva'
sys.path.insert(0, deva_root)
sys.path.insert(0, deva_root + '/deva')

print('='*70)
print('NAJA 系统性能分析')
print('='*70)
print(f'分析时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print()

# 创建性能分析器
profiler = cProfile.Profile()
profiler.enable()

try:
    print('[1/3] 导入 SR 注册表...')
    from deva.naja.register import SR, ensure_trading_clocks

    print('[2/3] 初始化事件总线...')
    from deva.naja.events import get_event_bus

    print('[3/3] 初始化市场热点系统...')
    from deva.naja.market_hotspot.integration.market_hotspot_integration import get_market_hotspot_integration
    integration = get_market_hotspot_integration()

    print()
    print('✓ Naja 系统初始化完成')
    print()
    print('模拟运行 2 秒...')
    time.sleep(2)
    print('✓ 模拟运行完成')

except Exception as e:
    print(f'初始化过程出错: {e}')
    import traceback
    traceback.print_exc()

finally:
    profiler.disable()

# 分析性能数据
print()
print('='*70)
print('性能分析结果')
print('='*70)

# 创建统计对象
stats = pstats.Stats(profiler)

# 按累计时间排序并输出
print()
print('【TOP 50 最耗时函数】(按累计时间排序)')
print('-'*90)
stats.sort_stats('cumulative')
stats.print_stats(50)

print()
print('='*70)
print('【TOP 50 最常调用函数】(按调用次数排序)')
print('-'*90)
stats.sort_stats('ncalls')
stats.print_stats(50)

# 保存完整报告
report_file = f'/tmp/naja_profile_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
stats.dump_stats(report_file)
print()
print(f'📄 完整性能数据已保存到: {report_file}')
print(f'   可以使用: python3 -m pstats {report_file} 查看')
