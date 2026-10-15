"""
QueryStateUpdater - 事件驱动的QueryState更新器

统一处理各类事件并更新QueryState，实现松耦合的架构设计。
"""

import logging
import threading
import time
import hashlib
from typing import Dict, Any, Optional

from deva.naja.events import get_event_bus

log = logging.getLogger(__name__)

_query_state_updater: Optional["QueryStateUpdater"] = None
_query_state_updater_lock = threading.Lock()


class QueryStateUpdater:
    """
    事件驱动的QueryState更新器
    
    订阅各类事件并统一更新QueryState，实现松耦合的架构设计。
    """
    
    def __init__(self, query_state=None):
        self.qs = query_state
        self._event_bus = get_event_bus()
        self._subscribe_to_events()
        self._hotspot_counter = 0
        self._hotspot_log_interval = 10
        self._last_data_hash: Optional[str] = None
        self._last_symbol_count = 0
        # 因「热点事件未携带真实行情」而跳过更新的累计次数（节流告警用，见
        # _note_skipped_hotspot —— 跳过是刻意的，但**不许静默**）
        self._hotspot_skip_count = 0
        self._hotspot_skip_log_every = 20
        log.info("[QueryStateUpdater] 初始化完成")

    def set_query_state(self, query_state):
        """显式设置 QueryState（依赖注入）"""
        self.qs = query_state
    
    def _subscribe_to_events(self):
        """订阅各类事件"""
        try:
            # 订阅热点计算事件
            self._event_bus.subscribe(
                'HotspotComputedEvent',
                self._on_hotspot_computed,
                priority=10
            )
            
            # 订阅全局市场数据事件
            self._event_bus.subscribe(
                'GlobalMarketDataEvent',
                self._on_global_market_data,
                priority=9
            )
            
            # 订阅新闻聚焦事件
            self._event_bus.subscribe(
                'TextFocusedEvent',
                self._on_text_focused,
                priority=8
            )
            
            # 订阅策略信号事件
            self._event_bus.subscribe(
                'StrategySignalEvent',
                self._on_strategy_signal,
                priority=7
            )
            
            # 订阅认知洞察事件
            self._event_bus.subscribe(
                'CognitiveInsightEvent',
                self._on_cognitive_insight,
                priority=6
            )
            
            # 订阅叙事状态事件
            self._event_bus.subscribe(
                'NarrativeStateEvent',
                self._on_narrative_state,
                priority=6
            )
            
            # 订阅流动性信号事件
            self._event_bus.subscribe(
                'LiquiditySignalEvent',
                self._on_liquidity_signal,
                priority=6
            )
            
            # 订阅美林时钟事件
            self._event_bus.subscribe(
                'MerrillClockEvent',
                self._on_merrill_clock,
                priority=6
            )
            
            log.info("[QueryStateUpdater] 已订阅所有事件")
        except Exception as e:
            log.error(f"[QueryStateUpdater] 订阅事件失败: {e}")
    
    def _on_hotspot_computed(self, event):
        """处理热点计算完成事件
        
        使用真实市场数据（returns/volumes/prices）更新 QueryState。
        如果数据未发生变化，则跳过更新以避免无意义的循环。
        """
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            # 从 symbol_weights 取股票代码（只用 key；值不做任何派生加工）
            symbols = list(event.symbol_weights.keys())
            if not symbols:
                log.debug("[QueryStateUpdater] 热点事件没有股票数据")
                return
            
            # ❗ returns / volumes / prices **必须全部**是事件携带的真实行情，
            #   缺任何一项就跳过本次更新 —— 绝不用 symbol_weights 顶替。
            #   旧写法在缺数据时拿 `symbol_weights[s] * 100` 冒充涨跌幅，而
            #   symbol_weights 的量级是 1.0~1.45，×100 就成了「平均涨幅 142%」。
            #   QueryState 是与 GlobalMarketScanner 共享的单例，这个伪造值会
            #   **覆盖**真市场数据，并被 RegimeEngine 拿去算 regime_score 与
            #   宏观流动性(macro_liquidity_signal)，把决策的环境输入变成人造数。
            #   实测：线上 /api/query/state 的 avg_change=142.3390579620452 与
            #   symbol_weights 均值×100 逐位相等（Δ=0），而同一批 hot_stocks
            #   里的真实 change_pct 是 +1.67 / −3.72 / −3.94 …
            #   宁可少更新一次，也不给决策喂假数。
            if not self._has_real_market_data(event, len(symbols)):
                self._note_skipped_hotspot(event, len(symbols))
                return
            returns = list(event.returns)
            volumes = list(event.volumes)
            prices = list(event.prices)

            # 变化检测：数据未变则跳过更新
            data_repr = f"{','.join(symbols)}|{','.join(f'{r:.2f}' for r in returns[:100])}"
            data_hash = hashlib.md5(data_repr.encode()).hexdigest()
            if data_hash == self._last_data_hash:
                # 数据无变化，静默跳过
                return
            self._last_data_hash = data_hash

            # 更新QueryState（使用真实数据）
            self.qs.update_from_market(
                symbols=symbols,
                returns=returns,
                volumes=volumes,
                prices=prices,
                timestamp=event.timestamp
            )
            
            # 只在数据真正变化时记录日志
            if len(symbols) != self._last_symbol_count:
                log.info(f"[QueryStateUpdater] 热点数据更新({event.market}): {len(symbols)}个股票")
                self._last_symbol_count = len(symbols)
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理热点事件失败: {e}")

    @staticmethod
    def _has_real_market_data(event, n_symbols: int) -> bool:
        """事件是否携带**逐标的、长度对齐**的真实行情三件套。

        三个字段都要有：`update_from_market` 会分别用 returns 算涨跌/波动、
        用 volumes 算量能离散度、用 prices 算派生特征，少一个就会出现
        「一半真一半假」的口径混用。
        """
        for field in ("returns", "volumes", "prices"):
            values = getattr(event, field, None)
            if not isinstance(values, (list, tuple)) or len(values) != n_symbols:
                return False
        return True

    def _note_skipped_hotspot(self, event, n_symbols: int) -> None:
        """热点事件缺真实行情 → 跳过更新，并留痕（节流告警，绝不静默）。

        为什么宁可跳过：QueryState 是 scanner 与本更新器**共享**的单例，
        这里的写入会覆盖 scanner 刚写的真市场数据。用权重凑出来的假数
        比「这次不更新」危险得多（后者只是旧值，前者是错的数）。
        """
        self._hotspot_skip_count += 1
        n = self._hotspot_skip_count
        if n == 1 or n % self._hotspot_skip_log_every == 0:
            log.warning(
                "[QueryStateUpdater] 热点事件(%s, %d 个标的)未携带真实行情"
                "(returns/volumes/prices)，跳过 QueryState 更新（累计 %d 次）"
                "—— 拒绝用 symbol_weights 伪造涨跌幅",
                getattr(event, "market", "?"), n_symbols, n,
            )

    def _on_global_market_data(self, event):
        """处理全局市场数据事件"""
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            # 从事件中提取数据
            symbols = event.symbols
            returns = event.returns
            volumes = event.volumes
            prices = event.prices
            
            if not symbols:
                log.debug("[QueryStateUpdater] 全局市场事件没有股票数据")
                return
            
            # 更新QueryState
            self.qs.update_from_market(
                symbols=symbols,
                returns=returns,
                volumes=volumes,
                prices=prices,
                timestamp=event.timestamp
            )
            
            log.info(f"[QueryStateUpdater] 已更新全局市场数据: {len(symbols)}个股票")
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理全局市场事件失败: {e}")
    
    def _on_text_focused(self, event):
        """处理文本聚焦事件"""
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            log.debug(f"[QueryStateUpdater] source={event.source}, importance={event.importance_score}, title={event.title[:30] if event.title else None}...")
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理文本事件失败: {e}")
    
    def _on_strategy_signal(self, event):
        """处理策略信号事件"""
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            # 这里可以根据需要更新QueryState中的策略相关字段
            # 例如更新策略状态、信号强度等
            log.debug(f"[QueryStateUpdater] 处理策略信号: {event.strategy_name} {event.symbol}")
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理策略信号失败: {e}")
    
    def _on_cognitive_insight(self, event):
        """处理认知洞察事件"""
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            # 更新认知洞察数据
            self.qs.cognitive_insights = {
                "insights": event.insights,
                "confidence": event.confidence,
                "timeliness": time.time() - event.timestamp
            }
            
            log.info(f"[QueryStateUpdater] 已更新认知洞察: {len(event.insights)}个洞察, 置信度={event.confidence:.2f}")
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理认知洞察事件失败: {e}")
    
    def _on_narrative_state(self, event):
        """处理叙事状态事件"""
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            # 更新叙事状态数据
            self.qs.narrative_state = {
                "current_narratives": event.current_narratives,
                "narrative_strength": event.narrative_strength,
                "narrative_risk": event.narrative_risk,
                "sentiment_score": event.sentiment_score
            }
            
            narrative_list = event.current_narratives[:5]
            excess = len(event.current_narratives) - 5
            narrative_str = f"{narrative_list}{f'... (+{excess})' if excess > 0 else ''}"
            log.info(f"[QueryStateUpdater] 已更新叙事状态: {narrative_str}, 强度={event.narrative_strength:.2f}, 风险={event.narrative_risk:.2f}")
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理叙事状态事件失败: {e}")
    
    def _on_liquidity_signal(self, event):
        """处理流动性信号事件"""
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            # 更新流动性状态数据
            self.qs.liquidity_state = {
                "prediction": event.prediction,
                "risk": event.risk,
                "signal": event.signal
            }
            
            log.info(f"[QueryStateUpdater] 已更新流动性信号: 预测={event.prediction:.2f}, 风险={event.risk:.2f}")
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理流动性信号事件失败: {e}")
    
    def _on_merrill_clock(self, event):
        """处理美林时钟事件"""
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            # 更新经济周期数据
            self.qs.economic_cycle = {
                "phase": event.phase,
                "asset_allocation": event.asset_allocation
            }
            
            log.info(f"[QueryStateUpdater] 已更新经济周期: 阶段={event.phase}")
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理美林时钟事件失败: {e}")
    
    def get_query_state(self):
        """获取QueryState实例"""
        return self.qs


def get_query_state_updater() -> QueryStateUpdater:
    """获取 QueryStateUpdater 单例。

    优先从 AppContainer 获取（生产环境）；AppContainer 不可用时
    （如测试环境）回退到模块级单例缓存。
    """
    global _query_state_updater
    from deva.naja.application import get_app_container
    container = get_app_container()
    if container and container.query_state_updater:
        return container.query_state_updater
    if _query_state_updater is None:
        with _query_state_updater_lock:
            if _query_state_updater is None:
                _query_state_updater = QueryStateUpdater()
    return _query_state_updater
