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
from deva.naja.infra.registry.singleton_registry import SR

from deva.naja.radar.trading_clock import TRADING_CLOCK_STREAM

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
        """处理交易时钟事件（统一时钟同时处理 A股 和 美股）"""
        if not self._running:
            return

        phase = event.get('phase')
        market = event.get('market', 'CN')
        event_type = event.get('type')

        if market == 'CN':
            log.info(f"[DailyReviewScheduler] 收到A股交易时钟信号: phase={phase}, type={event_type}")
            if phase == 'post_market' or (event_type == 'current_state' and phase == 'post_market'):
                self._schedule_replay(market='a_share', phase='post_market', delay_seconds=REPLAY_DELAY_AFTER_OPEN)
        elif market == 'US':
            log.info(f"[DailyReviewScheduler] 收到美股交易时钟信号: phase={phase}, type={event_type}, market={market}")
            if phase == 'post_market' or (event_type == 'current_state' and phase == 'post_market'):
                self._schedule_replay(market='us_share', phase='post_market', delay_seconds=REPLAY_DELAY_AFTER_OPEN)

    def _calculate_next_target(self, now: datetime):
        """
        计算下一个复盘目标时间

        Returns:
            tuple: (target_time, market) 或 (None, None) 表示今天无需复盘
        """
        targets = []

        # A 股复盘目标
        if not self._check_already_replayed_today(market='a_share'):
            if now.weekday() < 5:  # 工作日
                target_a = now.replace(hour=15, minute=30, second=0, microsecond=0)
                if target_a <= now:
                    # 已过 15:30，立即触发
                    target_a = now + timedelta(seconds=1)
                targets.append((target_a, 'a_share'))

        # 美股复盘目标
        if not self._check_already_replayed_today(market='us_share'):
            # 夏令时 04:00，冬令时 05:00，保守取 04:00 确保不遗漏
            target_us = now.replace(hour=4, minute=0, second=0, microsecond=0)
            if target_us <= now:
                # 已过 04:00，取明天
                target_us += timedelta(days=1)
            targets.append((target_us, 'us_share'))

        if not targets:
            return None, None

        # 返回最近的目标
        targets.sort(key=lambda x: x[0])
        return targets[0]

    def _run_loop(self):
        """主循环 - 精准等待并触发复盘"""
        log.info("[DailyReviewScheduler] 调度线程启动")

        while self._running and not self._stop_event.is_set():
            try:
                now = datetime.now()
                target_time, market = self._calculate_next_target(now)

                if target_time is None:
                    # 今天两个市场都已复盘，等待到明天凌晨
                    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    wait_seconds = (tomorrow - now).total_seconds()
                    log.info(f"[DailyReviewScheduler] 今天复盘已完成，等待到 {tomorrow.strftime('%Y-%m-%d %H:%M')}")
                    self._stop_event.wait(min(wait_seconds, 3600))  # 最多等待 1 小时
                    continue

                wait_seconds = (target_time - now).total_seconds()
                log.info(f"[DailyReviewScheduler] 精准等待: 目标时间={target_time.strftime('%H:%M')}, "
                         f"市场={market}, 等待={wait_seconds:.0f}秒")
                self._stop_event.wait(wait_seconds)

                # 检查是否被中断（stop 或时钟事件触发）
                if not self._running:
                    break

                # 到达目标时间，触发复盘
                log.info(f"[DailyReviewScheduler] 到达目标时间，触发 {market} 复盘")
                self._trigger_replay(market=market, phase='post_market')

            except Exception as e:
                log.error(f"[DailyReviewScheduler] 调度线程异常: {e}")
                self._stop_event.wait(30)

        log.info("[DailyReviewScheduler] 调度线程结束")

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

    def _schedule_replay(self, market: str = 'a_share', phase: str = 'post_market', delay_seconds: int = 30):
        """安排延迟复盘任务（保留用于交易时钟事件触发）"""
        def delayed_replay():
            time.sleep(delay_seconds)
            self._trigger_replay(market=market, phase=phase)

        thread = threading.Thread(target=delayed_replay, daemon=True, name=f'delayed-{market}-replay')
        thread.start()
        log.debug(f"[DailyReviewScheduler] 已安排{market} {delay_seconds}秒后执行{phase}复盘")

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
    from deva.naja.register import SR
    return DailyReviewScheduler()