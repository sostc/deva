"""
事件历史查询接口

为持久化的事件总线提供丰富的历史查询功能，支持：
- 按事件类型查询
- 按时间范围查询
- 按符号（symbol）查询
- 按方向（direction）查询
- 按置信度（confidence）查询
- 分页查询
- 聚合统计
"""

import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

log = logging.getLogger(__name__)


@dataclass
class QueryCondition:
    """查询条件"""
    event_type: Optional[str] = None
    symbol: Optional[str] = None
    direction: Optional[str] = None
    min_confidence: Optional[float] = None
    max_confidence: Optional[float] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    limit: int = 100
    offset: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {}
        if self.event_type:
            result['event_type'] = self.event_type
        if self.symbol:
            result['symbol'] = self.symbol
        if self.direction:
            result['direction'] = self.direction
        if self.min_confidence is not None:
            result['min_confidence'] = self.min_confidence
        if self.max_confidence is not None:
            result['max_confidence'] = self.max_confidence
        if self.start_time:
            result['start_time'] = self.start_time
        if self.end_time:
            result['end_time'] = self.end_time
        result['limit'] = self.limit
        result['offset'] = self.offset
        return result


@dataclass
class EventStats:
    """事件统计"""
    total_events: int = 0
    buy_signals: int = 0
    sell_signals: int = 0
    avg_confidence: float = 0.0
    max_confidence: float = 0.0
    min_confidence: float = 0.0
    timeline: Dict[str, int] = None  # 按小时/天统计
    
    def __post_init__(self):
        if self.timeline is None:
            self.timeline = {}


class EventQuery:
    """
    事件查询接口
    
    使用方式：
        from deva.naja.events.query_interface import EventQuery
        from deva.naja.events import get_event_bus
        
        bus = get_event_bus()
        query = EventQuery(bus)
        
        # 查询策略信号
        signals = query.query_strategy_signals(
            symbol='000001',
            direction='buy',
            days=7
        )
        
        # 获取统计
        stats = query.get_stats('StrategySignalEvent', days=30)
    """
    
    def __init__(self, event_bus):
        self.bus = event_bus
    
    def query_events(self, condition: QueryCondition) -> List[Dict[str, Any]]:
        """
        通用事件查询
        
        Args:
            condition: 查询条件
        
        Returns:
            事件列表（字典格式）
        """
        log.info(f"查询事件: {condition}")
        
        # 获取原始历史数据
        if condition.event_type:
            raw_history = self.bus.get_persistent_history(condition.event_type, limit=1000)
        else:
            # 如果没有指定类型，尝试查询常见类型
            raw_history = []
            for event_type in ['StrategySignalEvent', 'TradeDecisionEvent', 'HotspotComputedEvent']:
                try:
                    history = self.bus.get_persistent_history(event_type, limit=300)
                    if history:
                        raw_history.extend(history)
                except Exception as e:
                    log.debug(f"查询 {event_type} 失败: {e}")
        
        # 过滤
        filtered = []
        for event in raw_history:
            # 按条件过滤
            if not self._matches_condition(event, condition):
                continue
            
            filtered.append(event)
        
        # 排序（按时间倒序）
        filtered.sort(key=lambda e: e.get('timestamp', 0), reverse=True)
        
        # 分页
        start = condition.offset
        end = condition.offset + condition.limit
        result = filtered[start:end]
        
        log.info(f"查询结果: 总数 {len(filtered)}, 返回 {len(result)}")
        return result
    
    def _matches_condition(self, event: Dict[str, Any], condition: QueryCondition) -> bool:
        """检查事件是否匹配条件"""
        # 符号过滤
        if condition.symbol and event.get('symbol') != condition.symbol:
            return False
        
        # 方向过滤
        if condition.direction and event.get('direction') != condition.direction:
            return False
        
        # 置信度过滤
        confidence = event.get('confidence')
        if confidence is not None:
            if condition.min_confidence is not None and confidence < condition.min_confidence:
                return False
            if condition.max_confidence is not None and confidence > condition.max_confidence:
                return False
        
        # 时间过滤
        timestamp = event.get('timestamp')
        if timestamp is not None:
            if condition.start_time and timestamp < condition.start_time:
                return False
            if condition.end_time and timestamp > condition.end_time:
                return False
        
        return True
    
    def query_strategy_signals(self, 
                              symbol: Optional[str] = None,
                              direction: Optional[str] = None,
                              min_confidence: float = 0.0,
                              days: int = 7,
                              limit: int = 100) -> List[Dict[str, Any]]:
        """
        查询策略信号事件
        
        Args:
            symbol: 股票代码
            direction: 方向（buy/sell）
            min_confidence: 最小置信度
            days: 查询天数
            limit: 最大返回数
        
        Returns:
            策略信号列表
        """
        end_time = time.time()
        start_time = end_time - days * 86400
        
        condition = QueryCondition(
            event_type='StrategySignalEvent',
            symbol=symbol,
            direction=direction,
            min_confidence=min_confidence,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        return self.query_events(condition)
    
    def query_trade_decisions(self,
                             symbol: Optional[str] = None,
                             decision: Optional[str] = None,
                             days: int = 7,
                             limit: int = 100) -> List[Dict[str, Any]]:
        """
        查询交易决策事件
        
        Args:
            symbol: 股票代码
            decision: 决策（approved/rejected）
            days: 查询天数
            limit: 最大返回数
        
        Returns:
            交易决策列表
        """
        end_time = time.time()
        start_time = end_time - days * 86400
        
        condition = QueryCondition(
            event_type='TradeDecisionEvent',
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        results = self.query_events(condition)
        
        # 如果指定了 decision，进一步过滤
        if decision:
            results = [r for r in results if r.get('decision') == decision]
        
        return results
    
    def get_stats(self, event_type: str, days: int = 30) -> EventStats:
        """
        获取事件统计
        
        Args:
            event_type: 事件类型
            days: 统计天数
        
        Returns:
            事件统计信息
        """
        end_time = time.time()
        start_time = end_time - days * 86400
        
        condition = QueryCondition(
            event_type=event_type,
            start_time=start_time,
            end_time=end_time,
            limit=1000
        )
        
        events = self.query_events(condition)
        
        stats = EventStats()
        stats.total_events = len(events)
        
        # 计算买卖信号
        buy_count = 0
        sell_count = 0
        confidences = []
        
        for event in events:
            direction = event.get('direction')
            if direction == 'buy':
                buy_count += 1
            elif direction == 'sell':
                sell_count += 1
            
            confidence = event.get('confidence')
            if confidence is not None:
                confidences.append(confidence)
        
        stats.buy_signals = buy_count
        stats.sell_signals = sell_count
        
        if confidences:
            stats.avg_confidence = sum(confidences) / len(confidences)
            stats.max_confidence = max(confidences)
            stats.min_confidence = min(confidences)
        
        # 时间线统计（按天）
        timeline = {}
        for event in events:
            timestamp = event.get('timestamp')
            if timestamp:
                date_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
                timeline[date_str] = timeline.get(date_str, 0) + 1
        
        stats.timeline = timeline
        
        return stats
    
    def export_to_csv(self, event_type: str, output_path: str, days: int = 30):
        """
        导出事件到 CSV 文件
        
        Args:
            event_type: 事件类型
            output_path: 输出文件路径
            days: 导出天数
        """
        import csv
        
        condition = QueryCondition(
            event_type=event_type,
            days=days,
            limit=5000
        )
        
        events = self.query_events(condition)
        
        if not events:
            log.warning(f"没有找到 {event_type} 事件，跳过导出")
            return
        
        # 收集所有可能的列
        all_keys = set()
        for event in events:
            all_keys.update(event.keys())
        
        # 排序列
        sorted_keys = sorted(all_keys)
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=sorted_keys)
            writer.writeheader()
            writer.writerows(events)
        
        log.info(f"✅ 导出完成: {len(events)} 条事件 → {output_path}")
    
    def get_recent_signals_by_strategy(self, 
                                      strategy_name: Optional[str] = None,
                                      days: int = 7) -> Dict[str, List[Dict[str, Any]]]:
        """
        按策略分组查询近期信号
        
        Args:
            strategy_name: 策略名称（可选）
            days: 查询天数
        
        Returns:
            按策略分组的信号字典
        """
        signals = self.query_strategy_signals(days=days, limit=500)
        
        grouped = {}
        for signal in signals:
            name = signal.get('strategy_name', 'unknown')
            
            if strategy_name and name != strategy_name:
                continue
            
            if name not in grouped:
                grouped[name] = []
            
            grouped[name].append(signal)
        
        return grouped


# 创建全局查询接口
_global_query: Optional[EventQuery] = None

def get_event_query() -> EventQuery:
    """获取全局事件查询接口单例"""
    global _global_query
    if _global_query is None:
        from . import get_event_bus
        bus = get_event_bus()
        _global_query = EventQuery(bus)
        log.info("✅ 事件查询接口初始化完成")
    return _global_query


# 简单查询函数（快捷方式）

def query_recent_strategy_signals(symbol: Optional[str] = None, 
                                 direction: Optional[str] = None,
                                 days: int = 7,
                                 limit: int = 100) -> List[Dict[str, Any]]:
    """查询近期策略信号（快捷函数）"""
    return get_event_query().query_strategy_signals(symbol, direction, days=days, limit=limit)

def get_event_statistics(event_type: str, days: int = 30) -> EventStats:
    """获取事件统计（快捷函数）"""
    return get_event_query().get_stats(event_type, days)