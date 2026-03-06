#!/usr/bin/env python3
"""
手动修复失败的策略
"""

from deva.naja.strategy import get_strategy_manager


def fix_failed_strategy():
    """
    手动修复失败的策略
    """
    mgr = get_strategy_manager()
    mgr.load_from_db()
    
    # 获取失败的策略
    entry = mgr.get("286326a5e26f")
    if not entry:
        print("Strategy not found.")
        return
    
    print(f"Strategy: {entry.name}")
    print(f"ID: {entry.id}")
    
    # 手动构建正确的代码
    new_code = '''
import pandas as pd

def is_valid_stock(code, name):
    """
    Check if it's a valid stock
    Filter out:
    1. Indexes
    2. Delisted companies (name ends with '退')
    3. Non-stock data in A-shares (code starts with 15, 16, etc.)
    """
    # Filter indexes (name contains keywords)
    if name and any(keyword in name for keyword in ['指数', 'ETF', 'LOF', '基金', '债券', '权证']):
        return False
    
    # Filter delisted companies (name ends with '退')
    if name and name.endswith('退'):
        return False
    
    # Filter non-stock codes
    code_str = str(code)
    # 15开头的基金
    if code_str.startswith('15'):
        return False
    # 16开头的基金
    if code_str.startswith('16'):
        return False
    # Other common non-stock code prefixes
    non_stock_prefixes = ['000000', '999999', '888888']
    if code_str in non_stock_prefixes:
        return False
    
    return True

# 按 symbol 分组窗口模板（单策略内维护多标的滑动窗口）
# UI建议：
# - 计算模式：record（因为我们在代码里自行按 symbol 维护窗口）
# - 窗口类型：随意（不会用到）
#
# 输入假设：每条数据是 dict，至少包含 symbol、price
# 输出：仅在单个 symbol 窗口满时输出信号

from collections import deque
import time

WINDOW_SIZE = 5
MIN_CHANGE = 0.01  # 1%

# key: symbol -> deque[(ts, price)]
_symbol_windows = {}

def process(data):
    # 过滤非个股数据
    if isinstance(data, pd.DataFrame):
        # 确保索引是股票代码
        if not data.empty:
            # 复制DataFrame以避免修改原始数据
            data = data.copy()
            # 应用过滤逻辑
            valid_mask = []
            for idx, row in data.iterrows():
                code = idx
                name = row.get('name', '')
                valid_mask.append(is_valid_stock(code, name))
            # 过滤掉无效股票
            data = data[valid_mask]
            # 如果过滤后没有数据，返回None
            if data.empty:
                return None
    # 处理字典类型的输入（单条数据）
    elif isinstance(data, dict):
        # 检查是否为股票数据
        symbol = data.get('symbol', data.get('code', data.get('ts_code', '')))
        name = data.get('name', '')
        if symbol:
            if not is_valid_stock(symbol, name):
                return None

    if not isinstance(data, dict):
        return None

    symbol = data.get("symbol")
    if not symbol:
        return None

    try:
        price = float(data.get("price"))
    except Exception:
        return None

    ts = data.get("ts", time.time())

    w = _symbol_windows.get(symbol)
    if w is None:
        w = deque(maxlen=WINDOW_SIZE)
        _symbol_windows[symbol] = w

    w.append((ts, price))

    # 窗口未满，不输出
    if len(w) < WINDOW_SIZE:
        return None

    first_ts, first_price = w[0]
    last_ts, last_price = w[-1]

    if first_price == 0:
        return None

    change_ratio = (last_price - first_price) / first_price
    if change_ratio > MIN_CHANGE:
        signal = "BUY"
    elif change_ratio < -MIN_CHANGE:
        signal = "SELL"
    else:
        signal = "HOLD"

    return {
        "symbol": symbol,
        "window_size": WINDOW_SIZE,
        "start_ts": first_ts,
        "end_ts": last_ts,
        "start_price": first_price,
        "end_price": last_price,
        "change_ratio": change_ratio,
        "signal": signal,
    }
'''
    
    # 更新策略代码
    result = entry.update_config(func_code=new_code)
    if result.get('success'):
        print("✓ Updated successfully")
    else:
        print(f"✗ Update failed: {result.get('error')}")


if __name__ == "__main__":
    fix_failed_strategy()
