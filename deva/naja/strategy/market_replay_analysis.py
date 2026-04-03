#!/usr/bin/env python3
"""历史数据深度分析脚本"""

from deva import NB
from deva.naja.dictionary.tongdaxin_blocks import get_stock_block_mapping
from datetime import datetime
import pandas as pd
import numpy as np
from collections import defaultdict

print("=" * 80)
print("📊 历史数据深度分析 - 市场复盘")
print("=" * 80)

# 加载板块数据
print("\n[1/6] 加载板块概念数据...")
stock_to_blocks = get_stock_block_mapping()
print(f"      ✓ 加载了 {len(stock_to_blocks)} 只股票的板块数据")

# 加载历史快照
print("\n[2/6] 加载历史快照数据...")
db = NB('quant_snapshot_5min_window')
all_keys = sorted(list(db.keys()))

# 按日期组织数据
daily_data = defaultdict(list)
for key in all_keys:
    try:
        k_str = str(key)
        if '-' in k_str:
            date_str = k_str[:10]
        else:
            try:
                ts = float(k_str)
                date_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
            except:
                continue
        daily_data[date_str].append(key)
    except:
        pass

dates = sorted(daily_data.keys())
print(f"      ✓ {len(dates)} 天数据: {dates[0]} ~ {dates[-1]}")

# 每日的分析
print("\n[3/6] 分析每日市场表现...")
daily_stats = {}

def get_last_df(db, keys):
    """获取最后一个DataFrame格式的数据"""
    last_key = max(keys)
    data = db.get(last_key)

    if isinstance(data, pd.DataFrame):
        return data
    elif isinstance(data, list):
        return pd.DataFrame(data)
    else:
        return None

def ensure_numeric(df, col):
    """确保列是数值类型"""
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

for date in dates:
    keys = daily_data[date]

    last_df = get_last_df(db, keys)
    if last_df is None:
        continue

    last_df = ensure_numeric(last_df, 'p_change')

    total_stocks = len(last_df)
    gainers = len(last_df[last_df['p_change'] > 0])
    losers = len(last_df[last_df['p_change'] < 0])
    flat = len(last_df[last_df['p_change'] == 0])

    avg_change = last_df['p_change'].mean()
    median_change = last_df['p_change'].median()

    advance_decline = (gainers - losers) / (gainers + losers) if (gainers + losers) > 0 else 0

    limit_up = len(last_df[last_df['p_change'] >= 9.5])
    limit_down = len(last_df[last_df['p_change'] <= -9.5])

    daily_stats[date] = {
        'total': total_stocks,
        'gainers': gainers,
        'losers': losers,
        'flat': flat,
        'avg_change': avg_change,
        'median_change': median_change,
        'advance_decline': advance_decline,
        'limit_up': limit_up,
        'limit_down': limit_down,
        'last_df': last_df,
    }

print(f"      ✓ 分析完成: {len(daily_stats)} 天")

# 输出每日汇总
print("\n" + "=" * 80)
print("📅 每日市场表现汇总")
print("=" * 80)
print(f"{'日期':<12} {'上涨':<6} {'下跌':<6} {'平盘':<5} {'平均涨幅':<8} {'中位数':<8} {'涨跌停':<8} {'市场广度'}")
print("-" * 80)

for date in sorted(daily_stats.keys(), reverse=True):
    s = daily_stats[date]
    ad_str = f"+{s['advance_decline']:.3f}" if s['advance_decline'] > 0 else f"{s['advance_decline']:.3f}"
    print(f"{date:<12} {s['gainers']:<6} {s['losers']:<6} {s['flat']:<5} {s['avg_change']:>+7.2f}% {s['median_change']:>+7.2f}% {s['limit_up']:>3}/{s['limit_down']:<3} {ad_str}")

# 板块分析
print("\n[4/6] 分析板块表现...")

block_performance = defaultdict(list)

for date in sorted(daily_stats.keys()):
    last_df = daily_stats[date]['last_df']

    for _, row in last_df.iterrows():
        code = str(row.get('code', '')).strip()
        p_change = row.get('p_change', 0)

        if code in stock_to_blocks:
            blocks = stock_to_blocks[code]
            for block in blocks:
                block_performance[block].append({
                    'date': date,
                    'p_change': p_change,
                    'code': code,
                    'name': row.get('name', '')
                })

# 计算每个板块的平均表现
block_avg = {}
for block, records in block_performance.items():
    if len(records) >= 10:  # 只保留有足够数据的板块
        avg = np.mean([r['p_change'] for r in records])
        block_avg[block] = avg

print(f"      ✓ 分析了 {len(block_avg)} 个板块")

# 输出板块表现TOP10
print("\n" + "=" * 80)
print("🏆 板块表现排行榜")
print("=" * 80)

sorted_blocks = sorted(block_avg.items(), key=lambda x: x[1], reverse=True)

print("\n📈 涨幅前10板块:")
for i, (block, avg) in enumerate(sorted_blocks[:10], 1):
    print(f"  {i:2}. {block:<20} 平均涨幅: {avg:>+6.2f}%")

print("\n📉 跌幅前10板块:")
for i, (block, avg) in enumerate(sorted_blocks[-10:], 1):
    print(f"  {i:2}. {block:<20} 平均涨幅: {avg:>+6.2f}%")

# 个股分析
print("\n[5/6] 分析个股表现...")

# 找出每天涨幅前5和跌幅前5的个股
daily_top_movers = {}
for date in sorted(daily_stats.keys()):
    last_df = daily_stats[date]['last_df']

    top_gainers = last_df.nlargest(5, 'p_change')[['code', 'name', 'p_change']]
    top_losers = last_df.nsmallest(5, 'p_change')[['code', 'name', 'p_change']]

    daily_top_movers[date] = {
        'gainers': top_gainers.to_dict('records'),
        'losers': top_losers.to_dict('records')
    }

print(f"      ✓ 分析完成")

print("\n" + "=" * 80)
print("🔥 每日强势股/弱势股")
print("=" * 80)

for date in sorted(daily_top_movers.keys(), reverse=True)[:5]:
    movers = daily_top_movers[date]
    print(f"\n📅 {date}")

    print("  涨幅前5:")
    for r in movers['gainers']:
        print(f"    {r['name']}({r['code']}) {r['p_change']:+.2f}%")

    print("  跌幅前5:")
    for r in movers['losers']:
        print(f"    {r['name']}({r['code']}) {r['p_change']:+.2f}%")

# 市场变化趋势分析
print("\n[6/6] 市场变化趋势分析...")

print("\n" + "=" * 80)
print("📈 市场趋势变化")
print("=" * 80)

sorted_dates = sorted(daily_stats.keys())
for i in range(1, len(sorted_dates)):
    prev_date = sorted_dates[i-1]
    curr_date = sorted_dates[i]

    prev_stats = daily_stats[prev_date]
    curr_stats = daily_stats[curr_date]

    change_in_ad = curr_stats['advance_decline'] - prev_stats['advance_decline']
    change_str = f"+{change_in_ad:.3f}" if change_in_ad > 0 else f"{change_in_ad:.3f}"

    sentiment = "📈 转暖" if change_in_ad > 0.1 else ("📉 转冷" if change_in_ad < -0.1 else "➡️ 持平")

    print(f"  {prev_date} → {curr_date}: {sentiment} (广度变化: {change_str})")

print("\n" + "=" * 80)
print("✅ 分析完成")
print("=" * 80)