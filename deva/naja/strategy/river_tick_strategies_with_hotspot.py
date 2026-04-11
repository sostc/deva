"""
River-based tick strategies with Hotspot awareness

在原有策略基础上增加热点感知能力
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import math

try:
    import pandas as pd
except Exception:
    pd = None

from river import anomaly, cluster, drift

from .hotspot_aware_strategies import HotspotAwareMixin


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


class RiverTickAnomalyHSTWithHotspot(HotspotAwareMixin):
    """
    带热点感知的 HalfSpaceTrees 异常检测策略

    优化点：
    1. 市场平静时降低检测频率
    2. 只关注高热点股票的异常
    """

    def __init__(self, n_trees: int = 25, height: int = 15, window_size: int = 250):
        HotspotAwareMixin.__init__(self)

        self._model = anomaly.HalfSpaceTrees(n_trees=n_trees, height=height, window_size=window_size)
        self._last = None
        self._frame_count = 0
        self._skip_threshold = 0.2

    def on_data(self, data: Any, context: Optional[Dict] = None) -> None:
        """
        处理数据

        Args:
            data: DataFrame数据
            context: 热点上下文（由调度中心传入）
        """
        self._frame_count += 1

        global_hotspot = 0.5
        if context and 'global_hotspot' in context:
            global_hotspot = context['global_hotspot']
        else:
            global_hotspot = self.get_global_hotspot()

        if global_hotspot < self._skip_threshold:
            if self._frame_count % 5 != 0:
                return

        feats = self._extract_features(data)
        if not feats:
            self._last = None
            return

        score = self._model.score_one(feats)
        self._model.learn_one(feats)

        adjusted_score = score * (0.8 + global_hotspot * 0.4)

        self._last = {
            "signal_type": "tick_anomaly_hst_hotspot",
            "score": _safe_float(adjusted_score),
            "raw_score": _safe_float(score),
            "global_hotspot": global_hotspot,
            "features": feats,
        }

    def _extract_features(self, data: Any) -> Dict[str, float]:
        """提取特征"""
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

        if self._use_hotspot:
            features["global_hotspot"] = self.get_global_hotspot()

        return features

    def get_signal(self) -> Optional[Dict[str, Any]]:
        if self._last is None:
            return None

        signal = dict(self._last)

        score = signal.get("score", 0)
        global_hotspot = signal.get("global_hotspot", 0.5)
        features = signal.get("features", {})

        html_parts = []
        html_parts.append('<div style="margin-bottom:12px;">')
        html_parts.append('<div style="font-weight:600;color:#2563eb;margin-bottom:8px;">🧪 市场异常检测 (HST + Hotspot)</div>')

        hotspot_color = '#ef4444' if global_hotspot > 0.7 else '#f59e0b' if global_hotspot > 0.4 else '#22c55e'
        html_parts.append(f'<div style="font-size:12px;color:#666;margin-bottom:8px;">全局热点: <span style="color:{hotspot_color};font-weight:600;">{global_hotspot:.2f}</span></div>')

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
        n_trees = int(params.get("n_trees", 25))
        height = int(params.get("height", 15))
        window_size = int(params.get("window_size", 250))
        self._model = anomaly.HalfSpaceTrees(n_trees=n_trees, height=height, window_size=window_size)


class RiverTickVolumePriceSpikeWithHotspot(HotspotAwareMixin):
    """
    带热点感知的量价尖峰识别策略

    优化点：
    1. 只关注高热点股票的量价异动
    2. 根据全局热点调整敏感度
    """

    def __init__(self, vol_z_threshold: float = 2.0):
        HotspotAwareMixin.__init__(self)

        self._vol_z_threshold = float(vol_z_threshold)
        self._last = None

    def on_data(self, data: Any, context: Optional[Dict] = None) -> None:
        """处理数据"""
        if pd is None:
            return

        df = None
        if isinstance(data, dict) and "data" in data:
            df = data["data"]
        elif isinstance(data, pd.DataFrame):
            df = data

        if df is None or df.empty:
            self._last = None
            return

        global_hotspot = 0.5
        if context and 'global_hotspot' in context:
            global_hotspot = context['global_hotspot']
        else:
            global_hotspot = self.get_global_hotspot()

        feats = self._extract_features(df)
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

        adjusted_score = score * (0.5 + global_hotspot)

        self._last = {
            "signal_type": "tick_volume_price_spike_hotspot",
            "score": _safe_float(adjusted_score),
            "raw_score": _safe_float(score),
            "global_hotspot": global_hotspot,
            "features": feats,
        }

    def _extract_features(self, df: pd.DataFrame) -> Dict[str, float]:
        """提取特征"""
        features: Dict[str, float] = {}

        if "volume" in df.columns:
            vol = pd.to_numeric(df["volume"], errors="coerce")
            features["volume_sum"] = _safe_float(vol.sum())
            features["volume_mean"] = _safe_float(vol.mean())

        if "now" in df.columns:
            now = pd.to_numeric(df["now"], errors="coerce")
            features["price_mean"] = _safe_float(now.mean())
            features["price_std"] = _safe_float(now.std())

        features["rows"] = _safe_float(len(df))

        return features

    def get_signal(self) -> Optional[Dict[str, Any]]:
        if self._last is None:
            return None

        signal = dict(self._last)

        score = signal.get("score", 0)
        global_hotspot = signal.get("global_hotspot", 0.5)
        features = signal.get("features", {})

        html_parts = []
        html_parts.append('<div style="margin-bottom:12px;">')
        html_parts.append('<div style="font-weight:600;color:#f97316;margin-bottom:8px;">⚡ 量价尖峰识别 (Hotspot)</div>')

        hotspot_color = '#ef4444' if global_hotspot > 0.7 else '#f59e0b' if global_hotspot > 0.4 else '#22c55e'
        html_parts.append(f'<div style="font-size:12px;color:#666;margin-bottom:8px;">全局热点: <span style="color:{hotspot_color};font-weight:600;">{global_hotspot:.2f}</span></div>')

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


HOTSPOT_STRATEGIES = {
    "tick_anomaly_hst_hotspot": RiverTickAnomalyHSTWithHotspot,
    "tick_volume_price_spike_hotspot": RiverTickVolumePriceSpikeWithHotspot,
}


def get_hotspot_strategy(name: str, **kwargs):
    """获取热点感知策略实例"""
    cls = HOTSPOT_STRATEGIES.get(name)
    if cls:
        return cls(**kwargs)
    return None