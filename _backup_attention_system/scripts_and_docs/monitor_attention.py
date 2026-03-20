#!/usr/bin/env python3
"""
实时监控注意力变化

运行此脚本可以实时查看注意力系统的变化
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

import time

print("="*60)
print("🔍 注意力变化实时监控")
print("="*60)
print("\n按 Ctrl+C 停止\n")

# 获取历史追踪器
from deva.naja.attention.history_tracker import get_history_tracker
from deva.naja.attention_integration import get_attention_integration

tracker = get_history_tracker()
integration = get_attention_integration()

last_change_count = 0
last_snapshot_count = 0

while True:
    try:
        # 获取当前状态
        summary = tracker.get_summary()
        current_changes = summary['change_count']
        current_snapshots = summary['snapshot_count']
        
        # 如果有新数据
        if current_snapshots > last_snapshot_count:
            print(f"\n📊 快照 #{current_snapshots} | 变化 #{current_changes}")
            
            # 显示全局注意力
            if integration and integration.attention_system:
                global_attn = integration.attention_system._last_global_attention
                print(f"   全局注意力: {global_attn:.3f}")
            
            # 显示热门板块
            if summary['current_hot_sectors']:
                print(f"   热门板块: {len(summary['current_hot_sectors'])} 个")
                for sector_id, sector_name, weight in summary['current_hot_sectors'][:3]:
                    print(f"      • {sector_name}: {weight:.3f}")
            
            # 显示热门股票
            if summary['current_hot_symbols']:
                print(f"   热门股票: {len(summary['current_hot_symbols'])} 只")
                for symbol, symbol_name, weight in summary['current_hot_symbols'][:3]:
                    name_str = f" {symbol_name}" if symbol_name != symbol else ""
                    print(f"      • {symbol}{name_str}: {weight:.2f}")
        
        # 如果有新变化
        if current_changes > last_change_count:
            new_changes = current_changes - last_change_count
            print(f"\n🔄 检测到 {new_changes} 个新变化:")
            
            recent_changes = tracker.get_recent_changes(n=new_changes)
            for change in recent_changes:
                emoji = {
                    'new_hot': '🔥',
                    'cooled': '❄️',
                    'strengthen': '📈',
                    'weaken': '📉'
                }.get(change.change_type, '•')
                
                print(f"   {emoji} {change.description}")
                print(f"      {change.old_weight:.3f} → {change.new_weight:.3f} ({change.change_percent:+.1f}%)")
        
        last_change_count = current_changes
        last_snapshot_count = current_snapshots
        
        time.sleep(1)
        
    except KeyboardInterrupt:
        print("\n\n监控已停止")
        break
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        time.sleep(2)

print("\n" + "="*60)

# 显示最终报告
print("\n📋 最终报告:")
summary = tracker.get_summary()
print(f"   总快照数: {summary['snapshot_count']}")
print(f"   总变化数: {summary['change_count']}")

# 显示转移报告
report = tracker.get_attention_shift_report()
if report['has_shift']:
    print("\n🔄 注意力转移 detected!")
    if report.get('sector_shift'):
        print("   板块发生转移")
    if report.get('symbol_shift'):
        print("   个股发生转移")
else:
    print("\n✅ 未检测到明显的注意力转移")

print("="*60)
