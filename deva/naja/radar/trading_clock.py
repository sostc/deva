"""
TradingClock - 感知系统/交易时钟/开盘收盘

别名/关键词: 交易时钟、开盘、盘中、收盘、trading clock、market hours

发布交易时段信号，供所有需要响应交易时间的组件订阅：
- call_auction: 集合竞价 (09:15-09:25)
- pre_market: 盘前 (09:25-09:30)
- trading: 交易中 (09:30-11:30 / 13:00-15:00)
- lunch: 午间休市 (11:30-13:00)
- post_market: 盘后 (15:00-15:30)
- closed: 收盘/休市

信号类型：
- current_state: 系统启动时发布，包含当前时段信息
- phase_change: 时段变化时发布，包含变化前后信息

使用方式:
    >>> from deva.naja.radar.trading_clock import get_trading_clock, TRADING_CLOCK_STREAM
    >>> tc = get_trading_clock()
    >>> TRADING_CLOCK_STREAM.sink(lambda x: print(f"交易信号: {x}"))

---

"""

import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Any

from deva import NS

log = logging.getLogger(__name__)

TRADING_CLOCK_STREAM = NS(
    'trading_clock',
    description='交易时间信号流，发布交易时段变化信号',
    cache_max_len=10,
    cache_max_age_seconds=300,
)


class TradingClock:
    """
    交易时钟 - 统一发布交易时段信号

    只有一个实例，负责：
    1. 精确计算下一个时间点
    2. 只在时段变化时发布信号
    3. 提供当前时段查询
    """

    _instance: Optional['TradingClock'] = None
    _lock = threading.Lock()

    PHASES = ['closed', 'call_auction', 'pre_market', 'trading', 'lunch', 'post_market']

    PHASE_TIMES = {
        'closed': {'hour': 9, 'minute': 15, 'next_phase': None},
        'call_auction': {'hour': 9, 'minute': 25, 'next_phase': 'pre_market'},
        'pre_market': {'hour': 9, 'minute': 30, 'next_phase': 'trading'},
        'trading': {'hour': 11, 'minute': 30, 'next_phase': 'lunch'},
        'lunch': {'hour': 13, 'minute': 0, 'next_phase': 'trading'},
        'post_market': {'hour': 15, 'minute': 0, 'next_phase': 'closed'},
    }

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._current_phase: str = 'closed'
        self._last_emit_time: float = 0
        self._subscribers: List[Callable] = []

        self._initialized = True
        log.info("[TradingClock] 交易时钟初始化完成")

    def start(self):
        """启动交易时钟"""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()

        self._thread = threading.Thread(target=self._run_loop, daemon=True, name='trading-clock')
        self._thread.start()

        self._current_phase = self._get_phase_at(datetime.now())

        self._emit_current_state()

        log.info("[TradingClock] 交易时钟已启动")

    def stop(self):
        """停止交易时钟"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=3.0)

        log.info("[TradingClock] 交易时钟已停止")

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]):
        """
        订阅交易时段信号

        Args:
            callback: 回调函数，接收信号字典
        """
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable):
        """取消订阅"""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    @property
    def current_phase(self) -> str:
        """获取当前时段"""
        return self._get_phase_at(datetime.now())

    def get_current_signal(self) -> Dict[str, Any]:
        """获取当前时段信号（不发布）"""
        now = datetime.now()
        phase = self._get_phase_at(now)
        next_info = self._get_next_change_info(now, phase)

        return {
            'type': 'current_state',
            'phase': phase,
            'timestamp': now.timestamp(),
            'datetime': now.isoformat(),
            'next_phase': next_info['next_phase'],
            'next_change_time': next_info['next_change_time'].isoformat() if next_info['next_change_time'] else None,
            'seconds_until_next': next_info['seconds_until_next'],
        }

    def _get_phase_at(self, dt: datetime) -> str:
        """计算指定时间的时段"""
        if dt.weekday() >= 5:
            return 'closed'

        t = dt.time()
        h, m = t.hour, t.minute
        total_minutes = h * 60 + m

        CALL_AUCTION_START = 9 * 60 + 15
        CALL_AUCTION_END = 9 * 60 + 25
        PRE_START = 9 * 60 + 25
        PRE_END = 9 * 60 + 30
        MORNING_END = 11 * 60 + 30
        LUNCH_END = 13 * 60
        AFTERNOON_END = 15 * 60
        POST_END = 15 * 60 + 30

        if total_minutes < CALL_AUCTION_START:
            return 'closed'
        elif CALL_AUCTION_START <= total_minutes < CALL_AUCTION_END:
            return 'call_auction'
        elif CALL_AUCTION_END <= total_minutes < PRE_END:
            return 'pre_market'
        elif PRE_END <= total_minutes < MORNING_END:
            return 'trading'
        elif MORNING_END <= total_minutes < LUNCH_END:
            return 'lunch'
        elif LUNCH_END <= total_minutes < AFTERNOON_END:
            return 'trading'
        elif AFTERNOON_END <= total_minutes < POST_END:
            return 'post_market'
        else:
            return 'closed'

    def _get_next_change_info(self, now: datetime, current_phase: str) -> Dict:
        """计算当前时段的下一次变化信息"""
        today = now.date()
        next_change_time = None
        seconds_until_next = None

        if current_phase == 'closed':
            next_day = now + timedelta(days=1)
            while next_day.weekday() >= 5:
                next_day += timedelta(days=1)
            next_change_time = datetime.combine(next_day, datetime.min.time().replace(hour=9, minute=15))
            seconds_until_next = (next_change_time - now).total_seconds()

        elif current_phase == 'call_auction':
            next_change_time = datetime.combine(today, datetime.min.time().replace(hour=9, minute=25))
            seconds_until_next = (next_change_time - now).total_seconds()

        elif current_phase == 'pre_market':
            next_change_time = datetime.combine(today, datetime.min.time().replace(hour=9, minute=30))
            seconds_until_next = (next_change_time - now).total_seconds()

        elif current_phase == 'trading':
            if now.time().hour < 12:
                next_change_time = datetime.combine(today, datetime.min.time().replace(hour=11, minute=30))
            else:
                next_change_time = datetime.combine(today, datetime.min.time().replace(hour=15, minute=0))
            seconds_until_next = (next_change_time - now).total_seconds()

        elif current_phase == 'lunch':
            next_change_time = datetime.combine(today, datetime.min.time().replace(hour=13, minute=0))
            seconds_until_next = (next_change_time - now).total_seconds()

        elif current_phase == 'post_market':
            next_change_time = datetime.combine(today, datetime.min.time().replace(hour=15, minute=30))
            seconds_until_next = (next_change_time - now).total_seconds()

        return {
            'next_phase': self.PHASE_TIMES.get(current_phase, {}).get('next_phase'),
            'next_change_time': next_change_time,
            'seconds_until_next': max(0, seconds_until_next) if seconds_until_next else None,
        }

    def _run_loop(self):
        """主循环"""
        log.info("[TradingClock] 时钟线程开始")

        while self._running and not self._stop_event.is_set():
            try:
                now = datetime.now()
                new_phase = self._get_phase_at(now)

                if new_phase != self._current_phase:
                    self._emit_phase_change(new_phase, now)

                seconds_until_next = self._calculate_sleep_time(now, new_phase)
                sleep_time = max(1, min(seconds_until_next, 60))

                self._stop_event.wait(sleep_time)

            except Exception as e:
                log.error(f"[TradingClock] 时钟循环异常: {e}")
                self._stop_event.wait(5)

        log.info("[TradingClock] 时钟线程结束")

    def _calculate_sleep_time(self, now: datetime, phase: str) -> float:
        """计算到下一次变化的秒数"""
        info = self._get_next_change_info(now, phase)
        if info['seconds_until_next'] is not None:
            return max(1, info['seconds_until_next'])
        return 60

    def _emit_phase_change(self, new_phase: str, now: datetime):
        """发布时段变化信号"""
        old_phase = self._current_phase
        self._current_phase = new_phase

        signal = self.get_current_signal()
        signal['type'] = 'phase_change'
        signal['previous_phase'] = old_phase
        signal['change_reason'] = self._get_change_reason(old_phase, new_phase)

        TRADING_CLOCK_STREAM.emit(signal)

        for callback in self._subscribers:
            try:
                callback(signal)
            except Exception as e:
                log.error(f"[TradingClock] 订阅回调异常: {e}")

        if new_phase == 'post_market':
            try:
                from deva.naja.snapshot_manager import record_market_state_snapshot
                record_market_state_snapshot(force=True)
            except Exception as e:
                log.debug(f"[TradingClock] 记录市场状态快照失败: {e}")

        log.info(f"[TradingClock] 时段变化: {old_phase} -> {new_phase}")

    def _emit_current_state(self):
        """发布当前状态信号（系统启动时调用）"""
        signal = self.get_current_signal()
        signal['type'] = 'current_state'
        signal['previous_phase'] = None
        signal['change_reason'] = '系统启动'

        TRADING_CLOCK_STREAM.emit(signal)

        for callback in self._subscribers:
            try:
                callback(signal)
            except Exception as e:
                log.error(f"[TradingClock] 订阅回调异常: {e}")

        log.info(f"[TradingClock] 发布当前状态: {self._current_phase}")

    def _get_change_reason(self, old: str, new: str) -> str:
        """获取变化原因描述"""
        reasons = {
            ('closed', 'call_auction'): '集合竞价开始',
            ('call_auction', 'pre_market'): '集合竞价结束，等待交易',
            ('pre_market', 'trading'): '开始交易',
            ('trading', 'lunch'): '午间休市',
            ('lunch', 'trading'): '午间休市结束，下午交易开始',
            ('trading', 'post_market'): '收盘',
            ('post_market', 'closed'): '收盘后处理结束',
        }
        return reasons.get((old, new), f'{old} -> {new}')


_trading_clock: Optional[TradingClock] = None
_trading_clock_lock = threading.Lock()


def get_trading_clock() -> TradingClock:
    """获取交易时钟单例"""
    global _trading_clock
    if _trading_clock is None:
        with _trading_clock_lock:
            if _trading_clock is None:
                _trading_clock = TradingClock()
                _trading_clock.start()
    return _trading_clock


def trading_clock_signal(phase: str) -> bool:
    """
    判断当前是否处于指定时段

    Args:
        phase: 时段名称 ('trading', 'pre_market', etc.)

    Returns:
        是否处于该时段
    """
    tc = get_trading_clock()
    return tc.current_phase == phase


def is_trading_time() -> bool:
    """判断当前是否在交易时间内"""
    return trading_clock_signal('trading')


def is_market_closed() -> bool:
    """判断当前是否收盘/休市"""
    return trading_clock_signal('closed')


USTRADING_CLOCK_STREAM = NS(
    'us_trading_clock',
    description='美股交易时间信号流，发布美股交易时段变化信号',
    cache_max_len=10,
    cache_max_age_seconds=300,
)


class USTradingClock:
    """
    美股交易时钟

    复用 MarketSessionManager 的美股时段计算逻辑，发布美股交易时段信号。
    与 A股 TradingClock 完全独立，不修改原有信号机制。

    信号类型：
    - current_state: 系统启动时发布，包含当前时段信息
    - phase_change: 时段变化时发布，包含变化前后信息

    信号格式（与 A股 TradingClock 兼容）：
    - type: 'current_state' | 'phase_change'
    - market: 'US' （标识市场类型）
    - phase: 'trading' | 'pre_market' | 'post_market' | 'closed'
    - timestamp, datetime, next_phase, next_change_time, seconds_until_next
    """

    PHASES = ['closed', 'pre_market', 'trading', 'post_market']

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._current_phase: str = 'closed'
        self._last_emit_time: float = 0
        self._subscribers: List[Callable] = []

        from .global_market_config import get_market_session_manager
        self._market_mgr = get_market_session_manager()

        log.info("[USTradingClock] 美股交易时钟初始化完成")

    def start(self):
        """启动美股交易时钟"""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()

        self._thread = threading.Thread(target=self._run_loop, daemon=True, name='us-trading-clock')
        self._thread.start()

        self._current_phase = self._market_mgr.get_us_trading_phase()

        self._emit_current_state()

        log.info("[USTradingClock] 美股交易时钟已启动")

    def stop(self):
        """停止美股交易时钟"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=3.0)

        log.info("[USTradingClock] 美股交易时钟已停止")

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]):
        """订阅美股交易时段信号"""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable):
        """取消订阅"""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    @property
    def current_phase(self) -> str:
        """获取当前时段"""
        return self._market_mgr.get_us_trading_phase()

    def get_current_signal(self) -> Dict[str, Any]:
        """获取当前时段信号（不发布）"""
        now = datetime.now()
        phase = self.current_phase
        next_info = self._get_next_change_info(now, phase)

        return {
            'type': 'current_state',
            'market': 'US',
            'phase': phase,
            'timestamp': now.timestamp(),
            'datetime': now.isoformat(),
            'next_phase': next_info['next_phase'],
            'next_change_time': next_info['next_change_time'].isoformat() if next_info['next_change_time'] else None,
            'seconds_until_next': next_info['seconds_until_next'],
        }

    def _get_next_change_info(self, now: datetime, current_phase: str) -> Dict:
        """计算当前时段的下一次变化信息（美股）"""
        from pytz import timezone
        us_eastern = timezone('America/New_York')
        us_now = now.astimezone(us_eastern)
        today = us_now.date()

        next_change_time = None
        seconds_until_next = None

        if current_phase == 'closed':
            # 如果当前在美东时间 04:00 之前，下一次开盘仍是“当天 04:00”
            if us_now.time() < datetime.min.time().replace(hour=4, minute=0):
                next_day = us_now
            else:
                next_day = us_now + timedelta(days=1)
            while next_day.weekday() >= 5:
                next_day += timedelta(days=1)
            next_change_time = datetime.combine(next_day.date(), datetime.min.time().replace(hour=4, minute=0), tzinfo=us_eastern)
            seconds_until_next = (next_change_time - us_now).total_seconds()

        elif current_phase == 'pre_market':
            next_change_time = datetime.combine(today, datetime.min.time().replace(hour=9, minute=30), tzinfo=us_eastern)
            seconds_until_next = (next_change_time - us_now).total_seconds()

        elif current_phase == 'trading':
            next_change_time = datetime.combine(today, datetime.min.time().replace(hour=16, minute=0), tzinfo=us_eastern)
            seconds_until_next = (next_change_time - us_now).total_seconds()

        elif current_phase == 'post_market':
            next_change_time = datetime.combine(today, datetime.min.time().replace(hour=20, minute=0), tzinfo=us_eastern)
            seconds_until_next = (next_change_time - us_now).total_seconds()

        return {
            'next_phase': self._get_next_phase(current_phase),
            'next_change_time': next_change_time,
            'seconds_until_next': max(0, seconds_until_next) if seconds_until_next else None,
        }

    def _get_next_phase(self, current: str) -> Optional[str]:
        transitions = {
            'closed': 'pre_market',
            'pre_market': 'trading',
            'trading': 'post_market',
            'post_market': 'closed',
        }
        return transitions.get(current)

    def _run_loop(self):
        """主循环"""
        log.info("[USTradingClock] 时钟线程开始")

        while self._running and not self._stop_event.is_set():
            try:
                new_phase = self._market_mgr.get_us_trading_phase()

                if new_phase != self._current_phase:
                    self._emit_phase_change(new_phase)

                info = self._get_next_change_info(datetime.now(), new_phase)
                sleep_time = max(1, info['seconds_until_next'] or 60)

                self._stop_event.wait(sleep_time)

            except Exception as e:
                log.error(f"[USTradingClock] 时钟循环异常: {e}")
                self._stop_event.wait(5)

        log.info("[USTradingClock] 时钟线程结束")

    def _emit_phase_change(self, new_phase: str):
        """发布时段变化信号"""
        old_phase = self._current_phase
        self._current_phase = new_phase

        signal = self.get_current_signal()
        signal['type'] = 'phase_change'
        signal['previous_phase'] = old_phase
        signal['change_reason'] = self._get_change_reason(old_phase, new_phase)

        USTRADING_CLOCK_STREAM.emit(signal)

        for callback in self._subscribers:
            try:
                callback(signal)
            except Exception as e:
                log.error(f"[USTradingClock] 订阅回调异常: {e}")

        log.info(f"[USTradingClock] 时段变化: {old_phase} -> {new_phase}")

    def _emit_current_state(self):
        """发布当前状态信号（系统启动时调用）"""
        signal = self.get_current_signal()
        signal['type'] = 'current_state'
        signal['previous_phase'] = None
        signal['change_reason'] = '系统启动'

        USTRADING_CLOCK_STREAM.emit(signal)

        for callback in self._subscribers:
            try:
                callback(signal)
            except Exception as e:
                log.error(f"[USTradingClock] 订阅回调异常: {e}")

        log.info(f"[USTradingClock] 发布当前状态: {self._current_phase}")

    def _get_change_reason(self, old: str, new: str) -> str:
        """获取变化原因描述"""
        reasons = {
            ('closed', 'pre_market'): '盘前交易开始',
            ('pre_market', 'trading'): '美股开始交易',
            ('trading', 'post_market'): '盘后交易开始',
            ('post_market', 'closed'): '盘后交易结束',
        }
        return reasons.get((old, new), f'{old} -> {new}')


_us_trading_clock: Optional[USTradingClock] = None
_us_trading_clock_lock = threading.Lock()


def get_us_trading_clock() -> USTradingClock:
    """获取美股交易时钟单例"""
    global _us_trading_clock
    if _us_trading_clock is None:
        with _us_trading_clock_lock:
            if _us_trading_clock is None:
                _us_trading_clock = USTradingClock()
                _us_trading_clock.start()
    return _us_trading_clock


def us_trading_clock_signal(phase: str) -> bool:
    """判断美股当前是否处于指定时段"""
    tc = get_us_trading_clock()
    return tc.current_phase == phase


def is_us_trading_time() -> bool:
    """判断美股当前是否在交易时间内"""
    return us_trading_clock_signal('trading')


def is_us_market_closed() -> bool:
    """判断美股当前是否收盘/休市"""
    return us_trading_clock_signal('closed')
