"""
总线桥梁 - 连接认知总线和交易总线的桥梁

职责：
1. 监听重要认知事件，转换为交易信号
2. 监听交易决策，反馈给认知层
3. 提供跨总线的事件查询
"""

import time
import logging
from typing import Any, Dict, List, Optional, Set
from dataclasses import asdict

log = logging.getLogger(__name__)


class BusBridge:
    """
    连接认知总线和交易总线的桥梁
    
    通信场景：
    1. 认知 → 交易：重要叙事/风险事件触发交易信号
    2. 交易 → 认知：交易结果反馈认知调整
    """
    
    def __init__(self, cognitive_bus=None, trading_bus=None):
        """
        Args:
            cognitive_bus: 认知总线实例（从 cognitive_bus 导入）
            trading_bus: 交易总线实例（从 trading_bus 导入）
        """
        self.cognitive_bus = cognitive_bus
        self.trading_bus = trading_bus
        self._bridge_enabled = False
        
        # 转换规则配置
        self._cognitive_to_trading_rules = {
            # 认知事件类型 → (重要性阈值, 转换函数)
            'NARRATIVE_UPDATE': (0.7, self._narrative_to_strategy_signal),
            'TIMING_NARRATIVE_SHIFT': (0.8, self._timing_shift_to_signal),
            'RESONANCE_DETECTED': (0.75, self._resonance_to_signal),
            'RISK_ALERT': (0.9, self._risk_alert_to_signal),
        }
        
        # 统计
        self._bridge_stats = {
            'cognitive_to_trading': 0,
            'trading_to_cognitive': 0,
            'filtered_by_importance': 0,
            'conversion_errors': 0,
        }
        
        log.info("[BusBridge] 桥梁初始化完成（未启用）")
    
    def enable_bridge(self, enable: bool = True):
        """启用/禁用桥梁"""
        if enable and (self.cognitive_bus is None or self.trading_bus is None):
            log.error("启用桥梁失败：总线实例未设置")
            return False
        
        self._bridge_enabled = enable
        
        if enable:
            # 订阅认知总线的重要事件
            self._setup_cognitive_subscriptions()
            log.info("[BusBridge] 桥梁已启用")
        else:
            log.info("[BusBridge] 桥梁已禁用")
        
        return True
    
    def set_buses(self, cognitive_bus, trading_bus):
        """设置总线实例"""
        self.cognitive_bus = cognitive_bus
        self.trading_bus = trading_bus
        log.info("[BusBridge] 总线实例已设置")
        
        # 如果桥梁已启用，重新设置订阅
        if self._bridge_enabled:
            self._setup_cognitive_subscriptions()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取桥梁统计"""
        return dict(self._bridge_stats)
    
    # ============== 认知 → 交易转换 ==============
    
    def _setup_cognitive_subscriptions(self):
        """设置认知事件订阅"""
        if self.cognitive_bus is None:
            return
        
        # 清理旧订阅
        if hasattr(self, '_cognitive_subscription_id'):
            self.cognitive_bus.unsubscribe_cognitive(self._cognitive_subscription_id)
        
        # 创建新的订阅
        from .cognitive_bus import CognitiveEventType
        
        # 订阅所有重要认知事件
        self._cognitive_subscription_id = self.cognitive_bus.subscribe_cognitive(
            module_name='bus_bridge',
            callback=self._process_cognitive_event,
            event_types=list(CognitiveEventType),
            min_importance=0.6,  # 只关注重要性较高的事件
        )
        
        log.info(f"[BusBridge] 已订阅认知总线 (id={self._cognitive_subscription_id})")
    
    def _process_cognitive_event(self, event):
        """处理认知事件，转换为交易信号"""
        if not self._bridge_enabled or self.trading_bus is None:
            return
        
        try:
            event_type = event.event_type.value
            importance = event.importance
            
            # 检查是否有转换规则
            if event_type not in self._cognitive_to_trading_rules:
                return
            
            importance_threshold, conversion_func = self._cognitive_to_trading_rules[event_type]
            
            # 重要性阈值检查
            if importance < importance_threshold:
                self._bridge_stats['filtered_by_importance'] += 1
                log.debug(f"认知事件重要性不足: {event_type} importance={importance:.2f} < {importance_threshold}")
                return
            
            # 执行转换
            trading_event = conversion_func(event)
            if trading_event is None:
                return
            
            # 发布到交易总线
            result = self.trading_bus.publish(trading_event)
            if result > 0:
                self._bridge_stats['cognitive_to_trading'] += 1
                log.info(f"认知→交易转换: {event_type} → {trading_event.__class__.__name__}")
                
        except Exception as e:
            self._bridge_stats['conversion_errors'] += 1
            log.error(f"认知事件转换失败: {e}")
    
    def _narrative_to_strategy_signal(self, event) -> Optional[Any]:
        """叙事更新 → 策略信号"""
        from .trading_events import StrategySignalEvent, SignalDirection
        
        # 获取相关股票代码
        stock_codes = getattr(event, 'stock_codes', [])
        if not stock_codes:
            log.debug("叙事事件无关联股票，不转换")
            return None
        
        # 简单规则：根据叙事强度决定方向
        narrative_type = getattr(event, 'narrative_type', 'unknown')
        if narrative_type in ['risk', 'alert', 'warning']:
            direction = SignalDirection.SELL
        elif narrative_type in ['opportunity', 'trend', 'breakout']:
            direction = SignalDirection.BUY
        else:
            direction = SignalDirection.BUY  # 默认买
        
        # 创建策略信号
        from .trading_events import StrategySignalEvent
        
        return StrategySignalEvent(
            symbol=stock_codes[0],  # 取第一个相关股票
            direction=direction,
            confidence=event.confidence * 0.7,  # 认知信号置信度打折
            strategy_name=f"认知驱动:{event.event_type.value}",
            signal_type='cognitive_driven',
            current_price=None,  # 需要行情数据
            price_change_pct=0.0,
            importance=event.importance,
            market=getattr(event, 'market', 'CN'),
            metadata={
                'cognitive_source': event.source,
                'narrative_type': narrative_type,
                'original_confidence': event.confidence,
            },
            timestamp=time.time(),
        )
    
    def _timing_shift_to_signal(self, event) -> Optional[Any]:
        """时机叙事切换 → 策略信号"""
        from .trading_events import StrategySignalEvent, SignalDirection
        
        # 时机切换可能影响整个市场
        new_regime = getattr(event, 'new_regime', '')
        if new_regime in ['uptrend', 'bullish', 'breakout']:
            # 时机向好，发送买入信号（针对大盘或相关股票）
            direction = SignalDirection.BUY
        elif new_regime in ['downtrend', 'bearish', 'crash']:
            direction = SignalDirection.SELL
        else:
            return None
        
        # 如果没有具体股票，可以发全局信号
        # 这里简单示例
        from .trading_events import StrategySignalEvent
        
        return StrategySignalEvent(
            symbol='GLOBAL',  # 全局信号
            direction=direction,
            confidence=event.confidence * 0.6,
            strategy_name=f"时机转换:{new_regime}",
            signal_type='regime_shift',
            current_price=None,
            price_change_pct=0.0,
            importance=event.importance,
            market=getattr(event, 'market', 'CN'),
            metadata={
                'new_regime': new_regime,
                'old_regime': getattr(event, 'old_regime', ''),
                'original_event': 'TIMING_NARRATIVE_SHIFT',
            },
            timestamp=time.time(),
        )
    
    def _resonance_to_signal(self, event) -> Optional[Any]:
        """共振检测 → 策略信号"""
        # 共振通常是强信号
        from .trading_events import StrategySignalEvent, SignalDirection
        
        stock_codes = getattr(event, 'stock_codes', [])
        if not stock_codes:
            return None
        
        return StrategySignalEvent(
            symbol=stock_codes[0],
            direction=SignalDirection.BUY,  # 共振通常是买入信号
            confidence=event.confidence * 0.8,
            strategy_name='认知共振',
            signal_type='resonance',
            current_price=None,
            price_change_pct=0.0,
            importance=event.importance,
            market=getattr(event, 'market', 'CN'),
            metadata={
                'cognitive_source': event.source,
                'resonance_type': getattr(event, 'resonance_type', 'unknown'),
            },
            timestamp=time.time(),
        )
    
    def _risk_alert_to_signal(self, event) -> Optional[Any]:
        """风险告警 → 策略信号"""
        # 风险告警通常是卖出或减仓信号
        from .trading_events import StrategySignalEvent, SignalDirection
        
        stock_codes = getattr(event, 'stock_codes', [])
        if not stock_codes:
            return None
        
        risk_level = getattr(event, 'risk_level', 'unknown')
        if risk_level in ['high', 'critical', 'severe']:
            direction = SignalDirection.SELL
        else:
            direction = SignalDirection.SELL  # 风险事件默认卖
        
        return StrategySignalEvent(
            symbol=stock_codes[0],
            direction=direction,
            confidence=event.confidence * 0.9,
            strategy_name='风险驱动',
            signal_type='risk_alert',
            current_price=None,
            price_change_pct=0.0,
            importance=event.importance,
            market=getattr(event, 'market', 'CN'),
            metadata={
                'risk_level': risk_level,
                'cognitive_source': event.source,
            },
            timestamp=time.time(),
        )
    
    # ============== 交易 → 认知反馈 ==============
    
    def setup_trading_feedback(self):
        """设置交易决策反馈"""
        if self.trading_bus is None:
            return
        
        # 订阅交易决策事件
        from .trading_events import TradeDecisionEvent
        
        self._trading_subscription_id = self.trading_bus.subscribe(
            event_type='TradeDecisionEvent',
            callback=self._process_trade_decision,
            subscription_id='bridge_trading_feedback',
        )
        
        log.info(f"[BusBridge] 已订阅交易决策反馈 (id={self._trading_subscription_id})")
    
    def _process_trade_decision(self, event):
        """处理交易决策，反馈给认知层"""
        if not self._bridge_enabled or self.cognitive_bus is None:
            return
        
        try:
            # 分析决策结果
            decision = event.decision.value
            approval_score = event.approval_score
            signal_event = event.signal_event
            
            # 根据决策结果调整认知
            if decision == 'APPROVED':
                # 交易通过，可以增强相关叙事信心
                self._reinforce_narrative(signal_event, approval_score)
            elif decision == 'REJECTED':
                # 交易被拒，可能需要调整风险认知
                self._adjust_risk_cognition(signal_event, approval_score)
            
            self._bridge_stats['trading_to_cognitive'] += 1
            
        except Exception as e:
            log.error(f"交易决策反馈处理失败: {e}")
    
    def _reinforce_narrative(self, signal_event, approval_score):
        """增强叙事信心"""
        # 简单实现：记录成功的交易决策
        log.debug(f"交易通过，增强相关叙事信心: {signal_event}")
        
        # 实际中可以：
        # 1. 更新叙事强度
        # 2. 调整置信度
        # 3. 标记已验证的交易逻辑
    
    def _adjust_risk_cognition(self, signal_event, approval_score):
        """调整风险认知"""
        # 简单实现：记录被拒的交易决策
        log.debug(f"交易被拒，调整风险认知: {signal_event}")
        
        # 实际中可以：
        # 1. 提高风险等级
        # 2. 增加过滤条件
        # 3. 学习拒绝模式
    
    # ============== 公共接口 ==============
    
    def get_cross_bus_history(self, event_types: List[str], limit: int = 50) -> List[Dict]:
        """
        跨总线查询事件历史
        
        Args:
            event_types: 事件类型列表
            limit: 每类事件限制
            
        Returns:
            合并的事件历史
        """
        results = []
        
        # 从认知总线查询
        if self.cognitive_bus:
            # 这里简化实现，实际需要根据总线接口调整
            pass
        
        # 从交易总线查询
        if self.trading_bus:
            for event_type in event_types:
                try:
                    history = self.trading_bus.get_history(event_type, limit)
                    for item in history:
                        item['bus_type'] = 'trading'
                        results.append(item)
                except Exception:
                    pass
        
        # 按时间戳排序
        results.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        return results[:limit]


# ============== 单例实例 ==============

_bridge_instance = None


def get_bus_bridge() -> BusBridge:
    """获取桥梁单例"""
    global _bridge_instance
    
    if _bridge_instance is None:
        # 动态导入总线
        try:
            from .cognitive_bus import get_event_bus as get_cognitive_bus
            from .trading_bus import get_trading_bus
            
            cognitive_bus = get_cognitive_bus()
            trading_bus = get_trading_bus()
            
            _bridge_instance = BusBridge(cognitive_bus, trading_bus)
            log.info("[get_bus_bridge] 桥梁单例已创建")
            
        except ImportError as e:
            log.warning(f"无法导入总线实例: {e}")
            _bridge_instance = BusBridge()
    
    return _bridge_instance


def create_bus_bridge(cognitive_bus, trading_bus) -> BusBridge:
    """手动创建桥梁（用于测试）"""
    return BusBridge(cognitive_bus, trading_bus)