#!/usr/bin/env python3
"""Create or update River-based realtime ML strategies for NAJA.

Usage:
  python3 scripts/demo/create_river_replay_strategies.py
  python3 scripts/demo/create_river_replay_strategies.py --start
  python3 scripts/demo/create_river_replay_strategies.py --datasource-name 行情回放 --dict-name stock_block_dict_pytdx
"""

from __future__ import annotations

import argparse
import textwrap

from deva.naja.datasource import get_datasource_manager
from deva.naja.dictionary import get_dictionary_manager
from deva.naja.strategy import get_strategy_manager


STRATEGY_1 = textwrap.dedent(
    r'''
    # River 在线分类：挖掘短期上涨概率
    from river import compose, linear_model, optim, preprocessing

    _STATE = globals().setdefault("_river_up_prob_state", {
        "model": compose.Pipeline(
            preprocessing.StandardScaler(),
            linear_model.LogisticRegression(optimizer=optim.SGD(0.03))
        ),
        "prev": {},
    })

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

            # 延迟监督：用当前价格变化给上一时刻特征打标签
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
)


STRATEGY_2 = textwrap.dedent(
    r'''
    # River 在线异常检测：量价跳变 + 盘口结构突变
    from river import anomaly

    _STATE = globals().setdefault("_river_abnormal_state", {
        "model": anomaly.HalfSpaceTrees(seed=42, n_trees=20, height=8, window_size=250),
        "prev": {},
    })

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

    def process(data):
        rows = _rows(data)
        if not rows:
            return None

        model = _STATE["model"]
        prev = _STATE["prev"]
        scores = []

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
            p_price = _f(p0.get("price", price), price)
            p_vol_ema = _f(p0.get("vol_ema", volume), max(volume, 1.0))
            p_imb = _f(p0.get("imbalance", 0.0), 0.0)

            ret = (price - p_price) / (p_price + 1e-9)
            vol_ema = 0.92 * p_vol_ema + 0.08 * volume
            vol_ratio = volume / (vol_ema + 1e-9)
            spread = (ask - bid) / (price + 1e-9) if ask > 0 and bid > 0 else 0.0
            imbalance = (bid_size - ask_size) / (bid_size + ask_size + 1e-9)
            imbalance_jump = abs(imbalance - p_imb)

            x = {
                "abs_ret": abs(ret),
                "vol_ratio": vol_ratio,
                "spread": spread,
                "imbalance": imbalance,
                "imbalance_jump": imbalance_jump,
            }
            score = float(model.score_one(x))
            model.learn_one(x)

            scores.append({
                "code": s,
                "name": row.get("name", ""),
                "anomaly_score": round(score, 4),
                "price": round(price, 4),
                "ret": round(ret, 6),
                "vol_ratio": round(vol_ratio, 4),
                "imbalance_jump": round(imbalance_jump, 4),
                "blockname": row.get("blockname"),
                "industry": row.get("industry"),
            })

            prev[s] = {
                "price": price,
                "vol_ema": vol_ema,
                "imbalance": imbalance,
            }

        if not scores:
            return None

        scores.sort(key=lambda r: r["anomaly_score"], reverse=True)
        top_pick = scores[0] if scores else None
        
        return {
            "signal": "tick_abnormal_score",
            "signal_type": "BUY",
            "stock_code": top_pick.get("code") if top_pick else "",
            "stock_name": top_pick.get("name") if top_pick else "",
            "price": top_pick.get("price") if top_pick else 0,
            "confidence": min(1.0, top_pick.get("anomaly_score", 0) / 10.0) if top_pick else 0.5,
            "top_n": 8,
            "picks": scores[:8],
        }
    '''
)


STRATEGY_3 = textwrap.dedent(
    r'''
    # River 在线聚类：市场状态(震荡/趋势/高波动)
    from river import cluster

    _STATE = globals().setdefault("_river_regime_state", {
        "model": cluster.KMeans(n_clusters=3, halflife=0.4, seed=42),
        "cluster_stats": {},
    })

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

    def _map_semantic(stats):
        ids = list(stats.keys())
        if len(ids) < 3:
            return {i: i for i in ids}

        # 高波动: abs_ret + spread 最大
        high_vol = max(ids, key=lambda i: stats[i].get("abs_ret", 0.0) + stats[i].get("spread", 0.0))
        remain = [i for i in ids if i != high_vol]
        # 趋势: trend_strength 最大
        trend = max(remain, key=lambda i: stats[i].get("trend_strength", 0.0))
        osc = [i for i in remain if i != trend][0]
        return {osc: 0, trend: 1, high_vol: 2}

    def process(data):
        rows = _rows(data)
        if not rows:
            return None

        model = _STATE["model"]
        stats = _STATE["cluster_stats"]
        count = {0: 0, 1: 0, 2: 0}

        for row in rows:
            price = _price(row)
            if price <= 0:
                continue
            pre_close = _f(row.get("close", price), price)
            ret = (price - pre_close) / (pre_close + 1e-9)
            spread = (_f(row.get("ask", 0.0), 0.0) - _f(row.get("bid", 0.0), 0.0)) / (price + 1e-9)
            bid_size = _f(row.get("bid_size", row.get("bid_vol", 0.0)), 0.0)
            ask_size = _f(row.get("ask_size", row.get("ask_vol", 0.0)), 0.0)
            imbalance = (bid_size - ask_size) / (bid_size + ask_size + 1e-9)

            x = {
                "ret": ret,
                "abs_ret": abs(ret),
                "spread": spread,
                "imbalance": imbalance,
                "volume": _f(row.get("volume", row.get("vol", 0.0)), 0.0),
            }

            model.learn_one(x)
            cid = int(model.predict_one(x))
            s = stats.setdefault(cid, {"n": 0, "abs_ret": 0.0, "spread": 0.0, "trend_strength": 0.0})
            s["n"] += 1
            s["abs_ret"] = 0.95 * s["abs_ret"] + 0.05 * abs(ret)
            s["spread"] = 0.95 * s["spread"] + 0.05 * abs(spread)
            s["trend_strength"] = 0.95 * s["trend_strength"] + 0.05 * (abs(ret) / (abs(ret) + abs(spread) + 1e-9))

        if not stats:
            return None

        semantic_map = _map_semantic(stats)
        for raw_id, sem_id in semantic_map.items():
            count[sem_id] += int(stats.get(raw_id, {}).get("n", 0))

        dominant = max(count.keys(), key=lambda i: count[i])
        names = {0: "cluster 0: 震荡", 1: "cluster 1: 趋势", 2: "cluster 2: 高波动"}

        return {
            "signal": "market_climate_cluster",
            "dominant_cluster": int(dominant),
            "dominant_name": names[dominant],
            "distribution": count,
        }
    '''
)


STRATEGY_4 = textwrap.dedent(
    r'''
    # River 订单流失衡：盘口先行信号
    from river import compose, linear_model, optim, preprocessing

    _STATE = globals().setdefault("_river_ofi_state", {
        "model": compose.Pipeline(
            preprocessing.StandardScaler(),
            linear_model.LogisticRegression(optimizer=optim.SGD(0.02))
        ),
        "prev": {},
    })

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

    def process(data):
        rows = _rows(data)
        if not rows:
            return None

        model = _STATE["model"]
        prev = _STATE["prev"]
        out = []

        for row in rows:
            s = _sym(row)
            if not s:
                continue
            price = _price(row)
            if price <= 0:
                continue

            bid = _f(row.get("bid", row.get("bid_price", 0.0)), 0.0)
            ask = _f(row.get("ask", row.get("ask_price", 0.0)), 0.0)
            bid_size = _f(row.get("bid_size", row.get("bid_vol", 0.0)), 0.0)
            ask_size = _f(row.get("ask_size", row.get("ask_vol", 0.0)), 0.0)
            spread = (ask - bid) / (price + 1e-9) if ask > 0 and bid > 0 else 0.0

            p0 = prev.get(s, {})
            p_bid_size = _f(p0.get("bid_size", bid_size), bid_size)
            p_ask_size = _f(p0.get("ask_size", ask_size), ask_size)
            p_spread = _f(p0.get("spread", spread), spread)

            ofi = (bid_size - p_bid_size) - (ask_size - p_ask_size)
            depth_imb = (bid_size - ask_size) / (bid_size + ask_size + 1e-9)
            spread_change = spread - p_spread

            x = {
                "ofi": ofi,
                "depth_imb": depth_imb,
                "spread": spread,
                "spread_change": spread_change,
                "p_change": _f(row.get("p_change", 0.0), 0.0),
            }

            if "feat" in p0 and "price" in p0:
                y = 1 if price > _f(p0.get("price"), price) else 0
                model.learn_one(p0["feat"], y)

            up_proba = model.predict_proba_one(x).get(1, 0.5)
            out.append({
                "code": s,
                "name": row.get("name", ""),
                "order_flow_up_probability": round(float(up_proba), 4),
                "price": round(price, 4),
                "ofi": round(ofi, 2),
                "depth_imb": round(depth_imb, 4),
                "spread_change": round(spread_change, 6),
                "blockname": row.get("blockname"),
                "industry": row.get("industry"),
            })

            prev[s] = {
                "price": price,
                "feat": x,
                "bid_size": bid_size,
                "ask_size": ask_size,
                "spread": spread,
            }

        if not out:
            return None

        out.sort(key=lambda r: r["order_flow_up_probability"], reverse=True)
        top_pick = out[0] if out else None
        
        return {
            "signal": "order_flow_imbalance_lead",
            "signal_type": "BUY",
            "stock_code": top_pick.get("code") if top_pick else "",
            "stock_name": top_pick.get("name") if top_pick else "",
            "price": top_pick.get("price") if top_pick else 0,
            "confidence": top_pick.get("order_flow_up_probability", 0.5) if top_pick else 0.5,
            "top_n": 8,
            "picks": out[:8],
        }
    '''
)


STRATEGY_5 = textwrap.dedent(
    r'''
    # River 微观结构波动异常：小幅震荡/高频抖动/突然放大
    from river import anomaly

    _STATE = globals().setdefault("_river_micro_vol_state", {
        "model": anomaly.HalfSpaceTrees(seed=7, n_trees=20, height=8, window_size=200),
        "prev": {},
    })

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

    def process(data):
        rows = _rows(data)
        if not rows:
            return None

        model = _STATE["model"]
        prev = _STATE["prev"]
        out = []

        for row in rows:
            s = _sym(row)
            if not s:
                continue
            price = _price(row)
            if price <= 0:
                continue

            p0 = prev.get(s, {})
            p_price = _f(p0.get("price", price), price)
            p_ret = _f(p0.get("ret", 0.0), 0.0)
            ret = (price - p_price) / (p_price + 1e-9)

            short_vol = 0.80 * _f(p0.get("short_vol", abs(ret)), abs(ret)) + 0.20 * abs(ret)
            long_vol = 0.97 * _f(p0.get("long_vol", abs(ret)), abs(ret)) + 0.03 * abs(ret)
            vol_ratio = short_vol / (long_vol + 1e-9)
            micro_jitter = abs(ret - p_ret)

            x = {
                "abs_ret": abs(ret),
                "short_vol": short_vol,
                "long_vol": long_vol,
                "vol_ratio": vol_ratio,
                "micro_jitter": micro_jitter,
            }

            score = float(model.score_one(x))
            model.learn_one(x)

            out.append({
                "code": s,
                "name": row.get("name", ""),
                "micro_vol_anomaly_score": round(score, 4),
                "price": round(price, 4),
                "vol_ratio": round(vol_ratio, 4),
                "micro_jitter": round(micro_jitter, 6),
                "blockname": row.get("blockname"),
                "industry": row.get("industry"),
            })

            prev[s] = {
                "price": price,
                "ret": ret,
                "short_vol": short_vol,
                "long_vol": long_vol,
            }

        if not out:
            return None

        out.sort(key=lambda r: r["micro_vol_anomaly_score"], reverse=True)
        top_pick = out[0] if out else None
        
        return {
            "signal": "microstructure_volatility_anomaly",
            "signal_type": "BUY",
            "stock_code": top_pick.get("code") if top_pick else "",
            "stock_name": top_pick.get("name") if top_pick else "",
            "price": top_pick.get("price") if top_pick else 0,
            "confidence": min(1.0, top_pick.get("micro_vol_anomaly_score", 0) / 10.0) if top_pick else 0.5,
            "top_n": 8,
            "picks": out[:8],
        }
    '''
)


STRATEGY_6 = textwrap.dedent(
    r'''
    # River 行为痕迹聚类：做市/分批大单/情绪驱动（由聚类结构映射）
    from river import cluster

    _STATE = globals().setdefault("_river_behavior_state", {
        "model": cluster.KMeans(n_clusters=3, halflife=0.35, seed=24),
        "prev": {},
        "cluster_stats": {},
    })

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

    def _map_labels(stats):
        ids = list(stats.keys())
        if len(ids) < 3:
            return {i: "待学习" for i in ids}

        # 情绪驱动: burst 最大
        emo = max(ids, key=lambda i: stats[i].get("burst", 0.0))
        remain = [i for i in ids if i != emo]
        # 做市: abs_ret 最小 且 spread 最小
        mm = min(remain, key=lambda i: stats[i].get("abs_ret", 0.0) + stats[i].get("spread", 0.0))
        sliced = [i for i in remain if i != mm][0]

        return {
            mm: "高频做市",
            sliced: "大单分批执行",
            emo: "情绪驱动交易",
        }

    def process(data):
        rows = _rows(data)
        if not rows:
            return None

        model = _STATE["model"]
        prev = _STATE["prev"]
        stats = _STATE["cluster_stats"]
        out = []

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
            spread = (ask - bid) / (price + 1e-9) if ask > 0 and bid > 0 else 0.0
            bid_size = _f(row.get("bid_size", row.get("bid_vol", 0.0)), 0.0)
            ask_size = _f(row.get("ask_size", row.get("ask_vol", 0.0)), 0.0)
            depth_imb = abs((bid_size - ask_size) / (bid_size + ask_size + 1e-9))

            p0 = prev.get(s, {})
            p_price = _f(p0.get("price", price), price)
            p_vol_ema = _f(p0.get("vol_ema", volume), max(volume, 1.0))
            ret = (price - p_price) / (p_price + 1e-9)
            vol_ema = 0.9 * p_vol_ema + 0.1 * volume
            vol_ratio = volume / (vol_ema + 1e-9)
            burst = abs(ret) * vol_ratio

            x = {
                "abs_ret": abs(ret),
                "spread": spread,
                "depth_imb": depth_imb,
                "vol_ratio": vol_ratio,
                "burst": burst,
            }

            model.learn_one(x)
            cid = int(model.predict_one(x))

            st = stats.setdefault(cid, {"n": 0, "abs_ret": 0.0, "spread": 0.0, "burst": 0.0})
            st["n"] += 1
            st["abs_ret"] = 0.95 * st["abs_ret"] + 0.05 * abs(ret)
            st["spread"] = 0.95 * st["spread"] + 0.05 * abs(spread)
            st["burst"] = 0.95 * st["burst"] + 0.05 * burst

            prev[s] = {"price": price, "vol_ema": vol_ema}
            out.append({
                "code": s,
                "name": row.get("name", ""),
                "cluster_id": cid,
                "price": round(price, 4),
                "burst": round(burst, 6),
                "abs_ret": round(abs(ret), 6),
                "blockname": row.get("blockname"),
                "industry": row.get("industry"),
            })

        if not out:
            return None

        label_map = _map_labels(stats)
        for item in out:
            item["behavior_label"] = label_map.get(item["cluster_id"], "待学习")

        out.sort(key=lambda r: r["burst"], reverse=True)
        top_pick = out[0] if out else None
        
        return {
            "signal": "trading_behavior_footprint",
            "signal_type": "BUY",
            "stock_code": top_pick.get("code") if top_pick else "",
            "stock_name": top_pick.get("name") if top_pick else "",
            "price": top_pick.get("price") if top_pick else 0,
            "confidence": 0.7,
            "top_n": 8,
            "picks": out[:8],
        }
    '''
)


STRATEGIES = [
    {
        "name": "river_短期方向概率_top",
        "description": "在线学习短期价格方向概率，输出上涨概率最高股票",
        "code": STRATEGY_1,
        "diagram_info": {
            "icon": "📈",
            "color": "#2E86DE",
            "description": "基于在线逻辑回归学习短期上涨方向概率，实时排序输出高概率标的。",
            "formula": "P(up|x)=sigmoid(w·x+b)",
            "logic": [
                "提取 ret_1/vol_ratio/spread/imbalance 等特征",
                "使用上一时刻特征 + 当前tick方向做延迟监督在线更新",
                "输出上涨概率 TopN 股票（附行业/板块）",
            ],
            "output": "short_term_up_probability + picks(top_n)",
        },
        "compute_mode": "record",
        "window_type": "sliding",
        "window_size": 5,
    },
    {
        "name": "river_量价盘口异常分数_top",
        "description": "检测成交量放大、价格跳跃、盘口结构突变，输出异常分数Top",
        "code": STRATEGY_2,
        "diagram_info": {
            "icon": "🚨",
            "color": "#E74C3C",
            "description": "使用 HalfSpaceTrees 对量价与盘口突变进行在线异常检测并输出高分标的。",
            "formula": "anomaly_score = HST.score(x)",
            "logic": [
                "构建 abs_ret/vol_ratio/spread/imbalance_jump 特征",
                "实时 score_one + learn_one",
                "按异常分数降序输出 TopN",
            ],
            "output": "tick_abnormal_score + picks(top_n)",
        },
        "compute_mode": "record",
        "window_type": "sliding",
        "window_size": 5,
    },
    {
        "name": "river_tick_市场气候聚类",
        "description": "在线聚类 tick 状态：震荡/趋势/高波动",
        "code": STRATEGY_3,
        "diagram_info": {
            "icon": "🌦️",
            "color": "#16A085",
            "description": "在线 KMeans 将 tick 流映射为震荡/趋势/高波动三类市场气候。",
            "formula": "cluster_id = KMeans.predict(x)",
            "logic": [
                "提取 ret/abs_ret/spread/imbalance/volume",
                "持续聚类并维护簇统计",
                "语义映射为 cluster0震荡/cluster1趋势/cluster2高波动",
            ],
            "output": "market_climate_cluster + dominant_cluster + distribution",
        },
        "compute_mode": "record",
        "window_type": "sliding",
        "window_size": 5,
    },
    {
        "name": "river_订单流失衡先行信号",
        "description": "基于 bid/ask/size/spread 的订单流失衡在线学习",
        "code": STRATEGY_4,
        "diagram_info": {
            "icon": "📊",
            "color": "#8E44AD",
            "description": "从盘口深度与价差变化学习订单流失衡，输出先行上涨概率。",
            "formula": "P(up|ofi,depth_imb,spread_change)",
            "logic": [
                "计算 OFI、深度失衡、价差变化",
                "使用延迟监督在线训练二分类模型",
                "输出 order_flow_up_probability TopN",
            ],
            "output": "order_flow_imbalance_lead + picks(top_n)",
        },
        "compute_mode": "record",
        "window_type": "sliding",
        "window_size": 5,
    },
    {
        "name": "river_微观结构波动异常_top",
        "description": "识别小幅震荡/高频抖动/突然放大等微观结构波动异常",
        "code": STRATEGY_5,
        "diagram_info": {
            "icon": "📡",
            "color": "#D35400",
            "description": "对微观结构波动状态做在线异常检测，识别突发放大与抖动异常。",
            "formula": "score = HST(abs_ret,vol_ratio,micro_jitter)",
            "logic": [
                "维护 short_vol/long_vol 与微抖动特征",
                "在线计算异常分数并增量学习",
                "输出微观结构异常 TopN",
            ],
            "output": "microstructure_volatility_anomaly + picks(top_n)",
        },
        "compute_mode": "record",
        "window_type": "sliding",
        "window_size": 5,
    },
    {
        "name": "river_交易行为痕迹聚类",
        "description": "聚类交易行为脚印并映射为做市/分批大单/情绪驱动",
        "code": STRATEGY_6,
        "diagram_info": {
            "icon": "🧭",
            "color": "#1ABC9C",
            "description": "对交易行为脚印进行在线聚类并映射为典型行为标签。",
            "formula": "behavior_label = map(KMeans.cluster)",
            "logic": [
                "提取 abs_ret/spread/depth_imb/vol_ratio/burst",
                "在线聚类并更新簇画像",
                "映射为高频做市/大单分批/情绪驱动标签",
            ],
            "output": "trading_behavior_footprint + picks(top_n)",
        },
        "compute_mode": "record",
        "window_type": "sliding",
        "window_size": 5,
    },
]


def _resolve_by_name(entries, name: str, fuzzy_keywords: list[str] | None = None):
    target = (name or "").strip().lower()
    for e in entries:
        if (getattr(e, "name", "") or "").strip().lower() == target and target:
            return e

    if fuzzy_keywords:
        lowered = [k.lower() for k in fuzzy_keywords if k]
        for e in entries:
            nm = (getattr(e, "name", "") or "").lower()
            if any(k in nm for k in lowered):
                return e
    return None


def main():
    parser = argparse.ArgumentParser(description="Create/Update River realtime ML strategies.")
    parser.add_argument("--datasource-name", default="行情回放", help="目标数据源名称（默认：行情回放）")
    parser.add_argument("--dict-name", default="stock_block_dict_pytdx", help="目标字典名称")
    parser.add_argument("--category", default="实验", help="策略类别")
    parser.add_argument("--start", action="store_true", help="创建后自动启动策略")
    parser.add_argument(
        "--strict-binding",
        action="store_true",
        help="严格要求数据源和字典存在，否则直接失败",
    )
    args = parser.parse_args()

    ds_mgr = get_datasource_manager()
    dict_mgr = get_dictionary_manager()
    st_mgr = get_strategy_manager()

    ds = _resolve_by_name(
        ds_mgr.list_all(),
        args.datasource_name,
        fuzzy_keywords=[args.datasource_name, "回放", "replay", "行情回放", "回放行情"],
    )
    dict_entry = _resolve_by_name(dict_mgr.list_all(), args.dict_name, fuzzy_keywords=[args.dict_name])
    if args.strict_binding:
        if ds is None:
            raise SystemExit(f"未找到数据源: {args.datasource_name}（可先在 UI 中创建/启动）")
        if dict_entry is None:
            raise SystemExit(f"未找到字典: {args.dict_name}（可先在字典管理中创建）")

    created, updated, started = [], [], []
    failed = []
    warnings = []

    bound_datasource_id = ds.id if ds else ""
    dictionary_profile_ids = [dict_entry.id] if dict_entry else []
    if ds is None:
        warnings.append(f"未找到数据源“{args.datasource_name}”，策略将先写入但不绑定数据源")
    if dict_entry is None:
        warnings.append(f"未找到字典“{args.dict_name}”，策略将先写入但不绑定字典补齐")

    for spec in STRATEGIES:
        existing = st_mgr.get_by_name(spec["name"])
        kwargs = dict(
            name=spec["name"],
            description=spec["description"],
            func_code=spec["code"],
            bound_datasource_id=bound_datasource_id,
            dictionary_profile_ids=dictionary_profile_ids,
            compute_mode=spec["compute_mode"],
            window_type=spec["window_type"],
            window_size=spec["window_size"],
            window_interval="10s",
            window_return_partial=False,
            max_history_count=300,
            category=args.category,
        )

        if existing:
            ret = existing.update_config(**{k: v for k, v in kwargs.items() if k != "name"})
            if not ret.get("success"):
                failed.append((spec["name"], ret.get("error", "unknown")))
                continue
            existing._metadata.diagram_info = spec.get("diagram_info", {})
            existing.save()
            updated.append(existing.id)
            entry_id = existing.id
        else:
            ret = st_mgr.create(**kwargs)
            if not ret.get("success"):
                failed.append((spec["name"], ret.get("error", "unknown")))
                continue
            entry = st_mgr.get(ret.get("id"))
            if entry:
                entry._metadata.diagram_info = spec.get("diagram_info", {})
                entry.save()
            created.append(ret.get("id"))
            entry_id = ret.get("id")

        if args.start and entry_id:
            sret = st_mgr.start(entry_id)
            if sret.get("success"):
                started.append(entry_id)
            else:
                failed.append((spec["name"], f"start failed: {sret.get('error', 'unknown')}"))

    print("=== River 策略创建结果 ===")
    print(f"数据源: {(ds.name + ' (' + ds.id + ')') if ds else args.datasource_name + ' (未绑定ID)'}")
    print(f"字典: {(dict_entry.name + ' (' + dict_entry.id + ')') if dict_entry else args.dict_name + ' (未绑定ID)'}")
    print(f"创建: {len(created)}")
    print(f"更新: {len(updated)}")
    print(f"启动: {len(started)}")
    if warnings:
        print("告警:")
        for w in warnings:
            print(f"- {w}")
    if failed:
        print("失败:")
        for name, err in failed:
            print(f"- {name}: {err}")


if __name__ == "__main__":
    main()
