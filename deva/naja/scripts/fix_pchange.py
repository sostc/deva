#!/usr/bin/env python3
"""修复历史数据中的p_change字段"""

from deva import NB
import pandas as pd

print('=' * 60)
print('修复 quant_snapshot_5min_window 中的 p_change 数据')
print('=' * 60)

db = NB('quant_snapshot_5min_window')
all_keys = list(db.keys())

fixed_count = 0
skipped_count = 0
error_count = 0

for k in all_keys:
    data = db.get(k)

    try:
        if isinstance(data, pd.DataFrame):
            if 'p_change' in data.columns and 'now' in data.columns and 'close' in data.columns:
                zero_mask = data['p_change'] == 0
                calc_mask = zero_mask & (data['close'] != 0)
                if calc_mask.sum() > 0:
                    data['p_change'] = (data['now'] - data['close']) / data['close']
                    data['change_pct'] = data['p_change']
                    db[k] = data
                    fixed_count += 1
                else:
                    skipped_count += 1
            else:
                skipped_count += 1

        elif isinstance(data, list):
            needs_fix = False
            for item in data:
                if isinstance(item, dict):
                    close = item.get('close', 0)
                    now = item.get('now', 0)
                    p_change = item.get('p_change', 0)
                    if p_change == 0 and close != 0:
                        item['p_change'] = (now - close) / close
                        needs_fix = True

            if needs_fix:
                db[k] = data
                fixed_count += 1
            else:
                skipped_count += 1

    except Exception as e:
        error_count += 1

print()
print(f'修复完成:')
print(f'  修复: {fixed_count} 条')
print(f'  跳过: {skipped_count} 条')
print(f'  错误: {error_count} 条')