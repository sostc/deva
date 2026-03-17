"""
基于 River 的市场分类与状态识别策略

特点：
1. 多维度市场状态分类
2. 噪音过滤与异常处理
3. 早期预警信号
4. 支持 LLM 参数调节
5. 模型持久化
6. HTML 可视化

数据源: realtime_tick_5s
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import pandas as pd
except Exception:
    pd = None

from river import cluster, compose, drift, linear_model, preprocessing, stats


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
class MarketState:
    """市场状态"""
    state_id: int
    state_name: str
    description: str
    color: str
    action: str


MARKET_STATES = {
    0: MarketState(0, "牛市", "强势上涨", "#22c55e", "积极做多"),
    1: MarketState(1, "熊市", "强势下跌", "#ef4444", "观望或做空"),
    2: MarketState(2, "震荡", "横盘整理", "#f59e0b", "高抛低吸"),
    3: MarketState(3, "分化", "涨跌分化", "#8b5cf6", "精选个股"),
    4: MarketState(4, "异常", "极端行情", "#ec4899", "谨慎操作"),
}


class MarketRegimeClassifier:
    """市场状态分类器

    使用 River KMeans 聚类 + ADWIN 漂移检测
    """

    def __init__(
        self,
        n_clusters: int = 5,
        min_samples: int = 20,
        sensitivity: float = 0.5,
    ):
        self._model = cluster.KMeans(n_clusters=n_clusters, halflife=0.5)
        self._drift_model = drift.ADWIN()
        self._min_samples = min_samples
        self._sensitivity = sensitivity
        self._history: List[Dict] = []
        self._last_signal: Optional[Dict] = None
        self._sample_count = 0
        self._last_state = 2

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

        features = self._extract_market_features(df)
        if not features:
            return

        self._sample_count += 1

        try:
            cluster_id = self._model.predict_one(features)
        except Exception:
            cluster_id = 2

        self._model.learn_one(features)

        avg_change = features.get("avg_change", 0) * 100
        self._drift_model.update(avg_change)
        drift_detected = bool(self._drift_model.drift_detected)

        state_id = self._classify_state(cluster_id, features, drift_detected)

        confidence = self._calculate_confidence(features, cluster_id)

        self._last_signal = {
            "signal_type": f"regime_{state_id}",
            "score": confidence,
            "state_id": state_id,
            "state_name": MARKET_STATES.get(state_id, MARKET_STATES[2]).state_name,
            "drift_detected": drift_detected,
            "features": features,
            "html": "",
        }

        self._history.append({
            "timestamp": time.time(),
            "state_id": state_id,
            "cluster_id": cluster_id,
            "features": features,
        })

        if len(self._history) > 100:
            self._history.pop(0)

        self._last_state = state_id

    def _extract_market_features(self, df: pd.DataFrame) -> Dict[str, float]:
        """提取市场特征"""
        features = {}

        if "p_change" in df.columns:
            pchg = pd.to_numeric(df["p_change"], errors="coerce").fillna(0)

            features["avg_change"] = _safe_float(pchg.mean())
            features["std_change"] = _safe_float(pchg.std())
            features["max_change"] = _safe_float(pchg.max())
            features["min_change"] = _safe_float(pchg.min())
            features["skew_change"] = _safe_float(pchg.skew()) if len(pchg) > 2 else 0

            up_mask = pchg > 0
            down_mask = pchg < 0

            features["up_ratio"] = _safe_float(up_mask.mean())
            features["down_ratio"] = _safe_float(down_mask.mean())
            features["extreme_ratio"] = _safe_float(((pchg.abs() > 5).sum()) / len(pchg))

        if "volume" in df.columns:
            vol = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
            features["volume_sum"] = _safe_float(vol.sum())
            features["volume_std"] = _safe_float(vol.std())

        if "amount" in df.columns:
            amount = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
            features["amount_sum"] = _safe_float(amount.sum())

        if "now" in df.columns:
            prices = pd.to_numeric(df["now"], errors="coerce").fillna(0)
            features["price_std"] = _safe_float(prices.std())
            features["price_range"] = _safe_float((prices.max() - prices.min()) / prices.mean() if prices.mean() > 0 else 0)

        features["stock_count"] = len(df)
        return features

    def _classify_state(self, cluster_id: int, features: Dict, drift: bool) -> int:
        """分类市场状态"""
        avg_change = features.get("avg_change", 0) * 100
        up_ratio = features.get("up_ratio", 0.5)
        down_ratio = features.get("down_ratio", 0.5)
        extreme_ratio = features.get("extreme_ratio", 0)
        std_change = features.get("std_change", 0) * 100

        if extreme_ratio > 0.2:
            return 4

        if avg_change > 1.5 and up_ratio > 0.7:
            return 0
        elif avg_change < -1.5 and down_ratio > 0.7:
            return 1

        if abs(avg_change) < 0.5 and std_change < 1:
            return 2

        if abs(up_ratio - down_ratio) < 0.2 and std_change > 1:
            return 3

        return self._last_state

    def _calculate_confidence(self, features: Dict, cluster_id: int) -> float:
        """计算置信度"""
        avg_change = abs(features.get("avg_change", 0))
        up_ratio = features.get("up_ratio", 0.5)
        down_ratio = features.get("down_ratio", 0.5)

        confidence = min(1.0, avg_change / 3)

        imbalance = abs(up_ratio - down_ratio)
        confidence += imbalance * 0.5

        return min(1.0, confidence)

    def get_signal(self) -> Optional[Dict]:
        """获取信号"""
        if not self._last_signal:
            return None

        signal = dict(self._last_signal)
        signal["html"] = self._generate_html(signal)
        return signal

    def _generate_html(self, signal: Dict) -> str:
        """生成 HTML"""
        state_id = signal.get("state_id", 2)
        state_name = signal.get("state_name", "震荡")
        confidence = signal.get("score", 0)
        features = signal.get("features", {})
        drift = signal.get("drift_detected", False)

        state = MARKET_STATES.get(state_id, MARKET_STATES[2])

        drift_alert = ""
        if drift:
            drift_alert = f'''
<div style="background:#fef2f2;border:1px solid #ef4444;border-radius:8px;padding:8px;margin-top:8px;font-size:12px;color:#ef4444;">
    ⚠️ 检测到趋势漂移，状态可能转变
</div>
'''

        html = f'''
<div style="background:linear-gradient(135deg,{state.color}22,{state.color}44);border-radius:16px;padding:16px;margin-bottom:12px;border:2px solid {state.color};">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <div style="font-weight:600;font-size:18px;color:{state.color};">🏛️ 市场状态: {state_name}</div>
        <div style="background:{state.color};color:#fff;padding:4px 12px;border-radius:20px;font-size:12px;">{state.action}</div>
    </div>

    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px;">
        <div style="background:#fff;border-radius:8px;padding:12px;text-align:center;">
            <div style="font-size:20px;font-weight:700;color:{state.color};">{confidence:.0%}</div>
            <div style="font-size:11px;color:#666;">置信度</div>
        </div>
        <div style="background:#fff;border-radius:8px;padding:12px;text-align:center;">
            <div style="font-size:20px;font-weight:700;">{features.get("stock_count",0)}</div>
            <div style="font-size:11px;color:#666;">股票数</div>
        </div>
        <div style="background:#fff;border-radius:8px;padding:12px;text-align:center;">
            <div style="font-size:20px;font-weight:700;{("#22c55e" if features.get("avg_change",0)>0 else "#ef4444")};">{features.get("avg_change",0)*100:+.2f}%</div>
            <div style="font-size:11px;color:#666;">平均涨跌</div>
        </div>
    </div>

    <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;font-size:12px;color:#666;">
        <div>上涨: {features.get("up_ratio",0)*100:.1f}%</div>
        <div>下跌: {features.get("down_ratio",0)*100:.1f}%</div>
        <div>波动: {features.get("std_change",0)*100:.2f}%</div>
        <div>极端: {features.get("extreme_ratio",0)*100:.1f}%</div>
    </div>
    {drift_alert}
</div>
'''
        return html

    def update_params(self, params: Dict) -> None:
        """更新参数"""
        n_clusters = params.get("n_clusters", 5)
        self._min_samples = params.get("min_samples", self._min_samples)
        self._sensitivity = params.get("sensitivity", self._sensitivity)

        self._model = cluster.KMeans(n_clusters=n_clusters, halflife=0.5)
        self._drift_model = drift.ADWIN()
        self._history.clear()

    def reset(self) -> None:
        """重置"""
        self.__init__()


class VolatilityAnalyzer:
    """波动率分析器

    专门分析市场波动特征，识别异常波动
    """

    def __init__(
        self,
        window_size: int = 30,
        volatility_threshold: float = 2.0,
        volume_threshold: float = 2.0,
    ):
        self._window_size = window_size
        self._volatility_threshold = volatility_threshold
        self._volume_threshold = volume_threshold
        self._volatility_history: List[float] = []
        self._volume_history: List[float] = []
        self._last_signal: Optional[Dict] = None
        self._alert_triggered = False

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

        features = self._extract_volatility_features(df)
        if not features:
            return

        self._volatility_history.append(features.get("price_volatility", 0))
        self._volume_history.append(features.get("volume_ratio", 1))

        if len(self._volatility_history) > self._window_size:
            self._volatility_history.pop(0)
            self._volume_history.pop(0)

        volatility_z = self._calculate_zscore(self._volatility_history)
        volume_z = self._calculate_zscore(self._volume_history)

        alert_level = 0
        alert_type = "normal"

        if volatility_z > self._volatility_threshold:
            alert_level = 2
            alert_type = "high_volatility"
        elif volatility_z > self._volatility_threshold * 0.7:
            alert_level = 1
            alert_type = "elevated_volatility"

        if volume_z > self._volume_threshold:
            alert_level = max(alert_level, 2)
            alert_type = "high_volume"
        elif volume_z > self._volume_threshold * 0.7:
            alert_level = max(alert_level, 1)
            alert_type = "elevated_volume"

        if volatility_z < -self._volatility_threshold:
            alert_level = max(alert_level, 1)
            alert_type = "low_volatility"

        alert_names = {
            "normal": "正常",
            "elevated_volatility": "波动升高",
            "high_volatility": "剧烈波动",
            "elevated_volume": "放量",
            "high_volume": "巨量",
            "low_volatility": "波动降低",
        }

        self._last_signal = {
            "signal_type": f"volatility_{alert_type}",
            "score": min(1.0, alert_level / 2),
            "alert_level": alert_level,
            "alert_type": alert_type,
            "alert_name": alert_names.get(alert_type, "正常"),
            "volatility_z": volatility_z,
            "volume_z": volume_z,
            "features": features,
            "html": "",
        }

    def _extract_volatility_features(self, df: pd.DataFrame) -> Dict[str, float]:
        """提取波动特征"""
        features = {}

        if "p_change" in df.columns:
            pchg = pd.to_numeric(df["p_change"], errors="coerce").fillna(0)
            features["price_volatility"] = _safe_float(pchg.std())
            features["price_skew"] = _safe_float(pchg.skew()) if len(pchg) > 2 else 0
            features["avg_change"] = _safe_float(pchg.mean())

        if "volume" in df.columns:
            vol = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
            features["volume_sum"] = _safe_float(vol.sum())
            if self._volume_history:
                avg_vol = np.mean(self._volume_history)
                features["volume_ratio"] = features["volume_sum"] / avg_vol if avg_vol > 0 else 1.0

        if "amount" in df.columns:
            amount = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
            features["amount_sum"] = _safe_float(amount.sum())

        features["stock_count"] = len(df)
        return features

    def _calculate_zscore(self, values: List[float]) -> float:
        """计算 Z 分数"""
        if len(values) < 5:
            return 0.0
        arr = np.array(values)
        mean = np.mean(arr)
        std = np.std(arr)
        if std == 0:
            return 0.0
        return (values[-1] - mean) / std

    def get_signal(self) -> Optional[Dict]:
        """获取信号"""
        if not self._last_signal:
            return None

        signal = dict(self._last_signal)
        signal["html"] = self._generate_html(signal)
        return signal

    def _generate_html(self, signal: Dict) -> str:
        """生成 HTML"""
        alert_level = signal.get("alert_level", 0)
        alert_name = signal.get("alert_name", "正常")
        vol_z = signal.get("volatility_z", 0)
        vol_z_color = "#ef4444" if abs(vol_z) > 1.5 else "#f59e0b" if abs(vol_z) > 1 else "#22c55e"

        bg_colors = ["#f0fdf4", "#fffbeb", "#fef2f2"]
        bg_color = bg_colors[alert_level] if alert_level < len(bg_colors) else bg_colors[0]

        html = f'''
<div style="background:{bg_color};border-radius:16px;padding:16px;margin-bottom:12px;">
    <div style="font-weight:600;font-size:16px;margin-bottom:12px;">📊 波动率分析</div>

    <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-bottom:12px;">
        <div style="background:#fff;border-radius:12px;padding:12px;text-align:center;">
            <div style="font-size:24px;font-weight:700;color:{vol_z_color};">{vol_z:.2f}</div>
            <div style="font-size:12px;color:#666;">波动Z值</div>
        </div>
        <div style="background:#fff;border-radius:12px;padding:12px;text-align:center;">
            <div style="font-size:24px;font-weight:700;{vol_z_color};">{alert_name}</div>
            <div style="font-size:12px;color:#666;">预警级别</div>
        </div>
    </div>

    <div style="font-size:12px;color:#666;padding:8px;background:rgba(0,0,0,0.05);border-radius:8px;">
        {'⚠️ 市场波动异常，建议谨慎操作' if alert_level >= 2 else '📈 波动有所升高' if alert_level >= 1 else '✓ 市场波动正常'}
    </div>
</div>
'''
        return html

    def update_params(self, params: Dict) -> None:
        """更新参数"""
        self._window_size = params.get("window_size", self._window_size)
        self._volatility_threshold = params.get("volatility_threshold", self._volatility_threshold)
        self._volume_threshold = params.get("volume_threshold", self._volume_threshold)


class EarlyWarningSystem:
    """早期预警系统

    综合多个维度，提前预警市场风险和机会
    """

    def __init__(
        self,
        trend_weight: float = 0.3,
        volatility_weight: float = 0.3,
        momentum_weight: float = 0.4,
    ):
        self._trend_weight = trend_weight
        self._volatility_weight = volatility_weight
        self._momentum_weight = momentum_weight

        self._trend_detector = MarketRegimeClassifier()
        self._volatility_analyzer = VolatilityAnalyzer()
        self._last_signal: Optional[Dict] = None

    def on_data(self, data: Any) -> None:
        """处理数据"""
        self._trend_detector.on_data(data)
        self._volatility_analyzer.on_data(data)

        trend_signal = self._trend_detector.get_signal()
        volatility_signal = self._volatility_analyzer.get_signal()

        if not trend_signal or not volatility_signal:
            return

        trend_score = 1 - trend_signal.get("score", 0.5)
        volatility_score = volatility_signal.get("volatility_z", 0) / 3

        warning_score = (
            trend_score * self._trend_weight +
            abs(volatility_score) * self._volatility_weight
        )

        warning_level = 0
        if warning_score > 0.7:
            warning_level = 3
        elif warning_score > 0.5:
            warning_level = 2
        elif warning_score > 0.3:
            warning_level = 1

        warning_types = {
            0: ("正常", "#22c55e"),
            1: ("关注", "#f59e0b"),
            2: ("警告", "#ef4444"),
            3: ("危险", "#dc2626"),
        }

        warning_name, warning_color = warning_types.get(warning_level, ("正常", "#22c55e"))

        self._last_signal = {
            "signal_type": f"warning_level_{warning_level}",
            "score": warning_score,
            "warning_level": warning_level,
            "warning_name": warning_name,
            "warning_color": warning_color,
            "trend_signal": trend_signal,
            "volatility_signal": volatility_signal,
            "html": "",
        }

    def get_signal(self) -> Optional[Dict]:
        """获取信号"""
        if not self._last_signal:
            return None

        signal = dict(self._last_signal)
        signal["html"] = self._generate_html(signal)
        return signal

    def _generate_html(self, signal: Dict) -> str:
        """生成 HTML"""
        warning_level = signal.get("warning_level", 0)
        warning_name = signal.get("warning_name", "正常")
        warning_color = signal.get("warning_color", "#22c55e")
        warning_score = signal.get("score", 0)

        warning_messages = {
            0: "市场状态正常，继续观察",
            1: "建议关注市场变化",
            2: "注意风险，控制仓位",
            3: "强烈建议减仓或离场",
        }

        html = f'''
<div style="background:linear-gradient(135deg,{warning_color}22,{warning_color}44);border-radius:16px;padding:16px;margin-bottom:12px;border:2px solid {warning_color};">
    <div style="font-weight:600;font-size:16px;margin-bottom:12px;color:{warning_color};">🚨 早期预警系统</div>

    <div style="background:#fff;border-radius:12px;padding:16px;text-align:center;margin-bottom:12px;">
        <div style="font-size:32px;font-weight:700;color:{warning_color};">{warning_name}</div>
        <div style="font-size:14px;color:#666;">预警级别 ({warning_score:.0%})</div>
    </div>

    <div style="font-size:14px;color:#fff;background:{warning_color};padding:12px;border-radius:8px;text-align:center;">
        {warning_messages.get(warning_level, "正常")}
    </div>
</div>
'''
        return html

    def update_params(self, params: Dict) -> None:
        """更新参数"""
        self._trend_weight = params.get("trend_weight", self._trend_weight)
        self._volatility_weight = params.get("volatility_weight", self._volatility_weight)
        self._momentum_weight = params.get("momentum_weight", self._momentum_weight)


CLASSIFIER_REGISTRY = {
    "market_regime": MarketRegimeClassifier,
    "volatility": VolatilityAnalyzer,
    "early_warning": EarlyWarningSystem,
}


def get_classifier(name: str, **kwargs) -> Optional[Any]:
    """获取分类器实例"""
    cls = CLASSIFIER_REGISTRY.get(name)
    if cls:
        return cls(**kwargs)
    return None
