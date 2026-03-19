"""
Weight Pool Module - 多对多权重池

功能:
- 解决个股 ↔ 多板块的映射关系
- 一个 symbol 可属于多个 sector
- 最终权重由多个 sector 决定
- 支持快速查找 O(1)

性能优化:
- 预分配 numpy 数组
- 向量化计算
- 增量更新
"""

import numpy as np
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from collections import defaultdict
import time


@dataclass
class SymbolWeightConfig:
    """个股权重配置"""
    base_weight: float = 1.0  # 基础权重
    max_weight: float = 5.0   # 最大权重
    min_weight: float = 0.1   # 最小权重
    local_activity_sensitivity: float = 1.0  # 本地活动敏感度


class WeightPool:
    """
    多对多权重池
    
    权重计算:
    symbol_weight = f(sector_attention, local_activity)
    
    其中:
    - sector_attention: 来自 SectorAttentionEngine
    - local_activity: 个股波动、成交量变化、tick 异动
    """
    
    def __init__(
        self,
        max_symbols: int = 5000,
        config: Optional[SymbolWeightConfig] = None
    ):
        self.max_symbols = max_symbols
        self.config = config or SymbolWeightConfig()
        
        # Symbol 映射
        self._symbol_to_idx: Dict[str, int] = {}
        self._idx_to_symbol: Dict[int, str] = {}
        self._symbol_sectors: Dict[str, List[str]] = defaultdict(list)
        
        # 预分配权重数组
        self._weights = np.zeros(max_symbols)
        self._base_weights = np.ones(max_symbols)  # 基础权重
        self._local_activity = np.zeros(max_symbols)
        
        # 缓存 sector 注意力
        self._sector_attention: Dict[str, float] = {}
        
        # 局部活动历史 (用于计算 local_activity)
        self._price_history: Dict[str, List[float]] = defaultdict(list)
        self._volume_history: Dict[str, List[float]] = defaultdict(list)
        self._history_window = 10
        
        self._last_update_time = 0.0
    
    def register_symbol(self, symbol: str, sectors: List[str], base_weight: float = 1.0) -> bool:
        """
        注册个股到权重池
        
        Args:
            symbol: 股票代码
            sectors: 所属板块列表
            base_weight: 基础权重
        """
        if len(self._symbol_to_idx) >= self.max_symbols:
            return False
        
        if symbol in self._symbol_to_idx:
            # 已存在，更新板块映射
            self._symbol_sectors[symbol] = sectors
            idx = self._symbol_to_idx[symbol]
            self._base_weights[idx] = base_weight
            return True
        
        idx = len(self._symbol_to_idx)
        self._symbol_to_idx[symbol] = idx
        self._idx_to_symbol[idx] = symbol
        self._symbol_sectors[symbol] = sectors
        self._base_weights[idx] = base_weight
        
        return True
    
    def update(
        self,
        symbols: np.ndarray,
        returns: np.ndarray,
        volumes: np.ndarray,
        sector_attention: Dict[str, float],
        timestamp: float
    ) -> Dict[str, float]:
        """
        更新权重池
        
        Args:
            symbols: 股票代码数组
            returns: 涨跌幅数组
            volumes: 成交量数组
            sector_attention: 板块注意力字典
            timestamp: 当前时间戳
            
        Returns:
            symbol_weights: 个股权重字典
        """
        self._sector_attention = sector_attention
        
        # 更新局部活动
        self._update_local_activity(symbols, returns, volumes)
        
        # 计算每个 symbol 的权重
        for symbol, idx in self._symbol_to_idx.items():
            weight = self._calc_symbol_weight(symbol, idx)
            self._weights[idx] = weight
        
        self._last_update_time = timestamp
        
        # 构建返回字典
        return {
            symbol: float(self._weights[idx])
            for symbol, idx in self._symbol_to_idx.items()
        }
    
    def _update_local_activity(
        self,
        symbols: np.ndarray,
        returns: np.ndarray,
        volumes: np.ndarray
    ):
        """更新个股局部活动度"""
        for i, symbol in enumerate(symbols):
            symbol_str = str(symbol)
            if symbol_str not in self._symbol_to_idx:
                continue
            
            idx = self._symbol_to_idx[symbol_str]
            
            # 更新历史
            self._price_history[symbol_str].append(float(returns[i]))
            self._volume_history[symbol_str].append(float(volumes[i]))
            
            # 限制历史长度
            if len(self._price_history[symbol_str]) > self._history_window:
                self._price_history[symbol_str] = self._price_history[symbol_str][-self._history_window:]
                self._volume_history[symbol_str] = self._volume_history[symbol_str][-self._history_window:]
            
            # 计算局部活动度
            activity = self._calc_local_activity(symbol_str)
            self._local_activity[idx] = activity
    
    def _calc_local_activity(self, symbol: str) -> float:
        """
        计算个股局部活动度
        
        维度:
        1. 价格波动率
        2. 成交量异常
        3. 近期趋势
        """
        prices = self._price_history.get(symbol, [])
        volumes = self._volume_history.get(symbol, [])
        
        if len(prices) < 3:
            return 0.0
        
        prices_arr = np.array(prices)
        volumes_arr = np.array(volumes)
        
        # 1. 价格波动率
        price_volatility = np.std(prices_arr) / (np.mean(np.abs(prices_arr)) + 1e-6)
        
        # 2. 成交量异常
        if len(volumes_arr) >= 2:
            volume_ratio = volumes_arr[-1] / (np.mean(volumes_arr[:-1]) + 1e-6)
            volume_anomaly = min(abs(volume_ratio - 1.0), 3.0) / 3.0
        else:
            volume_anomaly = 0.0
        
        # 3. 近期趋势强度
        trend_strength = abs(np.mean(prices_arr[-3:])) / 5.0  # 归一化
        
        # 综合活动度
        activity = (
            price_volatility * 0.4 +
            volume_anomaly * 0.3 +
            min(trend_strength, 1.0) * 0.3
        )
        
        return min(activity, 1.0)
    
    def _calc_symbol_weight(self, symbol: str, idx: int) -> float:
        """
        计算个股权重
        
        公式:
        weight = base_weight * (1 + sector_influence) * (1 + local_activity)
        
        其中 sector_influence 是所属板块注意力的加权平均
        """
        base_weight = self._base_weights[idx]
        local_activity = self._local_activity[idx]
        
        # 计算板块影响
        sectors = self._symbol_sectors.get(symbol, [])
        if not sectors:
            sector_influence = 0.0
        else:
            sector_scores = [
                self._sector_attention.get(s, 0.0)
                for s in sectors
            ]
            # 使用最大值而非平均值，突出重要板块影响
            sector_influence = max(sector_scores) if sector_scores else 0.0
        
        # 计算最终权重
        weight = base_weight * (1 + sector_influence) * (1 + local_activity * self.config.local_activity_sensitivity)
        
        # 裁剪到有效范围
        weight = max(self.config.min_weight, min(weight, self.config.max_weight))
        
        return weight
    
    def get_symbol_weight(self, symbol: str) -> float:
        """获取指定个股的权重"""
        idx = self._symbol_to_idx.get(symbol)
        if idx is None:
            return 0.0
        return float(self._weights[idx])
    
    def get_top_symbols(self, n: int = 50, min_weight: float = 0.0) -> List[Tuple[str, float]]:
        """获取权重最高的 N 个个股"""
        symbols = [
            (symbol, float(self._weights[idx]))
            for symbol, idx in self._symbol_to_idx.items()
            if self._weights[idx] >= min_weight
        ]
        symbols.sort(key=lambda x: x[1], reverse=True)
        return symbols[:n]
    
    def get_symbols_by_sector(self, sector_id: str) -> List[str]:
        """获取指定板块下的所有个股"""
        return [
            symbol for symbol, sectors in self._symbol_sectors.items()
            if sector_id in sectors
        ]
    
    def get_sector_weights(self, sector_id: str) -> Dict[str, float]:
        """获取指定板块下所有个股的权重"""
        symbols = self.get_symbols_by_sector(sector_id)
        return {
            symbol: self.get_symbol_weight(symbol)
            for symbol in symbols
        }
    
    def get_all_weights(self) -> Dict[str, float]:
        """获取所有权重的字典"""
        return {
            symbol: float(self._weights[idx])
            for symbol, idx in self._symbol_to_idx.items()
        }
    
    def reset(self):
        """重置权重池"""
        self._weights.fill(0.0)
        self._local_activity.fill(0.0)
        self._sector_attention.clear()
        self._price_history.clear()
        self._volume_history.clear()


class WeightPoolView:
    """
    权重池视图 - 提供不同粒度的权重查询
    """
    
    def __init__(self, weight_pool: WeightPool):
        self._pool = weight_pool
    
    def get_high_attention_symbols(self, threshold: float = 2.0) -> List[Tuple[str, float]]:
        """获取高注意力个股"""
        return self._pool.get_top_symbols(n=100, min_weight=threshold)
    
    def get_sector_leaders(self, sector_id: str, n: int = 10) -> List[Tuple[str, float]]:
        """获取板块龙头股"""
        weights = self._pool.get_sector_weights(sector_id)
        sorted_symbols = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        return sorted_symbols[:n]
    
    def get_attention_distribution(self) -> Dict[str, int]:
        """获取注意力分布统计"""
        weights = [
            self._pool.get_symbol_weight(s)
            for s in self._pool._symbol_to_idx.keys()
        ]
        
        distribution = {
            'very_high': sum(1 for w in weights if w >= 3.0),
            'high': sum(1 for w in weights if 2.0 <= w < 3.0),
            'medium': sum(1 for w in weights if 1.0 <= w < 2.0),
            'low': sum(1 for w in weights if w < 1.0)
        }
        
        return distribution