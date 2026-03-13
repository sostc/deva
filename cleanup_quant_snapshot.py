#!/usr/bin/env python3
"""
清理quant_snapshot_5min_window表中的脏数据
正确的格式：key是时间戳字符串，value是DataFrame
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

import pandas as pd
from deva import NB

def cleanup_dirty_data():
    """清理脏数据"""
    print("📋 检查quant_snapshot_5min_window表...")
    
    db = NB('quant_snapshot_5min_window')
    
    print(f"   当前数据量: {len(db)} 条")
    
    # 检查数据格式
    dirty_keys = []
    valid_keys = []
    
    for key, value in db.items():
        # 检查key是否是时间戳格式（如 "2026-03-12 14:10:00" 或 "snapshot_1234567890"）
        key_is_valid = False
        if isinstance(key, str):
            # 时间戳格式：数字或带snapshot_前缀的数字
            if key.replace('snapshot_', '').replace('.', '').isdigit() or '-' in key:
                key_is_valid = True
        
        # 检查value是否是DataFrame
        value_is_valid = isinstance(value, pd.DataFrame)
        
        if key_is_valid and value_is_valid:
            valid_keys.append(key)
            print(f"   ✅ 有效数据: {key} (DataFrame, {len(value)} rows)")
        else:
            dirty_keys.append(key)
            print(f"   ❌ 脏数据: {key}, 类型: {type(value)}")
    
    print(f"\n📊 数据统计:")
    print(f"   脏数据: {len(dirty_keys)} 条")
    print(f"   有效数据: {len(valid_keys)} 条")
    
    # 删除脏数据
    if dirty_keys:
        print(f"\n🗑️  清理脏数据...")
        for key in dirty_keys:
            del db[key]
            print(f"   已删除: {key}")
        print(f"✅ 清理完成!")
    else:
        print(f"\n✅ 无脏数据需要清理")
    
    # 验证清理结果
    print(f"\n🔍 验证清理结果...")
    remaining_count = len(db)
    print(f"   剩余数据量: {remaining_count} 条")
    
    # 显示有效数据示例
    if remaining_count > 0:
        print(f"\n📋 有效数据示例:")
        for key, value in list(db.items())[:3]:
            if isinstance(value, pd.DataFrame):
                print(f"   {key}: {len(value)} rows x {len(value.columns)} columns")
                print(f"   列名: {list(value.columns[:5])}...")
    
    return remaining_count

if __name__ == '__main__':
    print("=" * 60)
    print("清理quant_snapshot_5min_window表中的脏数据")
    print("=" * 60)
    print()
    
    count = cleanup_dirty_data()
    
    print(f"\n🎯 任务完成!")
    print(f"清理后表中剩余: {count} 条有效数据 (DataFrame格式)")
