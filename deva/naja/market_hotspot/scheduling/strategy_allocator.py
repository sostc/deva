"""
Strategy Allocation & Control Module - 策略分配与调节

功能:
- 三层作用域策略: Global / Block / Symbol
- 策略动态加载/卸载
- 参数连续控制
- 策略启停机制
- DecisionHotspot 决策型热点集成

架构:
Hotspot = "势" (资源流向)
Strategy = "术" (如何利用资源)
DecisionHotspot = "决" (何时押注，押多少)
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
    BLOCK = "block"
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
    min_hotspot: float = 0.0      # 最小热点要求
    max_hotspot: float = 1.0      # 最大热点限制
    
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

    async def on_activate(self):
        """激活时调用（子类可覆盖）"""
        pass

    async def on_deactivate(self):
        """停用时调用（子类可覆盖）"""
        pass

    async def execute(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """执行策略（子类必须实现）"""
        return None
    
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
    1. 根据热点分配策略
    2. 动态加载/卸载策略
    3. 参数连续控制
    4. 策略启停管理
    5. DecisionHotspot 决策热点调制
    """

    def __init__(
        self,
        registry: Optional[StrategyRegistry] = None,
        max_strategies: int = 100
    ):
        self.registry = registry or StrategyRegistry()
        self.max_strategies = max_strategies

        self._active_strategies: Set[str] = set()
        self._strategy_params: Dict[str, StrategyParams] = {}

        self._allocation_history: List[Dict] = []

        self._param_mappers: Dict[str, Callable[[float], Any]] = {
            'threshold': self._map_threshold,
            'window': self._map_window,
            'position_size': self._map_position_size,
            'holding_time': self._map_holding_time,
            'risk_limit': self._map_risk_limit
        }

        self._decision_hotspot = None

    def set_decision_hotspot(self, decision_hotspot):
        """
        设置决策热点实例

        Args:
            decision_hotspot: DecisionHotspot 实例
        """
        self._decision_hotspot = decision_hotspot

    def get_decision_hotspot(self):
        """获取决策热点实例"""
        return self._decision_hotspot

    def _get_alpha(self) -> float:
        """获取策略准确性因子 α"""
        if self._decision_hotspot is None:
            return 1.0
        return self._decision_hotspot.compute_alpha(strategy_performance=0.5)

    def _get_temperature(self) -> float:
        """获取温度参数 T"""
        if self._decision_hotspot is None:
            return 1.0
        return self._decision_hotspot.compute_temperature()

    def _get_courage(self) -> float:
        """获取胆识因子（基于温度）"""
        T = self._get_temperature()
        return 2.0 - T

    def allocate(
        self,
        global_hotspot: float,
        block_hotspot: Dict[str, float],
        symbol_weights: Dict[str, float],
        timestamp: float
    ) -> Dict[str, Any]:
        """
        执行策略分配

        DecisionHotspot 调制:
        - α (策略准确性) 影响 position_size
        - T (温度/胆识) 影响 position_size 和 risk_limit
        - courage 影响总体的激进程度

        Returns:
            {
                'global': [strategy_ids...],
                'block': {block_id: [strategy_ids...]},
                'symbol': {symbol: [strategy_ids...]},
                'params': {strategy_id: StrategyParams},
                'decision': {alpha, temperature, courage}
            }
        """
        α = self._get_alpha()
        T = self._get_temperature()
        courage = self._get_courage()

        allocation = {
            'global': [],
            'block': {},
            'symbol': {},
            'params': {},
            'decision': {
                'alpha': α,
                'temperature': T,
                'courage': courage,
            }
        }
        
        # 1. 全局策略分配
        global_strategies = self._allocate_global_strategies(global_hotspot)
        allocation['global'] = [s.config.strategy_id for s in global_strategies]
        
        # 2. 题材策略分配
        for block_id, hotspot in block_hotspot.items():
            block_strategies = self._allocate_block_strategies(
                block_id, hotspot, global_hotspot
            )
            allocation['block'][block_id] = [
                s.config.strategy_id for s in block_strategies
            ]
        
        # 3. 个股策略分配
        top_symbols = sorted(
            symbol_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )[:50]  # 只关注前50
        
        for symbol, weight in top_symbols:
            symbol_strategies = self._allocate_symbol_strategies(
                symbol, weight, global_hotspot
            )
            allocation['symbol'][symbol] = [
                s.config.strategy_id for s in symbol_strategies
            ]
        
        # 4. 参数调节
        for strategy in self.registry.get_all():
            params = self._adjust_params(
                strategy,
                global_hotspot,
                block_hotspot,
                symbol_weights
            )
            allocation['params'][strategy.config.strategy_id] = params
            self._strategy_params[strategy.config.strategy_id] = params
        
        # 记录历史
        self._allocation_history.append({
            'timestamp': timestamp,
            'allocation': allocation,
            'global_hotspot': global_hotspot
        })
        
        return allocation
    
    def _allocate_global_strategies(
        self,
        global_hotspot: float
    ) -> List[Strategy]:
        """分配全局策略"""
        strategies = self.registry.get_by_scope(StrategyScope.GLOBAL)
        allocated = []
        
        for strategy in strategies:
            if self._should_activate(strategy, global_hotspot, {}):
                allocated.append(strategy)
                if strategy.config.strategy_id not in self._active_strategies:
                    self._activate_strategy(strategy)
            else:
                if strategy.config.strategy_id in self._active_strategies:
                    self._deactivate_strategy(strategy)
        
        return allocated
    
    def _allocate_block_strategies(
        self,
        block_id: str,
        block_hotspot: float,
        global_hotspot: float
    ) -> List[Strategy]:
        """分配题材策略"""
        strategies = self.registry.get_by_scope(StrategyScope.BLOCK)
        allocated = []

        for strategy in strategies:
            # 题材策略需要同时满足全局和题材热点
            effective_hotspot = (global_hotspot + block_hotspot) / 2

            if self._should_activate(strategy, effective_hotspot, {'block': block_id}):
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
        global_hotspot: float
    ) -> List[Strategy]:
        """分配个股策略"""
        strategies = self.registry.get_by_scope(StrategyScope.SYMBOL)
        allocated = []
        
        for strategy in strategies:
            # 个股策略受全局热点和个股权重共同影响
            effective_hotspot = (global_hotspot + min(symbol_weight / 3, 1.0)) / 2
            
            if self._should_activate(strategy, effective_hotspot, {'symbol': symbol}):
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
        hotspot: float,
        context: Dict[str, Any]
    ) -> bool:
        """判断是否应该激活策略"""
        config = strategy.config
        
        # 检查热点范围
        if hotspot < config.min_hotspot or hotspot > config.max_hotspot:
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
        global_hotspot: float,
        block_hotspot: Dict[str, float],
        symbol_weights: Dict[str, float]
    ) -> StrategyParams:
        """
        根据热点和 DecisionHotspot 调整策略参数

        DecisionHotspot 调制:
        - hotspot ↑ → threshold ↓ (更容易触发)
        - hotspot ↑ → position_size ↑
        - hotspot ↓ → holding_time ↓
        - hotspot ↑ → risk_limit ↑ (更宽松)
        - α (策略准确性) ↑ → position_size ↑ (更自信)
        - courage ↑ → position_size ↑, risk_limit ↑ (更激进)
        """
        base_params = strategy.config.params

        if strategy.config.scope == StrategyScope.GLOBAL:
            effective_hotspot = global_hotspot
        elif strategy.config.scope == StrategyScope.BLOCK:
            if block_hotspot:
                values = [v for v in block_hotspot.values() if isinstance(v, (int, float)) and not np.isnan(v) and not np.isinf(v)]
                effective_hotspot = np.mean(values) if values else global_hotspot
            else:
                effective_hotspot = global_hotspot
        else:
            effective_hotspot = global_hotspot

        α = self._get_alpha()
        courage = self._get_courage()

        hotspot_factor = effective_hotspot
        confidence_factor = α
        courage_factor = courage

        position_size_base = self._map_position_size(hotspot_factor)
        position_size = position_size_base * confidence_factor * (0.8 + 0.4 * courage_factor)

        risk_limit_base = self._map_risk_limit(hotspot_factor)
        risk_limit = risk_limit_base * (0.8 + 0.4 * courage_factor)

        new_params = StrategyParams(
            threshold=self._param_mappers['threshold'](effective_hotspot),
            window=int(self._param_mappers['window'](effective_hotspot)),
            position_size=min(position_size, 0.3),
            holding_time=int(self._param_mappers['holding_time'](effective_hotspot)),
            risk_limit=min(risk_limit, 0.15)
        )

        strategy.update_params(new_params)

        return new_params
    
    def _map_threshold(self, hotspot: float) -> float:
        """阈值映射: hotspot ↑ → threshold ↓"""
        # hotspot 0 -> threshold 0.7
        # hotspot 1 -> threshold 0.3
        return 0.7 - hotspot * 0.4
    
    def _map_window(self, hotspot: float) -> int:
        """窗口映射: hotspot ↑ → window ↓ (更敏感)"""
        # hotspot 0 -> window 20
        # hotspot 1 -> window 5
        return int(20 - hotspot * 15)
    
    def _map_position_size(self, hotspot: float) -> float:
        """仓位映射: hotspot ↑ → position_size ↑"""
        # hotspot 0 -> position_size 0.05
        # hotspot 1 -> position_size 0.2
        return 0.05 + hotspot * 0.15
    
    def _map_holding_time(self, hotspot: float) -> int:
        """持仓周期映射: hotspot ↓ → holding_time ↓"""
        # hotspot 0 -> holding_time 3
        # hotspot 1 -> holding_time 10
        return int(3 + hotspot * 7)
    
    def _map_risk_limit(self, hotspot: float) -> float:
        """风险限制映射: hotspot ↑ → risk_limit ↑"""
        # hotspot 0 -> risk_limit 0.03 (严格)
        # hotspot 1 -> risk_limit 0.08 (宽松)
        return 0.03 + hotspot * 0.05
    
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
            'decision': {
                'alpha': self._get_alpha(),
                'temperature': self._get_temperature(),
                'courage': self._get_courage(),
            },
            'by_scope': {
                'global': len([s for s in self._active_strategies
                              if self.registry.get(s) and
                              self.registry.get(s).config.scope == StrategyScope.GLOBAL]),
                'block': len([s for s in self._active_strategies
                              if self.registry.get(s) and
                              self.registry.get(s).config.scope == StrategyScope.BLOCK]),
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