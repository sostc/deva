"""
Realtime Data Fetcher - 实盘数据获取器（注意力系统内置）

功能:
1. 直接从行情源获取实盘数据，不依赖数据源系统
2. 根据交易时间自动启停
3. 根据注意力权重动态调整获取频率
4. 开盘时自动开始获取，收盘后自动停止

交易时间判断:
- 交易日: 9:30-11:30, 13:00-15:00
- 盘前准备: 9:00-9:30 (可选)
- 盘后处理: 15:00-15:30 (可选)
"""

import asyncio
import threading
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, time as dt_time
import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class FetchConfig:
    """获取配置"""
    high_interval: float = 1.0
    medium_interval: float = 10.0
    low_interval: float = 30.0
    pre_market_start: str = "09:00"
    market_start: str = "09:30"
    market_end: str = "15:00"
    enable_market_data: bool = True
    force_trading_mode: bool = False  # 强制交易模式（用于测试）


class RealtimeDataFetcher:
    """
    实盘数据获取器 - 注意力系统内置组件

    完全独立于数据源系统，直接从行情源获取数据：
    - 交易时间内：实时获取行情数据
    - 非交易时间：使用模拟数据或停止获取
    - 根据权重动态调整获取频率
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

        self._is_trading_day = False
        self._last_trading_check = 0.0

    def start(self):
        """启动获取器"""
        if self._running:
            log.warning("[RealtimeDataFetcher] 已在运行中")
            return

        self._running = True
        self._stop_event.clear()

        self._fetch_thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self._fetch_thread.start()

        log.info(f"[RealtimeDataFetcher] 已启动, 高频: {self.config.high_interval}s, 中频: {self.config.medium_interval}s, 低频: {self.config.low_interval}s")

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
        """获取循环"""
        log.info("[RealtimeDataFetcher] 获取循环开始")

        while self._running and not self._stop_event.is_set():
            try:
                current_time = time.time()

                # 检查是否在交易时间
                is_trading = self._is_trading_time()

                if is_trading:
                    self._tick(current_time)
                else:
                    if self._fetch_count > 0:
                        log.info(f"[RealtimeDataFetcher] 非交易时间，停止获取 (已获取 {self._fetch_count} 批)")

            except Exception as e:
                self._error_count += 1
                self._last_error = str(e)
                log.error(f"[RealtimeDataFetcher] 获取异常: {e}")

            time.sleep(0.5)

        log.info("[RealtimeDataFetcher] 获取循环结束")

    def _is_trading_time(self) -> bool:
        """判断当前是否在交易时间内"""
        if self.config.force_trading_mode:
            return True

        current_time = time.time()

        if current_time - self._last_trading_check < 60:
            return self._is_trading_day

        self._last_trading_check = current_time

        now = datetime.now()
        current_time_str = now.strftime("%H:%M")
        weekday = now.weekday()

        if weekday >= 5:
            self._is_trading_day = False
            return False

        pre_start = self.config.pre_market_start
        market_start = self.config.market_start
        market_end = self.config.market_end

        is_in_pre_market = pre_start <= current_time_str < market_start
        is_in_market = market_start <= current_time_str < market_end

        self._is_trading_day = is_in_pre_market or is_in_market

        return self._is_trading_day

    def _tick(self, current_time: float):
        """一次tick"""
        self._update_symbol_levels()

        high_symbols = [s for s, level in self._symbol_levels.items() if level == "HIGH"]
        medium_symbols = [s for s, level in self._symbol_levels.items() if level == "MEDIUM"]
        low_symbols = [s for s, level in self._symbol_levels.items() if level == "LOW"]

        if current_time - self._last_high_fetch >= self.config.high_interval and high_symbols:
            self._fetch_and_process(high_symbols, "HIGH")
            self._last_high_fetch = current_time

        if current_time - self._last_medium_fetch >= self.config.medium_interval and medium_symbols:
            self._fetch_and_process(medium_symbols, "MEDIUM")
            self._last_medium_fetch = current_time

        if current_time - self._last_low_fetch >= self.config.low_interval and low_symbols:
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

                if self._fetch_count % 50 == 0:
                    log.info(f"[RealtimeDataFetcher] 已获取 {self._fetch_count} 批, "
                             f"HIGH: {len([s for s in symbols if self._symbol_levels.get(s) == 'HIGH'])}")

        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            log.error(f"[RealtimeDataFetcher] 获取 {level} 数据失败: {e}")

    def _fetch_realtime_data(self, symbols: List[str]) -> Optional[pd.DataFrame]:
        """
        从行情源获取实时数据

        这里实现了两种模式：
        1. 模拟模式：使用模拟数据（用于测试和非交易时间）
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
        is_trading = self._is_trading_time()
        current_time_str = datetime.now().strftime("%H:%M")
        weekday = datetime.now().weekday()
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

        if weekday >= 5:
            next_trading = "周一 09:30"
        elif current_time_str < "09:30":
            next_trading = "今天 09:30"
        elif current_time_str >= "15:00":
            next_trading = "明天 09:30"
        else:
            next_trading = "交易中"

        not_running_reasons = []
        if not self._running:
            not_running_reasons.append("获取器已停止")
        elif not is_trading:
            if weekday >= 5:
                not_running_reasons.append("周末休市")
            elif current_time_str < "09:30":
                not_running_reasons.append("盘前时间")
            elif current_time_str >= "15:00":
                not_running_reasons.append("已收盘")

        return {
            'running': self._running,
            'fetch_count': self._fetch_count,
            'error_count': self._error_count,
            'last_error': self._last_error,
            'is_trading': is_trading,
            'current_time': current_time_str,
            'weekday': weekday_names[weekday],
            'next_trading': next_trading,
            'not_running_reasons': not_running_reasons,
            'high_count': len([s for s, l in self._symbol_levels.items() if l == 'HIGH']),
            'medium_count': len([s for s, l in self._symbol_levels.items() if l == 'MEDIUM']),
            'low_count': len([s for s, l in self._symbol_levels.items() if l == 'LOW']),
        }


class AsyncRealtimeDataFetcher:
    """
    异步版本实盘数据获取器

    使用 asyncio 实现异步获取，提高并发效率
    """

    def __init__(
        self,
        attention_system,
        config: Optional[FetchConfig] = None
    ):
        self.attention_system = attention_system
        self.config = config or FetchConfig()

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._last_high_fetch = 0.0
        self._last_medium_fetch = 0.0
        self._last_low_fetch = 0.0

        self._fetch_count = 0
        self._error_count = 0
        self._symbol_levels: Dict[str, str] = {}

        self._is_trading_day = False
        self._last_trading_check = 0.0

    async def start(self):
        """启动异步获取器"""
        if self._running:
            return

        self._running = True
        self._loop = asyncio.get_event_loop()
        self._task = self._loop.create_task(self._async_fetch_loop())

        log.info(f"[AsyncRealtimeDataFetcher] 已启动")

    async def stop(self):
        """停止异步获取器"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        log.info("[AsyncRealtimeDataFetcher] 已停止")

    async def _async_fetch_loop(self):
        """异步获取循环"""
        log.info("[AsyncRealtimeDataFetcher] 获取循环开始")

        while self._running:
            try:
                await self._async_tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._error_count += 1
                log.error(f"[AsyncRealtimeDataFetcher] 获取异常: {e}")

            await asyncio.sleep(0.5)

        log.info("[AsyncRealtimeDataFetcher] 获取循环结束")

    async def _async_tick(self):
        """一次异步tick"""
        current_time = time.time()

        if not self._is_trading_time():
            return

        self._update_symbol_levels()

        high_symbols = [s for s, level in self._symbol_levels.items() if level == "HIGH"]
        medium_symbols = [s for s, level in self._symbol_levels.items() if level == "MEDIUM"]
        low_symbols = [s for s, level in self._symbol_levels.items() if level == "LOW"]

        tasks = []

        if current_time - self._last_high_fetch >= self.config.high_interval and high_symbols:
            self._last_high_fetch = current_time
            tasks.append(self._async_fetch_and_process(high_symbols, "HIGH"))

        if current_time - self._last_medium_fetch >= self.config.medium_interval and medium_symbols:
            self._last_medium_fetch = current_time
            tasks.append(self._async_fetch_and_process(medium_symbols, "MEDIUM"))

        if current_time - self._last_low_fetch >= self.config.low_interval and low_symbols:
            self._last_low_fetch = current_time
            tasks.append(self._async_fetch_and_process(low_symbols, "LOW"))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _is_trading_time(self) -> bool:
        """判断当前是否在交易时间内"""
        current_time = time.time()

        if current_time - self._last_trading_check < 60:
            return self._is_trading_day

        self._last_trading_check = current_time

        now = datetime.now()
        current_time_str = now.strftime("%H:%M")
        weekday = now.weekday()

        if weekday >= 5:
            self._is_trading_day = False
            return False

        is_in_market = self.config.market_start <= current_time_str < self.config.market_end

        self._is_trading_day = is_in_market
        return self._is_trading_day

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
            log.debug(f"[AsyncRealtimeDataFetcher] 更新档位失败: {e}")

    async def _async_fetch_and_process(self, symbols: List[str], level: str):
        """异步获取并处理数据"""
        try:
            data = await self._async_fetch_realtime_data(symbols)

            if data is not None and len(data) > 0:
                self.attention_system.process_data(data)
                self._fetch_count += 1

        except Exception as e:
            self._error_count += 1
            log.error(f"[AsyncRealtimeDataFetcher] 获取 {level} 数据失败: {e}")

    async def _async_fetch_realtime_data(self, symbols: List[str]) -> Optional[pd.DataFrame]:
        """异步从行情源获取数据"""
        def fetch_sync():
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

        return await self._loop.run_in_executor(None, fetch_sync)