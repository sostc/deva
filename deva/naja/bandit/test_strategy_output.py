#!/usr/bin/env python3
"""验证修改后的策略输出格式"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 60)
print("验证修改后的策略输出格式")
print("=" * 60)

print("\n[1] 导入策略代码...")

exec_globals = {}

exec("""
def _f(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return d

def _rows(data):
    try:
        import pandas as pd
        if isinstance(data, pd.DataFrame):
            return data.to_dict("records")
    except Exception:
        pass
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    return []

def _sym(row):
    return str(row.get("code") or row.get("symbol") or row.get("ts_code") or "").strip()

def _price(row):
    for k in ("current", "now", "price", "last", "close", "open", "high", "low"):
        if k in row:
            p = _f(row.get(k), 0.0)
            if p > 0:
                return p
    return 0.0
""", exec_globals)

print("   ✅ 辅助函数导入成功")

print("\n[2] 测试 STRATEGY_1 格式...")

strategy_1_code = '''
from river import compose, linear_model, optim, preprocessing

_STATE = globals().setdefault("_river_up_prob_state", {
    "model": compose.Pipeline(
        preprocessing.StandardScaler(),
        linear_model.LogisticRegression(optimizer=optim.SGD(0.03))
    ),
    "prev": {},
})

def process(data):
    rows = _rows(data)
    if not rows:
        return None

    model = _STATE["model"]
    prev = _STATE["prev"]
    ranked = []

    for row in rows:
        s = _sym(row)
        if not s:
            continue

        price = _price(row)
        if price <= 0:
            continue

        volume = _f(row.get("volume", row.get("vol", 0.0)), 0.0)
        bid = _f(row.get("bid", row.get("bid_price", 0.0)), 0.0)
        ask = _f(row.get("ask", row.get("ask_price", 0.0)), 0.0)
        bid_size = _f(row.get("bid_size", row.get("bid_vol", 0.0)), 0.0)
        ask_size = _f(row.get("ask_size", row.get("ask_vol", 0.0)), 0.0)

        p0 = prev.get(s, {})
        last_price = _f(p0.get("price", price), price)
        last_vol_ema = _f(p0.get("vol_ema", volume), max(volume, 1.0))

        ret_1 = (price - last_price) / (last_price + 1e-9)
        vol_ema = 0.95 * last_vol_ema + 0.05 * volume
        vol_ratio = volume / (vol_ema + 1e-9)
        spread = (ask - bid) / (price + 1e-9) if ask > 0 and bid > 0 else 0.0
        imbalance = (bid_size - ask_size) / (bid_size + ask_size + 1e-9)

        x = {
            "ret_1": ret_1,
            "vol_ratio": vol_ratio,
            "spread": spread,
            "imbalance": imbalance,
            "p_change": _f(row.get("p_change", 0.0), 0.0),
        }

        if "feat" in p0 and "price" in p0:
            y = 1 if price > _f(p0.get("price"), price) else 0
            model.learn_one(p0["feat"], y)

        proba_up = model.predict_proba_one(x).get(1, 0.5)
        ranked.append({
            "code": s,
            "name": row.get("name", ""),
            "up_probability": round(float(proba_up), 4),
            "price": round(price, 4),
            "blockname": row.get("blockname"),
            "industry": row.get("industry"),
        })

        prev[s] = {"price": price, "feat": x, "vol_ema": vol_ema}

    if not ranked:
        return None

    ranked.sort(key=lambda r: r["up_probability"], reverse=True)
    top_pick = ranked[0] if ranked else None

    return {
        "signal": "short_term_up_probability",
        "signal_type": "BUY",
        "stock_code": top_pick.get("code") if top_pick else "",
        "stock_name": top_pick.get("name") if top_pick else "",
        "price": top_pick.get("price") if top_pick else 0,
        "confidence": top_pick.get("up_probability", 0.5) if top_pick else 0.5,
        "top_n": 8,
        "picks": ranked[:8],
    }
'''

exec(strategy_1_code, exec_globals)

test_data = [
    {"code": "SZ000001", "name": "平安银行", "price": 12.50, "volume": 1000000},
    {"code": "SZ000002", "name": "万科A", "price": 9.80, "volume": 800000},
    {"code": "SH600000", "name": "浦发银行", "price": 8.20, "volume": 600000},
]

result = exec_globals["process"](test_data)

if result:
    print(f"   ✅ 策略输出:")
    print(f"      - signal: {result.get('signal')}")
    print(f"      - signal_type: {result.get('signal_type')}")
    print(f"      - stock_code: {result.get('stock_code')}")
    print(f"      - stock_name: {result.get('stock_name')}")
    print(f"      - price: {result.get('price')}")
    print(f"      - confidence: {result.get('confidence')}")
    print(f"      - picks 数量: {len(result.get('picks', []))}")
else:
    print("   ❌ 策略返回 None")

print("\n[3] 验证 bandit 兼容字段...")

required_fields = ["signal_type", "stock_code", "price", "confidence"]
missing = [f for f in required_fields if f not in result or not result[f]]

if missing:
    print(f"   ❌ 缺少字段: {missing}")
else:
    print(f"   ✅ 所有 bandit 必需字段都存在")

print("\n" + "=" * 60)
print("验证完成")
print("=" * 60)
