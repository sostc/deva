"""
TradingClock - 统一交易时钟（支持 A股 + 美股）

别名/关键词: 交易时钟、开盘、盘中、收盘、trading clock、market hours

设计：
- 单一实例，同时监控 A股和美股市场
- 统一信号流，通过 market 字段区分市场
- A股时段：call_auction, pre_market, trading, lunch, post_market, closed
- 美股时段：pre_market, trading, post_market, closed

信号格式：
{
    'type': 'current_state' | 'phase_change',
    'market': 'CN' | 'US',
    'phase': 'trading' | 'closed' | ...,
    'previous_phase': ...,
    'timestamp': ...,
    'datetime': ...,
    'next_phase': ...,
    'next_change_time': ...,
    'seconds_until_next': ...,
    'change_reason': ...
}

使用方式:
    >>> from deva.naja.radar.trading_clock import TRADING_CLOCK_STREAM
    >>> from deva.naja.register import SR
    >>> tc = SR('trading_clock')
    >>> TRADING_CLOCK_STREAM.sink(lambda x: print(f"信号: market={x.get('market')}, phase={x.get('phase')}"))

---

"""

import threading
import logging
from datetime import datetime, timedelta, time
from typing import Callable, Dict, List, Optional, Any

import pytz

from deva import NS
from deva.naja.register import SR

log = logging.getLogger(__name__)

TRADING_CLOCK_STREAM = NS(
    'trading_clock',
    description='统一交易时间信号流，同时发布 A股 和 美股 时段信号',
    cache_max_len=20,
    cache_max_age_seconds=300,
)


class TradingClock:
    """
    统一交易时钟 - 同时支持 A股 和 美股

    只有一个实例，两个独立线程分别监控：
    - A股市场（中国北京时间）
    - 美股市场（美国东部时间）

    信号发布：
    - 通过 TRADING_CLOCK_STREAM 统一发布
    - 通过 market 字段区分：'CN' 表示 A股，'US' 表示美股
    """

    _instance: Optional['TradingClock'] = None
    _lock = threading.Lock()

    CN_PHASES = ['closed', 'call_auction', 'pre_market', 'trading', 'lunch', 'post_market']
    US_PHASES = ['closed', 'pre_market', 'trading', 'post_market']

    CN_PHASE_TIMES = {
        'closed': {'hour': 9, 'minute': 15, 'next_phase': None},
        'call_auction': {'hour': 9, 'minute': 25, 'next_phase': 'pre_market'},
        'pre_market': {'hour': 9, 'minute': 30, 'next_phase': 'trading'},
        'trading': {'hour': 11, 'minute': 30, 'next_phase': 'lunch'},
        'lunch': {'hour': 13, 'minute': 0, 'next_phase': 'trading'},
        'post_market': {'hour': 15, 'minute': 0, 'next_phase': 'closed'},
    }

    US_PHASE_TIMES = {
        'closed': {'hour': 4, 'minute': 0, 'next_phase': None},
        'pre_market': {'hour': 9, 'minute': 30, 'next_phase': 'trading'},
        'trading': {'hour': 16, 'minute': 0, 'next_phase': 'post_market'},
        'post_market': {'hour': 20, 'minute': 0, 'next_phase': 'closed'},
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
        self._cn_thread: Optional[threading.Thread] = None
        self._us_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._cn_current_phase: str = 'closed'
        self._us_current_phase: str = 'closed'
        self._subscribers: List[Callable] = []

        self._cn_market_mgr = None
        self._us_eastern = pytz.timezone('America/New_York')

        self._initialized = True
        log.info("[TradingClock] 统一交易时钟初始化完成（支持 A股 + 美股）")

    def start(self):
        """启动统一交易时钟"""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()

        self._cn_thread = threading.Thread(target=self._cn_run_loop, daemon=True, name='trading-clock-cn')
        self._us_thread = threading.Thread(target=self._us_run_loop, daemon=True, name='trading-clock-us')

        self._cn_thread.start()
        self._us_thread.start()

        self._cn_current_phase = self._get_cn_phase_at(datetime.now())
        self._us_current_phase = self._get_us_phase_at(datetime.now())

        self._emit_current_state('CN', self._cn_current_phase)
        self._emit_current_state('US', self._us_current_phase)

        log.info("[TradingClock] 统一交易时钟已启动（A股=%s, 美股=%s）",
                 self._cn_current_phase, self._us_current_phase)

    def stop(self):
        """停止统一交易时钟"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._cn_thread:
            self._cn_thread.join(timeout=3.0)
        if self._us_thread:
            self._us_thread.join(timeout=3.0)

        log.info("[TradingClock] 统一交易时钟已停止")

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]):
        """订阅交易时段信号（所有市场）"""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable):
        """取消订阅"""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    @property
    def cn_phase(self) -> str:
        """获取 A股当前时段"""
        return self._get_cn_phase_at(datetime.now())

    @property
    def us_phase(self) -> str:
        """获取美股当前时段"""
        return self._get_us_phase_at(datetime.now())

    def get_cn_signal(self) -> Dict[str, Any]:
        """获取 A股当前时段信号（不发布）"""
        now = datetime.now()
        phase = self._get_cn_phase_at(now)
        next_info = self._get_cn_next_change_info(now, phase)

        return {
            'type': 'current_state',
            'market': 'CN',
            'phase': phase,
            'timestamp': now.timestamp(),
            'datetime': now.isoformat(),
            'next_phase': next_info['next_phase'],
            'next_change_time': next_info['next_change_time'].isoformat() if next_info['next_change_time'] else None,
            'seconds_until_next': next_info['seconds_until_next'],
        }

    def get_us_signal(self) -> Dict[str, Any]:
        """获取美股当前时段信号（不发布）"""
        now = datetime.now()
        phase = self._get_us_phase_at(now)
        next_info = self._get_us_next_change_info(now, phase)

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

    def get_global_status(self) -> Dict[str, Any]:
        """获取全球市场综合状态"""
        cn_signal = self.get_cn_signal()
        us_signal = self.get_us_signal()

        return {
            'cn': {
                'phase': cn_signal['phase'],
                'is_trading': cn_signal['phase'] == 'trading',
                'is_closed': cn_signal['phase'] in ('closed', 'lunch'),
            },
            'us': {
                'phase': us_signal['phase'],
                'is_trading': us_signal['phase'] == 'trading',
                'is_closed': us_signal['phase'] == 'closed',
            },
            'global': self._compute_global_status(cn_signal['phase'], us_signal['phase']),
        }

    def _compute_global_status(self, cn_phase: str, us_phase: str) -> str:
        """计算全球市场综合状态"""
        if cn_phase == 'trading' or us_phase == 'trading':
            return 'global_trading'
        elif cn_phase == 'pre_market' or us_phase == 'pre_market':
            return 'global_pre_market'
        elif cn_phase == 'post_market' or us_phase == 'post_market':
            return 'global_post_market'
        else:
            return 'global_closed'

    def _get_cn_phase_at(self, dt: datetime) -> str:
        """计算 A股指定时间的时段"""
        if dt.weekday() >= 5:
            return 'closed'

        t = dt.time()
        h, m = t.hour, t.minute
        total_minutes = h * 60 + m

        CALL_AUCTION_START = 9 * 60 + 15
        CALL_AUCTION_END = 9 * 60 + 25
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

    def _get_us_phase_at(self, dt: datetime) -> str:
        """计算美股指定时间的时段（基于美东时间）"""
        us_now = dt.astimezone(self._us_eastern)
        # Check if it's a weekend (Saturday=5, Sunday=6)
        if us_now.weekday() >= 5:
            return 'closed'
        current_time = us_now.time()

        if time(4, 0) <= current_time < time(9, 30):
            return 'pre_market'
        elif time(9, 30) <= current_time < time(16, 0):
            return 'trading'
        elif time(16, 0) <= current_time < time(20, 0):
            return 'post_market'
        else:
            return 'closed'

    def _get_cn_next_change_info(self, now: datetime, current_phase: str) -> Dict:
        """计算 A股当前时段的下一次变化信息"""
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
            'next_phase': self.CN_PHASE_TIMES.get(current_phase, {}).get('next_phase'),
            'next_change_time': next_change_time,
            'seconds_until_next': max(0, seconds_until_next) if seconds_until_next else None,
        }

    def _get_us_next_change_info(self, now: datetime, current_phase: str) -> Dict:
        """计算美股当前时段的下一次变化信息"""
        us_now = now.astimezone(self._us_eastern)
        today = us_now.date()

        next_change_time = None
        seconds_until_next = None

        if current_phase == 'closed':
            if us_now.time() < time(4, 0):
                next_day = us_now
            else:
                next_day = us_now + timedelta(days=1)
            while next_day.weekday() >= 5:
                next_day += timedelta(days=1)
            naive_dt = datetime.combine(next_day.date(), datetime.min.time().replace(hour=4, minute=0))
            next_change_time = self._us_eastern.localize(naive_dt)
            seconds_until_next = (next_change_time - us_now).total_seconds()

        elif current_phase == 'pre_market':
            naive_dt = datetime.combine(today, datetime.min.time().replace(hour=9, minute=30))
            next_change_time = self._us_eastern.localize(naive_dt)
            seconds_until_next = (next_change_time - us_now).total_seconds()

        elif current_phase == 'trading':
            naive_dt = datetime.combine(today, datetime.min.time().replace(hour=16, minute=0))
            next_change_time = self._us_eastern.localize(naive_dt)
            seconds_until_next = (next_change_time - us_now).total_seconds()

        elif current_phase == 'post_market':
            naive_dt = datetime.combine(today, datetime.min.time().replace(hour=20, minute=0))
            next_change_time = self._us_eastern.localize(naive_dt)
            seconds_until_next = (next_change_time - us_now).total_seconds()

        return {
            'next_phase': self.US_PHASE_TIMES.get(current_phase, {}).get('next_phase'),
            'next_change_time': next_change_time,
            'seconds_until_next': max(0, seconds_until_next) if seconds_until_next else None,
        }

    def _cn_run_loop(self):
        """A股时钟主循环"""
        log.info("[TradingClock] A股时钟线程开始")

        while self._running and not self._stop_event.is_set():
            try:
                now = datetime.now()
                new_phase = self._get_cn_phase_at(now)

                if new_phase != self._cn_current_phase:
                    self._emit_phase_change('CN', new_phase, now)

                seconds_until_next = self._calculate_cn_sleep_time(now, new_phase)
                sleep_time = max(1, min(seconds_until_next, 60))

                self._stop_event.wait(sleep_time)

            except Exception as e:
                log.error(f"[TradingClock] A股时钟循环异常: {e}")
                self._stop_event.wait(5)

        log.info("[TradingClock] A股时钟线程结束")

    def _us_run_loop(self):
        """美股时钟主循环"""
        log.info("[TradingClock] 美股时钟线程开始")

        while self._running and not self._stop_event.is_set():
            try:
                now = datetime.now()
                new_phase = self._get_us_phase_at(now)

                if new_phase != self._us_current_phase:
                    self._emit_phase_change('US', new_phase, now)

                info = self._get_us_next_change_info(now, new_phase)
                sleep_time = max(1, info['seconds_until_next'] or 60)

                self._stop_event.wait(sleep_time)

            except Exception as e:
                log.error(f"[TradingClock] 美股时钟循环异常: {e}")
                self._stop_event.wait(5)

        log.info("[TradingClock] 美股时钟线程结束")

    def _calculate_cn_sleep_time(self, now: datetime, phase: str) -> float:
        """计算 A股到下一次变化的秒数"""
        info = self._get_cn_next_change_info(now, phase)
        if info['seconds_until_next'] is not None:
            return max(1, info['seconds_until_next'])
        return 60

    def _emit_phase_change(self, market: str, new_phase: str, now: datetime):
        """发布时段变化信号"""
        if market == 'CN':
            old_phase = self._cn_current_phase
            self._cn_current_phase = new_phase
            signal = self.get_cn_signal()
        else:
            old_phase = self._us_current_phase
            self._us_current_phase = new_phase
            signal = self.get_us_signal()

        signal['type'] = 'phase_change'
        signal['previous_phase'] = old_phase
        signal['change_reason'] = self._get_change_reason(market, old_phase, new_phase)

        TRADING_CLOCK_STREAM.emit(signal)

        for callback in self._subscribers:
            try:
                callback(signal)
            except Exception as e:
                log.error(f"[TradingClock] 订阅回调异常: {e}")

        if market == 'CN' and new_phase == 'post_market':
            try:
                from deva.naja.state.snapshot import record_market_state_snapshot
                record_market_state_snapshot(force=True)
            except Exception as e:
                log.debug(f"[TradingClock] 记录市场状态快照失败: {e}")

        log.info(f"[TradingClock] {market} 时段变化: {old_phase} -> {new_phase}")

    def _emit_current_state(self, market: str, phase: str):
        """发布当前状态信号"""
        if market == 'CN':
            signal = self.get_cn_signal()
        else:
            signal = self.get_us_signal()

        signal['type'] = 'current_state'
        signal['previous_phase'] = None
        signal['change_reason'] = '系统启动'

        TRADING_CLOCK_STREAM.emit(signal)

        for callback in self._subscribers:
            try:
                callback(signal)
            except Exception as e:
                log.error(f"[TradingClock] 订阅回调异常: {e}")

        log.info(f"[TradingClock] {market} 发布当前状态: {phase}")

    def _get_change_reason(self, market: str, old: str, new: str) -> str:
        """获取变化原因描述"""
        if market == 'CN':
            reasons = {
                ('closed', 'call_auction'): '集合竞价开始',
                ('call_auction', 'pre_market'): '集合竞价结束，等待交易',
                ('pre_market', 'trading'): '开始交易',
                ('trading', 'lunch'): '午间休市',
                ('lunch', 'trading'): '午间休市结束，下午交易开始',
                ('trading', 'post_market'): '收盘',
                ('post_market', 'closed'): '收盘后处理结束',
            }
        else:
            reasons = {
                ('closed', 'pre_market'): '盘前交易开始',
                ('pre_market', 'trading'): '美股开始交易',
                ('trading', 'post_market'): '盘后交易开始',
                ('post_market', 'closed'): '盘后交易结束',
            }
        return reasons.get((old, new), f'{old} -> {new}')


def trading_clock_signal(phase: str, market: str = 'CN') -> bool:
    """
    判断当前是否处于指定时段

    Args:
        phase: 时段名称 ('trading', 'pre_market', etc.)
        market: 市场 'CN' 或 'US'

    Returns:
        是否处于该时段
    """
    from deva.naja.application import get_app_container
    container = get_app_container()
    if container and container.trading_clock:
        tc = container.trading_clock
        if market == 'CN':
            return tc.cn_phase == phase
        else:
            return tc.us_phase == phase
    return False


def is_trading_time(market: str = 'CN') -> bool:
    """判断当前是否在交易时间内"""
    return trading_clock_signal('trading', market)


def is_market_closed(market: str = 'CN') -> bool:
    """判断当前是否收盘/休市"""
    return trading_clock_signal('closed', market)


def is_us_trading_time() -> bool:
    """判断美股当前是否在交易时间内"""
    return is_trading_time('US')


def is_us_market_closed() -> bool:
    """判断美股当前是否收盘/休市"""
    return is_market_closed('US')


def get_global_trading_status() -> Dict[str, Any]:
    """获取全球市场综合状态"""
    from deva.naja.application import get_app_container
    container = get_app_container()
    if container and container.trading_clock:
        return container.trading_clock.get_global_status()
    return {}



USTRADING_CLOCK_STREAM = TRADING_CLOCK_STREAM


def us_trading_clock_signal(phase: str) -> bool:
    """判断美股当前是否处于指定时段（兼容性别名）"""
    return trading_clock_signal(phase, 'US')


__all__ = [
    'TradingClock',
    'TRADING_CLOCK_STREAM',
    'USTRADING_CLOCK_STREAM',
    'trading_clock_signal',
    'is_trading_time',
    'is_market_closed',
    'is_us_trading_time',
    'is_us_market_closed',
    'get_global_trading_status',
    'us_trading_clock_signal',
]
