#!/usr/bin/env python3
from deva import NB
import sys

tables = [
    'naja_strategy_metrics',
    'naja_strategy_registry',
    'deva_bus_clients',
    'naja_bandit_decisions',
    'naja_bandit_actions'
]

for table_name in tables:
    db = NB(table_name)
    keys = list(db.keys())
    print('=' * 60)
    print(f'{table_name}: {len(keys)} 条')
    print('=' * 60)

    if keys:
        sample = db.get(keys[0])
        if isinstance(sample, dict):
            print('字段:', list(sample.keys()))
            size = sys.getsizeof(str(sample))
            print(f'单条大小: {size/1024:.1f} KB')
            print(f'估算总大小: {size * len(keys) / 1024 / 1024:.1f} MB')
            print()
            print('数据示例:')
            for k, v in list(sample.items())[:5]:
                v_str = str(v)
                if len(v_str) > 100:
                    v_str = v_str[:100] + '...'
                print(f'  {k}: {v_str}')
    print()