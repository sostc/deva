"""
Strategy Allocation & Control Module - 策略分配与调节

功能:
- 三层作用域策略: Global / Sector / Symbol
- 策略动态加载/卸载
- 参数连续控制
- 策略启停机制

架构:
Attention = "势" (资源流向)
Strategy = "术" (如何利用资源)
"""

import numpy as np
from typing import Dict, List, Optional, Set, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import time
import asyncio
from abc import ABC, abstractmethod


class StrategyScope(Enum):
    """策略作用域"""
    GLOBAL = "global"
    SECTOR = "sector"
    SYMBOL = "symbol"


class StrategyType(Enum):
    """策略类型"""
    OBSERVATION = "observation"    # 观测型/低频
    TREND = "trend"                # 趋势型
    EVENT_DRIVEN = "event_driven"  # 事件驱动/高频
    RISK_CONTROL = "risk_control"  # 风控型


@dataclass
class StrategyParams:
    """策略参数"""
    threshold: float = 0.5          # 触发阈值
    window: int = 10                # 观察窗口
    position_size: float = 0.1      # 仓位比例
    holding_time: int = 5           # 持仓周期(分钟)
    risk_limit: float = 0.05        # 风险约束(止损)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'threshold': self.threshold,
            'window': self.window,
            'position_size': self.position_size,
            'holding_time': self.holding_time,
            'risk_limit': self.risk_limit
        }


@dataclass
class StrategyConfig:
    """策略配置"""
    strategy_id: str
    name: str
    scope: StrategyScope
    strategy_type: StrategyType
    params: StrategyParams = field(default_factory=StrategyParams)
    
    # 激活条件
    min_attention: float = 0.0      # 最小注意力要求
    max_attention: float = 1.0      # 最大注意力限制
    
    # 依赖
    depends_on: List[str] = field(default_factory=list)
    
    # 优先级
    priority: int = 0


class Strategy(ABC):
    """策略基类"""
    
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.is_active = False
        self.state: Dict[str, Any] = {}
        self.last_execution_time = 0.0
        self.execution_count = 0
    
    @abstractmethod
    async def on_activate(self):
        """激活时调用"""
        pass
    
    @abstractmethod
    async def on_deactivate(self):
        """停用时调用"""
        pass
    
    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """执行策略"""
        pass
    
    def update_params(self, params: StrategyParams):
        """更新参数"""
        self.config.params = params
    
    def on(self):
        """启用策略"""
        self.is_active = True
    
    def off(self):
        """停用策略"""
        self.is_active = False
    
    def get_status(self) -> Dict[str, Any]:
        """获取策略状态"""
        return {
            'strategy_id': self.config.strategy_id,
            'name': self.config.name,
            'is_active': self.is_active,
            'scope': self.config.scope.value,
            'type': self.config.strategy_type.value,
            'execution_count': self.execution_count,
            'last_execution': self.last_execution_time
        }


class StrategyRegistry:
    """策略注册表"""
    
    def __init__(self):
        self._strategies: Dict[str, Strategy] = {}
        self._configs: Dict[str, StrategyConfig] = {}
        self._factories: Dict[str, Callable[[StrategyConfig], Strategy]] = {}
    
    def register_factory(
        self,
        strategy_type: str,
        factory: Callable[[StrategyConfig], Strategy]
    ):
        """注册策略工厂"""
        self._factories[strategy_type] = factory
    
    def create_strategy(self, config: StrategyConfig) -> Optional[Strategy]:
        """创建策略实例"""
        factory = self._factories.get(config.strategy_type.value)
        if factory:
            return factory(config)
        return None
    
    def register(self, strategy: Strategy):
        """注册策略实例"""
        self._strategies[strategy.config.strategy_id] = strategy
        self._configs[strategy.config.strategy_id] = strategy.config
    
    def unregister(self, strategy_id: str):
        """注销策略"""
        if strategy_id in self._strategies:
            del self._strategies[strategy_id]
        if strategy_id in self._configs:
            del self._configs[strategy_id]
    
    def get(self, strategy_id: str) -> Optional[Strategy]:
        """获取策略"""
        return self._strategies.get(strategy_id)
    
    def get_all(self) -> List[Strategy]:
        """获取所有策略"""
        return list(self._strategies.values())
    
    def get_by_scope(self, scope: StrategyScope) -> List[Strategy]:
        """获取指定作用域的策略"""
        return [
            s for s in self._strategies.values()
            if s.config.scope == scope
        ]
    
    def get_by_type(self, strategy_type: StrategyType) -> List[Strategy]:
        """获取指定类型的策略"""
        return [
            s for s in self._strategies.values()
            if s.config.strategy_type == strategy_type
        ]


class StrategyAllocator:
    """
    策略分配器
    
    核心功能:
    1. 根据注意力分配策略
    2. 动态加载/卸载策略
    3. 参数连续控制
    4. 策略启停管理
    """
    
    def __init__(
        self,
        registry: Optional[StrategyRegistry] = None,
        max_strategies: int = 100
    ):
        self.registry = registry or StrategyRegistry()
        self.max_strategies = max_strategies
        
        # 当前分配
        self._active_strategies: Set[str] = set()
        self._strategy_params: Dict[str, StrategyParams] = {}
        
        # 历史记录
        self._allocation_history: List[Dict] = []
        
        # 参数映射函数
        self._param_mappers: Dict[str, Callable[[float], Any]] = {
            'threshold': self._map_threshold,
            'window': self._map_window,
            'position_size': self._map_position_size,
            'holding_time': self._map_holding_time,
            'risk_limit': self._map_risk_limit
        }
    
    def allocate(
        self,
        global_attention: float,
        sector_attention: Dict[str, float],
        symbol_weights: Dict[str, float],
        timestamp: float
    ) -> Dict[str, Any]:
        """
        执行策略分配
        
        Returns:
            {
                'global': [strategy_ids...],
                'sector': {sector_id: [strategy_ids...]},
                'symbol': {symbol: [strategy_ids...]},
                'params': {strategy_id: StrategyParams}
            }
        """
        allocation = {
            'global': [],
            'sector': {},
            'symbol': {},
            'params': {}
        }
        
        # 1. 全局策略分配
        global_strategies = self._allocate_global_strategies(global_attention)
        allocation['global'] = [s.config.strategy_id for s in global_strategies]
        
        # 2. 板块策略分配
        for sector_id, attention in sector_attention.items():
            sector_strategies = self._allocate_sector_strategies(
                sector_id, attention, global_attention
            )
            allocation['sector'][sector_id] = [
                s.config.strategy_id for s in sector_strategies
            ]
        
        # 3. 个股策略分配
        top_symbols = sorted(
            symbol_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )[:50]  # 只关注前50
        
        for symbol, weight in top_symbols:
            symbol_strategies = self._allocate_symbol_strategies(
                symbol, weight, global_attention
            )
            allocation['symbol'][symbol] = [
                s.config.strategy_id for s in symbol_strategies
            ]
        
        # 4. 参数调节
        for strategy in self.registry.get_all():
            params = self._adjust_params(
                strategy,
                global_attention,
                sector_attention,
                symbol_weights
            )
            allocation['params'][strategy.config.strategy_id] = params
            self._strategy_params[strategy.config.strategy_id] = params
        
        # 记录历史
        self._allocation_history.append({
            'timestamp': timestamp,
            'allocation': allocation,
            'global_attention': global_attention
        })
        
        return allocation
    
    def _allocate_global_strategies(
        self,
        global_attention: float
    ) -> List[Strategy]:
        """分配全局策略"""
        strategies = self.registry.get_by_scope(StrategyScope.GLOBAL)
        allocated = []
        
        for strategy in strategies:
            if self._should_activate(strategy, global_attention, {}):
                allocated.append(strategy)
                if strategy.config.strategy_id not in self._active_strategies:
                    self._activate_strategy(strategy)
            else:
                if strategy.config.strategy_id in self._active_strategies:
                    self._deactivate_strategy(strategy)
        
        return allocated
    
    def _allocate_sector_strategies(
        self,
        sector_id: str,
        sector_attention: float,
        global_attention: float
    ) -> List[Strategy]:
        """分配板块策略"""
        strategies = self.registry.get_by_scope(StrategyScope.SECTOR)
        allocated = []
        
        for strategy in strategies:
            # 板块策略需要同时满足全局和板块注意力
            effective_attention = (global_attention + sector_attention) / 2
            
            if self._should_activate(strategy, effective_attention, {'sector': sector_id}):
                allocated.append(strategy)
                if strategy.config.strategy_id not in self._active_strategies:
                    self._activate_strategy(strategy)
            else:
                if strategy.config.strategy_id in self._active_strategies:
                    self._deactivate_strategy(strategy)
        
        return allocated
    
    def _allocate_symbol_strategies(
        self,
        symbol: str,
        symbol_weight: float,
        global_attention: float
    ) -> List[Strategy]:
        """分配个股策略"""
        strategies = self.registry.get_by_scope(StrategyScope.SYMBOL)
        allocated = []
        
        for strategy in strategies:
            # 个股策略受全局注意力和个股权重共同影响
            effective_attention = (global_attention + min(symbol_weight / 3, 1.0)) / 2
            
            if self._should_activate(strategy, effective_attention, {'symbol': symbol}):
                allocated.append(strategy)
                if strategy.config.strategy_id not in self._active_strategies:
                    self._activate_strategy(strategy)
            else:
                if strategy.config.strategy_id in self._active_strategies:
                    self._deactivate_strategy(strategy)
        
        return allocated
    
    def _should_activate(
        self,
        strategy: Strategy,
        attention: float,
        context: Dict[str, Any]
    ) -> bool:
        """判断是否应该激活策略"""
        config = strategy.config
        
        # 检查注意力范围
        if attention < config.min_attention or attention > config.max_attention:
            return False
        
        # 检查依赖
        for dep_id in config.depends_on:
            if dep_id not in self._active_strategies:
                return False
        
        return True
    
    def _activate_strategy(self, strategy: Strategy):
        """激活策略"""
        strategy.on()
        self._active_strategies.add(strategy.config.strategy_id)
        
        # 异步调用激活回调
        try:
            asyncio.create_task(strategy.on_activate())
        except:
            pass
    
    def _deactivate_strategy(self, strategy: Strategy):
        """停用策略"""
        strategy.off()
        self._active_strategies.discard(strategy.config.strategy_id)
        
        # 异步调用停用回调
        try:
            asyncio.create_task(strategy.on_deactivate())
        except:
            pass
    
    def _adjust_params(
        self,
        strategy: Strategy,
        global_attention: float,
        sector_attention: Dict[str, float],
        symbol_weights: Dict[str, float]
    ) -> StrategyParams:
        """
        根据注意力调整策略参数
        
        规则:
        - attention ↑ → threshold ↓ (更容易触发)
        - attention ↑ → position_size ↑
        - attention ↓ → holding_time ↓
        - attention ↑ → risk_limit ↑ (更宽松)
        """
        base_params = strategy.config.params
        
        # 计算有效注意力
        if strategy.config.scope == StrategyScope.GLOBAL:
            effective_attention = global_attention
        elif strategy.config.scope == StrategyScope.SECTOR:
            if sector_attention:
                # 过滤异常值
                values = [v for v in sector_attention.values() if isinstance(v, (int, float)) and not np.isnan(v) and not np.isinf(v)]
                effective_attention = np.mean(values) if values else global_attention
            else:
                effective_attention = global_attention
        else:
            effective_attention = global_attention
        
        # 应用映射
        new_params = StrategyParams(
            threshold=self._param_mappers['threshold'](effective_attention),
            window=int(self._param_mappers['window'](effective_attention)),
            position_size=self._param_mappers['position_size'](effective_attention),
            holding_time=int(self._param_mappers['holding_time'](effective_attention)),
            risk_limit=self._param_mappers['risk_limit'](effective_attention)
        )
        
        # 更新策略参数
        strategy.update_params(new_params)
        
        return new_params
    
    def _map_threshold(self, attention: float) -> float:
        """阈值映射: attention ↑ → threshold ↓"""
        # attention 0 -> threshold 0.7
        # attention 1 -> threshold 0.3
        return 0.7 - attention * 0.4
    
    def _map_window(self, attention: float) -> int:
        """窗口映射: attention ↑ → window ↓ (更敏感)"""
        # attention 0 -> window 20
        # attention 1 -> window 5
        return int(20 - attention * 15)
    
    def _map_position_size(self, attention: float) -> float:
        """仓位映射: attention ↑ → position_size ↑"""
        # attention 0 -> position_size 0.05
        # attention 1 -> position_size 0.2
        return 0.05 + attention * 0.15
    
    def _map_holding_time(self, attention: float) -> int:
        """持仓周期映射: attention ↓ → holding_time ↓"""
        # attention 0 -> holding_time 3
        # attention 1 -> holding_time 10
        return int(3 + attention * 7)
    
    def _map_risk_limit(self, attention: float) -> float:
        """风险限制映射: attention ↑ → risk_limit ↑"""
        # attention 0 -> risk_limit 0.03 (严格)
        # attention 1 -> risk_limit 0.08 (宽松)
        return 0.03 + attention * 0.05
    
    def get_active_strategies(self) -> List[str]:
        """获取当前激活的策略列表"""
        return list(self._active_strategies)
    
    def get_strategy_params(self, strategy_id: str) -> Optional[StrategyParams]:
        """获取策略参数"""
        return self._strategy_params.get(strategy_id)
    
    def control_scope(self, scope: StrategyScope, action: str):
        """
        控制整个作用域的策略
        
        action: 'on' | 'off'
        """
        strategies = self.registry.get_by_scope(scope)
        for strategy in strategies:
            if action == 'on':
                self._activate_strategy(strategy)
            else:
                self._deactivate_strategy(strategy)
    
    def control_type(self, strategy_type: StrategyType, action: str):
        """
        控制特定类型的策略
        
        action: 'on' | 'off'
        """
        strategies = self.registry.get_by_type(strategy_type)
        for strategy in strategies:
            if action == 'on':
                self._activate_strategy(strategy)
            else:
                self._deactivate_strategy(strategy)
    
    def get_allocation_summary(self) -> Dict[str, Any]:
        """获取分配摘要"""
        return {
            'active_count': len(self._active_strategies),
            'active_strategies': list(self._active_strategies),
            'by_scope': {
                'global': len([s for s in self._active_strategies 
                              if self.registry.get(s) and 
                              self.registry.get(s).config.scope == StrategyScope.GLOBAL]),
                'sector': len([s for s in self._active_strategies 
                              if self.registry.get(s) and 
                              self.registry.get(s).config.scope == StrategyScope.SECTOR]),
                'symbol': len([s for s in self._active_strategies 
                              if self.registry.get(s) and 
                              self.registry.get(s).config.scope == StrategyScope.SYMBOL])
            }
        }
    
    def reset(self):
        """重置分配器"""
        for strategy_id in list(self._active_strategies):
            strategy = self.registry.get(strategy_id)
            if strategy:
                self._deactivate_strategy(strategy)
        
        self._active_strategies.clear()
        self._strategy_params.clear()
        self._allocation_history.clear()