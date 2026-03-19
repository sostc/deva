"""Bandit 自动运行器

提供定时任务功能，自动执行 Bandit 选择和调节。
与 LLM Controller 的 auto_adjust 机制一致。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from deva import NB, when

from .optimizer import get_bandit_optimizer
from ..log_stream import get_log_stream, log_strategy

log = logging.getLogger(__name__)

BANDIT_CONFIG_TABLE = "naja_bandit_config"


class BanditAutoRunner:
    """Bandit 自动运行器
    
    提供定时任务功能：
    1. 定期选择最优策略
    2. 定期根据收益调整策略参数
    3. 与 LLM Controller 的 ensure_llm_auto_adjust_task 对应
    """
    
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        self._select_interval = 60
        self._adjust_interval = 300
        self._enabled = True
        
        self._last_select_ts = 0.0
        self._last_adjust_ts = 0.0
        
        self._load_config()
    
    def _load_config(self):
        """从数据库加载配置"""
        try:
            db = NB(BANDIT_CONFIG_TABLE)
            config = db.get("auto_config")
            if config:
                self._select_interval = config.get("select_interval", 60)
                self._adjust_interval = config.get("adjust_interval", 300)
                self._enabled = config.get("enabled", True)
                # 恢复运行状态
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
                "enabled": self._enabled,
                "was_running": self._running  # 保存运行状态
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
        
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        self._save_config()  # 保存运行状态
        
        log.info(f"BanditAutoRunner 已启动 (选择间隔: {self._select_interval}s, 调节间隔: {self._adjust_interval}s)")
    
    def stop(self):
        """停止自动运行"""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=5)
        
        self._save_config()  # 保存运行状态
        
        log.info("BanditAutoRunner 已停止")
    
    def _run_loop(self):
        """主循环"""
        while self._running and not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as e:
                log.error(f"BanditAutoRunner 运行错误: {e}")
            
            self._stop_event.wait(10)
    
    def _tick(self):
        """定时任务"""
        now = time.time()
        
        if self._enabled:
            if now - self._last_select_ts >= self._select_interval:
                self._do_select()
                self._last_select_ts = now
            
            if now - self._last_adjust_ts >= self._adjust_interval:
                self._do_adjust()
                self._last_adjust_ts = now
    
    def _do_select(self):
        """执行策略选择"""
        from ..strategy import get_strategy_manager
        
        mgr = get_strategy_manager()
        entries = mgr.list_all()
        
        if not entries:
            return
        
        available = [e.id for e in entries]
        
        optimizer = get_bandit_optimizer()
        result = optimizer.select_strategy(available)
        
        if result.get("success"):
            selected = result.get("selected")
            log.info(f"Bandit 自动选择策略: {selected}")
            log_strategy("INFO", "bandit", "auto_select", f"自动选择策略: {selected}")
        else:
            log_strategy("WARN", "bandit", "auto_select", f"选择失败: {result.get('error')}")
    
    def _do_adjust(self):
        """执行策略调节"""
        optimizer = get_bandit_optimizer()
        result = optimizer.review_and_adjust()
        
        if result.get("success") and result.get("actions"):
            log.info(f"Bandit 自动调节: {result.get('summary')}")
            log_strategy("INFO", "bandit", "auto_adjust", 
                        f"调节成功: {result.get('summary')}, 动作数: {len(result.get('actions', []))}")
        elif result.get("success"):
            log_strategy("INFO", "bandit", "auto_adjust", "无需调节")
        else:
            log_strategy("WARN", "bandit", "auto_adjust", f"调节失败: {result.get('error')}")
    
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
    
    def enable(self):
        """启用自动运行"""
        self._enabled = True
        self._save_config()
    
    def disable(self):
        """禁用自动运行"""
        self._enabled = False
        self._save_config()
    
    def get_status(self) -> dict:
        """获取状态"""
        return {
            "running": self._running,
            "enabled": self._enabled,
            "select_interval": self._select_interval,
            "adjust_interval": self._adjust_interval,
            "last_select_ts": self._last_select_ts,
            "last_adjust_ts": self._last_adjust_ts
        }


_runner: Optional[BanditAutoRunner] = None
_runner_lock = threading.Lock()


def get_bandit_runner() -> BanditAutoRunner:
    global _runner
    if _runner is None:
        with _runner_lock:
            if _runner is None:
                _runner = BanditAutoRunner()
    return _runner


def ensure_bandit_auto_runner(
    select_interval: int = 60,
    adjust_interval: int = 300,
    auto_start: bool = True,
) -> BanditAutoRunner:
    """确保 Bandit 自动运行器已配置
    
    与 LLM Controller.ensure_llm_auto_adjust_task 对应
    
    Args:
        select_interval: 策略选择间隔 (秒)
        adjust_interval: 策略调节间隔 (秒)
        auto_start: 是否自动启动
        
    Returns:
        BanditAutoRunner: 运行器实例
    """
    runner = get_bandit_runner()
    
    runner.set_select_interval(select_interval)
    runner.set_adjust_interval(adjust_interval)
    
    if auto_start:
        runner.start()
    
    return runner
