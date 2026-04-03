#!/usr/bin/env python3
"""清理NB.sqlite中的空表和旧数据"""

import sqlite3
import os

db_path = os.path.expanduser('~/.deva/nb.sqlite')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=' * 60)
print('清理 NB.sqlite 空表和旧数据')
print('=' * 60)

# 1. 找出所有空表
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
all_tables = [r[0] for r in cursor.fetchall()]

empty_tables = []
for t in all_tables:
    try:
        cursor.execute(f'SELECT COUNT(*) FROM "{t}"')
        count = cursor.fetchone()[0]
        if count == 0:
            empty_tables.append(t)
    except:
        pass

print(f'\n发现 {len(empty_tables)} 个空表')

# 2. 删除空表
print('\n删除空表...')
for t in empty_tables:
    try:
        cursor.execute(f'DROP TABLE IF EXISTS "{t}"')
        print(f'  ✓ 删除: {t}')
    except Exception as e:
        print(f'  ✗ 删除失败: {t} - {e}')

conn.commit()

# 3. 清理旧备份表
backup_tables = [t for t in all_tables if 'backup' in t.lower()]
if backup_tables:
    print(f'\n发现 {len(backup_tables)} 个备份表，删除...')
    for t in backup_tables:
        try:
            cursor.execute(f'DROP TABLE IF EXISTS "{t}"')
            print(f'  ✓ 删除: {t}')
        except Exception as e:
            print(f'  ✗ 删除失败: {t} - {e}')
    conn.commit()

# 4. 清理超旧数据（策略指标表保留最近3个月）
print('\n检查需要清理的旧数据...')

# 检查 naja_strategy_metrics
cursor.execute('SELECT COUNT(*) FROM naja_strategy_metrics')
metrics_count = cursor.fetchone()[0]
print(f'  naja_strategy_metrics: {metrics_count} 条')

conn.close()

print('\n' + '=' * 60)
print('清理完成!')
print('建议: 运行 VACUUM 压缩数据库文件')
print('  sqlite3 ~/.deva/nb.sqlite "VACUUM;"')
print('=' * 60)