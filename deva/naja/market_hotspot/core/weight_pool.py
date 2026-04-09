"""
Weight Pool Module - 多对多权重池

功能:
- 解决个股 ↔ 多题材的映射关系
- 一个 symbol 可属于多个 block
- 最终权重由多个 block 决定
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
import logging

log = logging.getLogger(__name__)


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
    symbol_weight = f(block_hotspot, local_activity)

    其中:
    - block_hotspot: 来自 BlockHotspotEngine
    - local_activity: 个股波动、成交量变化、tick 异动

    修复内容:
    - 添加历史字典key清理机制，防止内存泄漏
    """

    def __init__(
        self,
        max_symbols: int = 5000,
        config: Optional[SymbolWeightConfig] = None,
        max_history_stale_seconds: float = 3600.0
    ):
        self.max_symbols = max_symbols
        self.config = config or SymbolWeightConfig()
        self.max_history_stale_seconds = max_history_stale_seconds

        # Symbol 映射
        self._symbol_to_idx: Dict[str, int] = {}
        self._idx_to_symbol: Dict[int, str] = {}
        self._symbol_blocks: Dict[str, List[str]] = defaultdict(list)

        # 预分配权重数组
        self._weights = np.zeros(max_symbols)
        self._base_weights = np.ones(max_symbols)
        self._local_activity = np.zeros(max_symbols)

        # 缓存 block 热点
        self._block_hotspot: Dict[str, float] = {}

        # 局部活动历史 (用于计算 local_activity)
        # 修复：使用带时间戳的字典，支持自动清理
        self._price_history: Dict[str, List[float]] = {}
        self._volume_history: Dict[str, List[float]] = {}
        self._symbol_last_seen: Dict[str, float] = {}  # 跟踪symbol最后活跃时间
        self._history_window = 10
        self._cleanup_counter = 0
        self._cleanup_interval = 100  # 每100次update清理一次

        self._last_update_time = 0.0
    
    def register_symbol(self, symbol: str, blocks: List[str], base_weight: float = 1.0) -> bool:
        """
        注册个股到权重池
        
        Args:
            symbol: 股票代码
            blocks: 所属题材列表
            base_weight: 基础权重
        """
        if len(self._symbol_to_idx) >= self.max_symbols:
            return False
        
        if symbol in self._symbol_to_idx:
            # 已存在，更新题材映射
            self._symbol_blocks[symbol] = blocks
            idx = self._symbol_to_idx[symbol]
            self._base_weights[idx] = base_weight
            return True
        
        idx = len(self._symbol_to_idx)
        self._symbol_to_idx[symbol] = idx
        self._idx_to_symbol[idx] = symbol
        self._symbol_blocks[symbol] = blocks
        self._base_weights[idx] = base_weight
        
        return True
    
    def update(
        self,
        symbols: np.ndarray,
        returns: np.ndarray,
        volumes: np.ndarray,
        block_hotspot: Dict[str, float],
        timestamp: float
    ) -> Dict[str, float]:
        """
        更新权重池

        Args:
            symbols: 股票代码数组
            returns: 涨跌幅数组
            volumes: 成交量数组
            block_hotspot: 题材热点字典
            timestamp: 当前时间戳

        Returns:
            symbol_weights: 个股权重字典
        """
        self._block_hotspot = block_hotspot

        # 清理异常值
        returns = np.nan_to_num(returns, nan=0.0, posinf=50.0, neginf=-50.0)
        returns = np.clip(returns, -50.0, 50.0)
        volumes = np.nan_to_num(volumes, nan=0.0, posinf=1e15, neginf=0.0)
        volumes = np.clip(volumes, 0, 1e15)

        try:
            # 更新局部活动
            self._update_local_activity(symbols, returns, volumes)

            # 计算每个 symbol 的权重
            registered_count = 0
            for symbol, idx in self._symbol_to_idx.items():
                weight = self._calc_symbol_weight(symbol, idx)
                self._weights[idx] = weight
                registered_count += 1
            log.info(f"[WeightPool] update: symbols参数={len(symbols)}, 已注册={registered_count}, _symbol_to_idx={len(self._symbol_to_idx)}")
        except Exception as e:
            import traceback
            log.error(f"WeightPool 计算失败: {e}")
            log.error(traceback.format_exc())

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
        """更新个股局部活动度（带自动清理）"""
        current_time = time.time()

        for i, symbol in enumerate(symbols):
            symbol_str = str(symbol)
            if symbol_str not in self._symbol_to_idx:
                continue

            idx = self._symbol_to_idx[symbol_str]

            if symbol_str not in self._price_history:
                self._price_history[symbol_str] = []
                self._volume_history[symbol_str] = []

            self._price_history[symbol_str].append(float(returns[i]))
            self._volume_history[symbol_str].append(float(volumes[i]))
            self._symbol_last_seen[symbol_str] = current_time

            if len(self._price_history[symbol_str]) > self._history_window:
                self._price_history[symbol_str] = self._price_history[symbol_str][-self._history_window:]
                self._volume_history[symbol_str] = self._volume_history[symbol_str][-self._history_window:]

            activity = self._calc_local_activity(symbol_str)
            self._local_activity[idx] = activity

        self._cleanup_counter += 1
        if self._cleanup_counter >= self._cleanup_interval:
            self._cleanup_stale_history(current_time)

    def _cleanup_stale_history(self, current_time: float):
        """清理长期不活跃symbol的历史数据，防止内存泄漏"""
        stale_symbols = [
            symbol for symbol, last_seen in self._symbol_last_seen.items()
            if current_time - last_seen > self.max_history_stale_seconds
        ]

        for symbol in stale_symbols:
            if symbol in self._price_history:
                del self._price_history[symbol]
            if symbol in self._volume_history:
                del self._volume_history[symbol]
            if symbol in self._symbol_last_seen:
                del self._symbol_last_seen[symbol]

        if stale_symbols:
            log.info(f"[WeightPool] 清理了 {len(stale_symbols)} 个不活跃symbol的历史数据")

        self._cleanup_counter = 0
    
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
        weight = base_weight * (1 + block_influence) * (1 + local_activity)
        
        其中 block_influence 是所属题材热点的加权平均
        """
        base_weight = self._base_weights[idx]
        local_activity = self._local_activity[idx]
        
        # 计算题材影响
        blocks = self._symbol_blocks.get(symbol, [])
        if not blocks:
            block_influence = 0.0
        else:
            block_scores = [
                self._block_hotspot.get(s, 0.0)
                for s in blocks
            ]
            block_influence = max(block_scores) if block_scores else 0.0
        
        # 计算最终权重
        weight = base_weight * (1 + block_influence) * (1 + local_activity * self.config.local_activity_sensitivity)
        
        # 裁剪到有效范围
        weight = max(self.config.min_weight, min(weight, self.config.max_weight))
        
        return weight
    
    def get_symbol_weight(self, symbol: str) -> float:
        """获取指定个股的权重"""
        idx = self._symbol_to_idx.get(symbol)
        if idx is None:
            return 0.0
        raw_weight = float(self._weights[idx])
        if raw_weight < self.config.min_weight or raw_weight > self.config.max_weight:
            log.warning(f"[WeightPool] symbol={symbol} weight={raw_weight:.2f} 超出范围 [{self.config.min_weight}, {self.config.max_weight}], 限制")
            return max(self.config.min_weight, min(raw_weight, self.config.max_weight))
        return raw_weight
    
    def get_top_symbols(self, n: int = 50, min_weight: float = 0.0) -> List[Tuple[str, float]]:
        """获取权重最高的 N 个个股"""
        symbols = []
        for symbol, idx in self._symbol_to_idx.items():
            raw_weight = float(self._weights[idx])
            clipped_weight = max(self.config.min_weight, min(raw_weight, self.config.max_weight))
            if clipped_weight >= min_weight:
                symbols.append((symbol, clipped_weight))
        symbols.sort(key=lambda x: x[1], reverse=True)
        return symbols[:n]
    
    def get_symbols_by_block(self, block_id: str) -> List[str]:
        """获取指定题材下的所有个股"""
        return [
            symbol for symbol, blocks in self._symbol_blocks.items()
            if block_id in blocks
        ]
    
    def get_block_weights(self, block_id: str) -> Dict[str, float]:
        """获取指定题材下所有个股的权重"""
        symbols = self.get_symbols_by_block(block_id)
        return {
            symbol: self.get_symbol_weight(symbol)
            for symbol in symbols
        }
    
    def get_all_weights(self, filter_noise: bool = False) -> Dict[str, float]:
        """获取所有权重的字典

        Args:
            filter_noise: 是否过滤噪音股票。当为True时，会过滤掉B股、ST股等噪音股票。
        """
        from deva.naja.market_hotspot.integration.extended import get_mode_manager
        mode_manager = get_mode_manager()
        current_mode = mode_manager.get_mode() if mode_manager else 'unknown'

        if filter_noise:
            from ..processing.noise_filter import get_noise_filter
            noise_filter = get_noise_filter()
            result = {}
            for symbol, idx in self._symbol_to_idx.items():
                if not noise_filter.is_noise(symbol):
                    raw_weight = float(self._weights[idx])
                    clipped_weight = max(self.config.min_weight, min(raw_weight, self.config.max_weight))
                    result[symbol] = clipped_weight
            log.debug(f"[WeightPool] get_all_weights(mode={current_mode}, filter=True): 返回 {len(result)} 个已过滤权重")
            return result

        result = {}
        for symbol, idx in self._symbol_to_idx.items():
            raw_weight = float(self._weights[idx])
            clipped_weight = max(self.config.min_weight, min(raw_weight, self.config.max_weight))
            result[symbol] = clipped_weight
        log.debug(f"[WeightPool] get_all_weights(mode={current_mode}, filter=False): 返回 {len(result)} 个权重")
        return result

    def save_state(self) -> Dict:
        """保存权重池状态用于持久化"""
        return {
            'symbol_to_idx': self._symbol_to_idx,
            'idx_to_symbol': {int(k): v for k, v in self._idx_to_symbol.items()},
            'symbol_blocks': dict(self._symbol_blocks),
            'weights': self._weights[:len(self._symbol_to_idx)].tolist(),
            'base_weights': self._base_weights[:len(self._symbol_to_idx)].tolist(),
            'local_activity': self._local_activity[:len(self._symbol_to_idx)].tolist(),
            'price_history': self._price_history,
            'volume_history': self._volume_history,
            'symbol_last_seen': self._symbol_last_seen,
            'block_hotspot': self._block_hotspot,
            'last_update_time': self._last_update_time,
        }

    def load_state(self, state: Dict) -> bool:
        """从持久化状态恢复"""
        try:
            if not state:
                return False

            self._symbol_to_idx = state.get('symbol_to_idx', {})
            self._idx_to_symbol = {int(k): v for k, v in state.get('idx_to_symbol', {}).items()}

            self._symbol_blocks.clear()
            for symbol, blocks in state.get('symbol_blocks', {}).items():
                self._symbol_blocks[symbol] = blocks

            weights = state.get('weights', [])
            for i, w in enumerate(weights):
                if i < len(self._weights):
                    self._weights[i] = w

            base_weights = state.get('base_weights', [])
            for i, w in enumerate(base_weights):
                if i < len(self._base_weights):
                    self._base_weights[i] = w

            local_activity = state.get('local_activity', [])
            for i, a in enumerate(local_activity):
                if i < len(self._local_activity):
                    self._local_activity[i] = a

            self._price_history = state.get('price_history', {})
            self._volume_history = state.get('volume_history', {})
            self._symbol_last_seen = state.get('symbol_last_seen', {})
            self._block_hotspot = state.get('block_hotspot', {})
            self._last_update_time = state.get('last_update_time', 0.0)

            return True
        except Exception as e:
            log.warning(f"[WeightPool] load_state 失败: {e}")
            return False

    def reset(self):
        """重置权重池"""
        self._weights.fill(0.0)
        self._local_activity.fill(0.0)
        self._block_hotspot.clear()
        self._price_history.clear()
        self._volume_history.clear()
        self._symbol_last_seen.clear()
        self._cleanup_counter = 0


class WeightPoolView:
    """
    权重池视图 - 提供不同粒度的权重查询
    """
    
    def __init__(self, weight_pool: WeightPool):
        self._pool = weight_pool
    
    def get_high_hotspot_symbols(self, threshold: float = 2.0) -> List[Tuple[str, float]]:
        """获取高热点个股"""
        return self._pool.get_top_symbols(n=100, min_weight=threshold)

    def get_block_leaders(self, block_id: str, n: int = 10) -> List[Tuple[str, float]]:
        """获取题材龙头股"""
        weights = self._pool.get_block_weights(block_id)
        sorted_symbols = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        return sorted_symbols[:n]

    def get_hotspot_distribution(self) -> Dict[str, int]:
        """获取热点分布统计"""
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