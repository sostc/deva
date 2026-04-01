#!/usr/bin/env python3
"""分析Naja系统的数据源和策略配置"""

import sqlite3
import dill
import json

def main():
    conn = sqlite3.connect('/Users/spark/.deva/nb.sqlite')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("=" * 70)
    print("数据源 (Datasources)")
    print("=" * 70)

    cur.execute('SELECT COUNT(*) FROM naja_datasources')
    print(f"总数: {cur.fetchone()[0]}\n")

    cur.execute('SELECT key, value FROM naja_datasources')
    for row in cur.fetchall():
        k, v = row['key'], row['value']
        try:
            d = dill.loads(v)
            print(f"[{k[:12]}]")
            print(f"  keys: {list(d.keys()) if isinstance(d, dict) else type(d)}")
            if isinstance(d, dict):
                print(f"  full_data: {json.dumps(d, ensure_ascii=False, indent=2, default=str)[:500]}")
        except Exception as e:
            print(f"  [{k[:12]}] (解析失败: {e})")

    print()
    print("=" * 70)
    print("策略 (Strategies)")
    print("=" * 70)

    cur.execute('SELECT COUNT(*) FROM naja_strategies')
    print(f"总数: {cur.fetchone()[0]}\n")

    cur.execute('SELECT key, value FROM naja_strategies')
    for row in cur.fetchall():
        k, v = row['key'], row['value']
        try:
            d = dill.loads(v)
            print(f"[{k[:12]}]")
            print(f"  keys: {list(d.keys()) if isinstance(d, dict) else type(d)}")
            if isinstance(d, dict):
                print(f"  full_data: {json.dumps(d, ensure_ascii=False, indent=2, default=str)[:500]}")
        except Exception as e:
            print(f"  [{k[:12]}] (解析失败: {e})")

    conn.close()

if __name__ == '__main__':
    main()