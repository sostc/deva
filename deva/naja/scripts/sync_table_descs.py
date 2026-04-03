#!/usr/bin/env python3
"""同步表描述到数据库的default表"""

from deva import NB
from deva.naja.tables import ALL_TABLE_REGISTRIES

print('=' * 60)
print('同步表描述到数据库')
print('=' * 60)

default_db = NB('default')

# 获取所有注册表中的描述
total = 0
synced = 0

for table_name, desc in ALL_TABLE_REGISTRIES.items():
    total += 1
    current_desc = default_db.get(table_name)
    if current_desc != desc:
        default_db[table_name] = desc
        synced += 1
        print(f'✓ 同步: {table_name}')
    else:
        print(f'  跳过: {table_name} (无需更新)')

print()
print(f'总计: {synced}/{total} 个表已同步')
print()
print('同步完成!')