"""
QueryStateUpdater - 事件驱动的QueryState更新器

统一处理各类事件并更新QueryState，实现松耦合的架构设计。
"""

import logging
import time
from typing import Dict, Any

from deva.naja.register import SR
from deva.naja.events import get_event_bus

log = logging.getLogger(__name__)


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
            
            # 订阅新闻事件
            self._event_bus.subscribe(
                'TextFetchedEvent',
                self._on_text_fetched,
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
        """处理热点计算完成事件"""
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            # 从symbol_weights中提取股票代码和权重
            symbols = list(event.symbol_weights.keys())
            if not symbols:
                log.debug("[QueryStateUpdater] 热点事件没有股票数据")
                return
            
            # 转换为update_from_market所需的格式
            returns = [event.symbol_weights[s] * 100 for s in symbols]  # 转换为百分比
            volumes = [1.0 for _ in symbols]  # 占位成交量
            prices = [100.0 for _ in symbols]  # 占位价格
            
            # 更新QueryState
            self.qs.update_from_market(
                symbols=symbols,
                returns=returns,
                volumes=volumes,
                prices=prices,
                timestamp=event.timestamp
            )
            
            # 减少日志输出频率
            self._hotspot_counter += 1
            if self._hotspot_counter % self._hotspot_log_interval == 0:
                log.info(f"[QueryStateUpdater] 已更新热点数据: {len(symbols)}个股票, 市场={event.market}")
                self._hotspot_counter = 0
        except Exception as e:
            log.error(f"[QueryStateUpdater] 处理热点事件失败: {e}")
    
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
    
    def _on_text_fetched(self, event):
        """处理文本获取事件"""
        try:
            if not self.qs:
                log.warning("[QueryStateUpdater] QueryState 未初始化")
                return
            
            # 这里可以根据需要更新QueryState中的情绪或叙事相关字段
            # 例如更新市场情绪、叙事风险等
            log.debug(f"[QueryStateUpdater] 处理文本事件: {event.source}")
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
    """获取 QueryStateUpdater 单例（从 AppContainer 获取）"""
    from deva.naja.application import get_app_container
    container = get_app_container()
    if container and container.query_state_updater:
        return container.query_state_updater
    raise RuntimeError("QueryStateUpdater not found in AppContainer")
