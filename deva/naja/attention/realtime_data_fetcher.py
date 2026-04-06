"""
Realtime Data Fetcher - 实盘数据获取器（注意力系统内置）

功能:
1. 直接从 Sina 行情源获取实盘数据，不依赖数据源系统
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

Sina 数据获取：
- 使用 aiohttp 异步获取新浪行情
- 全量获取后按档位分离处理
- 复用 sample_sina_tick.py 的分类过滤逻辑
"""

import asyncio
import threading
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import pandas as pd
import numpy as np

from deva.naja.radar.trading_clock import (
    TRADING_CLOCK_STREAM,
    USTRADING_CLOCK_STREAM,
)

log = logging.getLogger(__name__)

_session = None


def _get_sina_session():
    """获取全局 aiohttp session"""
    global _session
    if _session is None or _session.closed:
        import aiohttp
        _session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=50, limit_per_host=20),
            timeout=aiohttp.ClientTimeout(total=30),
        )
    return _session


def _close_sina_session():
    """关闭全局 aiohttp session"""
    global _session
    if _session is not None and not _session.closed:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_session.close())
            else:
                loop.run_until_complete(_session.close())
        except Exception as e:
            log.warning(f"关闭 Sina session 失败: {e}")
        finally:
            _session = None


def _parse_sina_response(text: str) -> Dict:
    """解析新浪返回的数据"""
    result = {}
    for line in text.strip().split("\n"):
        if not line or '="' not in line:
            continue
        try:
            prefix, data = line.split('="')
            code = prefix.split("_")[-1]
            data = data.rstrip('"')
            if not data:
                continue
            fields = data.split(",")
            if len(fields) < 33:
                continue
            result[code] = {
                "name": fields[0],
                "open": float(fields[1]),
                "close": float(fields[2]),
                "now": float(fields[3]),
                "high": float(fields[4]),
                "low": float(fields[5]),
                "volume": int(fields[8]),
                "amount": float(fields[9]) if len(fields) > 9 and fields[9] else 0.0,
            }
        except Exception:
            continue
    return result


async def _fetch_sina_batch_async(codes: List[str], session=None) -> Dict:
    """异步获取一批股票数据"""
    if not codes:
        return {}
    if session is None:
        session = _get_sina_session()
    codes_str = ",".join(codes)
    url = f"https://hq.sinajs.cn/list={codes_str}"
    headers = {
        "Referer": "https://finance.sina.com.cn",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        log.debug(f"[_fetch_sina_batch_async] 请求 Sina API: codes数量={len(codes)}")
        async with session.get(url, headers=headers) as resp:
            log.debug(f"[_fetch_sina_batch_async] 响应状态: status={resp.status}")
            if resp.status != 200:
                return {}
            text = await resp.text()
            log.debug(f"[_fetch_sina_batch_async] 响应长度: {len(text)}")
            return _parse_sina_response(text)
    except Exception as e:
        log.error(f"[_fetch_sina_batch_async] 请求失败: {e}")
        return {}


async def _fetch_all_stocks_async() -> Optional[pd.DataFrame]:
    """异步获取全量股票数据"""
    import aiohttp

    STOCK_CATEGORIES = {
        "沪市主板": [f"sh{i}" for i in range(600000, 610000)] +
                   [f"sh{i}" for i in range(601000, 602000)] +
                   [f"sh{i}" for i in range(603000, 604000)] +
                   [f"sh{i}" for i in range(605000, 606000)],
        "科创板": [f"sh{i}" for i in range(688000, 689999)],
        "深市主板": [f"sz{i:06d}" for i in range(0, 1000)],
        "中小板": [f"sz{i:06d}" for i in range(2000, 3000)],
        "创业板": [f"sz{i:06d}" for i in range(300000, 302000)],
        "北交所": [f"bj{i}" for i in range(430000, 440000)] +
                 [f"bj{i}" for i in range(830000, 840000)] +
                 [f"bj{i}" for i in range(870000, 880000)],
    }

    codes = []
    for cat_codes in STOCK_CATEGORIES.values():
        codes.extend(cat_codes)
    codes = list(set(codes))
    log.debug(f"[_fetch_all_stocks_async] 股票代码总数: {len(codes)}")

    batch_size = 800
    all_data = {}

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=50, limit_per_host=20),
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            batch_data = await _fetch_sina_batch_async(batch, session)
            log.debug(f"[_fetch_all_stocks_async] 批次 {i//batch_size + 1}: 获取了 {len(batch_data)} 条数据")
            all_data.update(batch_data)
            await asyncio.sleep(0.05)

    log.debug(f"[_fetch_all_stocks_async] 总共获取: {len(all_data)} 条数据")

    if not all_data:
        log.debug("[_fetch_all_stocks_async] 无数据返回")
        return None

    df = pd.DataFrame(all_data).T
    return df


def _fetch_sina_sync(force_trading: bool = False) -> Optional[pd.DataFrame]:
    """同步获取 Sina 全量数据（在子线程中调用）"""
    try:
        log.debug("[_fetch_sina_sync] 开始获取 Sina 数据")
        try:
            result = asyncio.run(_fetch_all_stocks_async())
            if result is not None:
                log.debug(f"[_fetch_sina_sync] 获取完成: result={type(result)}, len={len(result)}")
            else:
                log.debug("[_fetch_sina_sync] 获取完成: result is None")
            return result
        except RuntimeError as e:
            if "Event loop is closed" in str(e) or "no running event loop" in str(e):
                log.warning(f"[_fetch_sina_sync] 事件循环问题，重试: {e}")
                import threading
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(_fetch_all_stocks_async())
                    return result
                finally:
                    loop.close()
            raise
    except Exception as e:
        log.error(f"[_fetch_sina_sync] 异常: {e}")
        import traceback
        log.error(traceback.format_exc())
        return None


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


SNAPSHOT_CONFIG_KEY = "realtime_data_fetcher_snapshot"


class RealtimeDataFetcher:
    """
    实盘数据获取器 - 注意力系统内置组件

    行为：
    - 只在交易时间运行（非交易时间完全停止）
    - 订阅交易时钟信号，收到 phase_change 时启停
    - 频率由 FrequencyScheduler 控制（HIGH=1s, MEDIUM=10s, LOW=60s）
    - 快照保存由 NB 配置控制开关

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
        self._us_last_fetch = 0.0

        self._fetch_count = 0
        self._error_count = 0
        self._last_error: Optional[str] = None

        self._symbol_levels: Dict[str, str] = {}

        self._cn_active: bool = False
        self._us_active: bool = False
        self._is_active: bool = False

        self._save_snapshot_enabled: bool = True
        self._last_snapshot_save_time: float = 0.0
        self._snapshot_save_count: int = 0

        self._load_snapshot_config()

    def start(self):
        """启动获取器"""
        if self._running:
            log.warning("[RealtimeDataFetcher] 已在运行中")
            return

        self._running = True
        self._stop_event.clear()

        log.info("[RealtimeDataFetcher] 启动中...")

        if self.config.force_trading_mode:
            self._cn_active = True
            self._us_active = True
            self._is_active = True
            self._activate()
            log.info("[RealtimeDataFetcher] 强制交易模式，跳过交易时钟订阅，全速运行")
        elif self.config.playback_mode:
            self._cn_active = True
            self._us_active = True
            self._is_active = True
            self._activate()
            log.info(f"[RealtimeDataFetcher] 回放模式启动，播放速度: {self.config.playback_speed}x")
        else:
            try:
                from deva.naja.radar.trading_clock import get_trading_clock, get_us_trading_clock

                tc = get_trading_clock()
                us_tc = get_us_trading_clock()

                tc.subscribe(self._on_cn_clock_signal)
                us_tc.subscribe(self._on_us_clock_signal)
                log.info("[RealtimeDataFetcher] 已订阅 A股/美股 交易时钟 (使用 subscribe)")

                cn_initial = tc.get_current_signal()
                us_initial = us_tc.get_current_signal()
                log.info(f"[RealtimeDataFetcher] 手动触发初始信号: cn_phase={cn_initial.get('phase')}, us_phase={us_initial.get('phase')}")
                self._on_cn_clock_signal(cn_initial)
                self._on_us_clock_signal(us_initial)
            except Exception as e:
                log.warning(f"[RealtimeDataFetcher] 订阅交易时钟失败: {e}，改用 STREAM.sink")
                TRADING_CLOCK_STREAM.sink(self._on_trading_clock_signal)
                USTRADING_CLOCK_STREAM.sink(self._on_trading_clock_signal)
            log.info("[RealtimeDataFetcher] 已启动，等待 A股/美股 交易信号...")

        self._fetch_thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self._fetch_thread.start()

    def _on_trading_clock_signal(self, signal: Dict[str, Any]):
        """处理交易时钟信号（通过 STREAM.sink 使用）

        信号格式:
        - type: 'current_state' | 'phase_change'
        - market: 'CN' | 'US'
        - phase: 'trading' | 'pre_market' | 'post_market' | 'closed'
        """
        signal_type = signal.get('type')
        market = signal.get('market', 'CN')
        phase = signal.get('phase')

        log.info(f"[RealtimeDataFetcher] 收到交易信号: market={market}, type={signal_type}, phase={phase}")

        if market == 'CN':
            self._update_cn_state(signal_type, phase)
        elif market == 'US':
            log.info(f"[RealtimeDataFetcher] 调用 _update_us_state: signal_type={signal_type}, phase={phase}")
            self._update_us_state(signal_type, phase)

    def _on_cn_clock_signal(self, signal: Dict[str, Any]):
        """处理A股交易时钟信号（通过 direct subscribe 使用）"""
        log.info(f"[RealtimeDataFetcher] 收到A股信号: {signal}")
        self._update_cn_state(signal.get('type'), signal.get('phase'))

    def _on_us_clock_signal(self, signal: Dict[str, Any]):
        """处理美股交易时钟信号（通过 direct subscribe 使用）"""
        signal_type = signal.get('type', 'unknown')
        phase = signal.get('phase', 'unknown')
        market = signal.get('market', 'US')
        timestamp = signal.get('timestamp', time.time())
        log.info(f"[RealtimeDataFetcher] 收到美股信号: type={signal_type}, market={market}, phase={phase}, timestamp={timestamp}")
        log.debug(f"[RealtimeDataFetcher] 美股信号详情: {signal}")
        self._update_us_state(signal_type, phase)

    def _update_cn_state(self, signal_type: str, phase: str):
        """更新 A股 状态"""
        old_active = self._cn_active

        if signal_type == 'current_state':
            self._cn_active = phase in ('trading', 'pre_market')
            log.debug(f"[RealtimeDataFetcher] A股 current_state: phase={phase}, active={self._cn_active}")

        elif signal_type == 'phase_change':
            old_phase = phase
            self._cn_active = phase in ('trading', 'pre_market')
            log.debug(f"[RealtimeDataFetcher] A股 phase_change: {old_phase} -> {phase}")

            if self._cn_active and not old_active:
                log.info(f"[RealtimeDataFetcher] A股开盘")

        self._update_overall_active()

    def _update_us_state(self, signal_type: str, phase: str):
        """更新 美股 状态"""
        old_active = self._us_active
        log.debug(f"[RealtimeDataFetcher] _update_us_state 被调用: signal_type={signal_type}, phase={phase}, old_us_active={old_active}")

        if signal_type == 'current_state':
            self._us_active = phase in ('trading', 'pre_market')
            log.debug(f"[RealtimeDataFetcher] 美股 current_state: phase={phase}, active={self._us_active}")

            if self._us_active:
                log.debug(f"[RealtimeDataFetcher] 调用 _run_async_in_thread(_fetch_and_sync_us)")
                self._run_async_in_thread(self._fetch_and_sync_us())

        elif signal_type == 'phase_change':
            old_phase = phase
            self._us_active = phase in ('trading', 'pre_market')
            log.debug(f"[RealtimeDataFetcher] 美股 phase_change: {old_phase} -> {phase}")

            if self._us_active and not old_active:
                log.info(f"[RealtimeDataFetcher] 美股开盘，开始获取数据")
                self._run_async_in_thread(self._fetch_and_sync_us())

        self._update_overall_active()

    def _run_async_in_thread(self, coro):
        """在子线程中安全运行异步协程"""
        def run_coro():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(coro)
            except Exception as e:
                log.error(f"[RealtimeDataFetcher] 异步执行失败: {e}")
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

        thread = threading.Thread(target=run_coro, daemon=True)
        thread.start()

    async def _fetch_and_sync_us(self):
        """获取美股数据并同步到持仓和注意力系统"""
        log.debug(f"[RealtimeDataFetcher] _fetch_and_sync_us 开始, attention_system={self.attention_system is not None}")
        try:
            us_data = await self._fetch_us_stocks()
            log.debug(f"[RealtimeDataFetcher] _fetch_us_stocks 返回: {len(us_data) if us_data else 0} 只")
            if us_data:
                self._sync_us_prices_to_portfolio(us_data)
                us_df = self._convert_us_to_dataframe(us_data)
                log.debug(f"[RealtimeDataFetcher] _convert_us_to_dataframe 返回: {us_df}, 类型: {type(us_df)}, 长度: {len(us_df) if us_df is not None else 'N/A'}")
                if us_df is not None and len(us_df) > 0:
                    log.debug(f"[RealtimeDataFetcher] 调用 _process_us_attention")
                    self._process_us_attention(us_df)
                    log.debug(f"[RealtimeDataFetcher] _process_us_attention 完成")
                    try:
                        from deva.naja.attention.integration import process_data_with_strategies
                        if self.attention_system is not None:
                            us_state = self.attention_system.get_us_attention_state()
                        else:
                            us_state = {}
                        context = {
                            'market': 'US',
                            'timestamp': time.time(),
                            'global_attention': us_state.get('global_attention', 0.5),
                            'activity': us_state.get('activity', 0.5),
                            'sector_weights': us_state.get('block_attention', {}),
                            'symbol_weights': us_state.get('symbol_weights', {}),
                        }
                        process_data_with_strategies(us_df, context)
                    except Exception as e:
                        log.warning(f"[RealtimeDataFetcher] US 策略处理失败: {e}")
                else:
                    log.debug(f"[RealtimeDataFetcher] us_df 为空，跳过 _process_us_attention")
        except Exception as e:
            log.error(f"[RealtimeDataFetcher] 获取美股数据异常: {e}")
            import traceback
            traceback.print_exc()

    def _update_overall_active(self):
        """更新整体活跃状态"""
        was_active = self._is_active
        self._is_active = self._cn_active or self._us_active

        if self._is_active and not was_active:
            self._activate()
            log.info(f"[RealtimeDataFetcher] 开始获取行情 (A股:{self._cn_active}, 美股:{self._us_active})")
        elif not self._is_active and was_active:
            self._deactivate()
            log.info(f"[RealtimeDataFetcher] 停止获取行情 (A股:{self._cn_active}, 美股:{self._us_active})")

    def _activate(self):
        """激活获取（开盘时调用）"""
        if self._is_active:
            log.debug("[RealtimeDataFetcher] _activate: 已经激活，跳过")
            return
        log.debug("[RealtimeDataFetcher] _activate: 激活数据获取器")
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

        _close_sina_session()

        log.info("[RealtimeDataFetcher] 已停止")

    def _fetch_loop(self):
        """获取循环 - 只在交易时间运行"""
        log.info("[RealtimeDataFetcher] 获取循环开始")
        log.warning(f"[RealtimeDataFetcher] DEBUG: _is_active={self._is_active}, _running={self._running}")

        while self._running and not self._stop_event.is_set():
            try:
                if self._is_active:
                    current_time = time.time()
                    log.debug(f"[RealtimeDataFetcher] _fetch_loop tick: _is_active=True, calling _tick()")
                    self._tick(current_time)
                else:
                    log.debug(f"[RealtimeDataFetcher] _fetch_loop: _is_active=False, skipping")

                self._stop_event.wait(0.5)

            except Exception as e:
                self._error_count += 1
                self._last_error = str(e)
                log.error(f"[RealtimeDataFetcher] 获取异常: {e}")
                self._stop_event.wait(1)

        log.info("[RealtimeDataFetcher] 获取循环结束")

    def _tick(self, current_time: float):
        """一次tick"""
        log.debug(f"[RealtimeDataFetcher] _tick 调用: _is_active={self._is_active}, current_time={current_time}")
        self._update_symbol_levels()

        high_symbols = [s for s, level in self._symbol_levels.items() if level == "HIGH"]
        medium_symbols = [s for s, level in self._symbol_levels.items() if level == "MEDIUM"]
        low_symbols = [s for s, level in self._symbol_levels.items() if level == "LOW"]

        log.debug(f"[RealtimeDataFetcher] _tick 档位统计: high={len(high_symbols)}, medium={len(medium_symbols)}, low={len(low_symbols)}, _symbol_levels总数={len(self._symbol_levels)}, force={self.config.force_trading_mode}")

        if not high_symbols and not medium_symbols and not low_symbols:
            if self._fetch_count == 0:
                log.debug(f"[RealtimeDataFetcher] 等待档位数据... (high: {len(high_symbols)}, medium: {len(medium_symbols)}, low: {len(low_symbols)})")
            if self.config.force_trading_mode:
                log.warning(f"[RealtimeDataFetcher] ⚠️ force_trading_mode: 强制获取全量数据, config.force_trading={self.config.force_trading_mode}")
                self._fetch_and_process([], "HIGH")
            return

        if self._us_active and not self._cn_active:
            log.debug(f"[RealtimeDataFetcher] _tick: 美股时段，跳过A股数据获取 (us_active={self._us_active}, cn_active={self._cn_active})")
            return

        if self._us_active and self._us_last_fetch == 0:
            self._run_async_in_thread(self._fetch_and_sync_us())

        if self._us_active and current_time - self._us_last_fetch >= self.config.base_high_interval:
            self._run_async_in_thread(self._fetch_and_sync_us())
            self._us_last_fetch = current_time

        speed = self.config.playback_speed if self.config.playback_mode else 1.0

        high_interval = self.config.base_high_interval / speed
        medium_interval = self.config.base_medium_interval / speed
        low_interval = self.config.base_low_interval / speed

        log.debug(f"[RealtimeDataFetcher] _tick 获取间隔: high={high_interval}s, medium={medium_interval}s, low={low_interval}s")

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
                log.debug("[RealtimeDataFetcher] _update_symbol_levels: frequency_scheduler 为 None")
                return

            all_symbols = list(fs._symbol_to_idx.keys())
            log.debug(f"[RealtimeDataFetcher] _update_symbol_levels: frequency_scheduler 有 {len(all_symbols)} 个符号")

            for symbol in all_symbols:
                level = fs.get_symbol_level(symbol)
                level_str = {0: "LOW", 1: "MEDIUM", 2: "HIGH"}.get(level.value, "LOW")
                self._symbol_levels[symbol] = level_str

            log.debug(f"[RealtimeDataFetcher] _update_symbol_levels 完成: 更新了 {len(all_symbols)} 个符号的档位")

        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 更新档位失败: {e}")

    def _fetch_and_process(self, symbols: List[str], level: str):
        """获取并处理数据"""
        try:
            log.debug(f"[RealtimeDataFetcher] _fetch_and_process 调用: level={level}, symbols数量={len(symbols)}, symbols[:5]={symbols[:5] if symbols else 'empty'}")
            data = self._fetch_realtime_data(symbols)
            log.debug(f"[RealtimeDataFetcher] _fetch_realtime_data 返回: data={type(data)}, len={len(data) if data is not None else 'None'}")

            if data is not None and len(data) > 0:
                log.debug(f"[RealtimeDataFetcher] 调用 attention_system.process_data, data行数={len(data)}, columns={list(data.columns)}")
                self.attention_system.process_data(data)
                self._fetch_count += 1

                self._write_to_market_data_bus(data)

                if level == "LOW" and self._save_snapshot_enabled:
                    self._save_market_snapshot(data)

                log.info(f"[RealtimeDataFetcher] [{level}] 获取 {len(data)} 条数据，累计 {self._fetch_count} 批")

                if self._fetch_count % 100 == 0:
                    log.info(f"[RealtimeDataFetcher] 已获取 {self._fetch_count} 批")
            else:
                log.debug(f"[RealtimeDataFetcher] 无数据返回: data is None or empty")

        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            log.error(f"[RealtimeDataFetcher] 获取 {level} 数据失败: {e}")

    def _fetch_realtime_data(self, symbols: List[str]) -> Optional[pd.DataFrame]:
        """
        从 Sina 行情源获取实时数据

        策略：全量获取后按 symbols 过滤
        - 高频档位：每 1s 获取一次（HIGH symbols）
        - 中频档位：每 10s 获取一次（MEDIUM symbols）
        - 低频档位：每 60s 获取一次（LOW symbols）

        注意：在源头过滤噪音股票（B股、ST股、低流动性）
        """
        try:
            df = _fetch_sina_sync(force_trading=self.config.force_trading_mode)

            if df is None or df.empty:
                return None

            df = self._apply_noise_filter_at_source(df)

            if not symbols:
                return df

            code_list = [s for s in symbols]
            filtered = df[df.index.isin(code_list)]

            if filtered.empty:
                return df

            filtered = filtered.copy()
            filtered['code'] = filtered.index
            if 'now' in filtered.columns and 'close' in filtered.columns:
                filtered['p_change'] = (filtered['now'] - filtered['close']) / filtered['close']
                filtered['change_pct'] = filtered['p_change']

            return filtered

        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 获取数据失败: {e}")
            return None

    def _apply_noise_filter_at_source(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        在数据源头应用噪音过滤

        过滤内容：
        1. B股（名称以B结尾或包含"B股"）
        2. ST股票
        3. 低流动性股票（成交金额/成交量过低）
        4. 低价股票
        """
        if df is None or df.empty:
            return df

        try:
            from deva.naja.attention.processing.noise_filter import get_noise_filter
            from deva.naja.attention.processing.block_noise_detector import BlockNoiseDetector

            if not hasattr(self, '_noise_filter') or self._noise_filter is None:
                self._noise_filter = get_noise_filter()
            if not hasattr(self, '_block_noise_detector') or self._block_noise_detector is None:
                self._block_noise_detector = BlockNoiseDetector.get_instance()

            noise_filter = self._noise_filter
            block_noise_detector = self._block_noise_detector

            original_count = len(df)
            mask = pd.Series([True] * len(df), index=df.index)

            if 'name' in df.columns:
                names = df['name'].astype(str)
                b_share_mask = ~(
                    names.str.endswith('B') |
                    names.str.endswith('b') |
                    names.str.contains('B股', regex=False, na=False) |
                    names.str.contains(' ST', regex=False, na=False) |
                    names.str.contains('*ST', regex=False, na=False)
                )
                mask &= b_share_mask

                filtered_names = df[~b_share_mask]
                if len(filtered_names) > 0:
                    log.debug(f"[RealtimeDataFetcher] 源头过滤B股/ST: {len(filtered_names)}只")

            if 'amount' in df.columns:
                amounts = df['amount']
                valid_amount_mask = (amounts >= noise_filter.config.min_amount) | (amounts == 0)
                mask &= valid_amount_mask

            if 'volume' in df.columns:
                volumes = df['volume']
                valid_volume_mask = (volumes >= noise_filter.config.min_volume) | (volumes == 0)
                mask &= valid_volume_mask

            if 'now' in df.columns:
                prices = df['now']
                valid_price_mask = prices >= noise_filter.config.min_price
                mask &= valid_price_mask

            filtered_df = df[mask].copy()

            if original_count - len(filtered_df) > 0:
                log.info(f"[RealtimeDataFetcher] 源头噪音过滤: 原始{original_count}条 -> 过滤后{len(filtered_df)}条 (过滤{original_count - len(filtered_df)}条, 过滤率{(original_count - len(filtered_df))/original_count*100:.1f}%)")

            return filtered_df

        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 源头噪音过滤失败: {e}")
            return df

    async def _fetch_us_stocks(self) -> Optional[Dict[str, Any]]:
        """获取美股数据

        从 GlobalMarketAPI 获取美股全量数据，返回格式：
        {
            'code': {'price': float, 'prev_close': float, 'change': float, 'change_pct': float, 'volume': int},
            ...
        }
        """
        try:
            from deva.naja.attention.data.global_market_futures import GlobalMarketAPI, US_STOCK_CODES

            api = GlobalMarketAPI()
            data = await api.fetch(list(US_STOCK_CODES.keys()))

            result = {}
            for sina_code, market_data in data.items():
                symbol = US_STOCK_CODES.get(sina_code, sina_code.replace('gb_', ''))
                result[symbol] = {
                    'price': market_data.current,
                    'prev_close': market_data.prev_close,
                    'change': market_data.change,
                    'change_pct': market_data.change_pct,
                    'volume': market_data.volume,
                    'high': market_data.high,
                    'low': market_data.low,
                    'name': market_data.name,
                }

            if result:
                log.debug(f"[RealtimeDataFetcher] 获取 {len(result)} 只美股数据")
            return result

        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 获取美股数据失败: {e}")
            return None

    def _sync_us_prices_to_portfolio(self, us_data: Dict[str, Any]):
        """同步美股数据到持仓和 MarketDataBus"""
        try:
            from deva.naja.bandit.portfolio_manager import get_portfolio_manager

            pm = get_portfolio_manager()
            price_map = {}
            prev_close_map = {}

            for code, info in us_data.items():
                price_map[code] = info['price']
                prev_close_map[code] = info['prev_close']

            pm.update_us_prices(price_map, prev_close_map)
            log.debug(f"[RealtimeDataFetcher] 同步 {len(us_data)} 只美股到持仓")
        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 同步美股到持仓失败: {e}")

        try:
            from deva.naja.bandit.market_data_bus import get_market_data_bus, MarketQuote
            bus = get_market_data_bus()
            now = time.time()
            for code, info in us_data.items():
                quote = MarketQuote(
                    code=code,
                    name=info.get('name', code),
                    current=info.get('price', 0),
                    prev_close=info.get('prev_close', 0),
                    change=info.get('change', 0),
                    change_pct=info.get('change_pct', 0),
                    volume=info.get('volume', 0),
                    high=info.get('high', 0),
                    low=info.get('low', 0),
                    market='US',
                    timestamp=now,
                    fetch_time=now,
                    is_stale=False,
                )
                if quote.current > 0:
                    bus.write_quotes({code: quote})
        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 同步美股到 MarketDataBus 失败: {e}")

    def _convert_us_to_dataframe(self, us_data: Dict[str, Any]) -> Optional[pd.DataFrame]:
        """将美股数据转换为注意力系统可处理的DataFrame格式

        字段映射：
        - code: 股票代码（如 nvda, aapl）
        - name: 股票名称
        - now: 当前价 (price)
        - close: 昨收价 (prev_close)
        - p_change: 涨跌幅 (change_pct)
        - volume: 成交量
        - high: 最高价
        - low: 最低价
        - sector: 主要板块 ID（从US_STOCK_SECTORS映射）
        - blocks: 板块关键词列表（完整叙事标签）
        - narrative: 核心叙事标签
        - market: 市场标识 'US'
        """
        if not us_data:
            return None

        try:
            from deva.naja.bandit.stock_sector_map import US_STOCK_SECTORS

            records = []
            for symbol, info in us_data.items():
                stock_info = US_STOCK_SECTORS.get(symbol, {})
                blocks = stock_info.get("blocks", [])
                sector = stock_info.get("sector", "other")
                narrative = stock_info.get("narrative", blocks[0] if blocks else sector)
                records.append({
                    'code': symbol,
                    'name': info.get('name', symbol),
                    'now': info.get('price', 0),
                    'close': info.get('prev_close', 0),
                    'open': info.get('open', info.get('price', 0)),
                    'high': info.get('high', 0),
                    'low': info.get('low', 0),
                    'p_change': info.get('change_pct', 0),
                    'volume': info.get('volume', 0),
                    'amount': info.get('volume', 0) * info.get('price', 0),
                    'sector': sector,
                    'blocks': blocks,
                    'narrative': narrative,
                    'market': 'US',
                })

            if not records:
                return None

            df = pd.DataFrame(records)
            df.set_index('code', inplace=True)
            all_blocks = [b for blocks in df['blocks'] for b in blocks]
            block_counts = {}
            for b in all_blocks:
                block_counts[b] = block_counts.get(b, 0) + 1
            log.debug(f"[RealtimeDataFetcher] 转换美股数据: {len(df)} 只, blocks分布: {block_counts}")
            return df

        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 转换美股数据失败: {e}")
            return None

    def _write_to_market_data_bus(self, df: pd.DataFrame):
        """将行情数据写入 MarketDataBus（供其他模块共享）"""
        if df is None or df.empty:
            return
        try:
            from deva.naja.bandit.market_data_bus import get_market_data_bus, MarketQuote
            bus = get_market_data_bus()
            now = time.time()
            for _, row in df.iterrows():
                try:
                    code = str(row.get('code', ''))
                    if not code:
                        continue
                    if code.startswith('sh'):
                        market = 'SH'
                    elif code.startswith('sz'):
                        market = 'SZ'
                    else:
                        market = str(row.get('market', 'US'))
                    quote = MarketQuote(
                        code=code,
                        name=str(row.get('name', code)),
                        current=float(row.get('now', 0)),
                        prev_close=float(row.get('close', row.get('prev_close', 0))),
                        change=float(row.get('price_change', 0)),
                        change_pct=float(row.get('p_change', 0)),
                        volume=int(row.get('volume', 0)),
                        high=float(row.get('high', 0)),
                        low=float(row.get('low', 0)),
                        open_price=float(row.get('open', 0)),
                        amount=float(row.get('amount', 0)),
                        market=market,
                        timestamp=row.get('timestamp', now),
                        fetch_time=now,
                        is_stale=False,
                    )
                    if quote.current > 0:
                        bus.write_quotes({code: quote})
                except Exception:
                    continue
        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 写入 MarketDataBus 失败: {e}")

    def _process_us_attention(self, us_df: pd.DataFrame):
        """处理美股注意力数据

        将美股数据送入注意力系统进行计算：
        1. 计算美股全局注意力
        2. 计算美股板块注意力
        3. 更新美股个股权重
        """
        if us_df is None or us_df.empty:
            log.debug(f"[RealtimeDataFetcher] _process_us_attention: us_df 为空或 None")
            return

        try:
            if self.attention_system is None:
                log.debug(f"[RealtimeDataFetcher] attention_system 为 None，跳过美股注意力处理")
                return

            if not hasattr(self.attention_system, '_initialized') or not self.attention_system._initialized:
                log.debug(f"[RealtimeDataFetcher] attention_system 未初始化 (_initialized={getattr(self.attention_system, '_initialized', 'N/A')})，跳过美股注意力处理")
                return

            symbols = us_df.index.values
            self._us_last_symbols = list(symbols)
            prices = us_df['now'].values if 'now' in us_df.columns else us_df['close'].values
            returns = us_df['p_change'].values if 'p_change' in us_df.columns else np.zeros(len(us_df))
            volumes = us_df['volume'].values if 'volume' in us_df.columns else np.zeros(len(us_df))

            returns = np.nan_to_num(returns, nan=0.0, posinf=50.0, neginf=-50.0)
            returns = np.clip(returns, -50.0, 50.0)
            volumes = np.nan_to_num(volumes, nan=0.0, posinf=1e15, neginf=0.0)
            prices = np.nan_to_num(prices, nan=0.0, posinf=1e6, neginf=0.0)

            sector_ids = us_df['sector'].values if 'sector' in us_df.columns else np.array(['其他'] * len(us_df))

            timestamp = time.time()

            has_method = hasattr(self.attention_system, 'process_us_snapshot')
            log.debug(f"[RealtimeDataFetcher] has process_us_snapshot: {has_method}")

            if has_method:
                log.info(f"[RealtimeDataFetcher] 开始处理美股注意力: {len(symbols)} 只股票, symbols={list(symbols)[:5]}")
                result = self.attention_system.process_us_snapshot(
                    symbols=symbols,
                    returns=returns,
                    volumes=volumes,
                    prices=prices,
                    sector_ids=sector_ids,
                    timestamp=timestamp
                )
                log.info(f"[RealtimeDataFetcher] 美股注意力处理完成: global_attention={result.get('global_attention', 'N/A')}, block_count={len(result.get('block_attention', {}))}")
            else:
                log.debug(f"[RealtimeDataFetcher] attention_system 不支持 process_us_snapshot 方法")
                log.debug(f"[RealtimeDataFetcher] attention_system 方法列表: {[m for m in dir(self.attention_system) if not m.startswith('_')]}")

        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 处理美股注意力失败: {e}")

    def _save_market_snapshot(self, data: pd.DataFrame):
        """保存市场快照到历史行情表（quant_snapshot_5min_window）"""
        try:
            from deva import NB

            if data is None or data.empty:
                return

            snapshot_db = NB("quant_snapshot_5min_window", key_mode="time")

            records = []
            timestamp = time.time()

            for idx, row in data.iterrows():
                code = idx
                # 计算涨跌幅（如果 DataFrame 中没有的话）
                p_change = row.get("p_change", 0)
                if p_change == 0 and row.get("close", 0) > 0 and row.get("now", 0) > 0:
                    p_change = (row.get("now", 0) - row.get("close", 0)) / row.get("close", 0)
                
                record = {
                    "timestamp": timestamp,
                    "code": code,
                    "name": row.get("name", ""),
                    "open": row.get("open", 0),
                    "close": row.get("close", 0),
                    "now": row.get("now", 0),
                    "high": row.get("high", 0),
                    "low": row.get("low", 0),
                    "volume": row.get("volume", 0),
                    "amount": row.get("amount", 0),
                    "p_change": p_change,
                }
                records.append(record)

            if records:
                snapshot_db.append(records)
                self._last_snapshot_save_time = timestamp
                self._snapshot_save_count += 1
                log.debug(f"[RealtimeDataFetcher] 保存快照 {len(records)} 条到 quant_snapshot_5min_window")

        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 保存快照失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            from deva.naja.radar.trading_clock import get_trading_clock, get_us_trading_clock

            cn_tc = get_trading_clock()
            us_tc = get_us_trading_clock()

            cn_signal = cn_tc.get_current_signal()
            us_signal = us_tc.get_current_signal()

            cn_phase = cn_signal.get('phase', 'closed')
            us_phase = us_signal.get('phase', 'closed')

            cn_next = cn_signal.get('next_change_time', '')
            us_next = us_signal.get('next_change_time', '')

            # 使用统一的格式化函数处理时间（自动转换时区到北京时间）
            from .ui_components.common import _format_next_time
            
            if cn_next:
                cn_next_str = _format_next_time(cn_next)
            else:
                cn_next_str = ''

            if us_next:
                us_next_str = _format_next_time(us_next)
            else:
                us_next_str = ''

            cn_info = {
                'phase': cn_phase,
                'phase_name': {'trading': '交易中', 'pre_market': '盘前', 'post_market': '盘后', 'closed': '休市', 'lunch': '午休'}.get(cn_phase, cn_phase),
                'next_change_time': cn_next_str,
                'next_phase': cn_signal.get('next_phase', ''),
                'next_phase_name': {'trading': '开盘', 'pre_market': '集合竞价', 'post_market': '盘后', 'closed': '休市', 'lunch': '午休'}.get(cn_signal.get('next_phase', ''), cn_signal.get('next_phase', '')),
            }

            us_info = {
                'phase': us_phase,
                'phase_name': {'trading': '交易中', 'pre_market': '盘前', 'post_market': '盘后', 'closed': '休市'}.get(us_phase, us_phase),
                'next_change_time': us_next_str,
                'next_phase': us_signal.get('next_phase', ''),
                'next_phase_name': {'trading': '收盘', 'pre_market': '开盘', 'post_market': '休市', 'closed': '开盘'}.get(us_signal.get('next_phase', ''), us_signal.get('next_phase', '')),
            }

        except Exception as e:
            cn_info = {'phase': 'unknown', 'phase_name': '未知', 'next_change_time': '', 'next_phase': '', 'next_phase_name': ''}
            us_info = {'phase': 'unknown', 'phase_name': '未知', 'next_change_time': '', 'next_phase': '', 'next_phase_name': ''}

        return {
            'running': self._running,
            'active': self._is_active,
            'cn_active': self._cn_active,
            'us_active': self._us_active,
            'fetch_count': self._fetch_count,
            'error_count': self._error_count,
            'last_error': self._last_error,
            'is_trading': self._cn_active,
            'is_us_trading': self._us_active,
            'is_force_trading_mode': self.config.force_trading_mode,
            'high_count': len([s for s, l in self._symbol_levels.items() if l == 'HIGH']),
            'medium_count': len([s for s, l in self._symbol_levels.items() if l == 'MEDIUM']),
            'low_count': len([s for s, l in self._symbol_levels.items() if l == 'LOW']),
            'us_stock_count': len(self._us_last_symbols) if hasattr(self, '_us_last_symbols') else 0,
            'us_fetch_count': getattr(self, '_us_fetch_count', 0),
            'cn_info': cn_info,
            'us_info': us_info,
        }

    def health_check(self) -> Dict[str, Any]:
        """
        健康检查，返回诊断信息

        Returns:
            dict: 包含健康状态的诊断信息
        """
        issues = []
        warnings = []

        if not self._running:
            issues.append("获取器未运行")

        if self._error_count > 10:
            warnings.append(f"错误次数较多: {self._error_count}")

        if self._running and self._fetch_count == 0 and not self.config.force_trading_mode:
            warnings.append("运行中但获取次数为0，可能处于非交易时间")

        if self._running and self._is_active and self._fetch_count > 0:
            success_rate = (self._fetch_count - self._error_count) / max(1, self._fetch_count) * 100
            if success_rate < 80:
                warnings.append(f"成功率较低: {success_rate:.1f}%")

        return {
            'healthy': len(issues) == 0,
            'running': self._running,
            'active': self._is_active,
            'fetch_count': self._fetch_count,
            'error_count': self._error_count,
            'issues': issues,
            'warnings': warnings,
            'last_error': self._last_error,
            'mode': 'force_realtime' if self.config.force_trading_mode else 'normal',
        }

    def _load_snapshot_config(self):
        """从 NB 加载快照保存配置"""
        try:
            from deva import NB
            config_db = NB("system_config", key_mode="explicit")
            config = config_db.get(SNAPSHOT_CONFIG_KEY)
            if config is not None and isinstance(config, dict):
                self._save_snapshot_enabled = config.get("enabled", True)
                log.info(f"[RealtimeDataFetcher] 加载快照配置: enabled={self._save_snapshot_enabled}")
            else:
                self._save_snapshot_enabled = True
        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 加载快照配置失败: {e}")
            self._save_snapshot_enabled = True

    def _save_snapshot_config(self):
        """保存快照保存配置到 NB"""
        try:
            from deva import NB
            config_db = NB("system_config", key_mode="explicit")
            config_db[SNAPSHOT_CONFIG_KEY] = {
                "enabled": self._save_snapshot_enabled,
                "updated_at": time.time(),
            }
        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 保存快照配置失败: {e}")

    def enable_snapshot_save(self):
        """启用快照保存"""
        self._save_snapshot_enabled = True
        self._save_snapshot_config()
        log.info("[RealtimeDataFetcher] 快照保存已启用")

    def disable_snapshot_save(self):
        """禁用快照保存"""
        self._save_snapshot_enabled = False
        self._save_snapshot_config()
        log.info("[RealtimeDataFetcher] 快照保存已禁用")

    def is_snapshot_save_enabled(self) -> bool:
        """快照保存是否启用"""
        return self._save_snapshot_enabled


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


_fetcher_instance: Optional[RealtimeDataFetcher] = None


def get_data_fetcher() -> Optional[RealtimeDataFetcher]:
    """获取全局 RealtimeDataFetcher 实例"""
    global _fetcher_instance
    import time

    if _fetcher_instance is not None:
        log.debug(f"[get_data_fetcher] 直接返回缓存：{id(_fetcher_instance)}")
        return _fetcher_instance

    # 等待 attention_system 初始化完成（最多等待 5 秒）
    max_wait = 5.0
    wait_step = 0.2
    waited = 0.0
    
    while waited < max_wait:
        try:
            from deva.naja.attention.integration.extended import get_attention_integration
            integration = get_attention_integration()
            
            # 检查是否已初始化完成
            if hasattr(integration, '_initialized_attention_system') and integration._initialized_attention_system:
                # 已初始化，获取 fetcher
                if integration.attention_system:
                    fetcher = integration.attention_system._realtime_fetcher
                    if fetcher is not None:
                        _fetcher_instance = fetcher
                        log.debug(f"[get_data_fetcher] 等待后获取到 fetcher: {id(fetcher)}")
                        return _fetcher_instance
                # 已初始化但没有 fetcher，直接返回
                log.debug(f"[get_data_fetcher] 已初始化但 fetcher 为 None")
                break
        except Exception as e:
            log.debug(f"[get_data_fetcher] 异常：{e}")
            pass
        
        time.sleep(wait_step)
        waited += wait_step

    log.debug(f"[get_data_fetcher] 等待超时，返回 None")
    return _fetcher_instance


def set_data_fetcher(fetcher: RealtimeDataFetcher):
    """设置全局 RealtimeDataFetcher 实例"""
    global _fetcher_instance
    log.debug(f"[DataFetcher] set_data_fetcher called: fetcher={fetcher}")
    _fetcher_instance = fetcher
    log.debug(f"[DataFetcher] _fetcher_instance now: {_fetcher_instance}")
