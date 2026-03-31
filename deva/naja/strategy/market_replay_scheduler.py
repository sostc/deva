"""
MarketReplayScheduler - 市场复盘调度器

功能：
1. 订阅交易时钟，在盘后(post_market)阶段自动触发复盘
2. 系统启动时检查今天是否已复盘，未复盘则延迟触发
3. 复盘结果推送到DTalk

使用方式：
    scheduler = MarketReplayScheduler()
    scheduler.start()
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from deva import NB

from deva.naja.radar.trading_clock import get_trading_clock, TRADING_CLOCK_STREAM

log = logging.getLogger(__name__)

REPLAY_STATE_TABLE = "naja_market_replay_state"
REPLAY_DELAY_AFTER_OPEN = 30


class MarketReplayScheduler:
    """
    市场复盘调度器

    工作流程：
    1. 系统启动时检查今天是否已复盘
    2. 订阅交易时钟的 post_market 信号
    3. 盘后阶段触发复盘任务
    4. 复盘结果推送到DTalk
    """

    _instance: Optional['MarketReplayScheduler'] = None
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

        self._initialized = True
        log.info("[MarketReplayScheduler] 调度器初始化完成")

    def start(self):
        """启动调度器"""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()

        self._thread = threading.Thread(target=self._run_loop, daemon=True, name='market-replay-scheduler')
        self._thread.start()

        TRADING_CLOCK_STREAM.sink(self._on_trading_clock_event)

        log.info("[MarketReplayScheduler] 调度器已启动")

    def stop(self):
        """停止调度器"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=5)

        log.info("[MarketReplayScheduler] 调度器已停止")

    def _on_trading_clock_event(self, event: dict):
        """处理交易时钟事件"""
        if not self._running:
            return

        phase = event.get('phase')
        event_type = event.get('type')

        log.info(f"[MarketReplayScheduler] 收到交易时钟信号: phase={phase}, type={event_type}")

        if phase == 'post_market' or (event_type == 'current_state' and phase == 'post_market'):
            self._schedule_replay(delay_seconds=REPLAY_DELAY_AFTER_OPEN)

    def _run_loop(self):
        """主循环 - 检查是否需要触发复盘"""
        log.info("[MarketReplayScheduler] 检查线程启动")

        while self._running and not self._stop_event.is_set():
            try:
                if not self._check_already_replayed_today():
                    tc = get_trading_clock()
                    current_phase = tc.current_phase

                    if current_phase == 'post_market' or current_phase == 'closed':
                        log.info("[MarketReplayScheduler] 今天尚未复盘，立即触发")
                        self._trigger_replay()
                    else:
                        next_check = self._get_next_check_time()
                        sleep_time = min(60, (next_check - datetime.now()).total_seconds())
                        log.info(f"[MarketReplayScheduler] 下次检查: {next_check}, 等待{sleep_time:.0f}秒")

                        self._stop_event.wait(max(10, sleep_time))
                else:
                    log.info("[MarketReplayScheduler] 今天已完成复盘，等待次日")
                    next_check = self._get_next_check_time()
                    sleep_time = (next_check - datetime.now()).total_seconds()
                    self._stop_event.wait(min(sleep_time, 3600))

            except Exception as e:
                log.error(f"[MarketReplayScheduler] 检查线程异常: {e}")
                self._stop_event.wait(30)

        log.info("[MarketReplayScheduler] 检查线程结束")

    def _check_already_replayed_today(self) -> bool:
        """检查今天是否已复盘"""
        try:
            nb = NB(REPLAY_STATE_TABLE)
            last_replay = nb.get('last_replay_date')
            today = datetime.now().strftime('%Y-%m-%d')

            if last_replay == today:
                log.info(f"[MarketReplayScheduler] 今天({today})已完成复盘")
                return True
            return False
        except Exception:
            return False

    def _mark_replayed_today(self):
        """标记今天已复盘"""
        try:
            nb = NB(REPLAY_STATE_TABLE)
            nb['last_replay_date'] = datetime.now().strftime('%Y-%m-%d')
            nb['last_replay_timestamp'] = time.time()
        except Exception as e:
            log.error(f"[MarketReplayScheduler] 标记复盘失败: {e}")

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

    def _schedule_replay(self, delay_seconds: int = 30):
        """安排延迟复盘任务"""
        def delayed_replay():
            time.sleep(delay_seconds)
            self._trigger_replay()

        thread = threading.Thread(target=delayed_replay, daemon=True, name='delayed-replay')
        thread.start()
        log.info(f"[MarketReplayScheduler] 已安排{delay_seconds}秒后执行复盘")

    def _trigger_replay(self):
        """触发复盘任务"""
        if self._check_already_replayed_today():
            log.info("[MarketReplayScheduler] 复盘任务跳过：今天已复盘")
            return

        try:
            log.info("[MarketReplayScheduler] 开始执行复盘任务")

            from deva.naja.strategy.market_replay_analyzer import run_replay_and_push
            report = run_replay_and_push()

            self._mark_replayed_today()

            log.info(f"[MarketReplayScheduler] 复盘任务完成")

        except Exception as e:
            log.error(f"[MarketReplayScheduler] 复盘任务失败: {e}")

    def trigger_manual_replay(self) -> bool:
        """手动触发复盘（用于认知页面按钮）"""
        try:
            log.info("[MarketReplayScheduler] 手动触发复盘")
            self._trigger_replay()
            return True
        except Exception as e:
            log.error(f"[MarketReplayScheduler] 手动复盘失败: {e}")
            return False


def get_replay_scheduler() -> MarketReplayScheduler:
    """获取复盘调度器单例"""
    return MarketReplayScheduler()