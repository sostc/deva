#!/usr/bin/env python3
"""Update market state monitoring strategy with new implementation code.

根据 description 和 diagram_info 重新实现策略代码。

公式: state = KMeans(features) + drift = ADWIN(p_change)
逻辑:
  1. 提取市场特征（涨跌分布、波动率等）
  2. KMeans 聚类判断市场状态
  3. ADWIN 检测状态漂移
输出: 市场状态：震荡/上涨/下跌 + 聚类ID + 漂移检测结果 + 市场特征指标
"""

from deva import NB


def update_market_state_strategy_code():
    """Update the market state monitoring strategy with new implementation code."""
    db = NB('naja_strategies')

    market_state_strategy_name = "市场状态监控"

    strategy_id = None
    for sid, value in db.items():
        name = value.get('metadata', {}).get('name', '')
        if name == market_state_strategy_name:
            strategy_id = sid
            break

    if not strategy_id:
        print(f"[ERROR] 未找到策略: {market_state_strategy_name}")
        return False

    print(f"[INFO] 找到策略: {market_state_strategy_name} (ID: {strategy_id})")

    strategy_data = db.get(strategy_id)
    if not strategy_data:
        print(f"[ERROR] 策略数据不存在")
        return False

    metadata = strategy_data.get('metadata', {})

    logic_code = '''from river import cluster, drift
from datetime import datetime

PARAMS = globals().setdefault("PARAMS", {})

def _p(name, default):
    try:
        return float(PARAMS.get(name, default))
    except Exception:
        return float(default)

def _p_int(name, default):
    try:
        return int(PARAMS.get(name, default))
    except Exception:
        return int(default)

_STATE = globals().setdefault("_unified_market_state", {
    "cluster_model": None,
    "drift_detector": None,
    "cluster_stats": {},
    "prev_state": None,
    "n_init": 20,
})

def _ensure_cluster():
    if _STATE["cluster_model"] is None:
        n_clusters = _p_int("n_clusters", 3)
        halflife = _p("halflife", 0.4)
        _STATE["cluster_model"] = cluster.KMeans(
            n_clusters=n_clusters,
            halflife=halflife,
            seed=42
        )
    return _STATE["cluster_model"]

def _ensure_drift():
    if _STATE["drift_detector"] is None:
        _STATE["drift_detector"] = drift.ADWIN()
    return _STATE["drift_detector"]

def _extract_features(data):
    """提取市场特征"""
    features = {}
    
    if isinstance(data, dict):
        rows = data.get("rows", [])
    elif isinstance(data, list):
        rows = data
    else:
        return features
    
    if not rows:
        return features
    
    p_changes = []
    up_count = 0
    down_count = 0
    flat_count = 0
    volumes = []
    prices = []
    
    for row in rows:
        if isinstance(row, dict):
            p_change = float(row.get("p_change", 0) or 0)
            volume = float(row.get("volume", 0) or 0)
            price = float(row.get("price", 0) or 0)
            
            p_changes.append(p_change)
            volumes.append(volume)
            prices.append(price)
            
            if p_change > 0:
                up_count += 1
            elif p_change < 0:
                down_count += 1
            else:
                flat_count += 1
    
    n = len(p_changes)
    if n > 0:
        features["avg_p_change"] = sum(p_changes) / n
        features["std_p_change"] = (sum((x - sum(p_changes)/n)**2 for x in p_changes) / n) ** 0.5 if n > 1 else 0
        features["max_p_change"] = max(p_changes) if p_changes else 0
        features["min_p_change"] = min(p_changes) if p_changes else 0
        features["up_count"] = up_count
        features["down_count"] = down_count
        features["flat_count"] = flat_count
        features["total_count"] = n
        features["up_ratio"] = up_count / n if n > 0 else 0
        features["down_ratio"] = down_count / n if n > 0 else 0
        features["volume_sum"] = sum(volumes)
        features["volume_avg"] = sum(volumes) / n if n > 0 else 0
        features["price_avg"] = sum(prices) / n if n > 0 else 0
    
    return features

def _get_state_name(cluster_id):
    """根据聚类ID获取状态名称"""
    state_names = {0: "震荡", 1: "上涨", 2: "下跌"}
    avg_p_change = _STATE.get("_last_avg_p_change", 0)
    
    if cluster_id is not None and cluster_id in state_names:
        base_name = state_names[cluster_id]
        if abs(avg_p_change) < 0.3:
            return "震荡"
        elif avg_p_change > 0.5:
            return "上涨"
        elif avg_p_change < -0.5:
            return "下跌"
    
    return "震荡"

def on_data(data):
    """主处理函数"""
    features = _extract_features(data)
    
    if not features or features.get("total_count", 0) < 5:
        return None
    
    cluster_model = _ensure_cluster()
    drift_detector = _ensure_drift()
    
    try:
        cluster_id = cluster_model.predict_one(features)
    except Exception:
        cluster_id = 0
    
    cluster_model.learn_one(features)
    
    avg_p_change = features.get("avg_p_change", 0)
    _STATE["_last_avg_p_change"] = avg_p_change
    
    drifted = False
    try:
        drifted = drift_detector.update(avg_p_change).detected_change
    except Exception:
        pass
    
    _STATE["cluster_stats"] = {
        "cluster_id": cluster_id,
        "n_clusters": cluster_model.n_clusters,
    }
    
    market_state = _get_state_name(cluster_id)
    prev_state = _STATE.get("prev_state")
    
    if drifted and prev_state and prev_state != market_state:
        state_changed = True
    else:
        state_changed = False
    
    _STATE["prev_state"] = market_state
    
    signal_type = "unified_market_state"
    
    return {
        "signal_type": signal_type,
        "score": abs(avg_p_change) / 10.0,
        "market_state": market_state,
        "cluster_id": cluster_id,
        "drift_detected": drifted,
        "state_changed": state_changed,
        "market_features": {
            "avg": "{:+.2f}%".format(avg_p_change),
            "std": "{:.3f}".format(features.get("std_p_change", 0)),
            "up": "{:.0%}".format(features.get("up_ratio", 0)),
            "down": "{:.0%}".format(features.get("down_ratio", 0)),
        },
        "timestamp": datetime.now().isoformat(),
    }
'''

    if 'diagram_info' not in metadata:
        metadata['diagram_info'] = {}

    metadata['diagram_info']['icon'] = "🌡️"
    metadata['diagram_info']['color'] = "#8b5cf6"
    metadata['description'] = "集成 KMeans 聚类和 ADWIN 漂移检测，统一输出市场状态信号。通过实时分析涨跌分布、波动率等市场特征，自动识别震荡、上涨、下跌三种市场状态，并检测状态切换。"
    metadata['diagram_info']['description'] = "集成 KMeans 聚类和 ADWIN 漂移检测，统一输出市场状态信号。"
    metadata['diagram_info']['formula'] = "state = KMeans(features) + drift = ADWIN(p_change)"
    metadata['diagram_info']['logic'] = [
        "提取市场特征（涨跌分布、波动率等）",
        "KMeans 聚类判断市场状态",
        "ADWIN 检测状态漂移"
    ]
    metadata['diagram_info']['output'] = "市场状态：震荡/上涨/下跌 + 聚类ID + 漂移检测结果 + 市场特征指标"

    if 'strategy_config' not in metadata:
        metadata['strategy_config'] = {}
    
    if 'logic' not in metadata['strategy_config']:
        metadata['strategy_config']['logic'] = {}
    
    metadata['strategy_config']['logic'] = {
        "type": "python",
        "code": logic_code
    }

    strategy_data['metadata'] = metadata
    db[strategy_id] = strategy_data

    print(f"[SUCCESS] 策略代码已更新")
    print(f"  - description: {metadata['description'][:50]}...")
    print(f"  - logic.code length: {len(logic_code)} chars")
    return True


if __name__ == "__main__":
    success = update_market_state_strategy_code()
    if success:
        print("\n✅ 市场状态监控策略代码更新完成！")
    else:
        print("\n❌ 更新失败")
