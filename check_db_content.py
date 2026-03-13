#!/usr/bin/env python3
"""
直接检查数据库中的realtime_tick_5s数据源配置
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from deva import NB

db = NB('naja_datasources')

# 查找realtime_tick_5s数据源
target_ds_id = None
for ds_id, ds_data in db.items():
    if isinstance(ds_data, dict):
        metadata = ds_data.get('metadata', {})
        name = metadata.get('name', '')
        if name == 'realtime_tick_5s':
            target_ds_id = ds_id
            break

if target_ds_id:
    print(f"找到realtime_tick_5s数据源，ID: {target_ds_id}")
    ds_data = db[target_ds_id]
    print(f"代码长度: {len(ds_data.get('func_code', ''))}")
    print(f"更新时间: {ds_data.get('metadata', {}).get('updated_at', '未知')}")
    print("\n代码内容:")
    print(ds_data.get('func_code', ''))
else:
    print("未找到realtime_tick_5s数据源")
