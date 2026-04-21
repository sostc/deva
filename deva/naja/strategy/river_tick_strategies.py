"""
River-based tick strategies for realtime_tick_5s DataFrame input.

These strategies focus on turning tick snapshots into signals with score
so Radar + Memory can consume them.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import math

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional in runtime
    pd = None

from river import anomaly, cluster, drift

from .model_persist import RiverStatePersistMixin, serialize_river_model, deserialize_river_model

log = logging.getLogger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def extract_tick_features(data: Any) -> Dict[str, float]:
    """
    Extract compact numeric features from tick DataFrame snapshots.
    Supports:
    - pandas.DataFrame
    - dict with key 'data' as DataFrame
    """
    if pd is None:
        return {}

    df = None
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], pd.DataFrame):
        df = data["data"]
    elif isinstance(data, pd.DataFrame):
        df = data

    if df is None or df.empty:
        return {}

    features: Dict[str, float] = {}

    # p_change
    if "p_change" in df.columns:
        pchg = pd.to_numeric(df["p_change"], errors="coerce")
    elif "now" in df.columns and "close" in df.columns:
        pchg = (pd.to_numeric(df["now"], errors="coerce") - pd.to_numeric(df["close"], errors="coerce")) / pd.to_numeric(df["close"], errors="coerce")
    else:
        pchg = None

    if pchg is not None:
        features["avg_p_change"] = _safe_float(pchg.mean())
        features["std_p_change"] = _safe_float(pchg.std())
        features["up_ratio"] = _safe_float((pchg > 0).mean())
        features["down_ratio"] = _safe_float((pchg < 0).mean())

    if "volume" in df.columns:
        vol = pd.to_numeric(df["volume"], errors="coerce")
        features["volume_sum"] = _safe_float(vol.sum())
        features["volume_mean"] = _safe_float(vol.mean())

    if "amount" in df.columns:
        amt = pd.to_numeric(df["amount"], errors="coerce")
        features["amount_sum"] = _safe_float(amt.sum())
        features["amount_mean"] = _safe_float(amt.mean())

    if "now" in df.columns:
        now = pd.to_numeric(df["now"], errors="coerce")
        features["price_mean"] = _safe_float(now.mean())
        features["price_std"] = _safe_float(now.std())

    features["rows"] = _safe_float(len(df))
    return features


class RiverTickAnomalyHST(RiverStatePersistMixin):
    """HalfSpaceTrees anomaly score on aggregated tick features."""

    MODEL_STATE_KEY = "river_tick_anomaly_hst_model"

    def __init__(self, n_trees: int = 25, height: int = 15, window_size: int = 250):
        self._n_trees = n_trees
        self._height = height
        self._window_size = window_size
        self._model = anomaly.HalfSpaceTrees(n_trees=n_trees, height=height, window_size=window_size)
        self._last = None
        self._persist_db = None
        self.try_load_state()

    def on_data(self, data: Any) -> None:
        feats = extract_tick_features(data)
        if not feats:
            self._last = None
            return
        score = self._model.score_one(feats)
        self._model.learn_one(feats)
        self._last = {
            "signal_type": "tick_anomaly_hst",
            "score": _safe_float(score),
            "features": feats,
        }
        self.try_save_state()

    def get_signal(self) -> Optional[Dict[str, Any]]:
        if self._last is None:
            return None
        
        signal = dict(self._last)
        
        score = signal.get("score", 0)
        features = signal.get("features", {})
        
        html_parts = []
        html_parts.append('<div style="margin-bottom:12px;">')
        html_parts.append('<div style="font-weight:600;color:#2563eb;margin-bottom:8px;">🧪 市场异常检测 (HST)</div>')
        html_parts.append('<div style="color:#666;font-size:12px;margin-bottom:8px;">HalfSpaceTrees 计算市场整体异常度</div>')
        
        score_color = '#ef4444' if score > 0.8 else '#f59e0b' if score > 0.5 else '#22c55e'
        score_bg = '#fef2f2' if score > 0.8 else '#fffbeb' if score > 0.5 else '#f0fdf4'
        
        html_parts.append('<div style="background:' + score_bg + ';border:1px solid ' + score_color + ';padding:12px;border-radius:12px;margin-bottom:12px;">')
        html_parts.append('<div style="font-size:12px;color:#666;">异常分数</div>')
        html_parts.append('<div style="font-size:28px;font-weight:700;color:' + score_color + ';">' + '{:.3f}'.format(score) + '</div>')
        html_parts.append('</div>')
        
        html_parts.append('<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;">')
        html_parts.append('<div style="background:#fff;padding:10px;border-radius:8px;text-align:center;">')
        html_parts.append('<div style="font-size:16px;font-weight:600;">' + str(int(features.get("rows", 0))) + '</div>')
        html_parts.append('<div style="font-size:11px;color:#888;">样本数</div>')
        html_parts.append('</div>')
        html_parts.append('<div style="background:#fff;padding:10px;border-radius:8px;text-align:center;">')
        html_parts.append('<div style="font-size:16px;font-weight:600;">' + '{:.2f}'.format(features.get("price_std", 0)) + '</div>')
        html_parts.append('<div style="font-size:11px;color:#888;">价格波动</div>')
        html_parts.append('</div>')
        html_parts.append('</div>')
        
        html_parts.append('</div>')
        
        signal["html"] = ''.join(html_parts)
        return signal

    def update_params(self, params: Dict[str, Any]) -> None:
        n_trees = int(params.get("n_trees", self._n_trees))
        height = int(params.get("height", self._height))
        window_size = int(params.get("window_size", self._window_size))
        self._n_trees = n_trees
        self._height = height
        self._window_size = window_size
        self._model = anomaly.HalfSpaceTrees(n_trees=n_trees, height=height, window_size=window_size)

    def _extract_model_state(self) -> Any:
        return self._model

    def _restore_model_state(self, state: Any) -> None:
        self._model = state


class RiverTickRegimeCluster(RiverStatePersistMixin):
    """KMeans clustering over market state features."""

    MODEL_STATE_KEY = "river_tick_regime_cluster_model"

    def __init__(self, n_clusters: int = 3, halflife: float = 0.6):
        self._n_clusters = n_clusters
        self._halflife = halflife
        self._model = cluster.KMeans(n_clusters=n_clusters, halflife=halflife)
        self._last = None
        self._persist_db = None
        self.try_load_state()

    def on_data(self, data: Any) -> None:
        feats = extract_tick_features(data)
        if not feats:
            self._last = None
            return
        try:
            cluster_id = self._model.predict_one(feats)
        except Exception:
            cluster_id = None
        self._model.learn_one(feats)
        self._last = {
            "signal_type": "tick_regime_cluster",
            "score": _safe_float(feats.get("std_p_change", 0.0)),
            "cluster": cluster_id,
            "features": feats,
        }
        self.try_save_state()

    def get_signal(self) -> Optional[Dict[str, Any]]:
        if self._last is None:
            return None
        
        signal = dict(self._last)
        
        cluster_id = signal.get("cluster", 0)
        features = signal.get("features", {})
        
        html_parts = []
        html_parts.append('<div style="margin-bottom:12px;">')
        html_parts.append('<div style="font-weight:600;color:#8b5cf6;margin-bottom:8px;">🎯 市场状态聚类</div>')
        html_parts.append('<div style="color:#666;font-size:12px;margin-bottom:8px;">KMeans 聚类判断市场状态</div>')
        
        state_names = {0: "震荡", 1: "上涨", 2: "下跌"}
        state_colors = {"震荡": "#f59e0b", "上涨": "#22c55e", "下跌": "#ef4444"}
        state_name = state_names.get(cluster_id, "未知")
        state_color = state_colors.get(state_name, "#6b7280")
        
        html_parts.append('<div style="background:#f8f9fa;border-radius:12px;padding:16px;margin-bottom:12px;">')
        html_parts.append('<div style="display:flex;justify-content:space-between;align-items:center;">')
        html_parts.append('<div>')
        html_parts.append('<div style="font-size:14px;color:#666;">市场状态</div>')
        html_parts.append('<div style="font-size:24px;font-weight:700;color:' + state_color + ';">' + state_name + '</div>')
        html_parts.append('</div>')
        html_parts.append('<div style="text-align:right;">')
        html_parts.append('<div style="font-size:14px;color:#666;">聚类ID</div>')
        html_parts.append('<div style="font-size:20px;font-weight:600;">' + str(cluster_id) + '</div>')
        html_parts.append('</div>')
        html_parts.append('</div>')
        
        html_parts.append('<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;">')
        html_parts.append('<div style="background:#fff;padding:10px;border-radius:8px;text-align:center;">')
        html_parts.append('<div style="font-size:16px;font-weight:600;">' + '{:+.2f}%'.format(features.get("avg_p_change", 0)) + '</div>')
        html_parts.append('<div style="font-size:11px;color:#888;">平均涨跌</div>')
        html_parts.append('</div>')
        html_parts.append('<div style="background:#fff;padding:10px;border-radius:8px;text-align:center;">')
        html_parts.append('<div style="font-size:16px;font-weight:600;">' + '{:.2f}'.format(features.get("std_p_change", 0)) + '</div>')
        html_parts.append('<div style="font-size:11px;color:#888;">波动率</div>')
        html_parts.append('</div>')
        html_parts.append('</div>')
        
        html_parts.append('</div>')
        
        signal["html"] = ''.join(html_parts)
        return signal

    def update_params(self, params: Dict[str, Any]) -> None:
        n_clusters = int(params.get("n_clusters", self._n_clusters))
        halflife = float(params.get("halflife", self._halflife))
        self._n_clusters = n_clusters
        self._halflife = halflife
        self._model = cluster.KMeans(n_clusters=n_clusters, halflife=halflife)

    def _extract_model_state(self) -> Any:
        return self._model

    def _restore_model_state(self, state: Any) -> None:
        self._model = state


class RiverTickDriftADWIN(RiverStatePersistMixin):
    """ADWIN drift detection on average price change."""

    MODEL_STATE_KEY = "river_tick_drift_adwin_model"

    def __init__(self, min_n: int = 30):
        self._model = drift.ADWIN()
        self._min_n = min_n
        self._count = 0
        self._last = None
        self._persist_db = None
        self.try_load_state()

    def on_data(self, data: Any) -> None:
        feats = extract_tick_features(data)
        if not feats:
            self._last = None
            return
        value = _safe_float(feats.get("avg_p_change", 0.0))
        self._model.update(value)
        self._count += 1
        drifted = bool(self._model.drift_detected) if self._count >= self._min_n else False
        self._last = {
            "signal_type": "tick_drift_adwin",
            "score": 1.0 if drifted else 0.0,
            "mean": value,
            "drift": drifted,
            "features": feats,
        }
        self.try_save_state()

    def get_signal(self) -> Optional[Dict[str, Any]]:
        if self._last is None:
            return None
        signal = dict(self._last)
        drifted = signal.get("drift", False)
        features = signal.get("features", {})
        html_parts = []
        html_parts.append('<div style="margin-bottom:12px;">')
        html_parts.append('<div style="font-weight:600;color:#ec4899;margin-bottom:8px;">📉 漂移检测 (ADWIN)</div>')
        html_parts.append('<div style="color:#666;font-size:12px;margin-bottom:8px;">在线漂移检测，捕捉趋势突变</div>')
        drift_color = '#ef4444' if drifted else '#22c55e'
        drift_text = '⚠️ 检测到漂移' if drifted else '✓ 稳定'
        drift_bg = '#fef2f2' if drifted else '#f0fdf4'
        html_parts.append('<div style="background:' + drift_bg + ';border:1px solid ' + drift_color + ';padding:12px;border-radius:12px;margin-bottom:12px;">')
        html_parts.append('<div style="font-size:14px;font-weight:600;color:' + drift_color + ';">' + drift_text + '</div>')
        html_parts.append('</div>')
        html_parts.append('<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;">')
        html_parts.append('<div style="background:#fff;padding:10px;border-radius:8px;text-align:center;">')
        html_parts.append('<div style="font-size:16px;font-weight:600;">' + str(int(features.get("n", 0))) + '</div>')
        html_parts.append('<div style="font-size:11px;color:#888;">样本数</div>')
        html_parts.append('</div>')
        html_parts.append('<div style="background:#fff;padding:10px;border-radius:8px;text-align:center;">')
        html_parts.append('<div style="font-size:16px;font-weight:600;">' + '{:.2f}'.format(features.get("avg_p_change", 0)) + '</div>')
        html_parts.append('<div style="font-size:11px;color:#888;">平均变化</div>')
        html_parts.append('</div>')
        html_parts.append('</div>')
        html_parts.append('</div>')
        signal["html"] = ''.join(html_parts)
        return signal

    def update_params(self, params: Dict[str, Any]) -> None:
        self._min_n = int(params.get("min_n", self._min_n))


class RiverTickVolumePriceSpike:
    """Simple momentum/volume spike scorer (not a River model)."""

    def __init__(self, vol_z_threshold: float = 2.0):
        self._vol_z_threshold = float(vol_z_threshold)
        self._last = None

    def on_data(self, data: Any) -> None:
        feats = extract_tick_features(data)
        if not feats:
            self._last = None
            return
        vol_mean = _safe_float(feats.get("volume_mean", 0.0))
        vol_sum = _safe_float(feats.get("volume_sum", 0.0))
        price_std = _safe_float(feats.get("price_std", 0.0))
        score = 0.0
        if vol_mean > 0:
            score += min(3.0, vol_sum / max(vol_mean, 1.0) / 1000.0)
        score += min(3.0, price_std * 10.0)
        self._last = {
            "signal_type": "tick_volume_price_spike",
            "score": _safe_float(score),
            "features": feats,
        }

    def get_signal(self) -> Optional[Dict[str, Any]]:
        if self._last is None:
            return None
        
        signal = dict(self._last)
        
        score = signal.get("score", 0)
        features = signal.get("features", {})
        
        html_parts = []
        html_parts.append('<div style="margin-bottom:12px;">')
        html_parts.append('<div style="font-weight:600;color:#f97316;margin-bottom:8px;">⚡ 量价尖峰识别</div>')
        html_parts.append('<div style="color:#666;font-size:12px;margin-bottom:8px;">量价瞬时冲击评分，快速捕捉尖峰异动</div>')
        
        score_color = '#ef4444' if score > 2.0 else '#f59e0b' if score > 1.0 else '#22c55e'
        score_bg = '#fef2f2' if score > 2.0 else '#fffbeb' if score > 1.0 else '#f0fdf4'
        
        html_parts.append('<div style="background:' + score_bg + ';border:1px solid ' + score_color + ';padding:12px;border-radius:12px;margin-bottom:12px;">')
        html_parts.append('<div style="font-size:12px;color:#666;">尖峰分数</div>')
        html_parts.append('<div style="font-size:28px;font-weight:700;color:' + score_color + ';">' + '{:.3f}'.format(score) + '</div>')
        html_parts.append('</div>')
        
        html_parts.append('<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;">')
        html_parts.append('<div style="background:#fff;padding:10px;border-radius:8px;text-align:center;">')
        html_parts.append('<div style="font-size:16px;font-weight:600;">' + '{:.1f}'.format(features.get("volume_sum", 0)/1e6) + 'M</div>')
        html_parts.append('<div style="font-size:11px;color:#888;">成交量</div>')
        html_parts.append('</div>')
        html_parts.append('<div style="background:#fff;padding:10px;border-radius:8px;text-align:center;">')
        html_parts.append('<div style="font-size:16px;font-weight:600;">' + '{:.2f}'.format(features.get("price_std", 0)) + '</div>')
        html_parts.append('<div style="font-size:11px;color:#888;">价格波动</div>')
        html_parts.append('</div>')
        html_parts.append('</div>')
        
        html_parts.append('</div>')
        
        signal["html"] = ''.join(html_parts)
        return signal

    def update_params(self, params: Dict[str, Any]) -> None:
        self._vol_z_threshold = float(params.get("vol_z_threshold", self._vol_z_threshold))


class RiverTickMomentumTrend:
    """Momentum trend scorer using recent avg_p_change and std."""

    def __init__(self, trend_scale: float = 100.0):
        self._trend_scale = float(trend_scale)
        self._last = None

    def on_data(self, data: Any) -> None:
        feats = extract_tick_features(data)
        if not feats:
            self._last = None
            return
        avg = _safe_float(feats.get("avg_p_change", 0.0))
        std = _safe_float(feats.get("std_p_change", 0.0))
        score = abs(avg) * self._trend_scale / max(std, 1e-6)
        self._last = {
            "signal_type": "tick_momentum_trend",
            "score": _safe_float(score),
            "direction": "up" if avg >= 0 else "down",
            "features": feats,
        }

    def get_signal(self) -> Optional[Dict[str, Any]]:
        if self._last is None:
            return None
        
        signal = dict(self._last)
        
        score = signal.get("score", 0)
        direction = signal.get("direction", "unknown")
        
        html_parts = []
        html_parts.append('<div style="margin-bottom:12px;">')
        html_parts.append('<div style="font-weight:600;color:#06b6d4;margin-bottom:8px;">📈 动量趋势</div>')
        html_parts.append('<div style="color:#666;font-size:12px;margin-bottom:8px;">基于近期涨跌和波动率计算动量</div>')
        
        dir_colors = {"up": "#22c55e", "down": "#ef4444", "unknown": "#6b7280"}
        dir_names = {"up": "上涨", "down": "下跌", "unknown": "震荡"}
        
        dir_color = dir_colors.get(direction, "#6b7280")
        dir_name = dir_names.get(direction, "震荡")
        
        html_parts.append('<div style="background:#f8f9fa;border-radius:12px;padding:16px;margin-bottom:12px;">')
        html_parts.append('<div style="display:flex;justify-content:space-between;align-items:center;">')
        html_parts.append('<div>')
        html_parts.append('<div style="font-size:14px;color:#666;">趋势方向</div>')
        html_parts.append('<div style="font-size:24px;font-weight:700;color:' + dir_color + ';">' + dir_name + '</div>')
        html_parts.append('</div>')
        html_parts.append('<div style="text-align:right;">')
        html_parts.append('<div style="font-size:14px;color:#666;">动量分数</div>')
        html_parts.append('<div style="font-size:20px;font-weight:600;">' + '{:.2f}'.format(score) + '</div>')
        html_parts.append('</div>')
        html_parts.append('</div>')
        html_parts.append('</div>')
        
        signal["html"] = ''.join(html_parts)
        return signal
    """Detect potential trend reversal using avg_p_change sign flip."""

    def __init__(self, min_delta: float = 0.001):
        self._min_delta = float(min_delta)
        self._prev_avg = None
        self._last = None

    def on_data(self, data: Any) -> None:
        feats = extract_tick_features(data)
        if not feats:
            self._last = None
            return
        avg = _safe_float(feats.get("avg_p_change", 0.0))
        reversal = False
        if self._prev_avg is not None:
            if (self._prev_avg >= self._min_delta and avg <= -self._min_delta) or (
                self._prev_avg <= -self._min_delta and avg >= self._min_delta
            ):
                reversal = True
        self._prev_avg = avg
        self._last = {
            "signal_type": "tick_trend_reversal",
            "score": 1.0 if reversal else 0.0,
            "direction": "up" if avg >= 0 else "down",
            "features": feats,
        }

    def get_signal(self) -> Optional[Dict[str, Any]]:
        if self._last is None:
            return None
        signal = dict(self._last)
        reversal = signal.get("score", 0) > 0.5
        direction = signal.get("direction", "unknown")
        features = signal.get("features", {})
        html_parts = []
        html_parts.append('<div style="margin-bottom:12px;">')
        html_parts.append('<div style="font-weight:600;color:#f59e0b;margin-bottom:8px;">🔄 趋势反转检测</div>')
        html_parts.append('<div style="color:#666;font-size:12px;margin-bottom:8px;">检测平均涨跌sign翻转，识别潜在反转</div>')
        rev_color = '#ef4444' if reversal else '#22c55e'
        rev_text = '⚠️ 可能反转' if reversal else '✓ 趋势延续'
        rev_bg = '#fef2f2' if reversal else '#f0fdf4'
        html_parts.append('<div style="background:' + rev_bg + ';border:1px solid ' + rev_color + ';padding:12px;border-radius:12px;margin-bottom:12px;">')
        html_parts.append('<div style="font-size:14px;font-weight:600;color:' + rev_color + ';">' + rev_text + '</div>')
        html_parts.append('</div>')
        html_parts.append('<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;">')
        html_parts.append('<div style="background:#fff;padding:10px;border-radius:8px;text-align:center;">')
        html_parts.append('<div style="font-size:16px;font-weight:600;">' + direction + '</div>')
        html_parts.append('<div style="font-size:11px;color:#888;">当前方向</div>')
        html_parts.append('</div>')
        html_parts.append('<div style="background:#fff;padding:10px;border-radius:8px;text-align:center;">')
        html_parts.append('<div style="font-size:16px;font-weight:600;">' + '{:.2f}'.format(features.get("avg_p_change", 0)) + '</div>')
        html_parts.append('<div style="font-size:11px;color:#888;">平均变化</div>')
        html_parts.append('</div>')
        html_parts.append('</div>')
        html_parts.append('</div>')
        signal["html"] = ''.join(html_parts)
        return signal

    def update_params(self, params: Dict[str, Any]) -> None:
        self._min_delta = float(params.get("min_delta", self._min_delta))


class RiverTickVolatilityBurst:
    """Volatility burst detector based on std_p_change."""

    def __init__(self, burst_threshold: float = 0.02):
        self._burst_threshold = float(burst_threshold)
        self._last = None

    def on_data(self, data: Any) -> None:
        feats = extract_tick_features(data)
        if not feats:
            self._last = None
            return
        std = _safe_float(feats.get("std_p_change", 0.0))
        burst = std >= self._burst_threshold
        self._last = {
            "signal_type": "tick_volatility_burst",
            "score": _safe_float(std),
            "burst": burst,
            "features": feats,
        }

    def get_signal(self) -> Optional[Dict[str, Any]]:
        return self._last

    def update_params(self, params: Dict[str, Any]) -> None:
        self._burst_threshold = float(params.get("burst_threshold", self._burst_threshold))


class RiverTickBreadthConcentration:
    """Market breadth concentration based on up/down ratio."""

    def __init__(self, strong_threshold: float = 0.65):
        self._strong_threshold = float(strong_threshold)
        self._last = None

    def on_data(self, data: Any) -> None:
        feats = extract_tick_features(data)
        if not feats:
            self._last = None
            return
        up_ratio = _safe_float(feats.get("up_ratio", 0.0))
        down_ratio = _safe_float(feats.get("down_ratio", 0.0))
        concentration = max(up_ratio, down_ratio)
        direction = "up" if up_ratio >= down_ratio else "down"
        self._last = {
            "signal_type": "tick_breadth_concentration",
            "score": _safe_float(concentration),
            "direction": direction,
            "features": feats,
        }

    def get_signal(self) -> Optional[Dict[str, Any]]:
        return self._last

    def update_params(self, params: Dict[str, Any]) -> None:
        self._strong_threshold = float(params.get("strong_threshold", self._strong_threshold))


class RiverTickCapitalConcentration:
    """Capital concentration based on amount/volume dispersion."""

    def __init__(self, std_scale: float = 10.0):
        self._std_scale = float(std_scale)
        self._last = None

    def on_data(self, data: Any) -> None:
        feats = extract_tick_features(data)
        if not feats:
            self._last = None
            return
        amount_mean = _safe_float(feats.get("amount_mean", 0.0))
        amount_sum = _safe_float(feats.get("amount_sum", 0.0))
        volume_mean = _safe_float(feats.get("volume_mean", 0.0))
        score = 0.0
        if amount_mean > 0:
            score += min(3.0, amount_sum / max(amount_mean, 1.0) / 1000.0)
        score += min(3.0, volume_mean / 1e6)
        self._last = {
            "signal_type": "tick_capital_concentration",
            "score": _safe_float(score * self._std_scale / 10.0),
            "features": feats,
        }

    def get_signal(self) -> Optional[Dict[str, Any]]:
        return self._last

    def update_params(self, params: Dict[str, Any]) -> None:
        self._std_scale = float(params.get("std_scale", self._std_scale))
