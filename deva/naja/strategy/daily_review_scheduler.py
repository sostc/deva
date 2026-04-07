"""
DailyReviewScheduler - 市场复盘调度器

功能：
1. 订阅 A股和美股交易时钟，在盘后(post_market)阶段自动触发复盘
2. 系统启动时检查今天是否已复盘，未复盘则延迟触发
3. 复盘结果推送到 iMessage

每天两次复盘：
- A股盘后：15:30 后（北京时间）
- 美股盘后：04:00/05:00 后（北京时间，夏令时/冬令时）

使用方式：
    scheduler = DailyReviewScheduler()
    scheduler.start()
"""

import logging
import threading
import time
from datetime import datetime, timedelta, time as dtime
from typing import Optional

from deva import NB

from deva.naja.radar.trading_clock import get_trading_clock, TRADING_CLOCK_STREAM
from deva.naja.radar.trading_clock import get_us_trading_clock, USTRADING_CLOCK_STREAM

log = logging.getLogger(__name__)

REPLAY_STATE_TABLE = "naja_daily_review_state"
REPLAY_DELAY_AFTER_OPEN = 30


class DailyReviewScheduler:
    """
    市场复盘调度器

    工作流程：
    1. 系统启动时检查今天是否已复盘
    2. 订阅 A股和美股交易时钟的 post_market 信号
    3. 盘后阶段触发复盘任务（区分市场）
    4. 复盘结果推送到 iMessage

    每天两次复盘：
    - A股盘后：15:30 后（北京时间）
    - 美股盘后：04:00/05:00 后（北京时间）

    市场标识：'a_share' 或 'us_share'
    """

    _instance: Optional['DailyReviewScheduler'] = None
    _lock = threading.Lock()

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

        self._latest_sent_data = None
        self._downstream_callback = None

        self._initialized = True
        log.info("[DailyReviewScheduler] 调度器初始化完成")

    def set_downstream_callback(self, callback):
        """设置下游回调（支持 Lab 模式）"""
        self._downstream_callback = callback
        log.info("[DailyReviewScheduler] 已注册下游回调")

    def start(self):
        """启动调度器"""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()

        self._thread = threading.Thread(target=self._run_loop, daemon=True, name='market-replay-scheduler')
        self._thread.start()

        TRADING_CLOCK_STREAM.sink(self._on_trading_clock_event)
        USTRADING_CLOCK_STREAM.sink(self._on_us_trading_clock_event)

        log.info("[DailyReviewScheduler] 调度器已启动，订阅 A股和美股交易时钟")

    def stop(self):
        """停止调度器"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=5)

        log.info("[DailyReviewScheduler] 调度器已停止")

    def _on_trading_clock_event(self, event: dict):
        """处理 A股交易时钟事件"""
        if not self._running:
            return

        phase = event.get('phase')
        market = event.get('market', 'CN')
        event_type = event.get('type')

        log.info(f"[DailyReviewScheduler] 收到A股交易时钟信号: phase={phase}, type={event_type}")

        if phase == 'post_market' or (event_type == 'current_state' and phase == 'post_market'):
            self._schedule_replay(market='a_share', phase='post_market', delay_seconds=REPLAY_DELAY_AFTER_OPEN)

    def _on_us_trading_clock_event(self, event: dict):
        """处理美股交易时钟事件"""
        if not self._running:
            return

        phase = event.get('phase')
        market = event.get('market', 'US')
        event_type = event.get('type')

        log.info(f"[DailyReviewScheduler] 收到美股交易时钟信号: phase={phase}, type={event_type}, market={market}")

        if phase == 'post_market' or (event_type == 'current_state' and phase == 'post_market'):
            self._schedule_replay(market='us_share', phase='post_market', delay_seconds=REPLAY_DELAY_AFTER_OPEN)

    def _run_loop(self):
        """主循环 - 检查是否需要触发 A股和美股复盘"""
        log.info("[DailyReviewScheduler] 检查线程启动")

        while self._running and not self._stop_event.is_set():
            try:
                now = datetime.now()

                # 检查 A股复盘
                self._check_and_trigger_replay(market='a_share', now=now)

                # 检查美股复盘
                self._check_and_trigger_replay(market='us_share', now=now)

                # 计算下次检查时间
                next_check = self._get_next_check_time()
                sleep_time = min(60, (next_check - now).total_seconds())

                log.info(f"[DailyReviewScheduler] 下次检查: {next_check}, 等待{sleep_time:.0f}秒")
                self._stop_event.wait(max(10, sleep_time))

            except Exception as e:
                log.error(f"[DailyReviewScheduler] 检查线程异常: {e}")
                self._stop_event.wait(30)

        log.info("[DailyReviewScheduler] 检查线程结束")

    def _check_and_trigger_replay(self, market: str, now: datetime):
        """检查并触发指定市场的复盘"""
        if self._check_already_replayed_today(market=market):
            return

        if market == 'a_share':
            tc = get_trading_clock()
            current_phase = tc.current_phase

            # A股：周末不休市检查，但按交易时段判断
            if now.weekday() >= 5:
                return  # 周末不触发

            if current_phase == 'post_market':
                log.info(f"[DailyReviewScheduler] A股今天尚未复盘，立即触发")
                self._trigger_replay(market=market, phase='post_market')
            elif current_phase == 'closed':
                if now.time() >= dtime(15, 30):
                    log.info(f"[DailyReviewScheduler] A股收盘后尚未复盘，立即触发")
                    self._trigger_replay(market=market, phase='post_market')

        elif market == 'us_share':
            from deva.naja.radar.trading_clock import get_us_trading_clock
            us_tc = get_us_trading_clock()
            current_phase = us_tc.current_phase

            # 美股：每天 04:00/05:00 后检查
            # 北京时间 = 美东时间 + 12/13小时
            us_hour = now.hour
            is_us_post_market_time = us_hour >= 4 or (us_hour >= 0 and us_hour < 1)

            if current_phase == 'post_market' or (current_phase == 'closed' and is_us_post_market_time):
                log.info(f"[DailyReviewScheduler] 美股今天尚未复盘，立即触发")
                self._trigger_replay(market=market, phase='post_market')

    def _check_already_replayed_today(self, market: str = 'a_share', phase: str = 'post_market') -> bool:
        """
        检查今天指定市场的复盘是否已完成

        Args:
            market: 'a_share' 或 'us_share'
            phase: 'post_market' 或 'pre_market'
        """
        try:
            nb = NB(REPLAY_STATE_TABLE)
            today = datetime.now().strftime('%Y-%m-%d')

            key = f'last_{market}_{phase}_review_date'
            last_replay = nb.get(key)

            if last_replay == today:
                log.info(f"[DailyReviewScheduler] {market} 今天({today}) {phase}阶段已完成复盘")
                return True
            return False
        except Exception:
            return False

    def _mark_replayed_today(self, market: str = 'a_share', phase: str = 'post_market'):
        """
        标记指定市场今天已复盘

        Args:
            market: 'a_share' 或 'us_share'
            phase: 'post_market' 或 'pre_market'
        """
        try:
            nb = NB(REPLAY_STATE_TABLE)
            today = datetime.now().strftime('%Y-%m-%d')

            key = f'last_{market}_{phase}_review_date'
            nb[key] = today
            nb[f'{market}_last_replay_timestamp'] = time.time()
            log.info(f"[DailyReviewScheduler] 已标记{market} {phase}复盘: {today}")
        except Exception as e:
            log.error(f"[DailyReviewScheduler] 标记复盘失败: {e}")

    def _get_next_check_time(self) -> datetime:
        """获取下次检查时间"""
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')

        if now.hour < 15 or (now.hour == 15 and now.minute < 30):
            next_check = datetime.strptime(f"{today_str} 15:30", '%Y-%m-%d %H:%M')
        else:
            next_day = now + timedelta(days=1)
            while next_day.weekday() >= 5:
                next_day += timedelta(days=1)
            next_check = datetime.strptime(f"{next_day.strftime('%Y-%m-%d')} 15:30", '%Y-%m-%d %H:%M')

        return next_check

    def _schedule_replay(self, market: str = 'a_share', phase: str = 'post_market', delay_seconds: int = 30):
        """安排延迟复盘任务"""
        def delayed_replay():
            time.sleep(delay_seconds)
            self._trigger_replay(market=market, phase=phase)

        thread = threading.Thread(target=delayed_replay, daemon=True, name=f'delayed-{market}-replay')
        thread.start()
        log.info(f"[DailyReviewScheduler] 已安排{market} {delay_seconds}秒后执行{phase}复盘")

    def _trigger_replay(self, market: str = 'a_share', phase: str = 'post_market'):
        """触发复盘任务"""
        if self._check_already_replayed_today(market=market, phase=phase):
            log.info(f"[DailyReviewScheduler] 复盘任务跳过：{market} 今天{phase}阶段已复盘")
            return

        try:
            log.info(f"[DailyReviewScheduler] 开始执行{market} {phase}复盘任务")

            from deva.naja.strategy.daily_review import run_review_and_push
            report, pushed_ok = run_review_and_push(market=market)

            if not pushed_ok:
                log.warning(f"[DailyReviewScheduler] {market} 复盘生成完成但推送失败，未标记为已复盘")
                return

            self._mark_replayed_today(market=market, phase=phase)

            log.info(f"[DailyReviewScheduler] {market} {phase}复盘任务完成")

        except Exception as e:
            log.error(f"[DailyReviewScheduler] 复盘任务失败: {e}")

    def trigger_manual_replay(self, market: str = 'a_share', phase: str = 'post_market') -> bool:
        """手动触发复盘（用于认知页面按钮）"""
        try:
            log.info(f"[DailyReviewScheduler] 手动触发{market} {phase}复盘")
            self._trigger_replay(market=market, phase=phase)
            return True
        except Exception as e:
            log.error(f"[DailyReviewScheduler] 手动复盘失败: {e}")
            return False


def get_daily_review_scheduler() -> DailyReviewScheduler:
    """获取复盘调度器单例"""
    return DailyReviewScheduler()
