"""
Module 10: Attention Propagation - 注意力扩散传播

核心能力:
- 模拟板块之间的联动
- 当一个板块 attention 上升时，传播到相关板块

示例:
新能源 ↑ → 有色 ↑ → 电池 ↑

输入:
- sector_attention: 当前板块注意力
- sector_relation_matrix: 板块关系矩阵

输出:
- 传播后的 attention
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import time


@dataclass
class SectorRelation:
    """板块关系"""
    source_sector: str
    target_sector: str
    correlation: float
    delay_ticks: int
    strength: float


class RelationMatrix:
    """
    板块关系矩阵
    
    支持:
    - 手动定义关系
    - 从历史数据学习关系
    - 稀疏矩阵存储
    """
    
    def __init__(
        self,
        max_sectors: int = 100,
        default_correlation: float = 0.3,
        learning_rate: float = 0.01
    ):
        self.max_sectors = max_sectors
        self.default_correlation = default_correlation
        self.learning_rate = learning_rate
        
        self._sector_to_idx: Dict[str, int] = {}
        self._idx_to_sector: Dict[int, str] = {}
        
        self._relation_matrix: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._delay_matrix: Dict[str, Dict[str, int]] = defaultdict(dict)
        
        self._sector_history: Dict[str, List[float]] = {}
        self._history_window = 50
        
    def register_sector(self, sector_id: str) -> bool:
        """注册板块"""
        if sector_id in self._sector_to_idx:
            return True
        
        if len(self._sector_to_idx) >= self.max_sectors:
            return False
        
        idx = len(self._sector_to_idx)
        self._sector_to_idx[sector_id] = idx
        self._idx_to_sector[idx] = sector_id
        
        return True
    
    def set_relation(
        self,
        source: str,
        target: str,
        correlation: float,
        delay: int = 1,
        strength: float = 1.0
    ):
        """设置板块关系"""
        if source not in self._sector_to_idx or target not in self._sector_to_idx:
            return
        
        self._relation_matrix[source][target] = correlation * strength
        self._delay_matrix[source][target] = delay
    
    def get_relation(self, source: str, target: str) -> Tuple[float, int]:
        """
        获取板块关系
        
        Returns:
            (correlation, delay)
        """
        if source == target:
            return 1.0, 0
        
        correlation = self._relation_matrix.get(source, {}).get(target, self.default_correlation)
        delay = self._delay_matrix.get(source, {}).get(target, 1)
        
        return correlation, delay
    
    def get_upstream_sectors(self, sector_id: str) -> List[Tuple[str, float, int]]:
        """
        获取上游板块 (会影响到自己的板块)
        
        Returns:
            [(sector, correlation, delay), ...]
        """
        result = []
        
        for source, targets in self._relation_matrix.items():
            if sector_id in targets:
                correlation = targets[sector_id]
                delay = self._delay_matrix[source].get(sector_id, 1)
                result.append((source, correlation, delay))
        
        return result
    
    def get_downstream_sectors(self, sector_id: str) -> List[Tuple[str, float, int]]:
        """
        获取下游板块 (会被自己影响的板块)
        
        Returns:
            [(sector, correlation, delay), ...]
        """
        result = []
        
        targets = self._relation_matrix.get(sector_id, {})
        for target, correlation in targets.items():
            delay = self._delay_matrix[sector_id].get(target, 1)
            result.append((target, correlation, delay))
        
        return result
    
    def record_attention(self, sector_id: str, attention: float, timestamp: float):
        """记录注意力历史，用于学习关系"""
        if sector_id not in self._sector_history:
            self._sector_history[sector_id] = []
        
        self._sector_history[sector_id].append(attention)
        
        if len(self._sector_history[sector_id]) > self._history_window:
            self._sector_history[sector_id] = self._sector_history[sector_id][-self._history_window:]
    
    def learn_relations(self, min_correlation: float = 0.3):
        """
        从历史数据学习板块关系
        
        使用滞后相关性计算
        """
        sectors = list(self._sector_history.keys())
        
        for i, source in enumerate(sectors):
            for j, target in enumerate(sectors):
                if i >= j:
                    continue
                
                correlation = self._compute_lagged_correlation(source, target)
                
                if abs(correlation) > min_correlation:
                    delay = self._estimate_delay(source, target)
                    self.set_relation(source, target, abs(correlation), delay, 1.0)
                    self.set_relation(target, source, abs(correlation), delay, 1.0)
    
    def _compute_lagged_correlation(
        self,
        source: str,
        target: str,
        max_delay: int = 10
    ) -> float:
        """计算滞后相关性"""
        source_history = self._sector_history.get(source, [])
        target_history = self._sector_history.get(target, [])
        
        if len(source_history) < max_delay + 5 or len(target_history) < max_delay + 5:
            return 0.0
        
        best_corr = 0.0
        best_delay = 1
        
        for delay in range(1, max_delay + 1):
            source_shifted = source_history[:-delay] if delay > 0 else source_history
            target_aligned = target_history[delay:]
            
            min_len = min(len(source_shifted), len(target_aligned))
            if min_len < 5:
                continue
            
            source_arr = np.array(source_shifted[-min_len:])
            target_arr = np.array(target_aligned[-min_len:])
            
            corr = np.corrcoef(source_arr, target_arr)[0, 1]
            
            if not np.isnan(corr) and abs(corr) > abs(best_corr):
                best_corr = corr
                best_delay = delay
        
        return best_corr
    
    def _estimate_delay(self, source: str, target: str) -> int:
        """估计传播延迟"""
        source_history = self._sector_history.get(source, [])
        target_history = self._sector_history.get(target, [])
        
        if len(source_history) < 10 or len(target_history) < 10:
            return 1
        
        source_arr = np.array(source_history)
        target_arr = np.array(target_history)
        
        n = len(source_arr)
        
        best_delay = 1
        best_corr = 0.0
        
        for delay in range(1, min(10, n // 3)):
            source_shifted = source_arr[:-delay]
            target_aligned = target_arr[delay:]
            
            min_len = min(len(source_shifted), len(target_aligned))
            if min_len < 5:
                continue
            
            corr = np.corrcoef(
                source_shifted[-min_len:],
                target_aligned[-min_len:]
            )[0, 1]
            
            if not np.isnan(corr) and abs(corr) > abs(best_corr):
                best_corr = corr
                best_delay = delay
        
        return best_delay
    
    def get_all_relations(self) -> List[SectorRelation]:
        """获取所有关系"""
        relations = []
        
        for source, targets in self._relation_matrix.items():
            for target, correlation in targets.items():
                delay = self._delay_matrix[source].get(target, 1)
                relations.append(SectorRelation(
                    source_sector=source,
                    target_sector=target,
                    correlation=correlation,
                    delay_ticks=delay,
                    strength=1.0
                ))
        
        return relations
    
    def reset(self):
        """重置"""
        self._sector_to_idx.clear()
        self._idx_to_sector.clear()
        self._relation_matrix.clear()
        self._delay_matrix.clear()
        self._sector_history.clear()


class PropagationEngine:
    """
    传播引擎
    
    使用关系矩阵计算注意力传播
    """
    
    def __init__(
        self,
        relation_matrix: Optional[RelationMatrix] = None,
        decay_factor: float = 0.8,
        max_iterations: int = 3
    ):
        self.relations = relation_matrix or RelationMatrix()
        self.decay_factor = decay_factor
        self.max_iterations = max_iterations
        
        self._propagation_history: Dict[str, List[float]] = defaultdict(list)
        
    def propagate(
        self,
        sector_attention: Dict[str, float],
        timestamp: float
    ) -> Dict[str, float]:
        """
        计算传播后的注意力
        
        迭代传播直到收敛或达到最大迭代次数
        
        Args:
            sector_attention: 原始板块注意力
            timestamp: 时间戳
            
        Returns:
            传播后的注意力
        """
        attention = sector_attention.copy()
        
        sectors = list(attention.keys())
        
        for sector in sectors:
            self.relations.record_attention(sector, attention[sector], timestamp)
        
        for iteration in range(self.max_iterations):
            new_attention = attention.copy()
            
            changed = False
            
            for sector in sectors:
                upstream = self.relations.get_upstream_sectors(sector)
                
                if not upstream:
                    continue
                
                propagation = 0.0
                
                for source, correlation, delay in upstream:
                    if source not in attention:
                        continue
                    
                    source_attention = attention[source]
                    
                    source_history = self._propagation_history.get(source, [])
                    if len(source_history) >= delay:
                        delayed_attention = source_history[-delay]
                    else:
                        delayed_attention = source_attention
                    
                    propagation += delayed_attention * correlation * self.decay_factor
                
                if upstream:
                    propagation = propagation / len(upstream)
                    new_attention[sector] = attention[sector] + propagation
                    changed = True
            
            attention = new_attention
            
            if not changed:
                break
        
        for sector in sectors:
            self._propagation_history[sector].append(attention[sector])
            if len(self._propagation_history[sector]) > 100:
                self._propagation_history[sector] = self._propagation_history[sector][-100:]
        
        return attention
    
    def propagate_single_step(
        self,
        sector_attention: Dict[str, float],
        timestamp: float
    ) -> Dict[str, float]:
        """
        单步传播 (更轻量)
        """
        attention = sector_attention.copy()
        
        for sector in attention.keys():
            self.relations.record_attention(sector, attention[sector], timestamp)
        
        for sector in attention.keys():
            upstream = self.relations.get_upstream_sectors(sector)
            
            if not upstream:
                continue
            
            propagation = 0.0
            
            for source, correlation, delay in upstream:
                if source not in attention:
                    continue
                
                propagation += attention[source] * correlation * self.decay_factor
            
            propagation = propagation / len(upstream)
            attention[sector] = attention[sector] + propagation
        
        return attention
    
    def get_propagation_chain(
        self,
        source_sector: str,
        depth: int = 3
    ) -> List[Tuple[str, float]]:
        """
        获取从源板块开始的传播链
        
        Returns:
            [(sector, accumulated_attention), ...]
        """
        chain = []
        visited = set()
        
        current_sector = source_sector
        accumulated = 1.0
        
        for _ in range(depth):
            if current_sector in visited:
                break
            
            visited.add(current_sector)
            
            downstream = self.relations.get_downstream_sectors(current_sector)
            
            if not downstream:
                break
            
            best_next = max(downstream, key=lambda x: x[1])
            next_sector, correlation, _ = best_next
            
            accumulated *= correlation
            
            chain.append((next_sector, accumulated))
            
            current_sector = next_sector
        
        return chain
    
    def reset(self):
        """重置"""
        self._propagation_history.clear()


class AttentionPropagation:
    """
    注意力传播主控制器
    
    整合:
    - RelationMatrix: 关系矩阵
    - PropagationEngine: 传播引擎
    """
    
    def __init__(
        self,
        max_sectors: int = 100,
        enable_learning: bool = True,
        propagation_mode: str = "iterative"
    ):
        """
        Args:
            enable_learning: 是否从历史学习关系
            propagation_mode: 'iterative' 或 'single_step'
        """
        self.relation_matrix = RelationMatrix(max_sectors=max_sectors)
        self.engine = PropagationEngine(self.relation_matrix)
        self.enable_learning = enable_learning
        self.propagation_mode = propagation_mode
        
        self._propagated_history: Dict[str, List[float]] = defaultdict(list)
        
    def register_sector(self, sector_id: str) -> bool:
        """注册板块"""
        return self.relation_matrix.register_sector(sector_id)
    
    def set_relation(
        self,
        source: str,
        target: str,
        correlation: float,
        delay: int = 1
    ):
        """设置板块关系"""
        self.relation_matrix.set_relation(source, target, correlation, delay, 1.0)
    
    def add_upstream_relation(self, source: str, target: str, correlation: float):
        """
        添加上游关系 (source 影响 target)
        
        等价于: source → target
        """
        self.set_relation(source, target, correlation, delay=1)
    
    def add_downstream_relation(self, target: str, source: str, correlation: float):
        """
        添加下游关系 (target 被 source 影响)
        
        等价于: source → target
        """
        self.set_relation(source, target, correlation, delay=1)
    
    def propagate(
        self,
        sector_attention: Dict[str, float],
        timestamp: Optional[float] = None
    ) -> Dict[str, float]:
        """
        执行注意力传播
        """
        timestamp = timestamp or time.time()
        
        if self.propagation_mode == "single_step":
            result = self.engine.propagate_single_step(sector_attention, timestamp)
        else:
            result = self.engine.propagate(sector_attention, timestamp)
        
        for sector, attention in result.items():
            self._propagated_history[sector].append(attention)
        
        return result
    
    def learn_relations(self):
        """从历史学习关系"""
        if self.enable_learning:
            self.relation_matrix.learn_relations()
    
    def get_upstream_sectors(self, sector_id: str) -> List[Tuple[str, float, int]]:
        """获取上游板块"""
        return self.relation_matrix.get_upstream_sectors(sector_id)
    
    def get_downstream_sectors(self, sector_id: str) -> List[Tuple[str, float, int]]:
        """获取下游板块"""
        return self.relation_matrix.get_downstream_sectors(sector_id)
    
    def get_all_relations(self) -> List[SectorRelation]:
        """获取所有关系"""
        return self.relation_matrix.get_all_relations()
    
    def get_propagation_summary(self) -> Dict[str, Any]:
        """获取传播摘要"""
        return {
            'total_sectors': len(self.relation_matrix._sector_to_idx),
            'total_relations': len(self.get_all_relations()),
            'propagation_mode': self.propagation_mode,
            'enable_learning': self.enable_learning
        }
    
    def reset(self):
        """重置"""
        self.relation_matrix.reset()
        self.engine.reset()
        self._propagated_history.clear()
