"""Attention Tracker - 注意力跟踪器

跟踪注意力选中的标的，不需要实际成交即可形成反馈。

核心功能:
- 记录注意力选中的标的 (track_attention)
- 持续跟踪价格变化 (update_price)
- 生成观察反馈 (get_observation_result)
- 与 Bandit 和 FeedbackLoop 集成
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from collections import deque

from deva import NB
from deva.naja.register import SR

log = logging.getLogger(__name__)

ATTENTION_TRACKER_TABLE = "naja_attention_tracker"


@dataclass
class TrackedAttention:
    """跟踪中的注意力标的"""
    symbol: str
    block_id: str
    strategy_id: str
    strategy_name: str
    attention_score: float
    prediction_score: float
    action: str
    entry_price: float
    entry_time: float
    last_update_time: float
    current_price: float
    highest_price: float
    lowest_price: float
    market_state: str
    status: str = "TRACKING"
    exit_price: float = 0.0
    exit_time: float = 0.0
    close_reason: str = ""
    
    @property
    def return_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price * 100
    
    @property
    def price_change_pct(self) -> float:
        if self.highest_price == 0:
            return 0.0
        return (self.highest_price - self.entry_price) / self.entry_price * 100
    
    @property
    def holding_seconds(self) -> float:
        return time.time() - self.entry_time
    
    @property
    def max_favorable_move(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return (self.highest_price - self.entry_price) / self.entry_price * 100
    
    @property
    def max_adverse_move(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return (self.lowest_price - self.entry_price) / self.entry_price * 100


@dataclass 
class ObservationResult:
    """观察结果"""
    symbol: str
    block_id: str
    strategy_id: str
    attention_score: float
    prediction_score: float
    action: str
    entry_price: float
    exit_price: float
    holding_seconds: float
    return_pct: float
    max_favorable_move: float
    max_adverse_move: float
    market_state: str
    entry_time: float
    exit_time: float
    close_reason: str
    
    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'block_id': self.block_id,
            'strategy_id': self.strategy_id,
            'attention_score': self.attention_score,
            'prediction_score': self.prediction_score,
            'action': self.action,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'holding_seconds': self.holding_seconds,
            'return_pct': self.return_pct,
            'max_favorable_move': self.max_favorable_move,
            'max_adverse_move': self.max_adverse_move,
            'market_state': self.market_state,
            'entry_time': self.entry_time,
            'exit_time': self.exit_time,
            'close_reason': self.close_reason,
        }


@dataclass
class PriceUpdateSignal:
    """价格更新信号"""
    symbol: str
    current_price: float
    timestamp: float
    return_pct: float
    holding_seconds: float
    is_new_high: bool
    is_new_low: bool


class AttentionTracker:
    """
    注意力跟踪器
    
    职责:
    - 记录注意力选中的标的 (不需要实际成交)
    - 跟踪价格变化
    - 生成观察结果反馈
    
    与 BanditVirtualPortfolio 的区别:
    - BanditVirtualPortfolio 需要实际成交
    - AttentionTracker 只需要注意力选中即可
    - 更早开始学习,样本量更大
    """
    
    def __init__(
        self,
        observation_duration: float = 3600.0,
        min_confidence: float = 0.5,
        auto_close_on_expire: bool = True,
        frequency_scheduler=None,
    ):
        self._tracked: Dict[str, TrackedAttention] = {}
        self._lock = threading.RLock()

        self._db = NB(ATTENTION_TRACKER_TABLE)

        self._observation_duration = observation_duration
        self._min_confidence = min_confidence
        self._auto_close_on_expire = auto_close_on_expire
        self._frequency_scheduler = frequency_scheduler

        self._callbacks: List[Callable[[PriceUpdateSignal], None]] = []
        self._observation_callbacks: List[Callable[[ObservationResult], None]] = []

        self._price_history: Dict[str, deque] = {}
        self._max_history_len = 100

        self._load_from_db()
    
    def _load_from_db(self):
        """从数据库加载未完成跟踪"""
        try:
            data = self._db.items()
            for key, value in data.items():
                if isinstance(value, dict) and value.get('status') == 'TRACKING':
                    symbol = value.get('symbol')
                    if symbol:
                        tracked = self._from_dict(value)
                        self._tracked[symbol] = tracked
                        log.info(f"恢复跟踪: {symbol}")
        except Exception as e:
            log.debug(f"从数据库加载跟踪失败: {e}")
    
    def _save_to_db(self, tracked: TrackedAttention):
        """保存到数据库"""
        try:
            key = f"{tracked.symbol}_{int(tracked.entry_time * 1000)}"
            self._db[key] = self._to_dict(tracked)
        except Exception as e:
            log.debug(f"保存跟踪到数据库失败: {e}")
    
    def _to_dict(self, tracked: TrackedAttention) -> dict:
        return {
            'symbol': tracked.symbol,
            'block_id': tracked.block_id,
            'strategy_id': tracked.strategy_id,
            'strategy_name': tracked.strategy_name,
            'attention_score': tracked.attention_score,
            'prediction_score': tracked.prediction_score,
            'action': tracked.action,
            'entry_price': tracked.entry_price,
            'current_price': tracked.current_price,
            'highest_price': tracked.highest_price,
            'lowest_price': tracked.lowest_price,
            'entry_time': tracked.entry_time,
            'last_update_time': tracked.last_update_time,
            'market_state': tracked.market_state,
            'status': tracked.status,
            'exit_price': tracked.exit_price,
            'exit_time': tracked.exit_time,
            'close_reason': tracked.close_reason,
        }
    
    def _from_dict(self, data: dict) -> TrackedAttention:
        return TrackedAttention(
            symbol=data.get('symbol', ''),
            block_id=data.get('block_id', data.get('block_id', '')),
            strategy_id=data.get('strategy_id', ''),
            strategy_name=data.get('strategy_name', ''),
            attention_score=data.get('attention_score', 0.0),
            prediction_score=data.get('prediction_score', 0.0),
            action=data.get('action', ''),
            entry_price=data.get('entry_price', 0.0),
            current_price=data.get('current_price', 0.0),
            highest_price=data.get('highest_price', 0.0),
            lowest_price=data.get('lowest_price', 0.0),
            entry_time=data.get('entry_time', 0.0),
            last_update_time=data.get('last_update_time', 0.0),
            market_state=data.get('market_state', 'unknown'),
            status=data.get('status', 'TRACKING'),
            exit_price=data.get('exit_price', 0.0),
            exit_time=data.get('exit_time', 0.0),
            close_reason=data.get('close_reason', ''),
        )
    
    def track_attention(
        self,
        symbol: str,
        block_id: str,
        strategy_id: str,
        strategy_name: str,
        attention_score: float,
        prediction_score: float,
        action: str,
        entry_price: float,
        market_state: str = "unknown",
    ) -> Optional[TrackedAttention]:
        """
        开始跟踪一个注意力标的
        
        Args:
            symbol: 股票代码
            block_id: 题材ID
            strategy_id: 策略ID
            strategy_name: 策略名称
            attention_score: 注意力分数
            prediction_score: 预测分数
            action: 动作 (BUY/HOLD/SELL等)
            entry_price: 入场价格
            market_state: 市场状态
            
        Returns:
            TrackedAttention 或 None (如果置信度不足)
        """
        if prediction_score < self._min_confidence:
            log.debug(f"置信度不足跳过跟踪: {symbol} {prediction_score:.2f} < {self._min_confidence}")
            return None
        
        with self._lock:
            now = time.time()
            
            if symbol in self._tracked:
                existing = self._tracked[symbol]
                if existing.status == "TRACKING":
                    log.debug(f"标的已在跟踪中: {symbol}")
                    return existing
            
            tracked = TrackedAttention(
                symbol=symbol,
                block_id=block_id,
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                attention_score=attention_score,
                prediction_score=prediction_score,
                action=action,
                entry_price=entry_price,
                current_price=entry_price,
                highest_price=entry_price,
                lowest_price=entry_price,
                entry_time=now,
                last_update_time=now,
                market_state=market_state,
                status="TRACKING",
            )

            self._tracked[symbol] = tracked
            self._price_history[symbol] = deque(maxlen=self._max_history_len)
            self._save_to_db(tracked)

            self._register_to_frequency_scheduler(symbol, attention_score)
            self._add_to_price_monitor(symbol, entry_price, now)

            self._record_signal_to_reporter(
                symbol, block_id, strategy_id, strategy_name,
                action, attention_score, prediction_score, entry_price, market_state
            )

            log.info(f"开始跟踪注意力: {symbol} 注意力={attention_score:.2f} 预测={prediction_score:.2f}")
            return tracked

    def _register_to_frequency_scheduler(self, symbol: str, attention_score: float):
        """将 symbol 注册到频率调度器"""
        if self._frequency_scheduler is not None:
            try:
                self._frequency_scheduler.register_symbol(symbol)
            except Exception:
                pass

    def _add_to_price_monitor(self, symbol: str, entry_price: float, entry_time: float):
        """将 symbol 添加到 PriceMonitor"""
        try:
            pm = SR('price_monitor')
            if pm is not None:
                pm.add_tracked(symbol, entry_price, entry_time)
        except Exception:
            pass

    def _record_signal_to_reporter(
        self,
        symbol: str,
        block_id: str,
        strategy_id: str,
        strategy_name: str,
        action: str,
        attention_score: float,
        prediction_score: float,
        entry_price: float,
        market_state: str,
    ):
        """记录信号到报告生成器"""
        try:
            from deva.naja.market_hotspot.intelligence.feedback_report import get_feedback_report_generator
            reporter = get_feedback_report_generator()
            reporter.record_signal(
                symbol=symbol,
                block_id=block_id,
                strategy_id=strategy_id,
                action=action,
                attention_score=attention_score,
                prediction_score=prediction_score,
                entry_price=entry_price,
                market_state=market_state,
            )
        except Exception:
            pass
    
    def update_price(self, symbol: str, current_price: float, timestamp: Optional[float] = None) -> Optional[PriceUpdateSignal]:
        """
        更新标的的价格
        
        Args:
            symbol: 股票代码
            current_price: 当前价格
            timestamp: 时间戳
            
        Returns:
            PriceUpdateSignal 如果产生更新
        """
        if timestamp is None:
            timestamp = time.time()
        
        with self._lock:
            if symbol not in self._tracked:
                return None
            
            tracked = self._tracked[symbol]
            
            if tracked.status != "TRACKING":
                return None
            
            old_price = tracked.current_price
            tracked.current_price = current_price
            tracked.last_update_time = timestamp
            
            is_new_high = current_price > tracked.highest_price
            is_new_low = current_price < tracked.lowest_price
            
            if is_new_high:
                tracked.highest_price = current_price
            if is_new_low:
                tracked.lowest_price = current_price
            
            self._price_history[symbol].append({
                'price': current_price,
                'timestamp': timestamp,
            })
            
            return_pct = (current_price - tracked.entry_price) / tracked.entry_price * 100 if tracked.entry_price > 0 else 0
            holding_seconds = timestamp - tracked.entry_time
            
            signal = PriceUpdateSignal(
                symbol=symbol,
                current_price=current_price,
                timestamp=timestamp,
                return_pct=return_pct,
                holding_seconds=holding_seconds,
                is_new_high=is_new_high,
                is_new_low=is_new_low,
            )
            
            for callback in self._callbacks:
                try:
                    callback(signal)
                except Exception as e:
                    log.error(f"价格更新回调失败: {e}")
            
            self._save_to_db(tracked)
            return signal
    
    def close_tracking(
        self,
        symbol: str,
        exit_price: float,
        reason: str = "MANUAL",
        timestamp: Optional[float] = None
    ) -> Optional[ObservationResult]:
        """
        关闭跟踪,生成观察结果
        
        Args:
            symbol: 股票代码
            exit_price: 出场价格
            reason: 关闭原因
            timestamp: 时间戳
        """
        if timestamp is None:
            timestamp = time.time()
        
        with self._lock:
            if symbol not in self._tracked:
                return None
            
            tracked = self._tracked[symbol]
            
            if tracked.status != "TRACKING":
                return None
            
            tracked.status = "CLOSED"
            tracked.exit_price = exit_price
            tracked.exit_time = timestamp
            tracked.close_reason = reason
            
            result = ObservationResult(
                symbol=tracked.symbol,
                block_id=tracked.block_id,
                strategy_id=tracked.strategy_id,
                attention_score=tracked.attention_score,
                prediction_score=tracked.prediction_score,
                action=tracked.action,
                entry_price=tracked.entry_price,
                exit_price=exit_price,
                holding_seconds=tracked.holding_seconds,
                return_pct=tracked.return_pct,
                max_favorable_move=tracked.max_favorable_move,
                max_adverse_move=tracked.max_adverse_move,
                market_state=tracked.market_state,
                entry_time=tracked.entry_time,
                exit_time=timestamp,
                close_reason=reason,
            )
            
            self._save_to_db(tracked)
            
            for callback in self._observation_callbacks:
                try:
                    callback(result)
                except Exception as e:
                    log.error(f"观察结果回调失败: {e}")
            
            log.info(f"关闭跟踪: {symbol} 原因={reason} 收益={result.return_pct:.2f}%")
            return result
    
    def check_expired(self) -> List[ObservationResult]:
        """检查并关闭过期的跟踪"""
        results = []
        now = time.time()
        
        with self._lock:
            expired = []
            
            for symbol, tracked in self._tracked.items():
                if tracked.status != "TRACKING":
                    continue
                
                if now - tracked.entry_time > self._observation_duration:
                    expired.append(symbol)
            
            for symbol in expired:
                tracked = self._tracked[symbol]
                result = self.close_tracking(
                    symbol,
                    tracked.current_price,
                    reason="EXPIRED",
                    timestamp=now
                )
                if result:
                    results.append(result)
        
        return results
    
    def register_price_callback(self, callback: Callable[[PriceUpdateSignal], None]):
        """注册价格更新回调"""
        self._callbacks.append(callback)
    
    def register_observation_callback(self, callback: Callable[[ObservationResult], None]):
        """注册观察结果回调"""
        self._observation_callbacks.append(callback)
    
    def get_tracked(self, symbol: str) -> Optional[TrackedAttention]:
        """获取跟踪中的标的"""
        return self._tracked.get(symbol)
    
    def get_all_tracked(self) -> List[TrackedAttention]:
        """获取所有跟踪中的标的"""
        with self._lock:
            return [t for t in self._tracked.values() if t.status == "TRACKING"]
    
    def get_price_history(self, symbol: str) -> List[dict]:
        """获取价格历史"""
        if symbol in self._price_history:
            return list(self._price_history[symbol])
        return []
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        with self._lock:
            tracking = [t for t in self._tracked.values() if t.status == "TRACKING"]
            closed = [t for t in self._tracked.values() if t.status == "CLOSED"]
            
            closed_returns = [t.return_pct for t in closed if t.return_pct != 0]
            
            return {
                'tracking_count': len(tracking),
                'closed_count': len(closed),
                'total_tracked': len(self._tracked),
                'avg_return': sum(closed_returns) / len(closed_returns) if closed_returns else 0,
                'win_rate': sum(1 for r in closed_returns if r > 0) / len(closed_returns) if closed_returns else 0,
            }


_attention_tracker: Optional[AttentionTracker] = None
_tracker_lock = threading.Lock()


def get_attention_tracker(
    observation_duration: float = 3600.0,
    min_confidence: float = 0.5,
    frequency_scheduler=None,
) -> AttentionTracker:
    """获取 AttentionTracker 单例"""
    global _attention_tracker
    if _attention_tracker is None:
        with _tracker_lock:
            if _attention_tracker is None:
                _attention_tracker = AttentionTracker(
                    observation_duration=observation_duration,
                    min_confidence=min_confidence,
                    frequency_scheduler=frequency_scheduler,
                )
    return _attention_tracker


def ensure_attention_tracker(
    observation_duration: float = 3600.0,
    min_confidence: float = 0.5,
    frequency_scheduler=None,
) -> AttentionTracker:
    """确保 AttentionTracker 已初始化"""
    return get_attention_tracker(observation_duration, min_confidence, frequency_scheduler)
