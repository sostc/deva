"""
Module 10: Hotspot Propagation - 热点扩散传播

核心能力:
- 模拟题材之间的联动
- 当一个题材 attention 上升时，传播到相关题材

示例:
新能源 ↑ → 有色 ↑ → 电池 ↑

输入:
- block_hotspot: 当前题材热点
- block_relation_matrix: 题材关系矩阵

输出:
- 传播后的 attention
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import time


@dataclass
class BlockRelation:
    """题材关系"""
    source_block: str
    target_block: str
    correlation: float
    delay_ticks: int
    strength: float


class RelationMatrix:
    """
    题材关系矩阵

    支持:
    - 手动定义关系
    - 从历史数据学习关系
    - 稀疏矩阵存储
    - 集成统一的 BlockNoiseDetector 进行噪音题材过滤
    """

    _noise_detector = None

    def __init__(
        self,
        max_blocks: int = 5000,
        default_correlation: float = 0.3,
        learning_rate: float = 0.01
    ):
        self.max_blocks = max_blocks
        self.default_correlation = default_correlation
        self.learning_rate = learning_rate

        self._block_to_idx: Dict[str, int] = {}
        self._idx_to_block: Dict[int, str] = {}

        self._relation_matrix: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._delay_matrix: Dict[str, Dict[str, int]] = defaultdict(dict)

        self._block_history: Dict[str, List[float]] = {}
        self._history_window = 50

        self._relation_quality_scores: Dict[str, float] = {}
        self._auto_blacklist_enabled: bool = True

        if RelationMatrix._noise_detector is None:
            try:
                from deva.naja.market_hotspot.processing.block_noise_detector import BlockNoiseDetector
                RelationMatrix._noise_detector = BlockNoiseDetector.get_instance()
            except Exception:
                RelationMatrix._noise_detector = None

    def _get_noise_detector(self):
        """获取噪音检测器"""
        return RelationMatrix._noise_detector

    def _is_noise_by_pattern(self, block_id: str, block_name: str = None) -> bool:
        """检查题材是否匹配噪音模式"""
        detector = self._get_noise_detector()
        if detector:
            return detector.is_noise(block_id, block_name)

        blacklist_patterns = [
            '通达信', '系统', 'ST', 'B股', '基金', '指数', '期权', '期货',
            '上证', '深证', '沪深', '大盘', '权重', '综合', '行业', '地域',
            '概念', '风格', '上证所', '深交所', '_sys', '_index', '884',
            '物业管理', '含B股', '地方版', '预预', '昨日', '近日',
        ]
        display = block_name if block_name else block_id
        for pattern in blacklist_patterns:
            if pattern in display or pattern in block_id:
                return True
        return False
        
    def register_block(self, block_id: str) -> bool:
        """注册题材"""
        if block_id in self._block_to_idx:
            return True
        
        if len(self._block_to_idx) >= self.max_blocks:
            return False
        
        idx = len(self._block_to_idx)
        self._block_to_idx[block_id] = idx
        self._idx_to_block[idx] = block_id
        
        return True
    
    def set_relation(
        self,
        source: str,
        target: str,
        correlation: float,
        delay: int = 1,
        strength: float = 1.0
    ):
        """设置题材关系"""
        if source not in self._block_to_idx or target not in self._block_to_idx:
            return
        
        self._relation_matrix[source][target] = correlation * strength
        self._delay_matrix[source][target] = delay
    
    def get_relation(self, source: str, target: str) -> Tuple[float, int]:
        """
        获取题材关系
        
        Returns:
            (correlation, delay)
        """
        if source == target:
            return 1.0, 0
        
        correlation = self._relation_matrix.get(source, {}).get(target, self.default_correlation)
        delay = self._delay_matrix.get(source, {}).get(target, 1)
        
        return correlation, delay
    
    def get_upstream_blocks(self, block_id: str) -> List[Tuple[str, float, int]]:
        """
        获取上游题材 (会影响到自己的题材)
        
        Returns:
            [(block, correlation, delay), ...]
        """
        result = []
        
        for source, targets in self._relation_matrix.items():
            if block_id in targets:
                correlation = targets[block_id]
                delay = self._delay_matrix[source].get(block_id, 1)
                result.append((source, correlation, delay))
        
        return result
    
    def get_downstream_blocks(self, block_id: str) -> List[Tuple[str, float, int]]:
        """
        获取下游题材 (会被自己影响的题材)
        
        Returns:
            [(block, correlation, delay), ...]
        """
        result = []
        
        targets = self._relation_matrix.get(block_id, {})
        for target, correlation in targets.items():
            delay = self._delay_matrix[block_id].get(target, 1)
            result.append((target, correlation, delay))
        
        return result
    
    def record_attention(self, block_id: str, attention: float, timestamp: float):
        """记录热点历史，用于学习关系"""
        if block_id not in self._block_history:
            self._block_history[block_id] = []
        
        self._block_history[block_id].append(attention)
        
        if len(self._block_history[block_id]) > self._history_window:
            self._block_history[block_id] = self._block_history[block_id][-self._history_window:]

    def _should_blacklist(self, block_name: str) -> bool:
        """检查题材是否应该加入黑名单（兼容旧接口）"""
        return self._is_noise_by_pattern(block_name, block_name)

    def is_block_valid(self, block_id: str) -> bool:
        """判断题材是否有效（非噪声）"""
        detector = self._get_noise_detector()
        if detector:
            return not detector.is_noise(block_id)
        return True

    def _compute_relation_quality(self, source: str, target: str, correlation: float, delay: int) -> float:
        """计算关系质量分数"""
        quality = 0.0
        if abs(correlation) >= 0.98:
            quality -= 0.5
        elif abs(correlation) >= 0.5 and abs(correlation) <= 0.95:
            quality += 0.3
        if 1 <= delay <= 5:
            quality += 0.2
        elif delay > 8:
            quality -= 0.1
        source_history = self._block_history.get(source, [])
        target_history = self._block_history.get(target, [])
        if len(source_history) >= 10 and len(target_history) >= 10:
            variance_source = np.var(source_history) if source_history else 0
            variance_target = np.var(target_history) if target_history else 0
            if variance_source > 0.001 and variance_target > 0.001:
                quality += 0.2
            else:
                quality -= 0.3
        return max(0.0, quality)

    def _auto_update_blacklist(self):
        """自动更新黑名单"""
        detector = self._get_noise_detector()
        if not self._auto_blacklist_enabled:
            return
        for block_id in list(self._block_history.keys()):
            if detector and detector.is_noise(block_id):
                continue
            history = self._block_history.get(block_id, [])
            if len(history) < 10:
                continue
            variance = np.var(history)
            if variance < 0.0001:
                if detector:
                    detector.add_to_blacklist(block_id, reason="低方差噪音")
                continue
            quality_scores = []
            for other_block in self._block_history.keys():
                if other_block == block_id:
                    continue
                if detector and detector.is_noise(other_block):
                    continue
                if block_id not in self._relation_matrix.get(other_block, {}):
                    continue
                corr = self._relation_matrix[other_block].get(block_id, 0)
                delay = self._delay_matrix.get(other_block, {}).get(block_id, 1)
                quality = self._compute_relation_quality(other_block, block_id, corr, delay)
                quality_scores.append(quality)
            if quality_scores:
                avg_quality = sum(quality_scores) / len(quality_scores)
                self._relation_quality_scores[block_id] = avg_quality
                if avg_quality < 0.1:
                    if detector:
                        detector.add_to_blacklist(block_id, reason=f"低关系质量 {avg_quality:.3f}")

    def add_to_blacklist(self, block_id: str):
        """手动添加题材到黑名单"""
        detector = self._get_noise_detector()
        if detector:
            detector.add_to_blacklist(block_id, reason="手动添加")

    def remove_from_blacklist(self, block_id: str):
        """从黑名单移除"""
        detector = self._get_noise_detector()
        if detector:
            detector.remove_from_blacklist(block_id)

    def get_blacklist(self) -> set:
        """获取当前黑名单"""
        detector = self._get_noise_detector()
        if detector:
            return detector.get_all_noise_blocks()
        return set()

    def learn_relations(self, min_correlation: float = 0.3):
        """从历史数据学习题材关系"""
        self._auto_update_blacklist()
        detector = self._get_noise_detector()
        blocks = [s for s in self._block_history.keys()]
        if detector:
            blocks = detector.get_valid_blocks(blocks)
        
        for i, source in enumerate(blocks):
            for j, target in enumerate(blocks):
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
        source_history = self._block_history.get(source, [])
        target_history = self._block_history.get(target, [])
        
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

            with np.errstate(invalid='ignore'):
                corr = np.corrcoef(source_arr, target_arr)[0, 1]

            if not np.isnan(corr) and abs(corr) > abs(best_corr):
                best_corr = corr
                best_delay = delay
        
        return best_corr
    
    def _estimate_delay(self, source: str, target: str) -> int:
        """估计传播延迟"""
        source_history = self._block_history.get(source, [])
        target_history = self._block_history.get(target, [])
        
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

            with np.errstate(invalid='ignore'):
                corr = np.corrcoef(
                    source_shifted[-min_len:],
                    target_aligned[-min_len:]
                )[0, 1]

            if not np.isnan(corr) and abs(corr) > abs(best_corr):
                best_corr = corr
                best_delay = delay
        
        return best_delay
    
    def get_all_relations(self) -> List[BlockRelation]:
        """获取所有关系"""
        relations = []
        
        for source, targets in self._relation_matrix.items():
            for target, correlation in targets.items():
                delay = self._delay_matrix[source].get(target, 1)
                relations.append(BlockRelation(
                    source_block=source,
                    target_block=target,
                    correlation=correlation,
                    delay_ticks=delay,
                    strength=1.0
                ))
        
        return relations
    
    def reset(self):
        """重置"""
        self._block_to_idx.clear()
        self._idx_to_block.clear()
        self._relation_matrix.clear()
        self._delay_matrix.clear()
        self._block_history.clear()


class PropagationEngine:
    """
    传播引擎
    
    使用关系矩阵计算热点传播
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
        block_hotspot: Dict[str, float],
        timestamp: float
    ) -> Dict[str, float]:
        """
        计算传播后的热点
        
        迭代传播直到收敛或达到最大迭代次数
        
        Args:
            block_hotspot: 原始题材热点
            timestamp: 时间戳
            
        Returns:
            传播后的热点
        """
        attention = block_hotspot.copy()
        
        blocks = list(attention.keys())
        
        for block in blocks:
            self.relations.record_attention(block, attention[block], timestamp)
        
        for iteration in range(self.max_iterations):
            new_attention = attention.copy()
            
            changed = False
            
            for block in blocks:
                upstream = self.relations.get_upstream_blocks(block)
                
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
                    new_attention[block] = attention[block] + propagation
                    changed = True
            
            attention = new_attention
            
            if not changed:
                break
        
        for block in blocks:
            self._propagation_history[block].append(attention[block])
            if len(self._propagation_history[block]) > 100:
                self._propagation_history[block] = self._propagation_history[block][-100:]
        
        return attention
    
    def propagate_single_step(
        self,
        block_hotspot: Dict[str, float],
        timestamp: float
    ) -> Dict[str, float]:
        """
        单步传播 (更轻量)
        """
        attention = block_hotspot.copy()
        
        for block in attention.keys():
            self.relations.record_attention(block, attention[block], timestamp)
        
        for block in attention.keys():
            upstream = self.relations.get_upstream_blocks(block)
            
            if not upstream:
                continue
            
            propagation = 0.0
            
            for source, correlation, delay in upstream:
                if source not in attention:
                    continue
                
                propagation += attention[source] * correlation * self.decay_factor
            
            propagation = propagation / len(upstream)
            attention[block] = attention[block] + propagation
        
        return attention
    
    def get_propagation_chain(
        self,
        source_block: str,
        depth: int = 3
    ) -> List[Tuple[str, float]]:
        """
        获取从源题材开始的传播链
        
        Returns:
            [(block, accumulated_attention), ...]
        """
        chain = []
        visited = set()
        
        current_block = source_block
        accumulated = 1.0
        
        for _ in range(depth):
            if current_block in visited:
                break
            
            visited.add(current_block)
            
            downstream = self.relations.get_downstream_blocks(current_block)
            
            if not downstream:
                break
            
            best_next = max(downstream, key=lambda x: x[1])
            next_block, correlation, _ = best_next
            
            accumulated *= correlation
            
            chain.append((next_block, accumulated))
            
            current_block = next_block
        
        return chain
    
    def reset(self):
        """重置"""
        self._propagation_history.clear()


class HotspotPropagation:
    """
    热点传播主控制器
    
    整合:
    - RelationMatrix: 关系矩阵
    - PropagationEngine: 传播引擎
    """
    
    def __init__(
        self,
        max_blocks: int = 5000,
        enable_learning: bool = True,
        propagation_mode: str = "iterative"
    ):
        """
        Args:
            enable_learning: 是否从历史学习关系
            propagation_mode: 'iterative' 或 'single_step'
        """
        self.relation_matrix = RelationMatrix(max_blocks=max_blocks)
        self.engine = PropagationEngine(self.relation_matrix)
        self.enable_learning = enable_learning
        self.propagation_mode = propagation_mode
        
        self._propagated_history: Dict[str, List[float]] = defaultdict(list)
        
    def register_block(self, block_id: str) -> bool:
        """注册题材"""
        return self.relation_matrix.register_block(block_id)
    
    def set_relation(
        self,
        source: str,
        target: str,
        correlation: float,
        delay: int = 1
    ):
        """设置题材关系"""
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
        block_hotspot: Dict[str, float],
        timestamp: Optional[float] = None
    ) -> Dict[str, float]:
        """
        执行热点传播
        """
        timestamp = timestamp or time.time()
        
        if self.propagation_mode == "single_step":
            result = self.engine.propagate_single_step(block_hotspot, timestamp)
        else:
            result = self.engine.propagate(block_hotspot, timestamp)
        
        for block, attention in result.items():
            self._propagated_history[block].append(attention)
        
        return result
    
    def learn_relations(self):
        """从历史学习关系"""
        if self.enable_learning:
            self.relation_matrix.learn_relations()

    def get_blacklist(self) -> set:
        """获取黑名单"""
        return self.relation_matrix.get_blacklist()

    def add_to_blacklist(self, block_id: str):
        """添加题材到黑名单"""
        self.relation_matrix.add_to_blacklist(block_id)

    def remove_from_blacklist(self, block_id: str):
        """从黑名单移除"""
        self.relation_matrix.remove_from_blacklist(block_id)

    def get_upstream_blocks(self, block_id: str) -> List[Tuple[str, float, int]]:
        """获取上游题材"""
        return self.relation_matrix.get_upstream_blocks(block_id)
    
    def get_downstream_blocks(self, block_id: str) -> List[Tuple[str, float, int]]:
        """获取下游题材"""
        return self.relation_matrix.get_downstream_blocks(block_id)
    
    def get_all_relations(self) -> List[BlockRelation]:
        """获取所有关系"""
        return self.relation_matrix.get_all_relations()
    
    def get_propagation_summary(self) -> Dict[str, Any]:
        """获取传播摘要"""
        return {
            'total_blocks': len(self.relation_matrix._block_to_idx),
            'total_relations': len(self.get_all_relations()),
            'propagation_mode': self.propagation_mode,
            'enable_learning': self.enable_learning
        }
    
    def reset(self):
        """重置"""
        self.relation_matrix.reset()
        self.engine.reset()
        self._propagated_history.clear()
