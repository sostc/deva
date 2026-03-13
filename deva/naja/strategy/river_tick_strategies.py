"""
River-based tick strategies for realtime_tick_5s DataFrame input.

These strategies focus on turning tick snapshots into signals with score
so Radar + Memory can consume them.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import math

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional in runtime
    pd = None

from river import anomaly, cluster, drift


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


class RiverTickAnomalyHST:
    """HalfSpaceTrees anomaly score on aggregated tick features."""

    def __init__(self, n_trees: int = 25, height: int = 15, window_size: int = 250):
        self._model = anomaly.HalfSpaceTrees(n_trees=n_trees, height=height, window_size=window_size)
        self._last = None

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

    def get_signal(self) -> Optional[Dict[str, Any]]:
        return self._last

    def update_params(self, params: Dict[str, Any]) -> None:
        # Rebuild model if core params change
        n_trees = int(params.get("n_trees", 25))
        height = int(params.get("height", 15))
        window_size = int(params.get("window_size", 250))
        self._model = anomaly.HalfSpaceTrees(n_trees=n_trees, height=height, window_size=window_size)


class RiverTickRegimeCluster:
    """KMeans clustering over market state features."""

    def __init__(self, n_clusters: int = 3, halflife: float = 0.6):
        self._model = cluster.KMeans(n_clusters=n_clusters, halflife=halflife)
        self._last = None

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

    def get_signal(self) -> Optional[Dict[str, Any]]:
        return self._last

    def update_params(self, params: Dict[str, Any]) -> None:
        n_clusters = int(params.get("n_clusters", 3))
        halflife = float(params.get("halflife", 0.6))
        self._model = cluster.KMeans(n_clusters=n_clusters, halflife=halflife)


class RiverTickDriftADWIN:
    """ADWIN drift detection on average price change."""

    def __init__(self, min_n: int = 30):
        self._model = drift.ADWIN()
        self._min_n = int(min_n)
        self._count = 0
        self._last = None

    def on_data(self, data: Any) -> None:
        feats = extract_tick_features(data)
        if not feats:
            self._last = None
            return
        value = _safe_float(feats.get("avg_p_change", 0.0))
        self._model.update(value)
        self._count += 1
        drifted = bool(self._model.change_detected) if self._count >= self._min_n else False
        self._last = {
            "signal_type": "tick_drift_adwin",
            "score": 1.0 if drifted else 0.0,
            "mean": value,
            "drift": drifted,
            "features": feats,
        }

    def get_signal(self) -> Optional[Dict[str, Any]]:
        return self._last

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
        return self._last

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
        return self._last

    def update_params(self, params: Dict[str, Any]) -> None:
        self._trend_scale = float(params.get("trend_scale", self._trend_scale))


class RiverTickTrendReversal:
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
        return self._last

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
