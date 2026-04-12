"""
Module 9: Hotspot Budget System - 热点预算系统

核心能力:
- 限制系统资源使用 (CPU/GPU/数据流量)
- 限制最多 N 个 symbol 进入高频模式
- 限制最多 M 个进入 PyTorch 处理
- 当市场全面活跃时，防止计算爆炸

核心概念:
- Hotspot Budget: 总预算池
- Budget Allocation: 预算分配
- Top-K Selection: 按 hotspot_score 排序截断
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import time


class BudgetLevel(Enum):
    """预算等级"""
    TIER1 = 1  # 高频计算 (GPU/实时)
    TIER2 = 2  # 中频计算 (CPU/准实时)
    TIER3 = 3  # 低频计算 (异步/批处理)


@dataclass
class BudgetConfig:
    """预算配置"""
    max_tier1_symbols: int = 20
    max_tier2_symbols: int = 100
    max_tier3_symbols: int = 500
    
    tier1_budget_per_symbol: float = 1.0
    tier2_budget_per_symbol: float = 0.5
    tier3_budget_per_symbol: float = 0.1
    
    total_budget: float = 50.0
    
    enable_budget_enforcement: bool = True
    enable_gpu_budget: bool = True
    
    gpu_max_symbols: int = 10
    gpu_memory_budget_mb: float = 2048.0


@dataclass
class BudgetAllocation:
    """预算分配结果"""
    tier1_symbols: List[str]
    tier2_symbols: List[str]
    tier3_symbols: List[str]
    
    tier1_total_cost: float
    tier2_total_cost: float
    tier3_total_cost: float
    
    total_cost: float
    budget_utilization: float
    
    rejected_symbols: List[str]
    timestamp: float


class ResourceMonitor:
    """
    资源监控器
    
    监控:
    - CPU 使用率
    - GPU 使用率/显存
    - 数据流量
    """
    
    def __init__(self):
        self._last_cpu_check = 0.0
        self._last_gpu_check = 0.0
        
        self._cpu_usage: float = 0.0
        self._gpu_memory_used: float = 0.0
        self._gpu_memory_total: float = 0.0
        
        self._check_interval = 1.0
        
    def check_cpu(self) -> float:
        """检查 CPU 使用率"""
        current_time = time.time()
        
        if current_time - self._last_cpu_check < self._check_interval:
            return self._cpu_usage
        
        try:
            import psutil
            self._cpu_usage = psutil.cpu_percent(interval=0.1) / 100.0
        except ImportError:
            self._cpu_usage = 0.5
        
        self._last_cpu_check = current_time
        return self._cpu_usage
    
    def check_gpu(self) -> Tuple[float, float]:
        """
        检查 GPU 使用情况
        
        Returns:
            (memory_used_mb, memory_total_mb)
        """
        current_time = time.time()
        
        if current_time - self._last_gpu_check < self._check_interval:
            return self._gpu_memory_used, self._gpu_memory_total
        
        try:
            import torch
            if torch.cuda.is_available():
                self._gpu_memory_used = torch.cuda.memory_allocated() / 1024**2
                self._gpu_memory_total = torch.cuda.get_device_properties(0).total_memory / 1024**2
            else:
                self._gpu_memory_used = 0.0
                self._gpu_memory_total = 0.0
        except ImportError:
            self._gpu_memory_used = 0.0
            self._gpu_memory_total = 0.0
        
        self._last_gpu_check = current_time
        return self._gpu_memory_used, self._gpu_memory_total
    
    def get_load_factor(self) -> float:
        """获取系统负载因子 (0-1)"""
        cpu = self.check_cpu()
        
        gpu_used, gpu_total = self.check_gpu()
        gpu_usage = gpu_used / gpu_total if gpu_total > 0 else 0.0
        
        return max(cpu, gpu_usage)
    
    def can_allocate_gpu(self, estimated_memory_mb: float) -> bool:
        """检查是否可以分配 GPU 内存"""
        gpu_used, gpu_total = self.check_gpu()
        
        return (gpu_used + estimated_memory_mb) < gpu_total * 0.9
    
    def reset(self):
        """重置"""
        self._cpu_usage = 0.0
        self._gpu_memory_used = 0.0
        self._gpu_memory_total = 0.0


class TopKBudgetAllocator:
    """
    Top-K 预算分配器
    
    核心逻辑:
    1. 按 hotspot_score 排序
    2. 从高到低分配预算
    3. 直到预算耗尽
    4. 剩余的 symbol 被拒绝
    """
    
    def __init__(self, config: Optional[BudgetConfig] = None):
        self.config = config or BudgetConfig()
        
        self._allocation_history: List[BudgetAllocation] = []
        self._symbol_tiers: Dict[str, BudgetLevel] = {}
        
    def allocate(
        self,
        symbol_scores: Dict[str, float],
        symbol_metadata: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> BudgetAllocation:
        """
        执行预算分配
        
        Args:
            symbol_scores: {symbol: hotspot_score}
            symbol_metadata: {symbol: {'gpu_needed': bool, 'estimated_cost': float}}
            
        Returns:
            BudgetAllocation
        """
        if not symbol_scores:
            return BudgetAllocation(
                tier1_symbols=[],
                tier2_symbols=[],
                tier3_symbols=[],
                tier1_total_cost=0.0,
                tier2_total_cost=0.0,
                tier3_total_cost=0.0,
                total_cost=0.0,
                budget_utilization=0.0,
                rejected_symbols=[],
                timestamp=time.time()
            )
        
        sorted_symbols = sorted(
            symbol_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        tier1 = []
        tier2 = []
        tier3 = []
        rejected = []
        
        tier1_cost = 0.0
        tier2_cost = 0.0
        tier3_cost = 0.0
        
        total_cost = 0.0
        
        gpu_count = 0
        
        for symbol, score in sorted_symbols:
            estimated_cost = self._estimate_cost(symbol, symbol_metadata)
            
            if len(tier1) < self.config.max_tier1_symbols:
                tier1.append(symbol)
                tier1_cost += self.config.tier1_budget_per_symbol * estimated_cost
                self._symbol_tiers[symbol] = BudgetLevel.TIER1
                gpu_count += 1
                
            elif len(tier2) < self.config.max_tier2_symbols:
                tier2.append(symbol)
                tier2_cost += self.config.tier2_budget_per_symbol * estimated_cost
                self._symbol_tiers[symbol] = BudgetLevel.TIER2
                
            elif len(tier3) < self.config.max_tier3_symbols:
                tier3.append(symbol)
                tier3_cost += self.config.tier3_budget_per_symbol * estimated_cost
                self._symbol_tiers[symbol] = BudgetLevel.TIER3
                
            else:
                rejected.append(symbol)
                self._symbol_tiers[symbol] = BudgetLevel.TIER3
            
            total_cost = tier1_cost + tier2_cost + tier3_cost
            
            if total_cost >= self.config.total_budget:
                break
        
        total_cost = tier1_cost + tier2_cost + tier3_cost
        utilization = total_cost / self.config.total_budget if self.config.total_budget > 0 else 0
        
        allocation = BudgetAllocation(
            tier1_symbols=tier1,
            tier2_symbols=tier2,
            tier3_symbols=tier3,
            tier1_total_cost=tier1_cost,
            tier2_total_cost=tier2_cost,
            tier3_total_cost=tier3_cost,
            total_cost=total_cost,
            budget_utilization=utilization,
            rejected_symbols=rejected,
            timestamp=time.time()
        )
        
        self._allocation_history.append(allocation)
        
        return allocation
    
    def _estimate_cost(
        self,
        symbol: str,
        metadata: Optional[Dict[str, Dict[str, Any]]]
    ) -> float:
        """估算 symbol 的计算成本"""
        if metadata and symbol in metadata:
            meta = metadata[symbol]
            return meta.get('estimated_cost', 1.0)
        return 1.0
    
    def get_symbol_tier(self, symbol: str) -> BudgetLevel:
        """获取 symbol 的预算等级"""
        return self._symbol_tiers.get(symbol, BudgetLevel.TIER3)
    
    def get_symbols_by_tier(self, tier: BudgetLevel) -> List[str]:
        """获取指定等级的所有 symbols"""
        return [
            s for s, t in self._symbol_tiers.items()
            if t == tier
        ]
    
    def get_allocation_summary(self) -> Dict[str, Any]:
        """获取分配摘要"""
        if not self._allocation_history:
            return {}
        
        last = self._allocation_history[-1]
        
        return {
            'tier1_count': len(last.tier1_symbols),
            'tier2_count': len(last.tier2_symbols),
            'tier3_count': len(last.tier3_symbols),
            'total_cost': last.total_cost,
            'budget_utilization': last.budget_utilization,
            'rejected_count': len(last.rejected_symbols)
        }
    
    def reset(self):
        """重置"""
        self._symbol_tiers.clear()
        self._allocation_history.clear()


class AdaptiveBudgetController:
    """
    自适应预算控制器
    
    根据系统负载动态调整预算配置
    """
    
    def __init__(
        self,
        base_config: BudgetConfig,
        resource_monitor: Optional[ResourceMonitor] = None
    ):
        self.base_config = base_config
        self.current_config = base_config
        self.resource_monitor = resource_monitor or ResourceMonitor()
        
        self._config_history: List[Tuple[float, BudgetConfig]] = []
        
    def adapt(
        self,
        current_load: Optional[float] = None
    ) -> BudgetConfig:
        """
        根据当前负载调整预算配置
        
        Args:
            current_load: 当前系统负载 (0-1)，如果 None 则自动检测
            
        Returns:
            调整后的 BudgetConfig
        """
        if current_load is None:
            current_load = self.resource_monitor.get_load_factor()
        
        config = BudgetConfig(
            max_tier1_symbols=self.base_config.max_tier1_symbols,
            max_tier2_symbols=self.base_config.max_tier2_symbols,
            max_tier3_symbols=self.base_config.max_tier3_symbols,
            tier1_budget_per_symbol=self.base_config.tier1_budget_per_symbol,
            tier2_budget_per_symbol=self.base_config.tier2_budget_per_symbol,
            tier3_budget_per_symbol=self.base_config.tier3_budget_per_symbol,
            total_budget=self.base_config.total_budget,
            enable_budget_enforcement=self.base_config.enable_budget_enforcement,
            enable_gpu_budget=self.base_config.enable_gpu_budget,
            gpu_max_symbols=self.base_config.gpu_max_symbols,
            gpu_memory_budget_mb=self.base_config.gpu_memory_budget_mb
        )
        
        if current_load > 0.8:
            config.max_tier1_symbols = max(5, int(self.base_config.max_tier1_symbols * 0.5))
            config.max_tier2_symbols = max(50, int(self.base_config.max_tier2_symbols * 0.7))
            config.total_budget = self.base_config.total_budget * 0.7
            config.gpu_max_symbols = max(3, int(self.base_config.gpu_max_symbols * 0.5))
            
        elif current_load > 0.6:
            config.max_tier1_symbols = max(10, int(self.base_config.max_tier1_symbols * 0.75))
            config.max_tier2_symbols = max(75, int(self.base_config.max_tier2_symbols * 0.85))
            config.total_budget = self.base_config.total_budget * 0.85
            config.gpu_max_symbols = max(5, int(self.base_config.gpu_max_symbols * 0.75))
            
        elif current_load < 0.3:
            config.max_tier1_symbols = min(30, int(self.base_config.max_tier1_symbols * 1.2))
            config.max_tier2_symbols = min(150, int(self.base_config.max_tier2_symbols * 1.2))
            config.total_budget = self.base_config.total_budget * 1.2
            config.gpu_max_symbols = min(15, int(self.base_config.gpu_max_symbols * 1.2))
        
        self.current_config = config
        self._config_history.append((time.time(), config))
        
        return config
    
    def get_current_config(self) -> BudgetConfig:
        """获取当前配置"""
        return self.current_config
    
    def reset(self):
        """重置"""
        self.current_config = self.base_config
        self._config_history.clear()


class HotspotBudgetSystem:
    """
    热点预算系统主控制器
    
    整合:
    - ResourceMonitor: 资源监控
    - TopKBudgetAllocator: Top-K 分配
    - AdaptiveBudgetController: 自适应控制
    
    使用方式:
    1. 系统负载高时 → 自动收紧预算
    2. 系统负载低时 → 自动放宽预算
    3. GPU 资源紧张 → 减少 PyTorch 处理
    """
    
    def __init__(
        self,
        config: Optional[BudgetConfig] = None,
        enable_adaptive: bool = True
    ):
        self.config = config or BudgetConfig()
        
        self.resource_monitor = ResourceMonitor()
        self.allocator = TopKBudgetAllocator(self.config)
        self.controller = AdaptiveBudgetController(
            self.config,
            self.resource_monitor
        ) if enable_adaptive else None
        
        self._enabled = True
        self._last_allocation: Optional[BudgetAllocation] = None
        
    def allocate(
        self,
        symbol_scores: Dict[str, float],
        symbol_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
        force_adapt: bool = True
    ) -> BudgetAllocation:
        """
        执行预算分配
        """
        if not self._enabled:
            return BudgetAllocation(
                tier1_symbols=list(symbol_scores.keys())[:self.config.max_tier1_symbols],
                tier2_symbols=list(symbol_scores.keys())[self.config.max_tier1_symbols:self.config.max_tier1_symbols + self.config.max_tier2_symbols],
                tier3_symbols=[],
                tier1_total_cost=0.0,
                tier2_total_cost=0.0,
                tier3_total_cost=0.0,
                total_cost=0.0,
                budget_utilization=0.0,
                rejected_symbols=[],
                timestamp=time.time()
            )
        
        if force_adapt and self.controller:
            self.controller.adapt()
        
        effective_config = (
            self.controller.current_config
            if self.controller
            else self.config
        )
        
        self.allocator.config = effective_config
        
        self._last_allocation = self.allocator.allocate(symbol_scores, symbol_metadata)
        
        return self._last_allocation
    
    def get_tier_symbols(self, tier: BudgetLevel) -> List[str]:
        """获取指定等级的所有 symbols"""
        return self.allocator.get_symbols_by_tier(tier)
    
    def get_high_frequency_symbols(self) -> List[str]:
        """获取高频 symbols (tier1)"""
        return self.get_tier_symbols(BudgetLevel.TIER1)
    
    def get_pytorch_symbols(self) -> List[str]:
        """
        获取应该进入 PyTorch 处理的 symbols
        
        受 GPU 预算限制
        """
        tier1 = self.get_tier_symbols(BudgetLevel.TIER1)
        
        if self.config.enable_gpu_budget:
            gpu_used, gpu_total = self.resource_monitor.check_gpu()
            gpu_available = (self.config.gpu_memory_budget_mb - gpu_used) / 1024
            
            if gpu_available < 1.0:
                return tier1[:self.config.gpu_max_symbols // 2]
            
            return tier1[:self.config.gpu_max_symbols]
        
        return tier1
    
    def get_medium_frequency_symbols(self) -> List[str]:
        """获取中频 symbols (tier2)"""
        return self.get_tier_symbols(BudgetLevel.TIER2)
    
    def get_low_frequency_symbols(self) -> List[str]:
        """获取低频 symbols (tier3 + rejected)"""
        tier3 = self.get_tier_symbols(BudgetLevel.TIER3)
        if self._last_allocation:
            return tier3 + self._last_allocation.rejected_symbols
        return tier3
    
    def is_enabled(self) -> bool:
        """检查是否启用"""
        return self._enabled
    
    def enable(self):
        """启用预算系统"""
        self._enabled = True
    
    def disable(self):
        """禁用预算系统"""
        self._enabled = False
    
    def get_system_load(self) -> float:
        """获取当前系统负载"""
        return self.resource_monitor.get_load_factor()
    
    def get_last_allocation(self) -> Optional[BudgetAllocation]:
        """获取上次分配结果"""
        return self._last_allocation
    
    def get_summary(self) -> Dict[str, Any]:
        """获取系统摘要"""
        return {
            'enabled': self._enabled,
            'system_load': self.get_system_load(),
            'current_config': {
                'max_tier1': self.config.max_tier1_symbols,
                'max_tier2': self.config.max_tier2_symbols,
                'max_tier3': self.config.max_tier3_symbols,
                'total_budget': self.config.total_budget
            },
            'allocation_summary': self.allocator.get_allocation_summary(),
            'gpu_memory_mb': self.resource_monitor.check_gpu()[0]
        }
    
    def reset(self):
        """重置"""
        self.resource_monitor.reset()
        self.allocator.reset()
        if self.controller:
            self.controller.reset()
        self._last_allocation = None
