"""
Global Attention Module - 全市场注意力计算

功能:
- 从全市场 snapshot 中提取市场状态
- 输出连续值 global_attention ∈ [0, +∞)
- 用于控制整体策略激进程度和数据源频率基线

性能目标:
- O(n) 复杂度，n 为股票数量
- 单次处理延迟 < 10ms
- 向量化计算，无 Python 层循环
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque
import time
import logging

log = logging.getLogger(__name__)


@dataclass
class MarketSnapshot:
    """市场快照数据结构"""
    symbols: np.ndarray  # 股票代码数组
    returns: np.ndarray  # 涨跌幅 (%)
    volumes: np.ndarray  # 成交量
    prices: np.ndarray   # 当前价格
    sector_ids: np.ndarray  # 板块ID映射
    timestamp: float


class GlobalAttentionEngine:
    """
    全市场注意力引擎
    
    计算逻辑:
    1. 市场波动率 (30%)
    2. 成交量异常 (30%)
    3. 涨跌分布 (20%)
    4. 趋势强度 (20%)
    """
    
    def __init__(
        self,
        history_window: int = 20,
        volatility_weight: float = 0.30,
        volume_weight: float = 0.30,
        distribution_weight: float = 0.20,
        trend_weight: float = 0.20,
    ):
        self.history_window = history_window
        self.weights = np.array([
            volatility_weight,
            volume_weight,
            distribution_weight,
            trend_weight
        ])
        
        # 预分配历史缓冲区 (ring buffer)
        self._history_buffer: deque = deque(maxlen=history_window)
        self._returns_history: Optional[np.ndarray] = None
        self._volume_history: Optional[np.ndarray] = None
        
        # 缓存上次计算结果
        self._last_attention: float = 0.0
        self._last_calc_time: float = 0.0
        
    def update(self, snapshot: MarketSnapshot) -> float:
        """
        更新并计算全局注意力分数

        Args:
            snapshot: 市场快照数据

        Returns:
            global_attention: 全局注意力分数 ∈ [0, +∞)
        """
        start_time = time.time()

        # 提取基础数据
        returns = snapshot.returns
        volumes = snapshot.volumes

        # 检查数据有效性
        if len(returns) == 0:
            return 0.0

        # 清理异常值
        returns = np.nan_to_num(returns, nan=0.0, posinf=50.0, neginf=-50.0)
        returns = np.clip(returns, -50.0, 50.0)
        volumes = np.nan_to_num(volumes, nan=0.0, posinf=1e15, neginf=0.0)
        volumes = np.clip(volumes, 0, 1e15)

        try:
            # 计算四个维度
            volatility_score = self._calc_volatility(returns)
            volume_score = self._calc_volume_anomaly(volumes)
            distribution_score = self._calc_distribution(returns)
            trend_score = self._calc_trend_strength(returns)

            # 加权求和
            scores = np.array([
                volatility_score,
                volume_score,
                distribution_score,
                trend_score
            ])

            attention = float(np.dot(scores, self.weights))
            attention = max(0.0, min(1.0, attention))  # 限制范围
        except Exception as e:
            import traceback
            log.error(f"GlobalAttention 计算失败: {e}")
            log.error(traceback.format_exc())
            attention = 0.0

        # 更新历史
        self._history_buffer.append({
            'returns': returns.copy(),
            'volumes': volumes.copy(),
            'attention': attention,
            'timestamp': snapshot.timestamp
        })

        self._last_attention = attention
        self._last_calc_time = time.time()

        return attention
    
    def _calc_volatility(self, returns: np.ndarray) -> float:
        """
        计算市场波动率分数
        使用标准差，归一化到 [0, 1]
        """
        if len(returns) == 0:
            return 0.0
        
        # 使用 MAD (Median Absolute Deviation) 更稳健
        median = np.median(returns)
        mad = np.median(np.abs(returns - median))
        
        # 转换为标准差估计 (MAD * 1.4826 ≈ STD for normal distribution)
        volatility = mad * 1.4826
        
        # 归一化: 假设正常市场波动率 < 5%
        score = min(volatility / 5.0, 1.0)
        
        return score
    
    def _calc_volume_anomaly(self, volumes: np.ndarray) -> float:
        """
        计算成交量异常分数
        对比历史平均成交量
        """
        if len(volumes) == 0 or len(self._history_buffer) < 5:
            return 0.0
        
        # 获取历史成交量均值
        recent_volumes = np.array([
            np.mean(h['volumes']) for h in list(self._history_buffer)[-5:]
        ])
        
        historical_mean = np.mean(recent_volumes)
        if historical_mean == 0:
            return 0.0
        
        current_mean = np.mean(volumes)
        
        # 计算异常程度
        ratio = current_mean / historical_mean
        
        # 归一化: ratio = 1 时 score = 0, ratio >= 3 时 score = 1
        if ratio >= 3.0:
            score = 1.0
        elif ratio <= 0.5:
            score = 0.0
        else:
            score = (ratio - 0.5) / 2.5
        
        return score
    
    def _calc_distribution(self, returns: np.ndarray) -> float:
        """
        计算涨跌分布分数
        衡量市场分歧程度
        """
        if len(returns) == 0:
            return 0.0
        
        # 计算上涨、下跌、平盘比例
        up_ratio = np.sum(returns > 0.5) / len(returns)
        down_ratio = np.sum(returns < -0.5) / len(returns)
        flat_ratio = 1.0 - up_ratio - down_ratio
        
        # 使用熵衡量分布的均匀程度
        # 越均匀 (分歧越大) -> 分数越高
        probs = np.array([up_ratio, down_ratio, flat_ratio])
        probs = probs[probs > 0.001]  # 避免 log(0) 和极小值
        
        if len(probs) <= 1:
            return 0.0
        
        try:
            # 限制 log 的输入范围，防止数值溢出
            log_probs = np.log2(np.clip(probs, 0.001, 1.0))
            entropy = -np.sum(probs * log_probs)
            max_entropy = np.log2(3)  # 三分类的最大熵
            score = float(np.clip(entropy / max_entropy, 0.0, 1.0))
        except (OverflowError, ValueError, FloatingPointError):
            score = 0.0
        
        return score
    
    def _calc_trend_strength(self, returns: np.ndarray) -> float:
        """
        计算趋势强度分数
        使用所有股票的平均涨跌幅绝对值
        """
        if len(returns) == 0:
            return 0.0
        
        mean_return = np.mean(np.abs(returns))
        
        # 归一化: 假设正常趋势强度 < 2%
        score = min(mean_return / 2.0, 1.0)
        
        return score
    
    def get_market_state(self) -> Dict:
        """获取当前市场状态摘要"""
        if not self._history_buffer:
            return {
                'attention': 0.0,
                'trend': 'unknown',
                'volatility': 0.0
            }
        
        recent = list(self._history_buffer)[-5:]
        avg_attention = np.mean([h['attention'] for h in recent])
        
        # 判断趋势
        if avg_attention > 0.7:
            trend = 'high_activity'
        elif avg_attention > 0.4:
            trend = 'moderate'
        else:
            trend = 'quiet'
        
        return {
            'attention': self._last_attention,
            'avg_attention': avg_attention,
            'trend': trend,
            'calc_latency_ms': (self._last_calc_time - time.time()) * 1000
        }
    
    def reset(self):
        """重置引擎状态"""
        self._history_buffer.clear()
        self._last_attention = 0.0
        self._last_calc_time = 0.0