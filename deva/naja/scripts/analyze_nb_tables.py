#!/usr/bin/env python3
import sqlite3
import os

db_path = os.path.expanduser('~/.deva/nb.sqlite')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cursor.fetchall()]

print('=' * 70)
print('NB.sqlite Table Analysis')
print('=' * 70)
print(f'File size: {os.path.getsize(db_path) / 1024 / 1024:.1f} MB')
print()

table_stats = []
for t in tables:
    try:
        cursor.execute(f'SELECT COUNT(*) FROM "{t}"')
        count = cursor.fetchone()[0]
        table_stats.append((t, count))
    except:
        table_stats.append((t, -1))

table_stats.sort(key=lambda x: x[1], reverse=True)

print(f"{'Table Name':<50} {'Rows':>10}")
print('-' * 62)

empty_tables = []
large_tables = []

for t, count in table_stats:
    if count == -1:
        print(f"{t:<50} {'ERROR':>10}")
    elif count == 0:
        empty_tables.append(t)
        print(f"{t:<50} {'0':>10}")
    else:
        marker = ''
        if count > 10000:
            large_tables.append((t, count))
            marker = ' [LARGE]'
        print(f"{t:<50} {count:>10,}{marker}")

conn.close()

print()
print('=' * 70)
print(f'Empty tables: {len(empty_tables)}')
print(f'Large tables (>10000 rows): {len(large_tables)}')
print('=' * 70)

if empty_tables:
    print()
    print('Empty Tables:')
    for t in empty_tables:
        print(f'  - {t}')

if large_tables:
    print()
    print('Large Tables:')
    for t, count in large_tables[:10]:
        print(f'  - {t}: {count:,} rows')