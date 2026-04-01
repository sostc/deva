#!/usr/bin/env python3
"""闭环状态审计查询脚本

用于查询和分析系统各闭环的执行状态。

Usage:
    python scripts/query_loop_audit.py --stats                    # 查看各闭环统计
    python scripts/query_loop_audit.py --recent 50              # 查看最近50条记录
    python scripts/query_loop_audit.py --loop-type dataflow     # 按类型筛选
    python scripts/query_loop_audit.py --status failed           # 查看失败的记录
    python scripts/query_loop_audit.py --today                  # 查看今天的数据
"""

import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

LOOP_AUDIT_TABLE = "naja_loop_audit"
DB_PATH = Path.home() / ".deva" / "nb.sqlite"


def get_connection():
    return sqlite3.connect(str(DB_PATH))


def get_stats(since_hours=24):
    """获取各闭环统计"""
    since = datetime.now() - timedelta(hours=since_hours)
    since_ts = since.timestamp()

    conn = get_connection()
    cur = conn.cursor()

    print(f"\n{'='*60}")
    print(f"闭环执行统计 (最近 {since_hours} 小时)")
    print(f"{'='*60}\n")

    cur.execute(f"""
        SELECT
            loop_type,
            COUNT(*) as total_count,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running,
            SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped,
            AVG(duration_ms) as avg_duration_ms,
            MAX(timestamp) as last_run
        FROM {LOOP_AUDIT_TABLE}
        WHERE timestamp >= ?
        GROUP BY loop_type
        ORDER BY total_count DESC
    """, (since_ts,))

    rows = cur.fetchall()
    if not rows:
        print("  暂无数据\n")
        conn.close()
        return

    print(f"{'闭环类型':<15} {'总数':>8} {'完成':>8} {'失败':>8} {'跳过':>8} {'平均耗时(ms)':>15} {'最后执行':>20}")
    print("-" * 90)

    for row in rows:
        loop_type, total, completed, failed, running, skipped, avg_dur, last_run = row
        last_run_str = datetime.fromtimestamp(last_run).strftime("%Y-%m-%d %H:%M:%S") if last_run else "N/A"
        avg_dur_str = f"{avg_dur:.2f}" if avg_dur else "N/A"
        print(f"{loop_type:<15} {total:>8} {completed:>8} {failed:>8} {skipped:>8} {avg_dur_str:>15} {last_run_str:>20}")

    print()
    conn.close()


def get_recent_records(limit=50, loop_type=None, status=None, since_hours=24):
    """获取最近记录"""
    since = datetime.now() - timedelta(hours=since_hours)
    since_ts = since.timestamp()

    conn = get_connection()
    cur = conn.cursor()

    print(f"\n{'='*60}")
    print(f"最近 {limit} 条记录")
    print(f"{'='*60}\n")

    query = f"SELECT * FROM {LOOP_AUDIT_TABLE} WHERE timestamp >= ?"
    params = [since_ts]

    if loop_type:
        query += " AND loop_type = ?"
        params.append(loop_type)

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    cur.execute(query, params)
    columns = [desc[0] for desc in cur.description]

    for row in cur.fetchall():
        d = dict(zip(columns, row))
        ts = datetime.fromtimestamp(d["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")

        print(f"[{ts}] {d['loop_type']:<15} | {d['stage']:<20} | {d['status']:<10}")
        print(f"    duration: {d['duration_ms']:.2f}ms")

        if d.get("data_in_summary"):
            try:
                di = json.loads(d["data_in_summary"]) if isinstance(d["data_in_summary"], str) else d["data_in_summary"]
                print(f"    data_in: {json.dumps(di, ensure_ascii=False)[:100]}")
            except:
                pass

        if d.get("error") and d["error"]:
            print(f"    ERROR: {d['error'][:100]}")

        print()

    conn.close()


def get_loop_trace(loop_id_prefix=None):
    """获取某个闭环的完整追踪"""
    if not loop_id_prefix:
        print("请提供 --loop-id 参数\n")
        return

    conn = get_connection()
    cur = conn.cursor()

    print(f"\n{'='*60}")
    print(f"闭环追踪: {loop_id_prefix}")
    print(f"{'='*60}\n")

    cur.execute(f"""
        SELECT * FROM {LOOP_AUDIT_TABLE}
        WHERE loop_id LIKE ?
        ORDER BY timestamp
    """, (f"{loop_id_prefix}%",))

    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()

    if not rows:
        print("  暂无数据\n")
        conn.close()
        return

    print(f"共 {len(rows)} 个阶段:\n")
    for i, row in enumerate(rows):
        d = dict(zip(columns, row))
        ts = datetime.fromtimestamp(d["timestamp"]).strftime("%H:%M:%S.%f")[:-3]
        print(f"  [{i+1}] {ts} | {d['stage']:<20} | {d['status']:<10} | {d['duration_ms']:.2f}ms")

        if d.get("data_in_summary"):
            try:
                di = json.loads(d["data_in_summary"]) if isinstance(d["data_in_summary"], str) else d["data_in_summary"]
                print(f"      IN:  {json.dumps(di, ensure_ascii=False)[:80]}")
            except:
                pass

        if d.get("data_out_summary"):
            try:
                do = json.loads(d["data_out_summary"]) if isinstance(d["data_out_summary"], str) else d["data_out_summary"]
                print(f"      OUT: {json.dumps(do, ensure_ascii=False)[:80]}")
            except:
                pass

        if d.get("error") and d["error"]:
            print(f"      ERR: {d['error'][:80]}")

        print()

    conn.close()


def get_failed_records(limit=20):
    """获取失败的记录"""
    conn = get_connection()
    cur = conn.cursor()

    print(f"\n{'='*60}")
    print(f"最近失败记录 (Top {limit})")
    print(f"{'='*60}\n")

    cur.execute(f"""
        SELECT * FROM {LOOP_AUDIT_TABLE}
        WHERE status = 'failed'
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))

    columns = [desc[0] for desc in cur.description]

    for row in cur.fetchall():
        d = dict(zip(columns, row))
        ts = datetime.fromtimestamp(d["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] {d['loop_type']:<15} | {d['stage']:<20}")
        print(f"    error: {d['error'][:150]}")
        print()

    conn.close()


def check_table_exists():
    """检查表是否存在"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name=?
    """, (LOOP_AUDIT_TABLE,))

    exists = cur.fetchone() is not None
    conn.close()
    return exists


def main():
    parser = argparse.ArgumentParser(description="闭环状态审计查询")
    parser.add_argument("--stats", action="store_true", help="查看各闭环统计")
    parser.add_argument("--recent", type=int, default=0, help="查看最近N条记录")
    parser.add_argument("--loop-type", type=str, help="按闭环类型筛选")
    parser.add_argument("--status", type=str, help="按状态筛选 (completed/failed/running/skipped)")
    parser.add_argument("--today", action="store_true", help="只查看今天的数据")
    parser.add_argument("--failed", action="store_true", help="查看失败记录")
    parser.add_argument("--loop-id", type=str, help="查看某个闭环的完整追踪")
    parser.add_argument("--hours", type=int, default=24, help="统计时间范围（小时）")
    parser.add_argument("--limit", type=int, default=50, help="返回记录数限制")

    args = parser.parse_args()

    if not check_table_exists():
        print(f"表 {LOOP_AUDIT_TABLE} 不存在，请先启动系统让审计模块初始化\n")
        return

    if args.today:
        args.hours = 24

    if args.failed:
        get_failed_records(args.limit)
    elif args.loop_id:
        get_loop_trace(args.loop_id)
    elif args.stats:
        get_stats(args.hours)
    elif args.recent > 0:
        get_recent_records(args.recent, args.loop_type, args.status, args.hours)
    else:
        get_stats(args.hours)
        print()
        get_recent_records(20, None, None, args.hours)


if __name__ == "__main__":
    main()