"""
交易总线 - 基于 Stream/NS/NB 的持久化事件总线

专为交易层事件设计：策略信号、交易决策、订单执行等
核心特性：
1. 基于 Stream 异步分发（可选）
2. NB 持久化支持
3. 去重窗口
4. 重要性阈值
5. 市场过滤
"""

import time
import threading
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Union
from dataclasses import asdict, dataclass, field
from collections import defaultdict, deque

log = logging.getLogger(__name__)

# 尝试导入 Stream/NS/NB，可选
try:
    from deva import NS, NB
    STREAM_AVAILABLE = True
except ImportError:
    STREAM_AVAILABLE = False
    log.warning("Stream/NB 不可用，回退到简化实现")


@dataclass
class TradingEventSubscription:
    """交易事件订阅配置"""
    callback: Callable
    subscription_id: str
    markets: Optional[Set[str]] = None
    priority: int = 0
    min_importance: float = 0.0
    created_at: float = field(default_factory=time.time)


@dataclass
class TradingBusStats:
    """交易总线统计"""
    total_published: int = 0
    total_delivered: int = 0
    total_dropped: int = 0
    by_event_type: Dict[str, int] = field(default_factory=dict)
    by_module: Dict[str, int] = field(default_factory=dict)


class TradingEventBus:
    """
    交易事件总线
    
    专门处理交易层事件：
    - StrategySignalEvent（策略发出的买卖信号）
    - TradeDecisionEvent（风险审核后的决策）
    - OrderExecutionEvent（订单执行结果）
    - PortfolioUpdateEvent（持仓更新）
    """
    
    def __init__(self, use_stream: bool = True, dedup_window: float = 30.0):
        """
        Args:
            use_stream: 是否使用 Stream/NS 实现（如果可用）
            dedup_window: 重复事件检测窗口（秒）
        """
        self._use_stream = use_stream and STREAM_AVAILABLE
        self._dedup_window = dedup_window
        self._lock = threading.RLock()
        self._recent_events = deque(maxlen=1000)  # (指纹, 时间戳)
        
        # 持久化配置
        self._persistent_types: Set[str] = set()
        self._nb_streams: Dict[str, Any] = {}
        
        # 订阅管理
        if self._use_stream:
            # 使用 NS 流
            self._subscriptions: Dict[str, List[TradingEventSubscription]] = {}
            log.info("[TradingEventBus] 使用 Stream/NS 实现")
        else:
            # 简化实现
            self._subscriptions = defaultdict(list)
            log.info("[TradingEventBus] 使用简化实现（无Stream）")
        
        # 统计
        self._stats = TradingBusStats()
        log.info(f"[TradingEventBus] 初始化完成 (去重窗口={dedup_window}s)")
    
    # ============== 配置方法 ==============
    
    def configure_persistence(self, event_type: str, persistent: bool = True):
        """配置事件类型是否持久化"""
        if persistent:
            self._persistent_types.add(event_type)
            if self._use_stream and event_type not in self._nb_streams:
                try:
                    # 创建 NB 流，按时间戳排序，支持追加
                    nb = NB(f'trading.{event_type}', 
                           key_mode='time', 
                           time_dict_policy='append')
                    self._nb_streams[event_type] = nb
                    log.info(f"📦 配置交易事件持久化: {event_type}")
                except Exception as e:
                    log.warning(f"创建 NB 流失败: {e}")
        else:
            self._persistent_types.discard(event_type)
    
    def enable_stream(self, enabled: bool = True):
        """启用/禁用 Stream 实现"""
        if enabled and not STREAM_AVAILABLE:
            log.warning("Stream 不可用，无法启用")
            return False
        
        self._use_stream = enabled
        log.info(f"[TradingEventBus] Stream 实现: {'启用' if enabled else '禁用'}")
        return True
    
    # ============== 发布订阅 ==============
    
    def publish(self, event) -> int:
        """
        发布交易事件
        
        Args:
            event: 事件 dataclass 实例
            
        Returns:
            分发到的订阅者数量
        """
        if event is None:
            return 0
        
        with self._lock:
            self._stats.total_published += 1
            
            event_type = type(event).__name__
            self._stats.by_event_type[event_type] = \
                self._stats.by_event_type.get(event_type, 0) + 1
            
            # 去重检查
            fingerprint = self._get_event_fingerprint(event)
            if self._is_duplicate(fingerprint):
                log.debug(f"  交易事件去重: {fingerprint}")
                self._stats.total_dropped += 1
                return 0
            
            # 记录去重
            self._recent_events.append((fingerprint, time.time()))
            self._cleanup_old_events()
            
            # 分发
            delivered = self._deliver_event(event, event_type)
            self._stats.total_delivered += delivered
            
            # 持久化
            if event_type in self._persistent_types:
                self._persist_event(event_type, event)
            
            # 高重要性事件无人接收告警
            if delivered == 0 and self._get_event_importance(event) >= 0.7:
                log.warning(f"⚠️ 高重要性交易事件无人接收: {event}")
            
            return delivered
    
    def subscribe(self, event_type: str, callback: Callable, 
                  subscription_id: Optional[str] = None,
                  markets: Optional[Set[str]] = None,
                  priority: int = 0,
                  min_importance: float = 0.0) -> str:
        """
        订阅交易事件
        
        Args:
            event_type: 事件类型（dataclass 类名）
            callback: 回调函数
            subscription_id: 可选订阅ID
            markets: 市场过滤（如 {'CN', 'US'}）
            priority: 优先级（数值越大优先级越高）
            min_importance: 重要性阈值
            
        Returns:
            订阅ID
        """
        sub_id = subscription_id or f"{event_type}_{int(time.time()*1000)}"
        
        subscription = TradingEventSubscription(
            callback=callback,
            subscription_id=sub_id,
            markets=markets,
            priority=priority,
            min_importance=min_importance,
        )
        
        with self._lock:
            subs = self._subscriptions.get(event_type, [])
            # 按优先级插入
            for i, sub in enumerate(subs):
                if sub.priority < subscription.priority:
                    subs.insert(i, subscription)
                    break
            else:
                subs.append(subscription)
            
            self._subscriptions[event_type] = subs
        
        log.debug(f"  订阅交易事件: {event_type} (id={sub_id})")
        return sub_id
    
    def unsubscribe(self, subscription_id: str):
        """取消订阅"""
        with self._lock:
            for event_type, subs in list(self._subscriptions.items()):
                new_subs = [sub for sub in subs if sub.subscription_id != subscription_id]
                if len(new_subs) != len(subs):
                    self._subscriptions[event_type] = new_subs
                    log.debug(f"  取消订阅: {subscription_id}")
                    return True
        return False
    
    # ============== 查询统计 ==============
    
    def get_stats(self) -> TradingBusStats:
        """获取统计信息"""
        with self._lock:
            return TradingBusStats(
                total_published=self._stats.total_published,
                total_delivered=self._stats.total_delivered,
                total_dropped=self._stats.total_dropped,
                by_event_type=dict(self._stats.by_event_type),
                by_module=dict(self._stats.by_module),
            )
    
    def get_history(self, event_type: str, limit: int = 100) -> List[Dict]:
        """
        查询事件历史（如果配置了持久化）
        
        Args:
            event_type: 事件类型
            limit: 返回数量限制
            
        Returns:
            事件列表（按时间倒序）
        """
        if not self._use_stream or event_type not in self._nb_streams:
            return []
        
        try:
            nb = self._nb_streams[event_type]
            # NB 流查询（具体方法取决于 NB API）
            data = getattr(nb, 'get', lambda: {})()
            if isinstance(data, dict):
                items = list(data.items())
                # 按时间戳排序（假设key是时间戳）
                sorted_items = sorted(items, key=lambda x: x[0], reverse=True)[:limit]
                return [{'timestamp': k, 'data': v} for k, v in sorted_items]
            return []
        except Exception as e:
            log.error(f"查询事件历史失败: {e}")
            return []
    
    # ============== 内部方法 ==============
    
    def _get_event_fingerprint(self, event) -> str:
        """生成事件指纹（用于去重）"""
        event_type = type(event).__name__
        
        # 根据事件类型生成指纹
        if event_type == 'StrategySignalEvent':
            # 策略信号：symbol + direction + 时间戳（分钟级）
            minute = int(time.time() / 60)
            return f"strategy:{getattr(event, 'symbol', '')}:{getattr(event, 'direction', '')}:{minute}"
        elif event_type == 'TradeDecisionEvent':
            # 交易决策：signal_event的指纹
            signal_event = getattr(event, 'signal_event', None)
            if signal_event:
                return f"decision:{self._get_event_fingerprint(signal_event)}"
        
        # 通用指纹：类型 + ID + 时间戳（分钟级）
        minute = int(time.time() / 60)
        return f"{event_type}:{id(event)}:{minute}"
    
    def _is_duplicate(self, fingerprint: str) -> bool:
        """检查事件是否重复"""
        now = time.time()
        for fp, ts in self._recent_events:
            if fp == fingerprint and now - ts < self._dedup_window:
                return True
        return False
    
    def _cleanup_old_events(self):
        """清理超过去重窗口的事件"""
        now = time.time()
        cutoff = now - self._dedup_window
        self._recent_events = deque(
            [(fp, ts) for fp, ts in self._recent_events if ts > cutoff],
            maxlen=self._recent_events.maxlen
        )
    
    def _get_event_importance(self, event) -> float:
        """获取事件重要性"""
        return getattr(event, 'importance', 0.5)
    
    def _deliver_event(self, event, event_type: str) -> int:
        """分发事件到订阅者"""
        subscribers = self._subscriptions.get(event_type, [])
        if not subscribers:
            return 0
        
        importance = self._get_event_importance(event)
        market = getattr(event, 'market', None)
        
        delivered = 0
        for sub in subscribers:
            try:
                # 重要性检查
                if importance < sub.min_importance:
                    continue
                
                # 市场过滤
                if sub.markets and market and market not in sub.markets:
                    continue
                
                sub.callback(event)
                delivered += 1
                
                # 记录模块统计
                module_name = sub.subscription_id.split('_')[0] if '_' in sub.subscription_id else 'unknown'
                self._stats.by_module[module_name] = \
                    self._stats.by_module.get(module_name, 0) + 1
                    
            except Exception as e:
                log.error(f"交易事件回调失败: {e}")
        
        return delivered
    
    def _persist_event(self, event_type: str, event):
        """持久化事件"""
        if not self._use_stream:
            return
        
        try:
            nb = self._nb_streams.get(event_type)
            if nb:
                # 序列化事件
                data = asdict(event) if hasattr(event, '__dataclass_fields__') else event
                nb.emit(data)
                log.debug(f"  NB持久化: {event_type}")
        except Exception as e:
            log.warning(f"事件持久化失败: {e}")
    
    # ============== 快捷方法 ==============
    
    def publish_strategy_signal(self, symbol: str, direction: str, confidence: float = 0.5,
                                strategy_name: str = "", current_price: Optional[float] = None,
                                importance: float = 0.5, market: str = "CN", **kwargs) -> int:
        """快捷发布策略信号事件"""
        from .trading_events import StrategySignalEvent
        
        event = StrategySignalEvent(
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            strategy_name=strategy_name,
            signal_type=str(direction).lower(),
            current_price=current_price,
            price_change_pct=kwargs.get('price_change_pct', 0.0),
            importance=importance,
            market=market,
            metadata=kwargs.get('metadata', {}),
            timestamp=time.time(),
        )
        
        return self.publish(event)
    
    def publish_trade_decision(self, signal_event, decision: str, 
                               approval_score: float = 0.5,
                               reason: str = "", **kwargs) -> int:
        """快捷发布交易决策事件"""
        from .trading_events import TradeDecisionEvent, DecisionResult
        
        event = TradeDecisionEvent(
            signal_event=signal_event,
            decision=DecisionResult(decision),
            approval_score=approval_score,
            approved_symbol=kwargs.get('approved_symbol', getattr(signal_event, 'symbol', '')),
            approved_direction=kwargs.get('approved_direction', getattr(signal_event, 'direction', '')),
            position_size=kwargs.get('position_size', 0.02),
            reason=reason,
            timestamp=time.time(),
        )
        
        return self.publish(event)


# ============== 单例实例 ==============

_trading_bus_instance = None
_trading_bus_lock = threading.RLock()


def get_trading_bus() -> TradingEventBus:
    """获取交易总线单例"""
    global _trading_bus_instance
    
    with _trading_bus_lock:
        if _trading_bus_instance is None:
            _trading_bus_instance = TradingEventBus()
    
    return _trading_bus_instance


def reset_trading_bus():
    """重置交易总线（测试用）"""
    global _trading_bus_instance
    
    with _trading_bus_lock:
        _trading_bus_instance = None