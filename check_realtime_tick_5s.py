#!/usr/bin/env python3
"""
检查realtime_tick_5s数据源的配置和执行逻辑
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from deva import NB

db = NB('naja_datasources')

print("=" * 60)
print("naja_datasources 数据库内容:")
print("=" * 60)

found = False
for ds_id, ds_data in db.items():
    if isinstance(ds_data, dict):
        metadata = ds_data.get('metadata', {})
        name = metadata.get('name', '未命名')
        source_type = metadata.get('source_type', 'unknown')
        
        print(f"\n- {name} (ID: {ds_id}, 类型: {source_type})")
        
        # 检查是否是realtime_tick_5s
        if 'realtime_tick_5s' in name.lower() or 'realtime_tick_5s' in str(ds_data):
            print("  🔍 找到目标数据源!")
            found = True
            
            # 打印完整的metadata
            print("  Metadata:")
            for key, value in metadata.items():
                print(f"    {key}: {value}")
            
            # 打印func_code
            func_code = ds_data.get('func_code', '')
            if func_code:
                print(f"  Func Code (长度: {len(func_code)}):")
                print("  " + "-" * 50)
                print(func_code)
                print("  " + "-" * 50)

if not found:
    print("\n❌ 未找到realtime_tick_5s数据源")

print(f"\n总计: {len(db)} 个数据源")
