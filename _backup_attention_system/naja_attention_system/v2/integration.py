"""
V2 Integration Layer - v1 到 v2 平滑升级集成层

核心目标:
- 支持 v1 → v2 平滑升级
- 不影响现有 v1 系统运行
- 新模块按需启用
- 渐进式接入

架构:
数据 →
    Attention (v1) →
        Prediction (v2 Module 7) →
            Propagation (v2 Module 10) →
                Budget (v2 Module 9) →
                    双引擎 (v1) →
                        Feedback (v2 Module 8) →
                            Strategy Learning (v2 Module 11) →
                                回流 Attention
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
import time

from ..attention_system import (
    AttentionSystem,
    AttentionSystemConfig,
    MarketSnapshot
)
from ..sector_attention import SectorConfig

from .predictive_attention import PredictiveAttentionEngine
from .feedback_loop import AttentionFeedbackLoop
from .budget_system import AttentionBudgetSystem, BudgetConfig, BudgetLevel
from .propagation import AttentionPropagation
from .strategy_learning import StrategyLearning


@dataclass
class V2Config:
    """V2 扩展配置"""
    enable_predictive: bool = True
    enable_feedback: bool = True
    enable_budget: bool = True
    enable_propagation: bool = False
    enable_strategy_learning: bool = False
    
    alpha: float = 0.7
    beta: float = 0.3
    
    budget_max_tier1: int = 20
    budget_max_tier2: int = 100
    budget_total: float = 50.0
    
    propagation_mode: str = "single_step"
    
    feedback_store_path: Optional[str] = None


class V2EnhancedAttentionSystem:
    """
    V2 增强型注意力系统
    
    在 v1 基础上集成 v2 新模块
    支持渐进式升级:
    1. 只启用部分 v2 模块
    2. 保持 v1 核心流程不变
    3. 新模块作为增强层
    """
    
    def __init__(
        self,
        v1_config: Optional[AttentionSystemConfig] = None,
        v2_config: Optional[V2Config] = None
    ):
        self.v2_config = v2_config or V2Config()
        
        self.v1_system = AttentionSystem(v1_config)
        self.v1_initialized = False
        
        if self.v2_config.enable_predictive:
            self.predictive_engine = PredictiveAttentionEngine(
                alpha=self.v2_config.alpha,
                beta=self.v2_config.beta
            )
        
        if self.v2_config.enable_propagation:
            self.propagation = AttentionPropagation(
                propagation_mode=self.v2_config.propagation_mode
            )
        
        if self.v2_config.enable_budget:
            budget_config = BudgetConfig(
                max_tier1_symbols=self.v2_config.budget_max_tier1,
                max_tier2_symbols=self.v2_config.budget_max_tier2,
                total_budget=self.v2_config.budget_total
            )
            self.budget_system = AttentionBudgetSystem(budget_config)
        
        if self.v2_config.enable_feedback:
            self.feedback_loop = AttentionFeedbackLoop(
                store_path=self.v2_config.feedback_store_path
            )
        
        if self.v2_config.enable_strategy_learning:
            self.strategy_learning = StrategyLearning()
        
        self._result_history: List[Dict[str, Any]] = []
        self._last_v2_result: Optional[Dict[str, Any]] = None
        
    def initialize(
        self,
        sectors: List[SectorConfig],
        symbol_sector_map: Dict[str, List[str]]
    ):
        """
        初始化 v1 系统 (向后兼容)
        """
        self.v1_system.initialize(sectors, symbol_sector_map)
        self.v1_initialized = True
        
        if hasattr(self, 'propagation'):
            for sector in sectors:
                self.propagation.register_sector(sector.sector_id)
    
    def process_snapshot(
        self,
        symbols: np.ndarray,
        returns: np.ndarray,
        volumes: np.ndarray,
        prices: np.ndarray,
        sector_ids: np.ndarray,
        timestamp: float,
        pattern_scores: Optional[Dict[str, float]] = None,
        returns_history: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """
        处理市场快照 (v1 + v2 增强)
        
        新流程:
        1. V1 处理 (Global/Sector/Weight/Frequency)
        2. V2 Prediction (如果启用)
        3. V2 Propagation (如果启用)
        4. V2 Budget (如果启用)
        5. 返回综合结果
        """
        if not self.v1_initialized:
            self._auto_initialize(symbols, sector_ids)
        
        v1_result = self.v1_system.process_snapshot(
            symbols, returns, volumes, prices, sector_ids, timestamp
        )
        
        final_attention = v1_result['symbol_weights']
        
        if hasattr(self, 'predictive_engine') and self.v2_config.enable_predictive:
            returns_arr = returns_history if returns_history is not None else returns
            
            base_volumes = np.mean(volumes) if len(volumes) > 0 else 1.0
            volume_ratios = volumes / base_volumes if len(volumes) > 0 else np.ones_like(volumes)
            
            prediction_results = self.predictive_engine.batch_predict(
                symbols=symbols,
                current_attention=final_attention,
                returns=returns_arr,
                volumes=volume_ratios,
                timestamps=np.full(len(symbols), timestamp)
            )
            
            adjusted_attention = {}
            for symbol, (pred_score, final_att) in prediction_results.items():
                adjusted_attention[symbol] = final_att
            
            v1_result['prediction_scores'] = {
                symbol: pred_score
                for symbol, (pred_score, _) in prediction_results.items()
            }
            v1_result['v2_adjusted_attention'] = adjusted_attention
            final_attention = adjusted_attention
        
        if hasattr(self, 'propagation') and self.v2_config.enable_propagation:
            propagated = self.propagation.propagate(
                v1_result['sector_attention'],
                timestamp
            )
            v1_result['propagated_sector_attention'] = propagated
        
        if hasattr(self, 'budget_system') and self.v2_config.enable_budget:
            budget_allocation = self.budget_system.allocate(final_attention)
            v1_result['budget_allocation'] = {
                'tier1': budget_allocation.tier1_symbols,
                'tier2': budget_allocation.tier2_symbols,
                'tier3': budget_allocation.tier3_symbols,
                'utilization': budget_allocation.budget_utilization,
                'rejected': budget_allocation.rejected_symbols
            }
            v1_result['tier_symbols'] = {
                'high_freq': budget_allocation.tier1_symbols,
                'medium_freq': budget_allocation.tier2_symbols,
                'low_freq': budget_allocation.tier3_symbols
            }
            
            v1_result['datasource_control'] = self._get_datasource_control_v2(
                budget_allocation
            )
        
        if hasattr(self, 'strategy_learning') and self.v2_config.enable_strategy_learning:
            available_strategies = list(self.v1_system.strategy_allocator.registry._strategies.keys())
            
            selection = self.strategy_learning.select_strategies(
                global_attention=v1_result['global_attention'],
                sector_attention=v1_result['sector_attention'],
                available_strategies=available_strategies,
                pattern_scores=pattern_scores
            )
            
            v1_result['strategy_selection'] = {
                'selected': selection.selected_strategies,
                'confidence': selection.selection_confidence,
                'market_state': selection.market_state.get_state_name()
            }
        
        v1_result['v2_enabled'] = {
            'predictive': self.v2_config.enable_predictive,
            'feedback': self.v2_config.enable_feedback,
            'budget': self.v2_config.enable_budget,
            'propagation': self.v2_config.enable_propagation,
            'strategy_learning': self.v2_config.enable_strategy_learning
        }
        
        self._last_v2_result = v1_result
        self._result_history.append(v1_result)
        
        return v1_result
    
    def _auto_initialize(
        self,
        symbols: np.ndarray,
        sector_ids: np.ndarray
    ):
        """自动初始化 (当只使用 v2 时)"""
        unique_sectors = np.unique(sector_ids)
        sector_configs = [
            SectorConfig(
                sector_id=str(s),
                name=str(s),
                symbols=set()
            )
            for s in unique_sectors
        ]
        
        symbol_sector_map = {}
        for i, symbol in enumerate(symbols):
            symbol_str = str(symbol)
            sector_list = symbol_sector_map.get(symbol_str, [])
            sector_list.append(str(sector_ids[i]))
            symbol_sector_map[symbol_str] = sector_list
        
        self.initialize(sector_configs, symbol_sector_map)
    
    def _get_datasource_control_v2(self, budget_allocation) -> Dict[str, Any]:
        """获取 v2 版本的 data source 控制"""
        return {
            'high_freq_symbols': budget_allocation.tier1_symbols,
            'medium_freq_symbols': budget_allocation.tier2_symbols,
            'low_freq_symbols': budget_allocation.tier3_symbols,
            'intervals': {
                'high': 1.0,
                'medium': 10.0,
                'low': 60.0
            },
            'budget_utilization': budget_allocation.budget_utilization,
            'timestamp': time.time()
        }
    
    def record_outcome(
        self,
        strategy_id: str,
        symbol: str,
        sector_id: str,
        attention_before: float,
        attention_after: float,
        prediction_score: float,
        action: str,
        pnl: float,
        holding_period: int,
        market_state: str = "unknown",
        volatility: float = 0.0,
        volume_ratio: float = 1.0,
        trend: float = 0.0
    ):
        """
        记录策略执行结果到反馈系统
        """
        if hasattr(self, 'feedback_loop') and self.v2_config.enable_feedback:
            self.feedback_loop.record_outcome(
                strategy_id=strategy_id,
                symbol=symbol,
                sector_id=sector_id,
                attention_before=attention_before,
                attention_after=attention_after,
                prediction_score=prediction_score,
                action=action,
                pnl=pnl,
                holding_period=holding_period,
                market_state=market_state,
                volatility=volatility,
                volume_ratio=volume_ratio,
                trend=trend
            )
        
        if hasattr(self, 'strategy_learning') and self.v2_config.enable_strategy_learning:
            self.strategy_learning.record_outcome(
                strategy_id=strategy_id,
                pnl=pnl,
                holding_time=holding_period
            )
    
    def get_attention_adjustment(self, symbol: str) -> float:
        """获取 symbol 的注意力调整"""
        if hasattr(self, 'feedback_loop') and self.v2_config.enable_feedback:
            if self._last_v2_result:
                attention = self._last_v2_result['symbol_weights'].get(symbol, 0.0)
                prediction = self._last_v2_result.get('prediction_scores', {}).get(symbol, 0.5)
                
                return self.feedback_loop.get_attention_adjustment(
                    symbol=symbol,
                    attention=attention,
                    prediction_score=prediction
                )
        return 1.0
    
    def apply_adjustment(
        self,
        symbol: str,
        attention: float
    ) -> float:
        """应用注意力调整"""
        adjustment = self.get_attention_adjustment(symbol)
        return attention * adjustment
    
    def get_budget_symbols(self) -> Dict[str, List[str]]:
        """获取各预算等级的 symbols"""
        if hasattr(self, 'budget_system') and self.v2_config.enable_budget:
            return {
                'tier1': self.budget_system.get_high_frequency_symbols(),
                'tier2': self.budget_system.get_medium_frequency_symbols(),
                'tier3': self.budget_system.get_low_frequency_symbols()
            }
        return {}
    
    def get_pytorch_symbols(self) -> List[str]:
        """获取应该进入 PyTorch 的 symbols"""
        if hasattr(self, 'budget_system') and self.v2_config.enable_budget:
            return self.budget_system.get_pytorch_symbols()
        return []
    
    def get_effective_patterns(self) -> List[str]:
        """获取有效模式"""
        if hasattr(self, 'feedback_loop') and self.v2_config.enable_feedback:
            return self.feedback_loop.get_effective_patterns()
        return []
    
    def get_ineffective_patterns(self) -> List[str]:
        """获取无效模式"""
        if hasattr(self, 'feedback_loop') and self.v2_config.enable_feedback:
            return self.feedback_loop.get_ineffective_patterns()
        return []
    
    def get_strategy_selection(self) -> Optional[Dict[str, Any]]:
        """获取当前策略选择"""
        if hasattr(self, 'strategy_learning') and self.v2_config.enable_strategy_learning:
            summary = self.strategy_learning.get_selection_summary()
            return summary.get('last_selection')
        return None
    
    def get_system_load(self) -> float:
        """获取系统负载"""
        if hasattr(self, 'budget_system') and self.v2_config.enable_budget:
            return self.budget_system.get_system_load()
        return 0.5
    
    def enable_module(self, module: str):
        """启用 v2 模块"""
        if module == 'predictive':
            self.v2_config.enable_predictive = True
        elif module == 'feedback':
            self.v2_config.enable_feedback = True
        elif module == 'budget':
            self.v2_config.enable_budget = True
        elif module == 'propagation':
            self.v2_config.enable_propagation = True
        elif module == 'strategy_learning':
            self.v2_config.enable_strategy_learning = True
    
    def disable_module(self, module: str):
        """禁用 v2 模块"""
        if module == 'predictive':
            self.v2_config.enable_predictive = False
        elif module == 'feedback':
            self.v2_config.enable_feedback = False
        elif module == 'budget':
            self.v2_config.enable_budget = False
        elif module == 'propagation':
            self.v2_config.enable_propagation = False
        elif module == 'strategy_learning':
            self.v2_config.enable_strategy_learning = False
    
    def persist_state(self):
        """持久化 v2 状态"""
        if hasattr(self, 'feedback_loop') and self.v2_config.enable_feedback:
            self.feedback_loop.persist()
        
        if hasattr(self, 'strategy_learning') and self.v2_config.enable_strategy_learning:
            self.strategy_learning.persist()
    
    def load_state(self):
        """加载 v2 状态"""
        if hasattr(self, 'feedback_loop') and self.v2_config.enable_feedback:
            self.feedback_loop.load()
        
        if hasattr(self, 'strategy_learning') and self.v2_config.enable_strategy_learning:
            self.strategy_learning.load()
    
    def get_v2_summary(self) -> Dict[str, Any]:
        """获取 v2 系统摘要"""
        summary = {
            'v2_enabled_modules': {
                'predictive': self.v2_config.enable_predictive,
                'feedback': self.v2_config.enable_feedback,
                'budget': self.v2_config.enable_budget,
                'propagation': self.v2_config.enable_propagation,
                'strategy_learning': self.v2_config.enable_strategy_learning
            },
            'v1_status': {
                'initialized': self.v1_initialized,
                'avg_latency_ms': self.v1_system.get_system_status().get('avg_latency_ms', 0)
            }
        }
        
        if hasattr(self, 'budget_system') and self.v2_config.enable_budget:
            summary['budget_summary'] = self.budget_system.get_summary()
        
        if hasattr(self, 'feedback_loop') and self.v2_config.enable_feedback:
            summary['feedback_summary'] = self.feedback_loop.get_summary()
        
        if hasattr(self, 'strategy_learning') and self.v2_config.enable_strategy_learning:
            summary['strategy_summary'] = self.strategy_learning.get_selection_summary()
            summary['learning_stats'] = self.strategy_learning.get_learning_stats()
        
        return summary
    
    def reset(self):
        """重置系统"""
        self.v1_system.reset()
        self._result_history.clear()
        self._last_v2_result = None
        
        if hasattr(self, 'predictive_engine'):
            self.predictive_engine.reset()
        if hasattr(self, 'propagation'):
            self.propagation.reset()
        if hasattr(self, 'budget_system'):
            self.budget_system.reset()
        if hasattr(self, 'feedback_loop'):
            self.feedback_loop.reset()
        if hasattr(self, 'strategy_learning'):
            self.strategy_learning.reset()


def create_v2_system(
    v1_config: Optional[AttentionSystemConfig] = None,
    enable_predictive: bool = True,
    enable_feedback: bool = True,
    enable_budget: bool = True,
    enable_propagation: bool = False,
    enable_strategy_learning: bool = False
) -> V2EnhancedAttentionSystem:
    """
    工厂函数: 创建 v2 增强系统
    
    示例:
    ```python
    # 完整启用 v2
    system = create_v2_system(
        enable_predictive=True,
        enable_feedback=True,
        enable_budget=True,
        enable_strategy_learning=True
    )
    
    # 只启用预测和预算
    system = create_v2_system(
        enable_predictive=True,
        enable_budget=True,
        enable_feedback=False,
        enable_propagation=False,
        enable_strategy_learning=False
    )
    ```
    """
    v2_config = V2Config(
        enable_predictive=enable_predictive,
        enable_feedback=enable_feedback,
        enable_budget=enable_budget,
        enable_propagation=enable_propagation,
        enable_strategy_learning=enable_strategy_learning
    )
    
    return V2EnhancedAttentionSystem(v1_config, v2_config)


def migrate_from_v1(
    existing_system: AttentionSystem,
    v2_config: Optional[V2Config] = None
) -> V2EnhancedAttentionSystem:
    """
    工厂函数: 从现有 v1 系统迁移到 v2
    
    保留 v1 的所有状态和配置
    """
    v2_config = v2_config or V2Config()
    
    v2_system = V2EnhancedAttentionSystem(
        v1_config=existing_system.config,
        v2_config=v2_config
    )
    
    v2_system.v1_system = existing_system
    v2_system.v1_initialized = existing_system._initialized
    
    return v2_system
