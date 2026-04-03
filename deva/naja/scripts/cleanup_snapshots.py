#!/usr/bin/env python3
"""清理 quant_snapshot_5min_window 中的旧数据"""

from deva import NB
from datetime import datetime
import time

print('=' * 60)
print('清理 quant_snapshot_5min_window 旧数据')
print('=' * 60)

# 保留最近N天
keep_days = 5

db = NB('quant_snapshot_5min_window')
all_keys = list(db.keys())

cutoff_time = time.time() - (keep_days * 86400)

print(f'保留策略: 最近 {keep_days} 天的数据')
print(f'截止时间: {datetime.fromtimestamp(cutoff_time)}')
print()

# 分类keys
to_delete = []
to_keep = []

for k in all_keys:
    k_str = str(k)
    if k_str.startswith('177'):
        try:
            key_time = float(k_str)
            if key_time < cutoff_time:
                to_delete.append((k, key_time))
            else:
                to_keep.append((k, key_time))
        except:
            to_keep.append((k, 0))
    else:
        to_keep.append((k, 0))

print(f'总记录数: {len(all_keys)}')
print(f'将删除: {len(to_delete)} 条')
print(f'将保留: {len(to_keep)} 条')

# 按日期统计将被删除的数据
delete_by_date = {}
for k, ts in to_delete:
    date_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
    delete_by_date[date_str] = delete_by_date.get(date_str, 0) + 1

if delete_by_date:
    print()
    print('将被删除的数据分布:')
    for date in sorted(delete_by_date.keys()):
        print(f'  {date}: {delete_by_date[date]} 条')

# 执行删除
if to_delete:
    print()
    confirm = input('确认删除以上旧数据? (y/n): ')
    if confirm.lower() == 'y':
        deleted = 0
        for k, _ in to_delete:
            try:
                del db[k]
                deleted += 1
            except:
                pass
        print(f'已删除: {deleted} 条')
    else:
        print('已取消删除')

# 验证保留的数据
print()
keep_by_date = {}
for k, ts in to_keep:
    if ts > 0:
        date_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
        keep_by_date[date_str] = keep_by_date.get(date_str, 0) + 1

if keep_by_date:
    print('保留的数据分布:')
    for date in sorted(keep_by_date.keys(), reverse=True):
        print(f'  {date}: {keep_by_date[date]} 条')