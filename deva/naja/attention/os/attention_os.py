"""
AttentionOS - 注意力操作系统

分层架构：
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Attention OS (注意力操作系统)                          │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    OS 应用层 (Applications)                            │   │
│  │                                                                      │   │
│  │  • StrategyDecisionMaker - 市场调度（题材/个股权重 + 频率控制）               │   │
│  │  • StrategyAllocator - 策略分配                                      │   │
│  │  • FrequencyController - 频率控制器                                  │   │
│  │  • ...其他模块                                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Attention Kernel (注意力内核)                       │   │
│  │                                                                      │   │
│  │  • QKV 注意力计算 - 智能分配注意力权重                                │   │
│  │  • ManasEngine - 三维融合决策中枢（天时+地势+人和）                    │   │
│  │  • Encoder - 事件编码器                                              │   │
│  │  • MultiHeadAttention - 多头注意力                                    │   │
│  │  • ValueSystem - 价值观驱动                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘

核心能力（被各方调用）：
    • compute_attention() - QKV 注意力计算
    • make_decision() - ManasEngine 决策
    • get_harmony() - 获取和谐状态

使用方式：
    attention_os = AttentionOS()
    attention_os.initialize()

    # 注意力计算
    result = attention_os.compute_attention(events, market_state)

    # 决策
    decision = attention_os.make_decision(market_state, portfolio)
"""

import time
import logging
from typing import Dict, Any, Optional, List
import threading

from .os_kernel import OSAttentionKernel
from .strategy_decision import StrategyDecisionMaker
from ..models.output import AttentionFusionOutput, AttentionKernelOutput
from ..text_importance_scorer import TextImportanceScorer
from deva.naja.register import SR

log = logging.getLogger(__name__)

# 向后兼容：保留旧名称的导入
AttentionKernel = OSAttentionKernel


class AttentionOS:
    """
    注意力操作系统

    统一入口，管理内核和应用层
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, insight_pool=None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, insight_pool=None):
        if self._initialized:
            return

        self.kernel = OSAttentionKernel()
        self.strategy_decision_maker = StrategyDecisionMaker(self.kernel)
        self._text_scorer = TextImportanceScorer(self)

        self._strategy_manager = None
        self._insight_pool = insight_pool
        
        # 事件订阅已迁移到 EventSubscriberRegistrar（应用层）
        # 不再在内部自动订阅

        self._initialized = True

    def set_insight_pool(self, insight_pool) -> None:
        """显式设置 InsightPool（依赖注入）"""
        self._insight_pool = insight_pool

    def initialize_strategies(self):
        """初始化所有交易策略"""
        if self._strategy_manager is not None:
            return

        from deva.naja.attention.strategies import (
            GlobalMarketSentinel,
            BlockRotationHunter,
            MomentumSurgeTracker,
            AnomalyPatternSniper,
            SmartMoneyFlowDetector,
            LiquidityCrisisTracker,
            PanicPeakDetector,
            RecoveryConfirmationMonitor,
        )
        from deva.naja.attention.strategies.us_strategies import (
            USGlobalMarketSentinel,
            USBlockRotationHunter,
            USMomentumSurgeTracker,
            USAnomalyPatternSniper,
            USSmartMoneyFlowDetector,
        )

        self._strategy_manager = {
            'cn_global_sentinel': GlobalMarketSentinel(market='CN'),
            'cn_block_rotation': BlockRotationHunter(market='CN'),
            'cn_momentum_tracker': MomentumSurgeTracker(market='CN'),
            'cn_anomaly_sniper': AnomalyPatternSniper(market='CN'),
            'cn_smart_money': SmartMoneyFlowDetector(market='CN'),
            'cn_liquidity_crisis': LiquidityCrisisTracker(market='CN'),
            'cn_panic_peak': PanicPeakDetector(market='CN'),
            'cn_recovery_monitor': RecoveryConfirmationMonitor(market='CN'),
            'us_global_sentinel': USGlobalMarketSentinel(),
            'us_block_rotation': USBlockRotationHunter(),
            'us_momentum_tracker': USMomentumSurgeTracker(),
            'us_anomaly_sniper': USAnomalyPatternSniper(),
            'us_smart_money': USSmartMoneyFlowDetector(),
        }

        for strategy in self._strategy_manager.values():
            strategy.subscribe_to_events()

        log.info(f"[AttentionOS] 已初始化 {len(self._strategy_manager)} 个策略 (A股 {8}, 美股 {5})")

    def get_strategy_signals(self, strategy_id: Optional[str] = None, n: int = 20) -> List[Dict]:
        """获取策略信号"""
        if self._strategy_manager is None:
            return []

        if strategy_id:
            strategy = self._strategy_manager.get(strategy_id)
            return strategy.get_recent_signals(n) if strategy else []

        all_signals = []
        for strategy in self._strategy_manager.values():
            all_signals.extend(strategy.get_recent_signals(n))

        return sorted(all_signals, key=lambda x: x['timestamp'], reverse=True)[:n]

    def _subscribe_to_hotspot_events(self):
        """订阅市场热点事件"""
        try:
            from deva.naja.events import get_event_bus
            event_bus = get_event_bus()
            event_bus.subscribe(
                'HotspotComputedEvent',
                self._on_hotspot_computed,
                markets={'US', 'CN'},
                priority=10
            )
            event_bus.subscribe(
                'HotspotShiftEvent',
                self._on_hotspot_shift,
                priority=5
            )
            log.info("[AttentionOS] 已订阅市场热点事件和热点转移事件")
        except Exception as e:
            log.warning(f"[AttentionOS] 订阅市场热点事件失败: {e}")

    def _subscribe_to_text_events(self):
        """订阅文本获取事件"""
        try:
            from deva.naja.events import get_event_bus
            event_bus = get_event_bus()
            event_bus.subscribe(
                'TextFetchedEvent',
                self._on_text_fetched,
                priority=10
            )
            log.info("[AttentionOS] 已订阅文本获取事件")
        except Exception as e:
            log.warning(f"[AttentionOS] 订阅文本获取事件失败: {e}")

    def _on_text_fetched(self, event):
        """处理文本获取事件 - TextImportanceScorer 进行重要性评分"""
        try:
            self._text_scorer.on_text_fetched(event)
        except Exception as e:
            log.debug(f"[AttentionOS] 处理文本获取事件失败: {e}")

    def _on_hotspot_computed(self, event):
        """处理热点计算完成事件"""
        try:
            market_data = {
                'market': event.market,
                'global_hotspot': event.global_hotspot,
                'activity': event.activity,
                'block_hotspot': event.block_hotspot,
                'symbol_weights': event.symbol_weights,
                'symbols': event.symbols,
            }

            self.strategy_decision_maker.schedule(market_data)

            log.debug(f"[AttentionOS] 处理热点事件: market={event.market}, global_hotspot={event.global_hotspot:.3f}")
        except Exception as e:
            log.debug(f"[AttentionOS] 处理热点事件失败: {e}")

    def _on_hotspot_shift(self, event):
        """处理热点转移事件 - 内核决定是否发送到 InsightPool"""
        try:
            should_emit = self._should_emit_to_insight(event)
            if should_emit:
                self._emit_shift_to_insight(event)
            log.debug(f"[AttentionOS] 处理热点转移事件: type={event.event_type}, emitted={should_emit}")
        except Exception as e:
            log.debug(f"[AttentionOS] 处理热点转移事件失败: {e}")

    def _should_emit_to_insight(self, event) -> bool:
        """根据事件类型和分数决定是否发送到 InsightPool"""
        score = getattr(event, 'score', 0.0)
        event_type = getattr(event, 'event_type', '')
        old_value = getattr(event, 'old_value', None)
        new_value = getattr(event, 'new_value', None)

        if score < 0.1:
            return False

        if event_type in ("global_hotspot_shift", "market_state_shift"):
            return True

        if event_type in ("block_concentration_shift", "market_activity_shift"):
            if old_value is not None and new_value is not None:
                change = abs(new_value - old_value) if old_value else 0
                return change >= 0.15
            return score >= 0.3

        if event_type in ("block_hotspot", "symbol_hotspot_change"):
            return score >= 0.3

        if event_type in ("effective_pattern", "ineffective_pattern"):
            return True

        if event_type == "hotspot_shift":
            return True

        return score >= 0.2

    def _emit_shift_to_insight(self, event):
        """发送热点转移事件到 InsightPool（带用户个性化打分）"""
        try:
            pool = self._insight_pool
            if not pool:
                return

            insight_data = {
                "theme": getattr(event, 'title', ''),
                "summary": getattr(event, 'content', ''),
                "symbols": [getattr(event, 'symbol', '')] if getattr(event, 'symbol', '') else [],
                "blocks": [getattr(event, 'block', '')] if getattr(event, 'block', '') else [],
                "confidence": min(0.9, max(0.3, getattr(event, 'score', 0.5))),
                "actionability": 0.5,
                "system_hotspot": getattr(event, 'score', 0.5),
                "source": "hotspot_shift",
                "signal_type": getattr(event, 'event_type', 'hotspot_shift'),
                "ts": getattr(event, 'timestamp', time.time()),
                "payload": getattr(event, 'payload', {}),
            }

            personalized = self.kernel.personalize_event(insight_data)
            pool.ingest_hotspot_event(personalized)
        except Exception as e:
            log.debug(f"[AttentionOS] 发送热点转移事件到 InsightPool 失败: {e}")

    def initialize(self):
        """初始化"""
        log.info("[AttentionOS] 初始化完成")

    def compute_attention(
        self,
        events: List[Any],
        market_state: Optional[Dict[str, Any]] = None,
        query_state: Optional[Any] = None
    ) -> AttentionKernelOutput:
        """
        计算注意力

        数据流与子系统影响：
        ┌─────────────────────────────────────────────────────────────────────────────┐
        │                         compute_attention()                               │
        │                                                                             │
        │  输出:                                                                       │
        │    • attention_weights ──────────────→ _allocate_weights()                  │
        │    • alpha ─────────────────────────→ final_weight 乘因子                  │
        │    • harmony_strength ──────────────→ _adjust_frequency()                   │
        │    • action_type ──────────────────→ _allocate_strategies()                │
        │    • regime ────────────────────────→ regime_factor *= 策略权重              │
        │    • vs.record_attention() ─────────→ ValueSystem                          │
        └─────────────────────────────────────────────────────────────────────────────┘

        影响的子系统：
          1. StrategyDecisionMaker.symbol_weights / block_weights
             final_weight = base_weight * attention_weight * alpha * harmony * confidence
          2. StrategyDecisionMaker.frequency_level
             composite_score = harmony * 0.5 + timing * 0.3 + (1.0 if regime > 0 else 0.3) * 0.2
          3. StrategyDecisionMaker.strategy_allocations
             根据 action_type 分配 momentum/mean_reversion/breakout/grid/wait 权重
        """
        return self.kernel.compute(events, market_state, query_state)

    def make_decision(
        self,
        market_state: Optional[Dict[str, Any]] = None,
        portfolio: Optional[Any] = None
    ) -> AttentionKernelOutput:
        """做决策"""
        return self.kernel.make_decision(market_state, portfolio)

    def schedule_market(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """市场调度"""
        return self.strategy_decision_maker.schedule(market_data)

    def get_harmony(self) -> Dict[str, Any]:
        """获取和谐状态"""
        return self.kernel.get_harmony()

    def get_kernel(self) -> OSAttentionKernel:
        """获取 AttentionKernel 实例（兼容 BanditOptimizer）"""
        return self.kernel


_attention_os: Optional[AttentionOS] = None


def get_attention_os() -> AttentionOS:
    """获取 AttentionOS 单例（从 AppContainer 获取）"""
    from deva.naja.application import get_app_container
    container = get_app_container()
    if container and container.attention_os:
        return container.attention_os
    raise RuntimeError("AttentionOS not found in AppContainer")
