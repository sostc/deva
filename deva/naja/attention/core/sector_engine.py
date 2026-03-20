"""
Sector Attention Module - 板块注意力计算

功能:
- 每个板块独立计算注意力
- 反映板块内部"变化是否扩散"
- 支持多板块并行
- 支持半衰期衰减

性能优化:
- 使用预分配 numpy 数组避免动态扩容
- 增量更新，避免全量 groupby
- O(num_sectors) 复杂度
"""

import numpy as np
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import time
import logging

log = logging.getLogger(__name__)


@dataclass
class SectorConfig:
    """板块配置"""
    sector_id: str
    name: str
    symbols: Set[str] = field(default_factory=set)
    decay_half_life: float = 300.0  # 半衰期(秒)，默认5分钟
    activation_threshold: float = 0.3  # 激活阈值


class SectorAttentionEngine:
    """
    板块注意力引擎
    
    计算逻辑:
    1. 板块内领涨股数量比例
    2. 板块内成交量集中度
    3. 板块内相关性变化
    4. 半衰期衰减
    """
    
    def __init__(
        self,
        sectors: Optional[List[SectorConfig]] = None,
        max_sectors: int = 100,
        update_threshold: float = 0.05,  # 最小变化才更新
    ):
        self.max_sectors = max_sectors
        self.update_threshold = update_threshold
        
        # 板块配置
        self._sectors: Dict[str, SectorConfig] = {}
        self._symbol_to_sectors: Dict[str, List[str]] = defaultdict(list)
        
        # 预分配注意力分数数组
        self._attention_scores = np.zeros(max_sectors)
        self._sector_id_to_idx: Dict[str, int] = {}
        self._idx_to_sector_id: Dict[int, str] = {}
        
        # 历史状态 (用于增量计算)
        self._last_update_time: Dict[str, float] = {}
        self._leader_counts: Dict[str, int] = {}
        self._volume_concentration: Dict[str, float] = {}
        
        # 初始化板块
        if sectors:
            for sector in sectors:
                self.register_sector(sector)
        
        self._last_calc_time = 0.0
    
    def register_sector(self, config: SectorConfig) -> bool:
        """注册板块"""
        if len(self._sectors) >= self.max_sectors:
            return False
        
        sector_id = config.sector_id
        idx = len(self._sectors)
        
        self._sectors[sector_id] = config
        self._sector_id_to_idx[sector_id] = idx
        self._idx_to_sector_id[idx] = sector_id
        
        # 建立 symbol -> sectors 映射
        for symbol in config.symbols:
            self._symbol_to_sectors[symbol].append(sector_id)
        
        self._last_update_time[sector_id] = time.time()
        return True
    
    def update(
        self,
        symbols: np.ndarray,
        returns: np.ndarray,
        volumes: np.ndarray,
        timestamp: float
    ) -> Dict[str, float]:
        """
        更新板块注意力分数

        Args:
            symbols: 股票代码数组
            returns: 涨跌幅数组
            volumes: 成交量数组
            timestamp: 当前时间戳

        Returns:
            sector_attention: 板块注意力字典
        """
        start_time = time.time()

        # 清理异常值
        returns = np.nan_to_num(returns, nan=0.0, posinf=50.0, neginf=-50.0)
        returns = np.clip(returns, -50.0, 50.0)
        volumes = np.nan_to_num(volumes, nan=0.0, posinf=1e15, neginf=0.0)
        volumes = np.clip(volumes, 0, 1e15)

        try:
            # 按板块聚合数据 (增量方式，避免 groupby)
            sector_data = self._aggregate_by_sector(symbols, returns, volumes)

            # 调试日志 - 只在第一次或sector_data变化时输出
            if not sector_data:
                log.warning(f"[SectorAttention] 警告: sector_data为空! symbols数量={len(symbols)}")
            elif all(len(d.get('returns', [])) == 0 for d in sector_data.values()):
                log.warning(f"[SectorAttention] 警告: 所有板块的returns为空! sector_data keys={list(sector_data.keys())[:5]}")
            else:
                # 输出有数据的板块数量
                sectors_with_data = [k for k, v in sector_data.items() if len(v.get('returns', [])) > 0]
                if len(sectors_with_data) > 0:
                    log.info(f"[SectorAttention] 有数据的板块数: {len(sectors_with_data)}, 样本: {sectors_with_data[:3]}")

            # 计算每个板块的注意力
            for sector_id, data in sector_data.items():
                if sector_id not in self._sectors:
                    continue

                sector = self._sectors[sector_id]
                idx = self._sector_id_to_idx[sector_id]

                # 计算新分数
                new_score = self._calc_sector_attention(
                    data['returns'],
                    data['volumes'],
                    sector
                )

                # 调试日志
                if len(sector_data) <= 5:  # 只在板块少时输出
                    log.info(f"[SectorAttention] sector={sector_id}, new_score={new_score:.3f}, data_returns={list(data['returns'][:3]) if len(data['returns']) > 0 else 'empty'}")

                # 应用半衰期衰减
                last_time = self._last_update_time.get(sector_id, timestamp)
                time_delta = timestamp - last_time
                max_time_delta = sector.decay_half_life * 10
                time_delta = min(time_delta, max_time_delta)
                try:
                    decay_factor = 0.5 ** (time_delta / sector.decay_half_life)
                except OverflowError:
                    decay_factor = 0.0

                # 混合新旧分数
                old_score = self._attention_scores[idx]
                blended_score = max(new_score, old_score * decay_factor)

                # 只有当变化超过阈值时才更新
                if abs(blended_score - old_score) > self.update_threshold:
                    self._attention_scores[idx] = blended_score
                    self._last_update_time[sector_id] = timestamp
        except Exception as e:
            import traceback
            log.error(f"SectorAttention 计算失败: {e}")
            log.error(traceback.format_exc())

        # 构建返回字典
        result = {
            sector_id: self._attention_scores[idx]
            for sector_id, idx in self._sector_id_to_idx.items()
        }

        self._last_calc_time = time.time()
        return result
    
    def _aggregate_by_sector(
        self,
        symbols: np.ndarray,
        returns: np.ndarray,
        volumes: np.ndarray
    ) -> Dict[str, Dict[str, np.ndarray]]:
        """
        按板块聚合数据
        使用预分配数组避免动态扩容
        """
        sector_data = defaultdict(lambda: {
            'returns': [],
            'volumes': []
        })
        
        # 遍历所有股票，分配到对应板块
        for i, symbol in enumerate(symbols):
            symbol_str = str(symbol)
            sector_ids = self._symbol_to_sectors.get(symbol_str, [])
            
            for sector_id in sector_ids:
                sector_data[sector_id]['returns'].append(returns[i])
                sector_data[sector_id]['volumes'].append(volumes[i])
        
        # 转换为 numpy 数组
        result = {}
        for sector_id, data in sector_data.items():
            result[sector_id] = {
                'returns': np.array(data['returns']),
                'volumes': np.array(data['volumes'])
            }
        
        return result
    
    def _calc_sector_attention(
        self,
        returns: np.ndarray,
        volumes: np.ndarray,
        sector: SectorConfig
    ) -> float:
        """
        计算单个板块的注意力分数
        
        维度:
        1. 领涨股比例 (40%)
        2. 成交量集中度 (30%)
        3. 内部相关性 (30%)
        """
        if len(returns) == 0:
            return 0.0
        
        # 1. 领涨股比例
        leader_threshold = np.percentile(np.abs(returns), 80) if len(returns) > 5 else 2.0
        leader_ratio = np.sum(np.abs(returns) >= leader_threshold) / len(returns)
        leader_score = min(leader_ratio * 2, 1.0)  # 归一化
        
        # 2. 成交量集中度 (使用 Gini 系数思想)
        if len(volumes) > 0:
            total_volume = np.sum(volumes)
            if total_volume > 1e-10:  # 避免除零
                sorted_volumes = np.sort(volumes)
                cumsum = np.cumsum(sorted_volumes)
                n = len(volumes)
                if cumsum[-1] > 1e-10:  # 再次检查
                    concentration = (n + 1 - 2 * np.sum(cumsum) / cumsum[-1]) / n
                    volume_score = max(0.0, min(1.0, concentration))
                else:
                    volume_score = 0.0
            else:
                volume_score = 0.0
        else:
            volume_score = 0.0
        
        # 3. 内部相关性 (使用收益率标准差作为代理)
        if len(returns) > 1:
            return_std = np.std(returns)
            # 标准差适中表示有分化但又有联动
            correlation_score = 1.0 - abs(return_std - 3.0) / 3.0
            correlation_score = max(0.0, min(1.0, correlation_score))
        else:
            correlation_score = 0.0
        
        # 加权求和
        score = (
            leader_score * 0.4 +
            volume_score * 0.3 +
            correlation_score * 0.3
        )
        
        return score
    
    def get_active_sectors(self, threshold: Optional[float] = None) -> List[str]:
        """获取活跃的板块列表"""
        threshold = threshold or 0.3
        
        active = []
        for sector_id, idx in self._sector_id_to_idx.items():
            if self._attention_scores[idx] >= threshold:
                active.append(sector_id)
        
        # 按注意力分数排序
        active.sort(key=lambda s: self._attention_scores[self._sector_id_to_idx[s]], reverse=True)
        return active
    
    def get_sector_attention(self, sector_id: str) -> float:
        """获取指定板块的注意力分数"""
        idx = self._sector_id_to_idx.get(sector_id)
        if idx is None:
            return 0.0
        return float(self._attention_scores[idx])
    
    def get_top_sectors(self, n: int = 5) -> List[Tuple[str, float]]:
        """获取注意力最高的 N 个板块"""
        sectors = [
            (sector_id, float(self._attention_scores[idx]))
            for sector_id, idx in self._sector_id_to_idx.items()
        ]
        sectors.sort(key=lambda x: x[1], reverse=True)
        return sectors[:n]
    
    def get_all_weights(self) -> Dict[str, float]:
        """获取所有板块的权重"""
        weights = {
            sector_id: float(self._attention_scores[idx])
            for sector_id, idx in self._sector_id_to_idx.items()
        }
        # 调试日志
        if len(weights) < 5:
            log.info(f"[SectorAttention] get_all_weights: 返回 {len(weights)} 个板块: {list(weights.keys())}")
        return weights
    
    def reset(self):
        """重置引擎状态"""
        self._attention_scores.fill(0.0)
        self._last_update_time.clear()
        self._leader_counts.clear()
        self._volume_concentration.clear()