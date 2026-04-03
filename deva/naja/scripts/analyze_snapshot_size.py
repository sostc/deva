#!/usr/bin/env python3
from deva import NB
import sys
from datetime import datetime
from collections import defaultdict

db = NB('quant_snapshot_5min_window')
all_keys = list(db.keys())

print('=' * 60)
print('quant_snapshot_5min_window 数据量分析')
print('=' * 60)

sample = db.get(all_keys[-1])
sample_size = sys.getsizeof(str(sample))
print(f'单条记录大小: {sample_size / 1024:.1f} KB')

total_keys = len(all_keys)
estimated_size = sample_size * total_keys / 1024 / 1024
print(f'总记录数: {total_keys}')
print(f'估算总大小: {estimated_size:.1f} MB')

print()
print('数据结构 (字段):')
if hasattr(sample, 'columns'):
    print(f'  列数: {len(sample.columns)}')
    print(f'  列名: {list(sample.columns)}')
elif isinstance(sample, list) and sample:
    print(f'  字段数: {len(sample[0].keys())}')
    print(f'  字段: {list(sample[0].keys())}')

daily_counts = defaultdict(int)
for k in all_keys:
    k_str = str(k)
    if k_str.startswith('177'):
        date_str = datetime.fromtimestamp(float(k_str)).strftime('%Y-%m-%d')
        daily_counts[date_str] += 1

print()
print('每天保存频率:')
for date in sorted(daily_counts.keys(), reverse=True)[:7]:
    print(f'  {date}: {daily_counts[date]} 条/天')