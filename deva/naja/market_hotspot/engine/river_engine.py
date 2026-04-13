"""
River 引擎 - 基础层/常态层

基于 River 库的在线学习引擎，提供：
- 实时统计量计算（均值、方差、EMA）
- 在线异常检测（Half-Space Trees）
- O(1)/tick 性能保证
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from collections import deque, defaultdict
import time

try:
    from river import stats
    from river import anomaly
    RIVER_AVAILABLE = True
except ImportError:
    RIVER_AVAILABLE = False
    print("[NewsMind] Warning: river not installed, using fallback implementations")

from .models import AnomalyLevel, AnomalySignal


class _FallbackStats:
    """备用统计量实现"""
    
    class Mean:
        def __init__(self):
            self._count = 0
            self._mean = 0.0
        
        def update(self, x):
            self._count += 1
            self._mean += (x - self._mean) / self._count
        
        def get(self):
            return self._mean if self._count > 0 else None
    
    class Var:
        def __init__(self):
            self._count = 0
            self._mean = 0.0
            self._m2 = 0.0
        
        def update(self, x):
            self._count += 1
            delta = x - self._mean
            self._mean += delta / self._count
            delta2 = x - self._mean
            self._m2 += delta * delta2
        
        def get(self):
            if self._count < 2:
                return None
            return self._m2 / (self._count - 1)
    
    class RollingMean:
        def __init__(self, window_size=20):
            self._window = deque(maxlen=window_size)
        
        def update(self, x):
            self._window.append(x)
        
        def get(self):
            if len(self._window) == 0:
                return None
            return np.mean(self._window)
    
    class RollingVar:
        def __init__(self, window_size=20):
            self._window = deque(maxlen=window_size)
        
        def update(self, x):
            self._window.append(x)
        
        def get(self):
            if len(self._window) < 2:
                return None
            return np.var(self._window, ddof=1)


class _FallbackAnomaly:
    """备用异常检测实现"""
    
    class GaussianScorer:
        def __init__(self):
            self._mean = 0.0
            self._var = 0.0
            self._count = 0
        
        def update(self, x):
            self._count += 1
            delta = x - self._mean
            self._mean += delta / self._count
            delta2 = x - self._mean
            self._var += delta * delta2
        
        def score_one(self, x):
            if self._count < 2:
                return 0.0
            std = np.sqrt(self._var / (self._count - 1))
            if std == 0:
                return 0.0
            return abs(x - self._mean) / std


class RiverEngine:
    """
    River 引擎 - 基础层/常态层
    
    功能:
    - 流式均值/方差
    - 在线回归
    - 残差检测
    - 输出 anomaly_score
    """
    
    def __init__(
        self,
        max_symbols: int = 5000,
        history_window: int = 20,
        anomaly_threshold_weak: float = 2.0,
        anomaly_threshold_strong: float = 3.5
    ):
        self.max_symbols = max_symbols
        self.history_window = history_window
        self.anomaly_threshold_weak = anomaly_threshold_weak
        self.anomaly_threshold_strong = anomaly_threshold_strong
        
        # Symbol 映射
        self._symbol_to_idx: Dict[str, int] = {}
        
        # 选择使用的统计量类
        if RIVER_AVAILABLE:
            self._MeanClass = stats.Mean
            self._VarClass = stats.Var
            self._RollingMeanClass = stats.RollingMean
            self._RollingVarClass = stats.RollingVar
            self._GaussianScorerClass = anomaly.GaussianScorer
        else:
            self._MeanClass = _FallbackStats.Mean
            self._VarClass = _FallbackStats.Var
            self._RollingMeanClass = _FallbackStats.RollingMean
            self._RollingVarClass = _FallbackStats.RollingVar
            self._GaussianScorerClass = _FallbackAnomaly.GaussianScorer
        
        # 统计量 (每个symbol独立)
        self._mean_estimators: Dict = {}
        self._var_estimators: Dict = {}
        self._anomaly_detectors: Dict = {}
        
        # 历史数据缓存
        self._price_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=history_window))
        self._volume_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=history_window))
        
        # 异常分数缓存
        self._anomaly_scores = np.zeros(max_symbols)
        self._last_update = np.zeros(max_symbols)
        
        # 统计
        self._processed_count = 0
        self._anomaly_count = 0
    
    def register_symbol(self, symbol: str) -> bool:
        """注册个股"""
        if symbol in self._symbol_to_idx:
            return True
        
        if len(self._symbol_to_idx) >= self.max_symbols:
            return False
        
        idx = len(self._symbol_to_idx)
        self._symbol_to_idx[symbol] = idx
        
        # 初始化统计量
        self._mean_estimators[symbol] = self._MeanClass()
        self._var_estimators[symbol] = self._VarClass()
        self._anomaly_detectors[symbol] = self._GaussianScorerClass()
        
        return True
    
    def process_tick(
        self,
        symbol: str,
        price: float,
        volume: float,
        timestamp: float
    ) -> Optional[AnomalySignal]:
        """
        处理单个 tick 数据
        
        返回:
            AnomalySignal 如果检测到异常，否则 None
        """
        if symbol not in self._symbol_to_idx:
            return None
        
        idx = self._symbol_to_idx[symbol]
        
        # 更新历史
        self._price_history[symbol].append(price)
        self._volume_history[symbol].append(volume)
        
        # 提取特征
        features = self._extract_features(symbol, price, volume)
        
        # 更新 River 统计量
        mean_est = self._mean_estimators[symbol]
        var_est = self._var_estimators[symbol]
        anomaly_det = self._anomaly_detectors[symbol]
        
        # 计算预测值 (使用均值作为简单预测)
        predicted = mean_est.get() if mean_est.get() is not None else price
        
        # 更新统计量
        mean_est.update(price)
        var_est.update(price)
        
        # 计算残差
        residual = abs(price - predicted)
        
        # 异常检测 - 使用基于标准差的方法
        std = np.sqrt(var_est.get()) if var_est.get() is not None else 0
        if std > 0:
            anomaly_score = residual / std
        else:
            anomaly_score = 0.0
        
        self._anomaly_scores[idx] = anomaly_score
        self._last_update[idx] = timestamp
        self._processed_count += 1
        
        # 判断异常等级
        anomaly_level = self._classify_anomaly(anomaly_score)
        
        if anomaly_level != AnomalyLevel.NORMAL:
            self._anomaly_count += 1
            return AnomalySignal(
                symbol=symbol,
                anomaly_score=anomaly_score,
                anomaly_level=anomaly_level,
                features=features,
                timestamp=timestamp
            )
        
        return None
    
    def _extract_features(
        self,
        symbol: str,
        price: float,
        volume: float
    ) -> Dict[str, float]:
        """提取特征"""
        features = {
            'price': price,
            'volume': volume,
            'price_change': 0.0,
            'volume_ratio': 1.0,
            'volatility': 0.0
        }

        prices = list(self._price_history[symbol])
        volumes = list(self._volume_history[symbol])

        if len(prices) >= 2:
            prev_price = prices[-2]
            if prev_price > 0.01:  # 避免除零或极小值
                features['price_change'] = (price - prev_price) / prev_price * 100
                # 限制范围，防止异常值
                features['price_change'] = max(-50.0, min(50.0, features['price_change']))

        if len(volumes) >= 2:
            avg_volume = np.mean(volumes[:-1]) if len(volumes) > 1 else volumes[0]
            if avg_volume > 0:
                features['volume_ratio'] = volume / avg_volume
                # 限制范围
                features['volume_ratio'] = max(0.01, min(100.0, features['volume_ratio']))

        if len(prices) >= 5:
            price_window = prices[-5:]
            mean_price = np.mean(price_window)
            if mean_price > 0.01:
                volatility = np.std(price_window) / mean_price * 100
                features['volatility'] = max(0.0, min(50.0, volatility))

        return features
    
    def _classify_anomaly(self, score: float) -> AnomalyLevel:
        """分类异常等级"""
        if score >= self.anomaly_threshold_strong:
            return AnomalyLevel.STRONG
        elif score >= self.anomaly_threshold_weak:
            return AnomalyLevel.WEAK
        else:
            return AnomalyLevel.NORMAL
    
    def get_anomaly_score(self, symbol: str) -> float:
        """获取个股的异常分数"""
        idx = self._symbol_to_idx.get(symbol)
        if idx is None:
            return 0.0
        return float(self._anomaly_scores[idx])
    
    def get_top_anomalies(self, n: int = 20, min_score: float = 0.0) -> List[Tuple[str, float]]:
        """获取异常分数最高的个股"""
        anomalies = [
            (symbol, float(self._anomaly_scores[idx]))
            for symbol, idx in self._symbol_to_idx.items()
            if self._anomaly_scores[idx] >= min_score
        ]
        anomalies.sort(key=lambda x: x[1], reverse=True)
        return anomalies[:n]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'processed_count': self._processed_count,
            'anomaly_count': self._anomaly_count,
            'anomaly_ratio': self._anomaly_count / max(self._processed_count, 1),
            'active_symbols': len(self._symbol_to_idx)
        }
    
    def reset(self):
        """重置引擎"""
        self._symbol_to_idx.clear()
        self._mean_estimators.clear()
        self._var_estimators.clear()
        self._anomaly_detectors.clear()
        self._price_history.clear()
        self._volume_history.clear()
        self._anomaly_scores.fill(0.0)
        self._last_update.fill(0.0)
        self._processed_count = 0
        self._anomaly_count = 0


