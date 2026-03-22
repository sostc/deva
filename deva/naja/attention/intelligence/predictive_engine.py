"""
Module 7: Predictive Attention Engine - 预测注意力引擎

核心能力:
- 提前判断当前变化是否会扩散成"市场机会"
- 从"响应系统"升级到"预见系统"

方法:
- EMA 加速度检测
- 二阶差分
- 简单回归预测

输出:
- prediction_score ∈ [0, 1]: 扩散概率
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import deque
import time


@dataclass
class PredictionResult:
    """预测结果"""
    sector_id: str
    symbol: str
    prediction_score: float
    acceleration: float
    momentum: float
    confidence: float
    timestamp: float


class EMAAccelerator:
    """
    EMA 加速度检测器

    原理:
    - 一阶导数 (velocity): 价格变化的速度
    - 二阶导数 (acceleration): 速度变化的加速度
    - 当加速度 > 0 时，说明变化正在加速，可能扩散

    修复内容:
    - 将 update() 拆分为无副作用的 predict() 和有副作用的 apply_update()
    - predict() 只计算不修改状态
    - apply_update() 才会更新内部 EMA 状态
    """

    def __init__(
        self,
        fast_period: int = 5,
        slow_period: int = 20,
        acceleration_threshold: float = 0.1
    ):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.acceleration_threshold = acceleration_threshold

        self._ema_fast: Dict[str, float] = {}
        self._ema_slow: Dict[str, float] = {}
        self._prev_ema_fast: Dict[str, float] = {}
        self._velocity: Dict[str, float] = {}

    def predict(self, symbol: str, value: float, timestamp: float) -> Tuple[float, float, float]:
        """
        无副作用预测 - 只计算不修改状态

        Returns:
            (velocity, acceleration, prediction_score)
        """
        alpha_fast = 2.0 / (self.fast_period + 1)
        alpha_slow = 2.0 / (self.slow_period + 1)

        prev_fast = self._ema_fast.get(symbol, value)
        prev_slow = self._ema_slow.get(symbol, value)

        ema_fast = alpha_fast * value + (1 - alpha_fast) * prev_fast
        ema_slow = alpha_slow * value + (1 - alpha_slow) * prev_slow

        velocity = ema_fast - prev_fast
        prev_velocity = self._velocity.get(symbol, 0.0)
        acceleration = velocity - prev_velocity

        prediction_score = self._calc_prediction_score(acceleration, velocity)

        return velocity, acceleration, prediction_score

    def apply_update(self, symbol: str, value: float, timestamp: float):
        """
        有副作用的状态更新 - 实际更新内部 EMA 状态
        """
        alpha_fast = 2.0 / (self.fast_period + 1)
        alpha_slow = 2.0 / (self.slow_period + 1)

        prev_fast = self._ema_fast.get(symbol, value)
        prev_slow = self._ema_slow.get(symbol, value)

        self._ema_fast[symbol] = alpha_fast * value + (1 - alpha_fast) * prev_fast
        self._ema_slow[symbol] = alpha_slow * value + (1 - alpha_slow) * prev_slow

        velocity = self._ema_fast[symbol] - prev_fast
        self._velocity[symbol] = velocity

    def update(self, symbol: str, value: float, timestamp: float) -> Tuple[float, float, float]:
        """兼容旧接口：先预测再更新状态"""
        result = self.predict(symbol, value, timestamp)
        self.apply_update(symbol, value, timestamp)
        return result

    def _calc_prediction_score(self, acceleration: float, velocity: float) -> float:
        """计算预测分数"""
        acc_norm = np.clip(acceleration / (self.acceleration_threshold + 1e-6), -1, 1)
        vel_norm = np.clip(velocity / 0.5, -1, 1)

        score = 0.6 * (acc_norm + 1) / 2 + 0.4 * (vel_norm + 1) / 2

        return float(np.clip(score, 0, 1))


class SecondOrderDifferentiator:
    """
    二阶差分检测器

    原理:
    - 使用离散差分近似二阶导数
    - f''(x) ≈ f(x) - 2f(x-1) + f(x-2)
    - 二阶差分 > 0 表示下凹（加速上升）
    - 二阶差分 < 0 表示上凸（加速下降）

    修复内容:
    - 将 update() 拆分为无副作用的 predict() 和有副作用的 apply_update()
    """

    def __init__(
        self,
        window_size: int = 5,
        diff_threshold: float = 0.05
    ):
        self.window_size = window_size
        self.diff_threshold = diff_threshold

        self._history: Dict[str, deque] = {}

    def predict(self, symbol: str, value: float, timestamp: float) -> float:
        """
        无副作用预测 - 只计算不修改状态

        Returns:
            prediction_score ∈ [0, 1]
        """
        history = self._history.get(symbol, deque(maxlen=self.window_size))

        if len(history) < 3:
            return 0.5

        values = [v for v, _ in history]
        values.append(value)

        first_diff = values[-1] - values[-2]
        second_diff = first_diff - (values[-2] - values[-3])

        score = self._calc_score(second_diff, first_diff)

        return float(score)

    def apply_update(self, symbol: str, value: float, timestamp: float):
        """
        有副作用的状态更新 - 实际更新内部历史
        """
        if symbol not in self._history:
            self._history[symbol] = deque(maxlen=self.window_size)

        self._history[symbol].append((value, timestamp))

    def update(self, symbol: str, value: float, timestamp: float) -> float:
        """兼容旧接口：先预测再更新状态"""
        result = self.predict(symbol, value, timestamp)
        self.apply_update(symbol, value, timestamp)
        return result

    def _calc_score(self, second_diff: float, first_diff: float) -> float:
        """计算预测分数"""
        second_norm = np.clip(second_diff / self.diff_threshold, -2, 2)
        first_norm = np.clip(first_diff / 0.1, -2, 2)

        score = 0.5 * (second_norm + 2) / 2 + 0.5 * (first_norm + 2) / 2

        return float(np.clip(score, 0, 1))


class MomentumPredictor:
    """
    动量预测器

    原理:
    - 计算历史动量的趋势
    - 如果动量在增强，预测会继续
    - 使用线性回归检测趋势

    修复内容:
    - 将 update() 拆分为无副作用的 predict() 和有副作用的 apply_update()
    """

    def __init__(
        self,
        lookback_period: int = 10,
        trend_threshold: float = 0.1
    ):
        self.lookback_period = lookback_period
        self.trend_threshold = trend_threshold

        self._momentum_history: Dict[str, deque] = {}

    def predict(
        self,
        symbol: str,
        returns: float,
        volume_ratio: float,
        timestamp: float
    ) -> float:
        """
        无副作用预测 - 只计算不修改状态

        Returns:
            prediction_score ∈ [0, 1]
        """
        history = self._momentum_history.get(symbol, deque(maxlen=self.lookback_period))

        momentum = returns * 0.7 + (volume_ratio - 1) * 0.3 * 10

        if len(history) < 3:
            return 0.5

        momentums = list(history)
        momentums.append(momentum)

        trend = self._calc_trend(momentums)
        strength = self._calc_strength(momentums)

        score = self._combine_score(trend, strength)

        return float(score)

    def apply_update(
        self,
        symbol: str,
        returns: float,
        volume_ratio: float,
        timestamp: float
    ):
        """
        有副作用的状态更新 - 实际更新内部动量历史
        """
        if symbol not in self._momentum_history:
            self._momentum_history[symbol] = deque(maxlen=self.lookback_period)

        momentum = returns * 0.7 + (volume_ratio - 1) * 0.3 * 10
        self._momentum_history[symbol].append(momentum)

    def update(
        self,
        symbol: str,
        returns: float,
        volume_ratio: float,
        timestamp: float
    ) -> float:
        """兼容旧接口：先预测再更新状态"""
        result = self.predict(symbol, returns, volume_ratio, timestamp)
        self.apply_update(symbol, returns, volume_ratio, timestamp)
        return result
    
    def _calc_trend(self, values: List[float]) -> float:
        """计算趋势 (简单线性回归斜率)"""
        n = len(values)
        if n < 2:
            return 0.0
        
        x = np.arange(n)
        y = np.array(values)
        
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        
        numerator = np.sum((x - x_mean) * (y - y_mean))
        denominator = np.sum((x - x_mean) ** 2) + 1e-6
        
        slope = numerator / denominator
        
        return float(np.clip(slope / self.trend_threshold, -1, 1))
    
    def _calc_strength(self, values: List[float]) -> float:
        """计算动量强度"""
        if not values:
            return 0.0
        
        recent = np.mean(values[-3:])
        historical = np.mean(values[:-3]) if len(values) > 3 else 0
        
        if abs(historical) < 1e-6:
            return 0.0 if abs(recent) < 1e-6 else np.sign(recent)
        
        strength = (recent - historical) / (abs(historical) + 1e-6)
        
        return float(np.clip(strength, -1, 1))
    
    def _combine_score(self, trend: float, strength: float) -> float:
        """组合分数"""
        score = 0.6 * (trend + 1) / 2 + 0.4 * (strength + 1) / 2
        return float(np.clip(score, 0, 1))


class PredictiveAttentionEngine:
    """
    预测注意力引擎主类
    
    整合多种轻量预测方法:
    - EMA 加速度
    - 二阶差分
    - 动量预测
    
    输出:
    final_attention = α * 当前attention + β * prediction_score
    
    其中:
    - α + β = 1
    - α 初始值 0.7
    - β 初始值 0.3
    """
    
    def __init__(
        self,
        alpha: float = 0.7,
        beta: float = 0.3,
        enable_ema: bool = True,
        enable_diff: bool = True,
        enable_momentum: bool = True
    ):
        self.alpha = alpha
        self.beta = beta
        
        self.ema = EMAAccelerator() if enable_ema else None
        self.diff = SecondOrderDifferentiator() if enable_diff else None
        self.momentum = MomentumPredictor() if enable_momentum else None
        
        self._prediction_history: Dict[str, List[float]] = {}
        self._last_scores: Dict[str, float] = {}
        self._last_sector_scores: Dict[str, float] = {}
        
    def predict(
        self,
        symbol: str,
        current_attention: float,
        returns: Optional[float] = None,
        volume_ratio: Optional[float] = None,
        timestamp: Optional[float] = None
    ) -> Tuple[float, float]:
        """
        无副作用预测 - 只计算不修改状态

        Args:
            symbol: 股票代码
            current_attention: 当前注意力分数
            returns: 涨跌幅 (可选)
            volume_ratio: 量比 (可选)
            timestamp: 时间戳

        Returns:
            (prediction_score, final_attention)
        """
        timestamp = timestamp or time.time()

        prediction_score = self._calc_prediction_score(
            symbol, returns, volume_ratio, timestamp
        )

        final_attention = (
            self.alpha * current_attention +
            self.beta * prediction_score
        )

        self._last_scores[symbol] = prediction_score

        return prediction_score, final_attention

    def apply_updates(
        self,
        symbol: str,
        returns: Optional[float],
        volume_ratio: Optional[float],
        timestamp: float
    ):
        """
        批量更新内部状态（在所有预测完成后调用）

        这样可以确保:
        1. 同一 snapshot 的多次 predict() 返回相同结果
        2. 状态只在 batch 处理完后才更新
        """
        if self.ema and returns is not None:
            self.ema.apply_update(symbol, returns, timestamp)

        if self.diff and returns is not None:
            self.diff.apply_update(symbol, returns, timestamp)

        if self.momentum and returns is not None and volume_ratio is not None:
            self.momentum.apply_update(symbol, returns, volume_ratio, timestamp)

    def batch_predict(
        self,
        symbols: np.ndarray,
        current_attention: Dict[str, float],
        returns: np.ndarray,
        volumes: np.ndarray,
        timestamps: np.ndarray
    ) -> Dict[str, Tuple[float, float]]:
        """
        批量预测（无副作用版本）

        预测完成后需要调用 apply_batch_updates() 来更新状态

        Returns:
            {symbol: (prediction_score, final_attention)}
        """
        results = {}

        base_volumes = np.mean(volumes) if len(volumes) > 0 else 1.0
        base_volumes = max(base_volumes, 1e-6)

        for i, symbol in enumerate(symbols):
            symbol_str = str(symbol)

            ret = float(returns[i]) if i < len(returns) else 0.0
            vol_ratio = float(volumes[i] / base_volumes) if i < len(volumes) else 1.0
            ts = float(timestamps[i]) if i < len(timestamps) else time.time()

            current = current_attention.get(symbol_str, 0.0)

            pred_score, final_att = self.predict(
                symbol_str, current, ret, vol_ratio, ts
            )

            results[symbol_str] = (pred_score, final_att)

        return results

    def apply_batch_updates(
        self,
        symbols: np.ndarray,
        returns: np.ndarray,
        volumes: np.ndarray,
        timestamps: np.ndarray
    ):
        """
        批量更新内部状态（在 batch_predict 之后调用）
        """
        base_volumes = np.mean(volumes) if len(volumes) > 0 else 1.0
        base_volumes = max(base_volumes, 1e-6)

        for i, symbol in enumerate(symbols):
            symbol_str = str(symbol)

            ret = float(returns[i]) if i < len(returns) else 0.0
            vol_ratio = float(volumes[i] / base_volumes) if i < len(volumes) else 1.0
            ts = float(timestamps[i]) if i < len(timestamps) else time.time()

            self.apply_updates(symbol_str, ret, vol_ratio, ts)

    def _calc_prediction_score(
        self,
        symbol: str,
        returns: Optional[float],
        volume_ratio: Optional[float],
        timestamp: float
    ) -> float:
        """计算综合预测分数（无副作用版本）"""
        scores = []
        weights = []

        if self.ema and returns is not None:
            _, _, ema_score = self.ema.predict(symbol, returns, timestamp)
            scores.append(ema_score)
            weights.append(0.3)

        if self.diff and returns is not None:
            diff_score = self.diff.predict(symbol, returns, timestamp)
            scores.append(diff_score)
            weights.append(0.3)

        if self.momentum and returns is not None and volume_ratio is not None:
            momentum_score = self.momentum.predict(
                symbol, returns, volume_ratio, timestamp
            )
            scores.append(momentum_score)
            weights.append(0.4)

        if not scores:
            return 0.5

        weights = np.array(weights)
        weights = weights / weights.sum()

        final_score = np.dot(np.array(scores), weights)

        return float(np.clip(final_score, 0, 1))
    
    def batch_predict(
        self,
        symbols: np.ndarray,
        current_attention: Dict[str, float],
        returns: np.ndarray,
        volumes: np.ndarray,
        timestamps: np.ndarray
    ) -> Dict[str, Tuple[float, float]]:
        """
        批量预测
        
        Returns:
            {symbol: (prediction_score, final_attention)}
        """
        results = {}
        
        base_volumes = np.mean(volumes) if len(volumes) > 0 else 1.0
        base_volumes = max(base_volumes, 1e-6)
        
        for i, symbol in enumerate(symbols):
            symbol_str = str(symbol)
            
            ret = float(returns[i]) if i < len(returns) else 0.0
            vol_ratio = float(volumes[i] / base_volumes) if i < len(volumes) else 1.0
            ts = float(timestamps[i]) if i < len(timestamps) else time.time()
            
            current = current_attention.get(symbol_str, 0.0)
            
            pred_score, final_att = self.predict(
                symbol_str, current, ret, vol_ratio, ts
            )
            
            results[symbol_str] = (pred_score, final_att)
        
        return results
    
    def get_prediction(self, symbol: str) -> float:
        """获取上次预测分数"""
        return self._last_scores.get(symbol, 0.5)
    
    def get_predictions_top_k(self, k: int = 20) -> List[Tuple[str, float]]:
        """获取预测分数最高的 K 个 symbol"""
        sorted_items = sorted(
            self._last_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_items[:k]

    def predict_sector(
        self,
        sector_id: str,
        sector_attention: float,
        sector_returns: float,
        sector_volume_ratio: float,
        timestamp: Optional[float] = None
    ) -> float:
        """执行板块预测"""
        timestamp = timestamp or time.time()

        scores = []
        weights = []

        if self.ema and sector_returns is not None:
            _, _, ema_score = self.ema.update(f"sector_{sector_id}", sector_returns, timestamp)
            scores.append(ema_score)
            weights.append(0.3)

        if self.diff and sector_returns is not None:
            diff_score = self.diff.update(f"sector_{sector_id}", sector_returns, timestamp)
            scores.append(diff_score)
            weights.append(0.3)

        if self.momentum and sector_returns is not None and sector_volume_ratio is not None:
            momentum_score = self.momentum.update(
                f"sector_{sector_id}", sector_returns, sector_volume_ratio, timestamp
            )
            scores.append(momentum_score)
            weights.append(0.4)

        if not scores:
            prediction_score = 0.5
        else:
            weights = np.array(weights)
            weights = weights / weights.sum()
            prediction_score = float(np.clip(np.dot(np.array(scores), weights), 0, 1))

        self._last_sector_scores[sector_id] = prediction_score
        return prediction_score

    def batch_predict_sectors(
        self,
        sector_attentions: Dict[str, float],
        sector_returns: Dict[str, float],
        sector_volume_ratios: Dict[str, float],
        timestamp: Optional[float] = None
    ) -> Dict[str, float]:
        """批量预测板块"""
        timestamp = timestamp or time.time()
        results = {}

        for sector_id in sector_attentions.keys():
            attention = sector_attentions.get(sector_id, 0.0)
            returns = sector_returns.get(sector_id, 0.0)
            vol_ratio = sector_volume_ratios.get(sector_id, 1.0)

            pred_score = self.predict_sector(
                sector_id, attention, returns, vol_ratio, timestamp
            )
            results[sector_id] = pred_score

        return results

    def get_sector_prediction(self, sector_id: str) -> float:
        """获取板块预测分数"""
        return self._last_sector_scores.get(sector_id, 0.5)

    def get_sector_predictions_top_k(self, k: int = 5) -> List[Tuple[str, float]]:
        """获取预测分数最高的 K 个板块"""
        sorted_items = sorted(
            self._last_sector_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_items[:k]

    def update_weights(self, alpha: float, beta: float):
        """更新组合权重"""
        if alpha + beta > 0:
            self.alpha = alpha / (alpha + beta)
            self.beta = beta / (alpha + beta)
    
    def reset(self):
        """重置引擎"""
        self._prediction_history.clear()
        self._last_scores.clear()
        if self.ema:
            self.ema.__init__()
        if self.diff:
            self.diff.__init__()
        if self.momentum:
            self.momentum.__init__()
