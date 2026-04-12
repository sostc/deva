"""BanditAutoRunner - Bandit系统/自动运行/执行

别名/关键词: 自动运行、执行、auto runner、bandit runner

Bandit 自动运行器

提供事件驱动的自动任务功能：
1. 订阅交易时钟事件，而非定时轮询
2. 根据交易时段变化执行相应动作
3. 实验模式下可使用更快的响应间隔

与 LLM Controller 的 auto_adjust 机制一致。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional
from deva.naja.register import SR

_loop_audit_log_stage = None

def _get_audit():
    global _loop_audit_log_stage
    if _loop_audit_log_stage is None:
        try:
            from ..infra.observability.loop_audit import LoopAudit
            _loop_audit_log_stage = lambda **kw: LoopAudit(**kw)
        except ImportError:
            _loop_audit_log_stage = lambda **kw: _DummyAudit()
    return _loop_audit_log_stage

class _DummyAudit:
    def __init__(self, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def record_data_out(self, *args, **kwargs): pass

from deva import NB

from .optimizer import get_bandit_optimizer
from ..infra.log.log_stream import get_log_stream, log_strategy
from ..radar.trading_clock import TRADING_CLOCK_STREAM

log = logging.getLogger(__name__)

BANDIT_CONFIG_TABLE = "naja_bandit_config"


class BanditAutoRunner:
    """Bandit 自动运行器

    事件驱动架构：
    1. 订阅 TRADING_CLOCK_STREAM 获取交易时段变化事件
    2. 根据 phase 变化执行相应动作（而非定时轮询）
    3. 使用 Timer 替代固定间隔轮询

    事件处理：
    - pre_market: 盘前准备，可提前选择策略
    - trading: 交易开始，执行选择 + 定时调节
    - lunch: 午休开始，取消定时器
    - post_market: 收盘，执行日终调节
    - closed: 休市，停止自动运行
    """

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._select_interval = 60
        self._adjust_interval = 300
        self._experiment_adjust_interval = 60
        self._enabled = True
        self._force_mode = False

        self._last_select_ts = 0.0
        self._last_adjust_ts = 0.0

        self._current_phase: str = 'closed'
        self._previous_phase: str = 'closed'

        self._select_timer: Optional[threading.Timer] = None
        self._adjust_timer: Optional[threading.Timer] = None
        self._adjust_timer_lock = threading.Lock()

        self._load_config()

    def _load_config(self):
        """从数据库加载配置"""
        try:
            db = NB(BANDIT_CONFIG_TABLE)
            config = db.get("auto_config")
            if config:
                self._select_interval = config.get("select_interval", 60)
                self._adjust_interval = config.get("adjust_interval", 300)
                self._experiment_adjust_interval = config.get("experiment_adjust_interval", 60)
                self._enabled = config.get("enabled", True)
                self._force_mode = config.get("force_mode", False)
                was_running = config.get("was_running", False)
                if was_running and self._enabled:
                    self._running = True
                    log.info("检测到 BanditAutoRunner 上次运行中，将自动恢复")
        except Exception:
            pass

    def _save_config(self):
        """保存配置到数据库"""
        try:
            db = NB(BANDIT_CONFIG_TABLE)
            db["auto_config"] = {
                "select_interval": self._select_interval,
                "adjust_interval": self._adjust_interval,
                "experiment_adjust_interval": self._experiment_adjust_interval,
                "enabled": self._enabled,
                "force_mode": self._force_mode,
                "was_running": self._running
            }
        except Exception:
            pass

    def start(self):
        """启动自动运行"""
        if self._running and self._thread and self._thread.is_alive():
            log.warning("BanditAutoRunner 已在运行中")
            return

        self._running = True
        self._stop_event.clear()

        TRADING_CLOCK_STREAM.sink(self._on_trading_clock_event)
        log.info("BanditAutoRunner 已订阅交易时钟事件")

        self._thread = threading.Thread(target=self._run_loop, daemon=True, name='bandit-auto-runner')
        self._thread.start()

        self._save_config()

        log.info(f"BanditAutoRunner 已启动 (选择间隔: {self._select_interval}s, 调节间隔: {self._adjust_interval}s)")

    def stop(self):
        """停止自动运行"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        self._cancel_timers()

        if self._thread:
            self._thread.join(timeout=5)

        self._save_config()

        log.info("BanditAutoRunner 已停止")

    def _run_loop(self):
        """主循环（简化版，只检查运行状态）"""
        while self._running and not self._stop_event.is_set():
            self._stop_event.wait(1)

    def _is_experiment_mode(self) -> bool:
        """检查是否处于实验模式"""
        try:
            from deva.naja.strategy import get_strategy_manager
            mgr = get_strategy_manager()
            experiment_info = mgr.get_experiment_info()
            return experiment_info.get("active", False)
        except Exception:
            return False

    def _is_allowed_to_run(self) -> bool:
        """检查是否允许运行"""
        if self._force_mode:
            return True
        if self._is_experiment_mode():
            return True
        if self._current_phase in ('trading', 'pre_market', 'call_auction'):
            return True
        import os
        if os.environ.get('NAJA_LAB_MODE'):
            return True
        return False

    def _on_trading_clock_event(self, signal: Dict[str, Any]):
        """处理交易时钟事件（事件驱动核心）"""
        if not self._running:
            return

        signal_type = signal.get('type')
        if signal_type != 'phase_change':
            return

        phase = signal.get('phase', 'closed')
        previous_phase = signal.get('previous_phase', 'closed')

        if phase == self._current_phase:
            return

        self._previous_phase = self._current_phase
        self._current_phase = phase

        log.info(f"[Bandit] 交易时钟事件: {self._previous_phase} -> {phase}")

        if self._is_experiment_mode():
            self._handle_experiment_phase(phase, previous_phase)
        else:
            self._handle_normal_phase(phase, previous_phase)

    def _handle_normal_phase(self, phase: str, previous_phase: str):
        """实盘模式：处理时段变化"""
        if phase == 'pre_market':
            self._on_pre_market(previous_phase)
        elif phase == 'trading':
            self._on_trading_start(previous_phase)
        elif phase == 'lunch':
            self._on_lunch_start(previous_phase)
        elif phase == 'post_market':
            self._on_post_market(previous_phase)
        elif phase == 'closed':
            self._on_market_closed(previous_phase)

    def _handle_experiment_phase(self, phase: str, previous_phase: str):
        """实验模式：处理时段变化（更快的响应）"""
        if phase == 'trading':
            self._on_trading_start(previous_phase, experiment_mode=True)
        elif phase == 'closed':
            self._cancel_timers()

    def _on_pre_market(self, previous_phase: str):
        """盘前准备"""
        if not self._is_allowed_to_run():
            return

        if self._force_mode or self._is_experiment_mode():
            log.info("[Bandit] 盘前准备，提前安排选择")
            self._schedule_select(delay=300)

    def _on_trading_start(self, previous_phase: str, experiment_mode: bool = False):
        """交易开始"""
        if not self._is_allowed_to_run():
            log.info("[Bandit] 非交易时段，不执行自动选择")
            return

        log.info(f"[Bandit] 交易时段开始，执行自动选择")

        self._do_select()

        if self._enabled:
            if experiment_mode or self._is_experiment_mode():
                interval = self._experiment_adjust_interval
            else:
                interval = self._adjust_interval

            self._schedule_adjust(interval=interval)

    def _on_lunch_start(self, previous_phase: str):
        """午休开始"""
        log.info("[Bandit] 午休开始，取消定时器")
        self._cancel_timers()

        if self._enabled and self._is_experiment_mode():
            self._do_adjust()

    def _on_post_market(self, previous_phase: str):
        """收盘"""
        log.info("[Bandit] 收盘，执行日终调节")
        self._cancel_timers()

        if self._enabled:
            self._do_adjust()

    def _on_market_closed(self, previous_phase: str):
        """休市"""
        log.info("[Bandit] 市场休市，停止自动运行")
        self._cancel_timers()

    def _schedule_select(self, delay: float):
        """延迟执行选择"""
        if self._select_timer:
            self._select_timer.cancel()

        log.info(f"[Bandit] 安排选择任务，延迟 {delay}s")

        self._select_timer = threading.Timer(delay, self._do_select)
        self._select_timer.start()

    def _schedule_adjust(self, interval: float):
        """设置定时调节（循环）"""
        def _repeat_adjust():
            if not self._running:
                return
            if self._is_allowed_to_run() and self._enabled:
                self._do_adjust()
                if self._running and self._enabled:
                    next_interval = self._experiment_adjust_interval if self._is_experiment_mode() else self._adjust_interval
                    with self._adjust_timer_lock:
                        self._adjust_timer = threading.Timer(next_interval, _repeat_adjust)
                        self._adjust_timer.start()
            else:
                log.debug("[Bandit] 调节任务因权限不足跳过")

        interval_to_use = self._experiment_adjust_interval if self._is_experiment_mode() else interval

        log.info(f"[Bandit] 安排调节任务，间隔 {interval_to_use}s")

        with self._adjust_timer_lock:
            if self._adjust_timer:
                self._adjust_timer.cancel()
            self._adjust_timer = threading.Timer(interval_to_use, _repeat_adjust)
            self._adjust_timer.start()

    def _cancel_timers(self):
        """取消所有定时器"""
        with self._adjust_timer_lock:
            if self._select_timer:
                self._select_timer.cancel()
                self._select_timer = None
            if self._adjust_timer:
                self._adjust_timer.cancel()
                self._adjust_timer = None

    def _do_select(self):
        """执行策略选择"""
        if not self._running:
            return

        if not self._is_allowed_to_run():
            log.debug("[Bandit] 非运行时段，跳过选择")
            return

        with _get_audit()(loop_type="bandit", stage="select_start", metadata={"phase": self._current_phase}) as audit:
            from ..strategy import get_strategy_manager

            mgr = get_strategy_manager()
            entries = mgr.list_all()

            if not entries:
                audit.record_data_out({"status": "skipped", "reason": "no_strategies"})
                return

            active_entries = [e for e in entries if e.is_processing_data()]
            if not active_entries:
                log.debug("[Bandit] 没有策略在处理数据，跳过选择")
                audit.record_data_out({"status": "skipped", "reason": "no_active_processing"})
                return

            available = [e.id for e in entries]

            optimizer = get_bandit_optimizer()
            result = optimizer.select_strategy(available)

            if result.get("success"):
                selected = result.get("selected")
                log.info(f"Bandit 自动选择策略: {selected}")
                log_strategy("INFO", "bandit", "auto_select", f"自动选择策略: {selected}")
                audit.record_data_out({"status": "completed", "selected": selected, "available": available})
            else:
                error = result.get('error')
                log_strategy("WARN", "bandit", "auto_select", f"选择失败: {error}")
                audit.record_data_out({"status": "failed", "error": error})

    def _do_adjust(self):
        """执行策略调节"""
        if not self._running:
            return

        if not self._is_allowed_to_run():
            log.debug("[Bandit] 非运行时段，跳过调节")
            return

        with _get_audit()(loop_type="bandit", stage="adjust", metadata={"phase": self._current_phase}) as audit:
            optimizer = get_bandit_optimizer()
            result = optimizer.review_and_adjust()

            if result.get("success") and result.get("actions"):
                log.info(f"Bandit 自动调节: {result.get('summary')}")
                log_strategy("INFO", "bandit", "auto_adjust",
                            f"调节成功: {result.get('summary')}, 动作数: {len(result.get('actions', []))}")
                audit.record_data_out({
                    "status": "completed",
                    "actions": len(result.get('actions', [])),
                    "summary": result.get('summary')
                })
            elif result.get("success"):
                log_strategy("INFO", "bandit", "auto_adjust", "无需调节")
                audit.record_data_out({"status": "completed", "actions": 0})
            else:
                error = result.get('error')
                log_strategy("WARN", "bandit", "auto_adjust", f"调节失败: {error}")
                audit.record_data_out({"status": "failed", "error": error})

    def run_once(self, dry_run: bool = False) -> dict:
        """手动运行一次

        Args:
            dry_run: 是否仅模拟

        Returns:
            dict: 运行结果
        """
        results = {
            "select": None,
            "adjust": None
        }

        from ..strategy import get_strategy_manager

        mgr = get_strategy_manager()
        entries = mgr.list_all()

        if entries:
            optimizer = get_bandit_optimizer()

            available = [e.id for e in entries]
            results["select"] = optimizer.select_strategy(available, dry_run=dry_run)

            if not dry_run:
                results["adjust"] = optimizer.review_and_adjust(dry_run=dry_run)

        return results

    def set_select_interval(self, seconds: int):
        """设置选择间隔"""
        self._select_interval = max(10, seconds)
        self._save_config()

    def set_adjust_interval(self, seconds: int):
        """设置调节间隔"""
        self._adjust_interval = max(30, seconds)
        self._save_config()

    def set_experiment_adjust_interval(self, seconds: int):
        """设置实验模式调节间隔"""
        self._experiment_adjust_interval = max(10, seconds)
        self._save_config()

    def enable(self):
        """启用自动运行"""
        self._enabled = True
        self._save_config()

    def disable(self):
        """禁用自动运行"""
        self._enabled = False
        self._cancel_timers()
        self._save_config()

    def get_status(self) -> dict:
        """获取状态"""
        return {
            "running": self._running,
            "enabled": self._enabled,
            "current_phase": self._current_phase,
            "previous_phase": self._previous_phase,
            "is_experiment": self._is_experiment_mode(),
            "select_interval": self._select_interval,
            "adjust_interval": self._adjust_interval,
            "experiment_adjust_interval": self._experiment_adjust_interval,
            "last_select_ts": self._last_select_ts,
            "last_adjust_ts": self._last_adjust_ts
        }


def ensure_bandit_auto_runner(
    select_interval: int = 60,
    adjust_interval: int = 300,
    experiment_adjust_interval: int = 60,
    auto_start: bool = True,
) -> BanditAutoRunner:
    """确保 Bandit 自动运行器已配置

    与 LLM Controller.ensure_llm_auto_adjust_task 对应

    Args:
        select_interval: 策略选择间隔 (秒)
        adjust_interval: 策略调节间隔 (秒)
        experiment_adjust_interval: 实验模式调节间隔 (秒)
        auto_start: 是否自动启动

    Returns:
        BanditAutoRunner: 运行器实例
    """
    runner = SR('bandit_runner')

    runner.set_select_interval(select_interval)
    runner.set_adjust_interval(adjust_interval)
    runner.set_experiment_adjust_interval(experiment_adjust_interval)

    if auto_start:
        runner.start()

    return runner
