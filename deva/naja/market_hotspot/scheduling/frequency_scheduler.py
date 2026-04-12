"""
Frequency Scheduler Module - 频率调度器

功能:
- 将连续权重转换为离散数据频率
- 支持三档频率（高/中/低）
- 支持滞后机制（避免频繁切换）
- 支持冷静期（cooldown）

性能优化:
- 预分配决策数组
- 增量更新
- O(n) 复杂度
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict
import time


class FrequencyLevel(Enum):
    """频率档位"""
    LOW = 0      # 低频: 60秒
    MEDIUM = 1   # 中频: 10秒
    HIGH = 2     # 高频: 1秒


@dataclass
class FrequencyConfig:
    """频率配置"""
    low_threshold: float = 1.0    # 低于此值为低频
    high_threshold: float = 2.5   # 高于此值为高频

    low_interval: float = 60.0
    medium_interval: float = 10.0
    high_interval: float = 5.0
    
    # 滞后机制
    hysteresis: float = 0.2       # 滞后阈值
    
    # 冷静期
    cooldown: float = 30.0        # 切换后冷静期(秒)
    
    # 最小变更原则
    min_change_ratio: float = 0.1  # 最小变更比例


class FrequencyScheduler:
    """
    频率调度器
    
    将 symbol 权重映射到频率档位:
    - weight < low_threshold: LOW
    - low_threshold <= weight < high_threshold: MEDIUM
    - weight >= high_threshold: HIGH
    
    特性:
    1. 滞后机制: 避免在阈值附近震荡
    2. 冷静期: 切换后一段时间内不再次切换
    3. 最小变更: 限制每次变更的 symbol 数量
    """
    
    def __init__(
        self,
        config: Optional[FrequencyConfig] = None,
        max_symbols: int = 5000
    ):
        self.config = config or FrequencyConfig()
        self.max_symbols = max_symbols
        
        # Symbol 映射
        self._symbol_to_idx: Dict[str, int] = {}
        self._idx_to_symbol: Dict[int, str] = {}
        
        # 当前频率档位 (预分配数组)
        self._current_levels = np.full(max_symbols, FrequencyLevel.LOW.value, dtype=np.int8)
        
        # 上次切换时间
        self._last_switch_time = np.zeros(max_symbols)
        
        # 上次权重 (用于滞后判断)
        self._last_weights = np.zeros(max_symbols)
        
        # 统计
        self._switch_count = 0
        self._last_schedule_time = 0.0

        # 受保护的符号集合（指数等，始终保持HIGH档位）
        self._protected_symbols: set = set()
    
    def register_symbol(self, symbol: str) -> bool:
        """注册个股"""
        if symbol in self._symbol_to_idx:
            return True
        
        if len(self._symbol_to_idx) >= self.max_symbols:
            return False
        
        idx = len(self._symbol_to_idx)
        self._symbol_to_idx[symbol] = idx
        self._idx_to_symbol[idx] = symbol
        
        return True

    def register_protected_symbol(self, symbol: str):
        """注册受保护的符号（始终保持HIGH档位）"""
        if symbol not in self._symbol_to_idx:
            self.register_symbol(symbol)
        self._protected_symbols.add(symbol)
        idx = self._symbol_to_idx.get(symbol)
        if idx is not None:
            self._current_levels[idx] = FrequencyLevel.HIGH.value

    def schedule(
        self,
        symbol_weights: Dict[str, float],
        timestamp: float
    ) -> Dict[str, FrequencyLevel]:
        """
        执行频率调度
        
        Args:
            symbol_weights: 个股权重字典
            timestamp: 当前时间戳
            
        Returns:
            symbol -> FrequencyLevel 映射
        """
        # 计算目标频率
        target_levels = self._calc_target_levels(symbol_weights)
        
        # 应用滞后和冷静期
        final_levels = self._apply_constraints(
            target_levels, symbol_weights, timestamp
        )
        
        # 更新状态
        changes = 0
        for symbol, level in final_levels.items():
            idx = self._symbol_to_idx.get(symbol)
            if idx is not None:
                old_level = self._current_levels[idx]
                if old_level != level.value:
                    self._current_levels[idx] = level.value
                    self._last_switch_time[idx] = timestamp
                    changes += 1
                
                self._last_weights[idx] = symbol_weights.get(symbol, 0.0)
        
        self._switch_count += changes
        self._last_schedule_time = timestamp
        
        return final_levels
    
    def _calc_target_levels(
        self,
        symbol_weights: Dict[str, float]
    ) -> Dict[str, FrequencyLevel]:
        """计算目标频率档位"""
        targets = {}

        for symbol, weight in symbol_weights.items():
            if symbol in self._protected_symbols:
                targets[symbol] = FrequencyLevel.HIGH
                continue

            if weight < self.config.low_threshold:
                level = FrequencyLevel.LOW
            elif weight < self.config.high_threshold:
                level = FrequencyLevel.MEDIUM
            else:
                level = FrequencyLevel.HIGH

            targets[symbol] = level
        
        return targets
    
    def _apply_constraints(
        self,
        target_levels: Dict[str, FrequencyLevel],
        symbol_weights: Dict[str, float],
        timestamp: float
    ) -> Dict[str, FrequencyLevel]:
        """
        应用约束:
        1. 滞后机制
        2. 冷静期
        3. 最小变更原则
        """
        final_levels = {}
        potential_changes = []
        
        # 第一遍: 识别可能的变更
        for symbol, target in target_levels.items():
            idx = self._symbol_to_idx.get(symbol)
            if idx is None:
                continue
            
            current = FrequencyLevel(self._current_levels[idx])
            
            if current == target:
                final_levels[symbol] = target
                continue
            
            # 检查冷静期
            time_since_switch = timestamp - self._last_switch_time[idx]
            if time_since_switch < self.config.cooldown:
                final_levels[symbol] = current
                continue
            
            # 检查滞后
            weight = symbol_weights.get(symbol, 0.0)
            last_weight = self._last_weights[idx]
            
            if self._should_switch_with_hysteresis(
                current, target, weight, last_weight
            ):
                potential_changes.append((symbol, target, weight))
            else:
                final_levels[symbol] = current
        
        # 应用最小变更原则
        if len(potential_changes) > 0:
            # 按权重变化幅度排序，优先处理变化大的
            potential_changes.sort(key=lambda x: abs(x[2] - self._last_weights[self._symbol_to_idx[x[0]]]), reverse=True)
            
            # 计算允许的最大变更数
            total_symbols = len(self._symbol_to_idx)
            max_changes = max(1, int(total_symbols * self.config.min_change_ratio))
            
            # 应用变更
            for i, (symbol, target, _) in enumerate(potential_changes):
                if i < max_changes:
                    final_levels[symbol] = target
                else:
                    idx = self._symbol_to_idx[symbol]
                    final_levels[symbol] = FrequencyLevel(self._current_levels[idx])
        
        return final_levels
    
    def _should_switch_with_hysteresis(
        self,
        current: FrequencyLevel,
        target: FrequencyLevel,
        weight: float,
        last_weight: float
    ) -> bool:
        """判断是否应该在滞后机制下切换"""
        if current == target:
            return True
        
        # 计算权重变化方向
        weight_change = weight - last_weight
        
        # 根据当前档位和目标档位确定阈值
        if current == FrequencyLevel.LOW and target == FrequencyLevel.MEDIUM:
            # 从低频升到中频: 需要超过 low_threshold + hysteresis
            threshold = self.config.low_threshold + self.config.hysteresis
            return weight >= threshold
        
        elif current == FrequencyLevel.MEDIUM and target == FrequencyLevel.LOW:
            # 从中频降到低频: 需要低于 low_threshold - hysteresis
            threshold = self.config.low_threshold - self.config.hysteresis
            return weight <= threshold
        
        elif current == FrequencyLevel.MEDIUM and target == FrequencyLevel.HIGH:
            # 从中频升到高频: 需要超过 high_threshold + hysteresis
            threshold = self.config.high_threshold + self.config.hysteresis
            return weight >= threshold
        
        elif current == FrequencyLevel.HIGH and target == FrequencyLevel.MEDIUM:
            # 从高频降到中频: 需要低于 high_threshold - hysteresis
            threshold = self.config.high_threshold - self.config.hysteresis
            return weight <= threshold
        
        elif current == FrequencyLevel.LOW and target == FrequencyLevel.HIGH:
            # 从低频直接升到高频: 需要大幅超过 high_threshold
            return weight >= self.config.high_threshold + self.config.hysteresis * 2
        
        elif current == FrequencyLevel.HIGH and target == FrequencyLevel.LOW:
            # 从高频直接降到低频: 需要大幅低于 low_threshold
            return weight <= self.config.low_threshold - self.config.hysteresis * 2
        
        return True
    
    def get_frequency_interval(self, level: FrequencyLevel) -> float:
        """获取频率档位对应的间隔时间"""
        if level == FrequencyLevel.LOW:
            return self.config.low_interval
        elif level == FrequencyLevel.MEDIUM:
            return self.config.medium_interval
        else:
            return self.config.high_interval
    
    def get_symbol_level(self, symbol: str) -> FrequencyLevel:
        """获取指定个股的频率档位"""
        idx = self._symbol_to_idx.get(symbol)
        if idx is None:
            return FrequencyLevel.LOW
        return FrequencyLevel(self._current_levels[idx])
    
    def get_symbols_by_level(self, level: FrequencyLevel) -> List[str]:
        """获取指定频率档位的所有个股"""
        return [
            symbol for symbol, idx in self._symbol_to_idx.items()
            if self._current_levels[idx] == level.value
        ]
    
    def get_schedule_summary(self) -> Dict:
        """获取调度摘要"""
        level_counts = defaultdict(int)
        
        for symbol, idx in self._symbol_to_idx.items():
            level = FrequencyLevel(self._current_levels[idx])
            level_counts[level.name] += 1
        
        return {
            'high_frequency': level_counts.get('HIGH', 0),
            'medium_frequency': level_counts.get('MEDIUM', 0),
            'low_frequency': level_counts.get('LOW', 0),
            'total_switches': self._switch_count,
            'last_schedule': self._last_schedule_time
        }
    
    def should_fetch(self, symbol: str, timestamp: float) -> bool:
        """判断是否应该获取该 symbol 的数据"""
        idx = self._symbol_to_idx.get(symbol)
        if idx is None:
            return False
        
        level = FrequencyLevel(self._current_levels[idx])
        interval = self.get_frequency_interval(level)
        
        last_fetch = self._last_switch_time[idx]
        return (timestamp - last_fetch) >= interval
    
    def reset(self):
        """重置调度器"""
        self._current_levels.fill(FrequencyLevel.LOW.value)
        self._last_switch_time.fill(0.0)
        self._last_weights.fill(0.0)
        self._switch_count = 0

    def get_all_levels(self) -> Dict[str, FrequencyLevel]:
        """获取所有 symbol 的当前频率档位"""
        return {
            symbol: FrequencyLevel(self._current_levels[idx])
            for symbol, idx in self._symbol_to_idx.items()
        }

    def save_state(self) -> Dict:
        """保存调度器状态用于持久化"""
        return {
            'symbol_to_idx': self._symbol_to_idx,
            'idx_to_symbol': {int(k): v for k, v in self._idx_to_symbol.items()},
            'current_levels': self._current_levels[:len(self._symbol_to_idx)].tolist(),
            'last_switch_time': self._last_switch_time[:len(self._symbol_to_idx)].tolist(),
            'last_weights': self._last_weights[:len(self._symbol_to_idx)].tolist(),
            'switch_count': self._switch_count,
            'last_schedule_time': self._last_schedule_time,
        }

    def load_state(self, state: Dict) -> bool:
        """从持久化状态恢复调度器"""
        try:
            if not state:
                return False

            self._symbol_to_idx = state.get('symbol_to_idx', {})
            self._idx_to_symbol = {int(k): v for k, v in state.get('idx_to_symbol', {}).items()}

            current_levels = state.get('current_levels', [])
            for i, level in enumerate(current_levels):
                if i < len(self._current_levels):
                    self._current_levels[i] = level

            last_switch_time = state.get('last_switch_time', [])
            for i, t in enumerate(last_switch_time):
                if i < len(self._last_switch_time):
                    self._last_switch_time[i] = t

            last_weights = state.get('last_weights', [])
            for i, w in enumerate(last_weights):
                if i < len(self._last_weights):
                    self._last_weights[i] = w

            self._switch_count = state.get('switch_count', 0)
            self._last_schedule_time = state.get('last_schedule_time', 0.0)

            return True
        except Exception as e:
            log.warning(f"[FrequencyScheduler] load_state 失败: {e}")
            return False


class AdaptiveFrequencyController:
    """
    自适应频率控制器
    
    根据 global_hotspot 动态调整频率配置
    """
    
    def __init__(self, base_config: Optional[FrequencyConfig] = None):
        self.base_config = base_config or FrequencyConfig()
        self.current_config = self.base_config
        
        # 配置历史
        self._config_history: List[Tuple[float, FrequencyConfig]] = []
    
    def adapt(self, global_hotspot: float, timestamp: float) -> FrequencyConfig:
        """
        根据全局热点调整频率配置
        
        逻辑:
        - hotspot 高: 提高所有档位的频率
        - hotspot 低: 降低所有档位的频率
        """
        config = FrequencyConfig()
        
        if global_hotspot > 0.7:
            # 高热点: 激进模式
            config.low_interval = self.base_config.low_interval * 0.5
            config.medium_interval = self.base_config.medium_interval * 0.5
            config.high_interval = self.base_config.high_interval * 0.5
            config.cooldown = self.base_config.cooldown * 0.5
        elif global_hotspot > 0.4:
            # 中等热点: 标准模式
            config = self.base_config
        else:
            # 低热点: 保守模式
            config.low_interval = self.base_config.low_interval * 2.0
            config.medium_interval = self.base_config.medium_interval * 2.0
            config.high_interval = self.base_config.high_interval * 2.0
            config.cooldown = self.base_config.cooldown * 2.0
        
        self.current_config = config
        self._config_history.append((timestamp, config))
        
        return config
    
    def get_config(self) -> FrequencyConfig:
        """获取当前配置"""
        return self.current_config