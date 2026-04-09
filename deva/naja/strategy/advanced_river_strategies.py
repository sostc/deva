"""
基于 River 的高级趋势检测策略

特点：
1. 早发现趋势变化 (Early Trend Detection)
2. 过滤低质量股票 (噪音过滤)
3. 题材与个股联动分析
4. 支持 LLM 参数调节
5. 支持模型持久化
6. HTML 可视化输出

数据源: realtime_tick_5s
字典: 通达信概念题材
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import pandas as pd
except Exception:
    pd = None

from river import anomaly, compose, drift, linear_model, preprocessing, stats, stream


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


@dataclass
class StockFilterConfig:
    """股票过滤配置"""
    min_price: float = 0.5          # 最低价格
    min_volume: float = 100000     # 最低成交量
    max_volatility: float = 0.5    # 最大波动率阈值
    min_volume_ratio: float = 0.5  # 最小量比


class NoiseFilter:
    """噪音股票过滤器"""

    def __init__(self, config: Optional[StockFilterConfig] = None):
        self.config = config or StockFilterConfig()
        self._volume_history: Dict[str, List[float]] = {}
        self._price_history: Dict[str, List[float]] = {}

    def filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """过滤低质量股票"""
        if df is None or df.empty:
            return df

        result = df.copy()

        if "now" in result.columns:
            result = result[result["now"] >= self.config.min_price]

        if "volume" in result.columns:
            result = result[result["volume"] >= self.config.min_volume]

        return result

    def is_noise_stock(self, code: str, price: float, volume: float) -> bool:
        """判断是否为噪音股票"""
        if price < self.config.min_price:
            return True
        if volume < self.config.min_volume:
            return True

        self._price_history.setdefault(code, []).append(price)
        self._volume_history.setdefault(code, []).append(volume)

        if len(self._price_history[code]) >= 10:
            prices = self._price_history[code][-10:]
            if np.std(prices) / np.mean(prices) if np.mean(prices) > 0 else 0 > self.config.max_volatility:
                return True

        return False

    def get_volume_ratio(self, code: str, current_volume: float) -> float:
        """获取量比"""
        history = self._volume_history.get(code, [])
        if len(history) < 5:
            return 1.0
        avg_volume = np.mean(history[-5:])
        return current_volume / avg_volume if avg_volume > 0 else 1.0


class EarlyTrendDetector:
    """早期趋势检测器

    使用 River 在线学习，检测趋势早期信号
    """

    def __init__(
        self,
        n_trees: int = 15,
        height: int = 8,
        window_size: int = 100,
        sensitivity: float = 0.3,
    ):
        self._model = anomaly.HalfSpaceTrees(
            n_trees=n_trees,
            height=height,
            window_size=window_size
        )
        self._drift_model = drift.ADWIN()
        self._sensitivity = sensitivity
        self._window_size = window_size
        self._history: List[Dict] = []
        self._last_signal: Optional[Dict] = None
        from deva.naja.market_hotspot.processing.noise_filter import get_noise_filter
        self._noise_filter = get_noise_filter()
        self._last_ts = 0

    def on_data(self, data: Any) -> None:
        """处理输入数据"""
        if pd is None:
            return

        df = None
        if isinstance(data, dict) and "data" in data:
            df = data["data"]
        elif isinstance(data, pd.DataFrame):
            df = data

        if df is None or df.empty:
            return

        df = self._noise_filter.filter(df)

        features = self._extract_features(df)

        if not features:
            return

        anomaly_score = self._model.score_one(features)
        self._model.learn_one(features)

        self._drift_model.update(features.get("avg_change", 0))
        drift_detected = bool(self._drift_model.drift_detected)

        self._history.append({
            "timestamp": time.time(),
            "anomaly_score": anomaly_score,
            "drift": drift_detected,
            "features": features,
        })

        if len(self._history) > self._window_size:
            self._history.pop(0)

        trend_score = self._calculate_trend_score(features, anomaly_score, drift_detected)

        signal_type = "trend_sideways"
        if trend_score > self._sensitivity * 2:
            signal_type = "trend_up_early"
        elif trend_score < -self._sensitivity * 2:
            signal_type = "trend_down_early"
        elif trend_score > self._sensitivity:
            signal_type = "trend_up"
        elif trend_score < -self._sensitivity:
            signal_type = "trend_down"

        self._last_signal = {
            "signal_type": signal_type,
            "score": abs(trend_score),
            "direction": 1 if trend_score > 0 else -1 if trend_score < 0 else 0,
            "anomaly_score": anomaly_score,
            "drift_detected": drift_detected,
            "features": features,
            "html": "",
        }

    def _extract_features(self, df: pd.DataFrame) -> Dict[str, float]:
        """提取特征"""
        features = {}

        if "p_change" in df.columns:
            pchg = pd.to_numeric(df["p_change"], errors="coerce").fillna(0)
        elif "now" in df.columns and "close" in df.columns:
            pchg = (pd.to_numeric(df["now"], errors="coerce") - pd.to_numeric(df["close"], errors="coerce")) / pd.to_numeric(df["close"], errors="coerce").replace(0, 1)
        else:
            return features

        features["avg_change"] = _safe_float(pchg.mean())
        features["std_change"] = _safe_float(pchg.std())
        features["max_change"] = _safe_float(pchg.max())
        features["min_change"] = _safe_float(pchg.min())
        features["up_ratio"] = _safe_float((pchg > 0).mean())
        features["down_ratio"] = _safe_float((pchg < 0).mean())

        if "volume" in df.columns:
            vol = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
            features["volume_sum"] = _safe_float(vol.sum())
            features["volume_std"] = _safe_float(vol.std())

        if "now" in df.columns:
            prices = pd.to_numeric(df["now"], errors="coerce").fillna(0)
            features["price_std"] = _safe_float(prices.std())
            features["price_range"] = _safe_float(prices.max() - prices.min())

        features["count"] = len(df)
        return features

    def _calculate_trend_score(self, features: Dict, anomaly_score: float, drift: bool) -> float:
        """计算趋势分数"""
        avg_change = features.get("avg_change", 0) * 100
        std_change = features.get("std_change", 0) * 100
        up_ratio = features.get("up_ratio", 0.5)
        down_ratio = features.get("down_ratio", 0.5)

        trend_score = avg_change * 2

        if up_ratio > 0.7:
            trend_score += std_change
        elif down_ratio > 0.7:
            trend_score -= std_change

        if drift:
            trend_score *= 1.5

        if anomaly_score > 0.8:
            trend_score *= 1.2

        return trend_score

    def get_signal(self) -> Optional[Dict[str, Any]]:
        """获取信号"""
        if not self._last_signal:
            return None

        signal = dict(self._last_signal)
        signal["html"] = self._generate_html(signal)
        return signal

    def _generate_html(self, signal: Dict) -> str:
        """生成 HTML"""
        direction = signal.get("direction", 0)
        score = signal.get("score", 0)
        signal_type = signal.get("signal_type", "sideways")

        direction_text = {"1": "上涨", "0": "震荡", "-1": "下跌"}
        direction_color = {"1": "#22c55e", "0": "#f59e0b", "-1": "#ef4444"}

        html = f'''
<div style="background:linear-gradient(135deg,#667eea,#764ba2);border-radius:16px;padding:16px;color:#fff;margin-bottom:12px;">
    <div style="font-weight:600;font-size:16px;margin-bottom:12px;">📈 早期趋势检测</div>
    <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:12px;">
        <div style="background:rgba(255,255,255,0.2);border-radius:12px;padding:12px;text-align:center;">
            <div style="font-size:24px;font-weight:700;">{direction_text.get(str(direction),"震荡")}</div>
            <div style="font-size:12px;opacity:0.8;">趋势方向</div>
        </div>
        <div style="background:rgba(255,255,255,0.2);border-radius:12px;padding:12px;text-align:center;">
            <div style="font-size:24px;font-weight:700;">{score:.2f}</div>
            <div style="font-size:12px;opacity:0.8;">置信度</div>
        </div>
    </div>
    <div style="margin-top:12px;padding:8px;background:rgba(255,255,255,0.1);border-radius:8px;font-size:12px;">
        {signal_type}
    </div>
</div>
'''
        return html

    def update_params(self, params: Dict[str, Any]) -> None:
        """更新参数"""
        n_trees = params.get("n_trees", 15)
        height = params.get("height", 8)
        window_size = params.get("window_size", 100)
        sensitivity = params.get("sensitivity", 0.3)

        self._model = anomaly.HalfSpaceTrees(n_trees=n_trees, height=height, window_size=window_size)
        self._drift_model = drift.ADWIN()
        self._sensitivity = sensitivity
        self._window_size = window_size
        self._history.clear()

    def reset(self) -> None:
        """重置"""
        self.__init__()

    def get_state(self) -> Dict:
        """获取状态"""
        return {
            "history_len": len(self._history),
            "sensitivity": self._sensitivity,
            "window_size": self._window_size,
        }

    def set_state(self, state: Dict) -> None:
        """设置状态"""
        if "sensitivity" in state:
            self._sensitivity = state["sensitivity"]
        if "window_size" in state:
            self._window_size = state["window_size"]


class BlockMomentumAnalyzer:
    """题材动量分析器

    分析题材内个股的联动性和动量
    """

    def __init__(
        self,
        min_stocks: int = 3,
        momentum_window: int = 5,
        correlation_threshold: float = 0.6,
    ):
        self._min_stocks = min_stocks
        self._momentum_window = momentum_window
        self._correlation_threshold = correlation_threshold
        self._stock_momentum: Dict[str, List[float]] = {}
        self._last_signal: Optional[Dict] = None
        self._block_history: List[Dict] = []
        self._block_name: str = ""
        self._stock_codes: List[str] = []

    def set_block_stocks(self, block_name: str, stock_codes: List[str]) -> None:
        """设置题材股票列表"""
        self._block_name = block_name
        self._stock_codes = stock_codes

    def on_data(self, data: Any) -> None:
        """处理数据"""
        if pd is None:
            return

        df = None
        if isinstance(data, dict) and "data" in data:
            df = data["data"]
        elif isinstance(data, pd.DataFrame):
            df = data

        if df is None or df.empty:
            return

        if hasattr(self, '_stock_codes') and hasattr(df, 'index'):
            df = df[df.index.isin(self._stock_codes)]

        if len(df) < self._min_stocks:
            return

        features = self._extract_block_features(df)

        momentum_score = self._calculate_momentum(features)

        if momentum_score > 0.3:
            signal_type = "block_strong"
        elif momentum_score > 0.1:
            signal_type = "block_rising"
        elif momentum_score < -0.3:
            signal_type = "block_weak"
        elif momentum_score < -0.1:
            signal_type = "block_falling"
        else:
            signal_type = "block_neutral"

        self._last_signal = {
            "signal_type": signal_type,
            "score": abs(momentum_score),
            "momentum": momentum_score,
            "features": features,
            "html": "",
        }

        self._block_history.append({
            "timestamp": time.time(),
            "momentum": momentum_score,
            "features": features,
        })

        if len(self._block_history) > 50:
            self._block_history.pop(0)

    def _extract_block_features(self, df: pd.DataFrame) -> Dict[str, float]:
        """提取题材特征"""
        features = {}

        if "p_change" in df.columns:
            pchg = pd.to_numeric(df["p_change"], errors="coerce").fillna(0)
            features["avg_change"] = _safe_float(pchg.mean())
            features["std_change"] = _safe_float(pchg.std())
            features["max_change"] = _safe_float(pchg.max())
            features["min_change"] = _safe_float(pchg.min())
            features["up_count"] = _safe_int((pchg > 0).sum())
            features["down_count"] = _safe_int((pchg < 0).sum())

        if "volume" in df.columns:
            vol = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
            features["volume_sum"] = _safe_float(vol.sum())

        if "amount" in df.columns:
            amount = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
            features["amount_sum"] = _safe_float(amount.sum())

        features["stock_count"] = len(df)
        return features

    def _calculate_momentum(self, features: Dict) -> float:
        """计算动量"""
        avg_change = features.get("avg_change", 0) * 100
        up_count = features.get("up_count", 0)
        down_count = features.get("down_count", 0)
        stock_count = features.get("stock_count", 1)

        up_ratio = up_count / stock_count if stock_count > 0 else 0

        momentum = avg_change

        if up_ratio > 0.7:
            momentum += abs(avg_change) * 0.5
        elif up_ratio < 0.3:
            momentum -= abs(avg_change) * 0.5

        return momentum

    def get_signal(self) -> Optional[Dict[str, Any]]:
        """获取信号"""
        if not self._last_signal:
            return None

        signal = dict(self._last_signal)
        signal["html"] = self._generate_html(signal)
        return signal

    def _generate_html(self, signal: Dict) -> str:
        """生成 HTML"""
        momentum = signal.get("momentum", 0)
        features = signal.get("features", {})

        signal_color = "#22c55e" if momentum > 0 else "#ef4444" if momentum < 0 else "#f59e0b"

        html = f'''
<div style="background:linear-gradient(135deg,#f093fb,#f5576c);border-radius:16px;padding:16px;color:#fff;margin-bottom:12px;">
    <div style="font-weight:600;font-size:16px;margin-bottom:12px;">🔥 题材动量分析</div>
    <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:12px;">
        <div style="background:rgba(255,255,255,0.2);border-radius:12px;padding:12px;text-align:center;">
            <div style="font-size:24px;font-weight:700;">{momentum:+.2f}%</div>
            <div style="font-size:12px;opacity:0.8;">动量分数</div>
        </div>
        <div style="background:rgba(255,255,255,0.2);border-radius:12px;padding:12px;text-align:center;">
            <div style="font-size:24px;font-weight:700;">{features.get("stock_count",0)}</div>
            <div style="font-size:12px;opacity:0.8;">股票数</div>
        </div>
    </div>
    <div style="margin-top:12px;display:grid;grid-template-columns:repeat(2,1fr);gap:8px;font-size:12px;">
        <div>上涨: {features.get("up_count",0)}</div>
        <div>下跌: {features.get("down_count",0)}</div>
    </div>
</div>
'''
        return html

    def update_params(self, params: Dict[str, Any]) -> None:
        """更新参数"""
        self._min_stocks = params.get("min_stocks", self._min_stocks)
        self._momentum_window = params.get("momentum_window", self._momentum_window)
        self._correlation_threshold = params.get("correlation_threshold", self._correlation_threshold)


class StockSelector:
    """个股精选器

    从题材中精选个股，给 Bandit 提供交易信号
    """

    def __init__(
        self,
        top_n: int = 5,
        min_score: float = 0.3,
        price_weight: float = 0.3,
        volume_weight: float = 0.3,
        change_weight: float = 0.4,
    ):
        self._top_n = top_n
        self._min_score = min_score
        self._price_weight = price_weight
        self._volume_weight = volume_weight
        self._change_weight = change_weight
        from deva.naja.market_hotspot.processing.noise_filter import get_noise_filter
        self._noise_filter = get_noise_filter()
        self._stock_scores: Dict[str, float] = {}
        self._last_signal: Optional[Dict] = None

    def on_data(self, data: Any) -> None:
        """处理数据"""
        if pd is None:
            return

        df = None
        if isinstance(data, dict) and "data" in data:
            df = data["data"]
        elif isinstance(data, pd.DataFrame):
            df = data

        if df is None or df.empty:
            return

        df = self._noise_filter.filter(df)

        if len(df) < 1:
            return

        df = df.copy()
        df["score"] = self._calculate_scores(df)

        df_sorted = df.sort_values("score", ascending=False)
        top_stocks = df_sorted.head(self._top_n)

        selected = []
        for code, row in top_stocks.iterrows():
            if row["score"] >= self._min_score:
                selected.append({
                    "stock_code": code,
                    "stock_name": row.get("name", code),
                    "price": _safe_float(row.get("now", 0)),
                    "change": _safe_float(row.get("p_change", 0)) * 100,
                    "volume": _safe_float(row.get("volume", 0)),
                    "score": _safe_float(row["score"]),
                })

        self._stock_scores = dict(zip(df_sorted.index, df_sorted["score"]))

        signal_type = "select_buy"
        if selected:
            best = selected[0]
            if best["change"] < -3:
                signal_type = "select_strong_sell"
            elif best["change"] < 0:
                signal_type = "select_sell"

        self._last_signal = {
            "signal_type": signal_type,
            "score": _safe_float(selected[0]["score"]) if selected else 0,
            "selected_stocks": selected,
            "html": "",
        }

    def _calculate_scores(self, df: pd.DataFrame) -> pd.Series:
        """计算综合评分"""
        scores = pd.Series(0.0, index=df.index)

        if "now" in df.columns:
            prices = pd.to_numeric(df["now"], errors="coerce").fillna(0)
            price_score = (prices - prices.min()) / (prices.max() - prices.min() + 0.001)
            scores += price_score * self._price_weight * 100

        if "volume" in df.columns:
            volumes = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
            vol_score = (volumes - volumes.min()) / (volumes.max() - volumes.min() + 0.001)
            scores += vol_score * self._volume_weight * 100

        if "p_change" in df.columns:
            changes = pd.to_numeric(df["p_change"], errors="coerce").fillna(0)
            change_score = (changes - changes.min()) / (changes.max() - changes.min() + 0.001)
            scores += change_score * self._change_weight * 100

        return scores

    def get_signal(self) -> Optional[Dict[str, Any]]:
        """获取信号"""
        if not self._last_signal:
            return None

        signal = dict(self._last_signal)
        signal["html"] = self._generate_html(signal)
        return signal

    def _generate_html(self, signal: Dict) -> str:
        """生成 HTML"""
        selected = signal.get("selected_stocks", [])

        if not selected:
            html = '''
<div style="background:linear-gradient(135deg,#4facfe,#00f2fe);border-radius:16px;padding:16px;color:#fff;margin-bottom:12px;">
    <div style="font-weight:600;font-size:16px;">🎯 个股精选</div>
    <div style="padding:20px;text-align:center;color:rgba(255,255,255,0.8);">暂无符合条件的股票</div>
</div>
'''
            return html

        rows = []
        for s in selected[:5]:
            change_color = "#22c55e" if s["change"] > 0 else "#ef4444"
            rows.append(f'''
<tr style="border-bottom:1px solid rgba(255,255,255,0.1);">
    <td style="padding:8px;">{s["stock_code"]}</td>
    <td style="padding:8px;">{s["stock_name"][:6] if s["stock_name"] else ""}</td>
    <td style="padding:8px;color:{change_color};">{s["change"]:+.2f}%</td>
    <td style="padding:8px;">{s["score"]:.2f}</td>
</tr>
''')

        html = f'''
<div style="background:linear-gradient(135deg,#4facfe,#00f2fe);border-radius:16px;padding:16px;color:#fff;margin-bottom:12px;">
    <div style="font-weight:600;font-size:16px;margin-bottom:12px;">🎯 个股精选 TOP{len(selected)}</div>
    <table style="width:100%;font-size:12px;">
        <tr style="color:rgba(255,255,255,0.7);">
            <th style="padding:8px;text-align:left;">代码</th>
            <th style="padding:8px;text-align:left;">名称</th>
            <th style="padding:8px;text-align:right;">涨跌幅</th>
            <th style="padding:8px;text-align:right;">评分</th>
        </tr>
        {''.join(rows)}
    </table>
</div>
'''
        return html

    def update_params(self, params: Dict[str, Any]) -> None:
        """更新参数"""
        self._top_n = params.get("top_n", self._top_n)
        self._min_score = params.get("min_score", self._min_score)
        self._price_weight = params.get("price_weight", self._price_weight)
        self._volume_weight = params.get("volume_weight", self._volume_weight)
        self._change_weight = params.get("change_weight", self._change_weight)

    def get_state(self) -> Dict:
        """获取状态"""
        return {
            "stock_scores": self._stock_scores,
            "top_n": self._top_n,
        }

    def set_state(self, state: Dict) -> None:
        """设置状态"""
        if "top_n" in state:
            self._top_n = state["top_n"]


STRATEGY_REGISTRY = {
    "early_trend": EarlyTrendDetector,
    "block_momentum": BlockMomentumAnalyzer,
    "stock_selector": StockSelector,
}


def get_strategy(name: str, **kwargs) -> Optional[Any]:
    """获取策略实例"""
    cls = STRATEGY_REGISTRY.get(name)
    if cls:
        return cls(**kwargs)
    return None
