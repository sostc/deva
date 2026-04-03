#!/usr/bin/env python3
from deva import NB
from datetime import datetime
from collections import defaultdict

tables = [
    ('naja_strategy_metrics', 'timestamp'),
    ('naja_strategy_registry', 'ts'),
    ('naja_bandit_decisions', 'timestamp'),
    ('naja_bandit_actions', 'timestamp'),
]

for table_name, time_field in tables:
    db = NB(table_name)
    keys = list(db.keys())

    print('=' * 60)
    print(f'{table_name}: {len(keys)} 条')
    print('=' * 60)

    monthly = defaultdict(int)
    for k in keys:
        data = db.get(k)
        if isinstance(data, dict):
            ts = data.get(time_field, 0)
            if ts:
                month = datetime.fromtimestamp(ts).strftime('%Y-%m')
                monthly[month] += 1

    print('月份分布:')
    for month in sorted(monthly.keys()):
        print(f'  {month}: {monthly[month]} 条')

    timestamps = []
    for k in keys:
        data = db.get(k)
        if isinstance(data, dict):
            ts = data.get(time_field, 0)
            if ts > 0:
                timestamps.append(ts)

    if timestamps:
        print(f'最早: {datetime.fromtimestamp(min(timestamps))}')
        print(f'最新: {datetime.fromtimestamp(max(timestamps))}')
    print()