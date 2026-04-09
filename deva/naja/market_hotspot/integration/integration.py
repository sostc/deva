"""
MarketHotspotIntelligence - 市场热点智能增强系统

在基础市场热点系统上增加智能增强模块：

数据流:
snapshot → Core (GlobalHotspot/Block/Weight) →
    Processing (Noise Filter) →
    Scheduling (Frequency/Strategy) →
    Intelligence Augmentation (Prediction/Propagation/Budget/Feedback/Learning) →
    Engine (River/PyTorch) →
    输出调度决策

智能增强模块:
1. PredictiveHotspotEngine - 预测热点
2. HotspotFeedbackLoop - 热点反馈
3. HotspotBudgetSystem - 热点预算
4. HotspotPropagation - 热点扩散
5. StrategyLearning - 策略学习
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
import time

from .market_hotspot_system import (
    MarketHotspotSystem,
    MarketHotspotSystemConfig,
    MarketSnapshot
)
from ..core import BlockConfig as BlockConfig
from deva.naja.market_hotspot.intelligence import (
    PredictiveHotspotEngine,
    HotspotFeedbackLoop,
    HotspotBudgetSystem,
    BudgetConfig,
    HotspotPropagation,
    StrategyLearning
)


@dataclass
class IntelligenceConfig:
    """智能增强配置"""
    enable_predictive: bool = True
    enable_feedback: bool = True
    enable_budget: bool = True
    enable_propagation: bool = True
    enable_strategy_learning: bool = True

    alpha: float = 0.7
    beta: float = 0.3

    budget_max_tier1: int = 20
    budget_max_tier2: int = 100
    budget_total: float = 50.0

    propagation_mode: str = "single_step"

    feedback_store_path: Optional[str] = None


IntelligenceAugmentedSystem = None


class _IntelligenceAugmentedSystemInternal:
    """
    增强型市场热点系统

    集成所有功能模块:
    1. Core (Global/Block/Weight)
    2. Processing (Noise Filter)
    3. Scheduling (Frequency/Strategy)
    4. Intelligence (Prediction/Propagation/Budget/Feedback/Learning)
    5. Engine (River/PyTorch)
    """

    def __init__(
        self,
        config: Optional[MarketHotspotSystemConfig] = None,
        intelligence_config: Optional[IntelligenceConfig] = None
    ):
        self.config = intelligence_config or IntelligenceConfig()

        self.base_system = MarketHotspotSystem(config)
        self._initialized = False

        if self.config.enable_predictive:
            self.predictive_engine = PredictiveHotspotEngine(
                alpha=self.config.alpha,
                beta=self.config.beta
            )

        if self.config.enable_propagation:
            self.propagation = HotspotPropagation(
                propagation_mode=self.config.propagation_mode
            )

        if self.config.enable_budget:
            budget_config = BudgetConfig(
                max_tier1_symbols=self.config.budget_max_tier1,
                max_tier2_symbols=self.config.budget_max_tier2,
                total_budget=self.config.budget_total
            )
            self.budget_system = HotspotBudgetSystem(budget_config)

        if self.config.enable_feedback:
            self.feedback_loop = HotspotFeedbackLoop(
                store_path=self.config.feedback_store_path
            )

        if self.config.enable_strategy_learning:
            self.strategy_learning = StrategyLearning()

        self._result_history: List[Dict[str, Any]] = []
        self._last_result: Optional[Dict[str, Any]] = None

    def initialize(
        self,
        blocks: List[BlockConfig],
        symbol_block_map: Dict[str, List[str]]
    ):
        """初始化系统"""
        self.base_system.initialize(blocks, symbol_block_map)
        self._initialized = True

        if hasattr(self, 'propagation'):
            for block in blocks:
                self.propagation.register_block(block.block_id)

    def process_snapshot(
        self,
        symbols: np.ndarray,
        returns: np.ndarray,
        volumes: np.ndarray,
        prices: np.ndarray,
        block_ids: np.ndarray,
        timestamp: float,
        pattern_scores: Optional[Dict[str, float]] = None,
        returns_history: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """
        处理市场快照

        流程:
        1. Base 处理 (Global/Block/Weight/Frequency)
        2. Prediction (如果启用)
        3. Propagation (如果启用)
        4. Budget (如果启用)
        5. 返回综合结果
        """
        if not self._initialized:
            self._auto_initialize(symbols, block_ids)

        result = self.base_system.process_snapshot(
            symbols, returns, volumes, prices, block_ids, timestamp
        )

        final_hotspot = result['symbol_weights']

        if hasattr(self, 'predictive_engine') and self.config.enable_predictive:
            returns_arr = returns_history if returns_history is not None else returns

            base_volumes = np.mean(volumes) if len(volumes) > 0 else 1.0
            volume_ratios = volumes / base_volumes if len(volumes) > 0 else np.ones_like(volumes)

            prediction_results = self.predictive_engine.batch_predict(
                symbols=symbols,
                current_hotspot=final_hotspot,
                returns=returns_arr,
                volumes=volume_ratios,
                timestamps=np.full(len(symbols), timestamp)
            )

            adjusted_hotspot = {}
            for symbol, (pred_score, final_att) in prediction_results.items():
                adjusted_hotspot[symbol] = final_att

            result['prediction_scores'] = {
                symbol: pred_score
                for symbol, (pred_score, _) in prediction_results.items()
            }
            result['adjusted_hotspot'] = adjusted_hotspot
            final_hotspot = adjusted_hotspot

        if hasattr(self, 'propagation') and self.config.enable_propagation:
            propagated = self.propagation.propagate(
                result['block_hotspot'],
                timestamp
            )
            result['propagated_block_hotspot'] = propagated

        if hasattr(self, 'budget_system') and self.config.enable_budget:
            budget_allocation = self.budget_system.allocate(final_hotspot)
            result['budget_allocation'] = {
                'tier1': budget_allocation.tier1_symbols,
                'tier2': budget_allocation.tier2_symbols,
                'tier3': budget_allocation.tier3_symbols,
                'utilization': budget_allocation.budget_utilization,
                'rejected': budget_allocation.rejected_symbols
            }
            result['tier_symbols'] = {
                'high_freq': budget_allocation.tier1_symbols,
                'medium_freq': budget_allocation.tier2_symbols,
                'low_freq': budget_allocation.tier3_symbols
            }

            result['datasource_control'] = self._get_datasource_control_with_budget(
                budget_allocation
            )

        if hasattr(self, 'strategy_learning') and self.config.enable_strategy_learning:
            available_strategies = list(self.base_system.strategy_allocator.registry._strategies.keys())

            selection = self.strategy_learning.select_strategies(
                global_hotspot=result['global_hotspot'],
                block_hotspot=result['block_hotspot'],
                available_strategies=available_strategies,
                pattern_scores=pattern_scores
            )

            result['strategy_selection'] = {
                'selected': selection.selected_strategies,
                'confidence': selection.selection_confidence,
                'market_state': selection.market_state.get_state_name()
            }

        result['enhanced'] = {
            'predictive': self.config.enable_predictive,
            'feedback': self.config.enable_feedback,
            'budget': self.config.enable_budget,
            'propagation': self.config.enable_propagation,
            'strategy_learning': self.config.enable_strategy_learning
        }

        self._last_result = result
        self._result_history.append(result)

        return result

    def _auto_initialize(
        self,
        symbols: np.ndarray,
        block_ids: np.ndarray
    ):
        """自动初始化"""
        unique_blocks = np.unique(block_ids)
        block_configs = [
            BlockConfig(
                block_id=str(s),
                name=str(s),
                symbols=set()
            )
            for s in unique_blocks
        ]

        symbol_block_map = {}
        for i, symbol in enumerate(symbols):
            symbol_str = str(symbol)
            block_list = symbol_block_map.get(symbol_str, [])
            block_list.append(str(block_ids[i]))
            symbol_block_map[symbol_str] = block_list

        self.initialize(block_configs, symbol_block_map)

    def _get_datasource_control_with_budget(self, budget_allocation) -> Dict[str, Any]:
        """获取数据源控制"""
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
        block_id: str,
        hotspot_before: float,
        hotspot_after: float,
        prediction_score: float,
        action: str,
        pnl: float,
        holding_period: int,
        market_state: str = "unknown",
        volatility: float = 0.0,
        volume_ratio: float = 1.0,
        trend: float = 0.0
    ):
        """记录策略执行结果"""
        if hasattr(self, 'feedback_loop') and self.config.enable_feedback:
            self.feedback_loop.record_outcome(
                strategy_id=strategy_id,
                symbol=symbol,
                block_id=block_id,
                hotspot_before=hotspot_before,
                hotspot_after=hotspot_after,
                prediction_score=prediction_score,
                action=action,
                pnl=pnl,
                holding_period=holding_period,
                market_state=market_state,
                volatility=volatility,
                volume_ratio=volume_ratio,
                trend=trend
            )

        if hasattr(self, 'strategy_learning') and self.config.enable_strategy_learning:
            self.strategy_learning.record_outcome(
                strategy_id=strategy_id,
                pnl=pnl,
                holding_time=holding_period
            )

    def get_hotspot_adjustment(self, symbol: str) -> float:
        """获取热点调整"""
        if hasattr(self, 'feedback_loop') and self.config.enable_feedback:
            if self._last_result:
                hotspot = self._last_result['symbol_weights'].get(symbol, 0.0)
                prediction = self._last_result.get('prediction_scores', {}).get(symbol, 0.5)

                return self.feedback_loop.get_hotspot_adjustment(
                    symbol=symbol,
                    hotspot_val=hotspot,
                    prediction_score=prediction
                )
        return 1.0

    def apply_adjustment(
        self,
        symbol: str,
        hotspot_val: float
    ) -> float:
        """应用热点调整"""
        adjustment = self.get_hotspot_adjustment(symbol)
        return hotspot_val * adjustment

    def get_budget_symbols(self) -> Dict[str, List[str]]:
        """获取各预算等级的symbols"""
        if hasattr(self, 'budget_system') and self.config.enable_budget:
            return {
                'tier1': self.budget_system.get_high_frequency_symbols(),
                'tier2': self.budget_system.get_medium_frequency_symbols(),
                'tier3': self.budget_system.get_low_frequency_symbols()
            }
        return {}

    def get_pytorch_symbols(self) -> List[str]:
        """获取应该进入PyTorch的symbols"""
        if hasattr(self, 'budget_system') and self.config.enable_budget:
            return self.budget_system.get_pytorch_symbols()
        return []

    def get_effective_patterns(self) -> List[str]:
        """获取有效模式"""
        if hasattr(self, 'feedback_loop') and self.config.enable_feedback:
            return self.feedback_loop.get_effective_patterns()
        return []

    def get_ineffective_patterns(self) -> List[str]:
        """获取无效模式"""
        if hasattr(self, 'feedback_loop') and self.config.enable_feedback:
            return self.feedback_loop.get_ineffective_patterns()
        return []

    def get_strategy_selection(self) -> Optional[Dict[str, Any]]:
        """获取当前策略选择"""
        if hasattr(self, 'strategy_learning') and self.config.enable_strategy_learning:
            summary = self.strategy_learning.get_selection_summary()
            return summary.get('last_selection')
        return None

    def get_system_load(self) -> float:
        """获取系统负载"""
        if hasattr(self, 'budget_system') and self.config.enable_budget:
            return self.budget_system.get_system_load()
        return 0.5

    def enable_module(self, module: str):
        """启用模块"""
        if module == 'predictive':
            self.config.enable_predictive = True
        elif module == 'feedback':
            self.config.enable_feedback = True
        elif module == 'budget':
            self.config.enable_budget = True
        elif module == 'propagation':
            self.config.enable_propagation = True
        elif module == 'strategy_learning':
            self.config.enable_strategy_learning = True

    def disable_module(self, module: str):
        """禁用模块"""
        if module == 'predictive':
            self.config.enable_predictive = False
        elif module == 'feedback':
            self.config.enable_feedback = False
        elif module == 'budget':
            self.config.enable_budget = False
        elif module == 'propagation':
            self.config.enable_propagation = False
        elif module == 'strategy_learning':
            self.config.enable_strategy_learning = False

    def persist_state(self):
        """持久化状态"""
        if hasattr(self, 'feedback_loop') and self.config.enable_feedback:
            self.feedback_loop.persist()

        if hasattr(self, 'strategy_learning') and self.config.enable_strategy_learning:
            self.strategy_learning.persist()

        if hasattr(self, 'hotspot_system') and self.hotspot_system is not None:
            try:
                from deva import NB
                state = self.hotspot_system.save_state()
                db = NB('naja_hotspot_state')
                db['hotspot_system_state'] = state
                db.persist()
                log.info(f"[MarketHotspotIntegration] 市场热点系统状态已持久化")
            except Exception as e:
                log.warning(f"[MarketHotspotIntegration] 持久化市场热点系统状态失败: {e}")

    def load_state(self):
        """加载状态"""
        if hasattr(self, 'feedback_loop') and self.config.enable_feedback:
            self.feedback_loop.load()

        if hasattr(self, 'strategy_learning') and self.config.enable_strategy_learning:
            self.strategy_learning.load()

        if hasattr(self, 'hotspot_system') and self.hotspot_system is not None:
            try:
                from deva import NB
                db = NB('naja_hotspot_state')
                if 'hotspot_system_state' in db:
                    state = db['hotspot_system_state']
                    self.hotspot_system.load_state(state)
                    log.info(f"[MarketHotspotIntegration] 市场热点系统状态已恢复")
                else:
                    log.info(f"[MarketHotspotIntegration] 未找到保存的市场热点系统状态")
            except Exception as e:
                log.warning(f"[MarketHotspotIntegration] 恢复市场热点系统状态失败: {e}")

    def get_summary(self) -> Dict[str, Any]:
        """获取系统摘要"""
        summary = {
            'enabled_modules': {
                'predictive': self.config.enable_predictive,
                'feedback': self.config.enable_feedback,
                'budget': self.config.enable_budget,
                'propagation': self.config.enable_propagation,
                'strategy_learning': self.config.enable_strategy_learning
            },
            'base_status': {
                'initialized': self._initialized,
                'avg_latency_ms': self.base_system.get_system_status().get('avg_latency_ms', 0)
            }
        }

        if hasattr(self, 'budget_system') and self.config.enable_budget:
            summary['budget_summary'] = self.budget_system.get_summary()

        if hasattr(self, 'feedback_loop') and self.config.enable_feedback:
            summary['feedback_summary'] = self.feedback_loop.get_summary()

        if hasattr(self, 'strategy_learning') and self.config.enable_strategy_learning:
            summary['strategy_summary'] = self.strategy_learning.get_selection_summary()
            summary['learning_stats'] = self.strategy_learning.get_learning_stats()

        return summary

    def reset(self):
        """重置系统"""
        self.base_system.reset()
        self._result_history.clear()
        self._last_result = None

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


def create_intelligence_system(
    config: Optional[MarketHotspotSystemConfig] = None,
    enable_predictive: bool = True,
    enable_feedback: bool = True,
    enable_budget: bool = True,
    enable_propagation: bool = False,
    enable_strategy_learning: bool = False
) -> _IntelligenceAugmentedSystemInternal:
    """
    工厂函数: 创建智能增强市场热点系统
    """
    intelligence_config = IntelligenceConfig(
        enable_predictive=enable_predictive,
        enable_feedback=enable_feedback,
        enable_budget=enable_budget,
        enable_propagation=enable_propagation,
        enable_strategy_learning=enable_strategy_learning
    )

    return _IntelligenceAugmentedSystemInternal(config, intelligence_config)


create_system = create_intelligence_system


def _get_intelligence_augmented_system(
    intelligence_config: Optional[IntelligenceConfig] = None,
    enable_propagation: bool = True,
    enable_strategy_learning: bool = True
) -> _IntelligenceAugmentedSystemInternal:
    """
    内部工厂函数：创建增强智能系统
    """
    config = MarketHotspotSystemConfig()
    intelligence_config = intelligence_config or IntelligenceConfig()

    return _IntelligenceAugmentedSystemInternal(
        config=config,
        intelligence_config=intelligence_config,
        enable_propagation=enable_propagation,
        enable_strategy_learning=enable_strategy_learning
    )


IntelligenceAugmentedSystem = _IntelligenceAugmentedSystemInternal
