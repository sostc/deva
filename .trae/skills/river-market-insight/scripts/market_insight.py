#!/usr/bin/env python3
"""
River 市场洞察核心分析脚本
从行情回放数据中提取市场状态，进行概念漂移检测和趋势分析
"""

import sqlite3
import pickle
import pandas as pd
import numpy as np
from river import drift
from collections import Counter


def load_market_data(db_path='/Users/spark/.deva/nb.sqlite', table='quant_snapshot_5min_window'):
    """加载市场数据"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"SELECT key, value FROM {table} ORDER BY key;")
    rows = cursor.fetchall()
    conn.close()
    return rows


def extract_metrics(row):
    """从单条数据提取市场指标"""
    key, value = row
    df = pickle.loads(value)
    
    if not isinstance(df, pd.DataFrame):
        return None
    
    df['p_change'] = pd.to_numeric(df['p_change'], errors='coerce').fillna(0)
    valid = df[abs(df['p_change']) < 1]
    
    if len(valid) == 0:
        return None
    
    up_count = (df['p_change'] > 0).sum()
    total = len(df)
    
    limit_up = (df['p_change'] >= 0.09).sum()
    limit_down = (df['p_change'] <= -0.09).sum()
    
    # 主要指数
    sz = df[df['code'] == '000001']
    zz = df[df['code'] == '399001']
    cy = df[df['code'] == '399006']
    
    return {
        'time': key,
        'date': key.split(' ')[0],
        'up_ratio': up_count / total,
        'limit_up': limit_up,
        'limit_down': limit_down,
        'sz_change': sz.iloc[0]['p_change'] * 100 if len(sz) > 0 else 0,
        'zz_change': zz.iloc[0]['p_change'] * 100 if len(zz) > 0 else 0,
        'cy_change': cy.iloc[0]['p_change'] * 100 if len(cy) > 0 else 0,
        'std': valid['p_change'].std() * 100,
    }


def classify_market(m):
    """市场状态分类"""
    if m['sz_change'] < -10:
        return '异常'
    if m['up_ratio'] > 0.55 and m['sz_change'] > 0.3:
        return '强势上涨'
    elif m['up_ratio'] < 0.3 and m['sz_change'] < -0.5:
        return '恐慌下跌'
    elif m['up_ratio'] > 0.4:
        return '偏多整理'
    elif m['up_ratio'] < 0.35:
        return '偏空整理'
    else:
        return '中性震荡'


def detect_abrupt_changes(metrics, threshold=0.15):
    """检测急剧变化"""
    changes = []
    for i in range(1, len(metrics)):
        prev = metrics[i-1]
        curr = metrics[i]
        
        if curr['sz_change'] < -10 or prev['sz_change'] < -10:
            continue
        
        change = curr['up_ratio'] - prev['up_ratio']
        
        if abs(change) > threshold:
            changes.append({
                'time': curr['time'],
                'prev_up': prev['up_ratio'],
                'curr_up': curr['up_ratio'],
                'change': change,
                'prev_sz': prev['sz_change'],
                'curr_sz': curr['sz_change'],
                'prev_down': prev['limit_down'],
                'curr_down': curr['limit_down'],
            })
    
    return changes


def detect_concept_drift(metrics):
    """概念漂移检测"""
    adwin = drift.ADWIN()
    drift_points = []
    
    for i, m in enumerate(metrics):
        state = m['up_ratio']
        if adwin.update(state):
            drift_points.append((i, m['time'], state))
    
    return drift_points


def analyze_market_phases(metrics):
    """市场阶段分析"""
    phases = []
    current = None
    
    for m in metrics:
        if m['sz_change'] < -10:
            continue
        phase = classify_market(m)
        if phase != current:
            phases.append({
                'time': m['time'],
                'phase': phase,
                'up': m['up_ratio'],
                'sz': m['sz_change'],
            })
            current = phase
    
    return phases


def daily_summary(metrics):
    """每日总结"""
    daily = {}
    for m in metrics:
        if m['sz_change'] < -10:
            continue
        d = m['date']
        if d not in daily:
            daily[d] = {'first': m, 'last': m}
        daily[d]['last'] = m
    
    result = {}
    for date, data in daily.items():
        first = data['first']
        last = data['last']
        
        up_change = last['up_ratio'] - first['up_ratio']
        sz_change = last['sz_change'] - first['sz_change']
        
        if up_change > 0.1:
            trend = '反弹'
        elif up_change < -0.1:
            trend = '回落'
        else:
            trend = '震荡'
        
        result[date] = {
            'trend': trend,
            'up_change': up_change,
            'sz_change': sz_change,
            'first_up': first['up_ratio'],
            'last_up': last['up_ratio'],
            'first_sz': first['sz_change'],
            'last_sz': last['sz_change'],
            'first_limit_down': first['limit_down'],
            'last_limit_down': last['limit_down'],
        }
    
    return result


def run_analysis(db_path='/Users/spark/.deva/nb.sqlite'):
    """运行完整分析"""
    print("=" * 80)
    print("River 市场洞察分析")
    print("=" * 80)
    
    # 加载数据
    rows = load_market_data(db_path)
    print(f"\n加载了 {len(rows)} 条数据")
    
    # 提取指标
    metrics = []
    for row in rows:
        m = extract_metrics(row)
        if m:
            metrics.append(m)
    
    print(f"提取了 {len(metrics)} 组市场指标")
    
    # 检测急剧变化
    print("\n" + "=" * 80)
    print("【急剧变化检测】")
    print("=" * 80)
    
    changes = detect_abrupt_changes(metrics)
    
    deterioration = [c for c in changes if c['change'] < 0]
    improvement = [c for c in changes if c['change'] > 0]
    
    print(f"\n🔴 市场急剧恶化 ({len(deterioration)}次):")
    for c in deterioration[:5]:
        print(f"  {c['time']}: 上涨{c['prev_up']:.1%}→{c['curr_up']:.1%} ({c['change']:.1%})")
    
    print(f"\n🟢 市场急剧好转 ({len(improvement)}次):")
    for c in improvement[:5]:
        print(f"  {c['time']}: 上涨{c['prev_up']:.1%}→{c['curr_up']:.1%} ({c['change']:+.1%})")
    
    # 概念漂移
    print("\n" + "=" * 80)
    print("【概念漂移检测】")
    print("=" * 80)
    
    drifts = detect_concept_drift(metrics)
    print(f"检测到 {len(drifts)} 个漂移点")
    
    # 市场阶段
    print("\n" + "=" * 80)
    print("【市场阶段演进】")
    print("=" * 80)
    
    phases = analyze_market_phases(metrics)
    for p in phases:
        emoji = "📈" if "上涨" in p['phase'] else ("📉" if "恐慌" in p['phase'] else "➡️")
        print(f"{emoji} {p['time'][:10]} {p['time'][11:16]}: {p['phase']}")
    
    # 每日总结
    print("\n" + "=" * 80)
    print("【每日总结】")
    print("=" * 80)
    
    daily = daily_summary(metrics)
    for date in sorted(daily.keys()):
        d = daily[date]
        emoji = "📈" if d['trend'] == '反弹' else ("📉" if d['trend'] == '回落' else "➡️")
        print(f"\n📅 {date} {emoji}")
        print(f"   上涨比例: {d['first_up']:.1%} → {d['last_up']:.1%} ({d['up_change']:+.1%})")
        print(f"   上证涨跌: {d['first_sz']:.2f}% → {d['last_sz']:.2f}%")
        print(f"   跌停数: {d['first_limit_down']} → {d['last_limit_down']}")
    
    return {
        'metrics': metrics,
        'changes': changes,
        'drifts': drifts,
        'phases': phases,
        'daily': daily,
    }


if __name__ == '__main__':
    run_analysis()
