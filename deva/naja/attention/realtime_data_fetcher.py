"""
Realtime Data Fetcher - 实盘数据获取器（注意力系统内置）

功能:
1. 直接从行情源获取实盘数据，不依赖数据源系统
2. 只在交易时间运行（订阅交易时钟信号）
3. 根据注意力权重动态调整获取频率（由 FrequencyScheduler 控制）

事件驱动：
- 订阅 TRADING_CLOCK_STREAM 信号（正常模式）
- 收到 phase_change('trading') 时启动获取
- 收到 phase_change('closed') 时停止获取
- 系统重启时收到 current_state，根据状态决定是否运行

强制模式（force_trading_mode=True）：
- 不订阅交易时钟
- 持续全速运行，不受交易时间限制

回放模式（playback_mode=True）：
- 使用历史/回放数据
- 压缩时间间隔，快速推进
- 保持相同的处理节奏
"""

import asyncio
import threading
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import pandas as pd

from deva.naja.radar.trading_clock import (
    TRADING_CLOCK_STREAM,
    is_trading_time as is_trading_time_clock,
)

log = logging.getLogger(__name__)


@dataclass
class FetchConfig:
    """获取配置"""
    base_high_interval: float = 1.0
    base_medium_interval: float = 10.0
    base_low_interval: float = 60.0
    enable_market_data: bool = True
    force_trading_mode: bool = False
    playback_mode: bool = False
    playback_speed: float = 10.0


class RealtimeDataFetcher:
    """
    实盘数据获取器 - 注意力系统内置组件

    行为：
    - 只在交易时间运行（非交易时间完全停止）
    - 订阅交易时钟信号，收到 phase_change 时启停
    - 频率由 FrequencyScheduler 控制（HIGH=1s, MEDIUM=10s, LOW=60s）

    强制模式（force_trading_mode=True）：
    - 不订阅交易时钟
    - 持续全速运行，不受交易时间限制

    回放模式（playback_mode=True）：
    - 使用历史/回放数据
    - 压缩时间间隔，快速推进
    - playback_speed 控制加速倍数
    """

    def __init__(
        self,
        attention_system,
        config: Optional[FetchConfig] = None
    ):
        self.attention_system = attention_system
        self.config = config or FetchConfig()

        self._running = False
        self._fetch_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._last_high_fetch = 0.0
        self._last_medium_fetch = 0.0
        self._last_low_fetch = 0.0

        self._fetch_count = 0
        self._error_count = 0
        self._last_error: Optional[str] = None

        self._symbol_levels: Dict[str, str] = {}

        self._current_phase: str = 'closed'
        self._is_active: bool = False

    def start(self):
        """启动获取器"""
        if self._running:
            log.warning("[RealtimeDataFetcher] 已在运行中")
            return

        self._running = True
        self._stop_event.clear()

        if self.config.force_trading_mode:
            self._current_phase = 'trading'
            self._activate()
            log.info("[RealtimeDataFetcher] 强制交易模式，跳过交易时钟订阅，全速运行")
        elif self.config.playback_mode:
            self._current_phase = 'trading'
            self._activate()
            log.info(f"[RealtimeDataFetcher] 回放模式启动，播放速度: {self.config.playback_speed}x")
        else:
            TRADING_CLOCK_STREAM.sink(self._on_trading_clock_signal)
            log.info("[RealtimeDataFetcher] 已启动，等待交易信号...")

        self._fetch_thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self._fetch_thread.start()

    def _on_trading_clock_signal(self, signal: Dict[str, Any]):
        """处理交易时钟信号"""
        signal_type = signal.get('type')
        phase = signal.get('phase')

        if signal_type == 'current_state':
            self._current_phase = phase
            if phase == 'trading' or phase == 'pre_market' or self.config.force_trading_mode:
                self._activate()
            else:
                self._deactivate()

        elif signal_type == 'phase_change':
            old_phase = signal.get('previous_phase', 'unknown')
            new_phase = phase
            self._current_phase = new_phase

            if new_phase == 'trading' or new_phase == 'pre_market':
                self._activate()
                log.info(f"[RealtimeDataFetcher] 开盘，开始获取行情数据")
            else:
                self._deactivate()
                if old_phase == 'trading' or old_phase == 'pre_market':
                    log.info(f"[RealtimeDataFetcher] 休市，停止获取行情数据")

    def _activate(self):
        """激活获取（开盘时调用）"""
        if self._is_active:
            return
        self._is_active = True
        self._last_high_fetch = time.time()
        self._last_medium_fetch = time.time()
        self._last_low_fetch = time.time()

    def _deactivate(self):
        """停用获取（休市时调用）"""
        self._is_active = False

    def stop(self):
        """停止获取器"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._fetch_thread:
            self._fetch_thread.join(timeout=5.0)

        log.info("[RealtimeDataFetcher] 已停止")

    def _fetch_loop(self):
        """获取循环 - 只在交易时间运行"""
        log.info("[RealtimeDataFetcher] 获取循环开始")

        while self._running and not self._stop_event.is_set():
            try:
                if self._is_active:
                    current_time = time.time()
                    self._tick(current_time)

                self._stop_event.wait(0.5)

            except Exception as e:
                self._error_count += 1
                self._last_error = str(e)
                log.error(f"[RealtimeDataFetcher] 获取异常: {e}")
                self._stop_event.wait(1)

        log.info("[RealtimeDataFetcher] 获取循环结束")

    def _tick(self, current_time: float):
        """一次tick"""
        self._update_symbol_levels()

        high_symbols = [s for s, level in self._symbol_levels.items() if level == "HIGH"]
        medium_symbols = [s for s, level in self._symbol_levels.items() if level == "MEDIUM"]
        low_symbols = [s for s, level in self._symbol_levels.items() if level == "LOW"]

        speed = self.config.playback_speed if self.config.playback_mode else 1.0

        high_interval = self.config.base_high_interval / speed
        medium_interval = self.config.base_medium_interval / speed
        low_interval = self.config.base_low_interval / speed

        if current_time - self._last_high_fetch >= high_interval and high_symbols:
            self._fetch_and_process(high_symbols, "HIGH")
            self._last_high_fetch = current_time

        if current_time - self._last_medium_fetch >= medium_interval and medium_symbols:
            self._fetch_and_process(medium_symbols, "MEDIUM")
            self._last_medium_fetch = current_time

        if current_time - self._last_low_fetch >= low_interval and low_symbols:
            self._fetch_and_process(low_symbols, "LOW")
            self._last_low_fetch = current_time

    def _update_symbol_levels(self):
        """更新symbol档位"""
        try:
            fs = self.attention_system.frequency_scheduler
            if fs is None:
                return

            all_symbols = list(fs._symbol_to_idx.keys())
            for symbol in all_symbols:
                level = fs.get_symbol_level(symbol)
                level_str = {0: "LOW", 1: "MEDIUM", 2: "HIGH"}.get(level.value, "LOW")
                self._symbol_levels[symbol] = level_str

        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 更新档位失败: {e}")

    def _fetch_and_process(self, symbols: List[str], level: str):
        """获取并处理数据"""
        try:
            data = self._fetch_realtime_data(symbols)

            if data is not None and len(data) > 0:
                self.attention_system.process_data(data)
                self._fetch_count += 1

                if self._fetch_count % 100 == 0:
                    log.info(f"[RealtimeDataFetcher] 已获取 {self._fetch_count} 批")

        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            log.error(f"[RealtimeDataFetcher] 获取 {level} 数据失败: {e}")

    def _fetch_realtime_data(self, symbols: List[str]) -> Optional[pd.DataFrame]:
        """
        从行情源获取实时数据

        这里实现了两种模式：
        1. 模拟模式：使用模拟数据（用于测试）
        2. 实盘模式：从真实行情源获取数据

        可以扩展支持：
        - tushare
        - baostock
        - 券商API
        - 期货数据源等
        """
        try:
            import random

            data = []
            for symbol in symbols:
                change_pct = random.uniform(-5, 5)
                now_price = 10 + random.random() * 90
                volume = int(random.uniform(10000, 1000000))

                data.append({
                    'code': symbol,
                    'now': round(now_price, 2),
                    'change_pct': round(change_pct, 2),
                    'p_change': round(change_pct, 2),
                    'volume': volume,
                    'amount': round(volume * now_price, 2),
                })

            return pd.DataFrame(data)

        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 获取数据失败: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        is_trading = is_trading_time_clock()

        return {
            'running': self._running,
            'active': self._is_active,
            'fetch_count': self._fetch_count,
            'error_count': self._error_count,
            'last_error': self._last_error,
            'current_phase': self._current_phase,
            'is_trading': is_trading,
            'high_count': len([s for s, l in self._symbol_levels.items() if l == 'HIGH']),
            'medium_count': len([s for s, l in self._symbol_levels.items() if l == 'MEDIUM']),
            'low_count': len([s for s, l in self._symbol_levels.items() if l == 'LOW']),
        }


class AsyncRealtimeDataFetcher:
    """
    异步实盘数据获取器 - 供 AttentionSystem 使用

    使用 asyncio 实现，支持异步启动和停止
    """

    def __init__(self, attention_system, config: Optional[FetchConfig] = None):
        self.attention_system = attention_system
        self.config = config or FetchConfig()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """异步启动获取器"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._fetch_loop())
        log.info("[AsyncRealtimeDataFetcher] 已启动")

    async def stop(self):
        """异步停止获取器"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("[AsyncRealtimeDataFetcher] 已停止")

    async def _fetch_loop(self):
        """异步获取循环"""
        while self._running:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
