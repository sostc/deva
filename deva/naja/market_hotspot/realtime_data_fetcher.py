"""
Realtime Data Fetcher - 实盘数据获取器（热点系统内置）

功能:
1. 直接从 Sina 行情源获取实盘数据，不依赖数据源系统
2. 只在交易时间运行（订阅交易时钟信号）
3. 根据热点权重动态调整获取频率（由 FrequencyScheduler 控制：HIGH=5s, MEDIUM=10s, LOW=60s）

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
import os
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
from deva.naja.register import SR

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


def _get_cn_codes_from_registry():
    """从 BlockDictionary 获取 A 股代码列表"""
    try:
        from deva.naja.dictionary.blocks import get_block_dictionary
        bd = get_block_dictionary()
        codes = list(bd.get_all_stocks('CN'))
        if codes:
            log.info(f"[_get_cn_codes_from_registry] 从 BlockDictionary 获取到 {len(codes)} 只 A 股")
            return codes
    except Exception as e:
        log.warning(f"[_get_cn_codes_from_registry] 获取失败: {e}")
    return None


async def _fetch_all_stocks_async() -> Optional[pd.DataFrame]:
    """异步获取全量股票数据"""
    import aiohttp
    import sys

    print(f"[ASYNC] _fetch_all_stocks_async 开始, PID={os.getpid()}", flush=True)
    log.debug(f"[_fetch_all_stocks_async] 开始获取...")

    codes = _get_cn_codes_from_registry()
    if not codes:
        log.error("[_fetch_all_stocks_async] StockRegistry 为空，无法获取股票代码列表")
        return None

    print(f"[ASYNC] 股票代码总数: {len(codes)}", flush=True)
    log.debug(f"[_fetch_all_stocks_async] 股票代码总数: {len(codes)}")

    batch_size = 800
    all_data = {}

    print(f"[ASYNC] 创建 ClientSession...", flush=True)
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=50, limit_per_host=20),
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:
        print(f"[ASYNC] ClientSession 创建成功，开始获取批次...", flush=True)
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            print(f"[ASYNC] 获取批次 {i//batch_size + 1}, 代码数: {len(batch)}", flush=True)
            batch_data = await _fetch_sina_batch_async(batch, session)
            print(f"[ASYNC] 批次 {i//batch_size + 1} 返回: {len(batch_data)} 条", flush=True)
            log.debug(f"[_fetch_all_stocks_async] 批次 {i//batch_size + 1} 返回: {len(batch_data)} 条")
            all_data.update(batch_data)
            await asyncio.sleep(0.05)

    print(f"[ASYNC] 所有批次获取完成，总共: {len(all_data)} 条", flush=True)
    log.debug(f"[_fetch_all_stocks_async] 总共获取: {len(all_data)} 条数据")

    if not all_data:
        log.debug("[_fetch_all_stocks_async] 无数据返回")
        return None

    df = pd.DataFrame(all_data).T
    return df


def _fetch_sina_sync(force_trading: bool = False) -> Optional[pd.DataFrame]:
    """同步获取 Sina 全量数据（在子线程中调用）"""
    import sys
    print(f"[SINA_SYNC] 开始 PID={os.getpid()}", flush=True)
    try:
        log.debug("[_fetch_sina_sync] 开始获取 Sina 数据")
        # 直接使用新事件循环，避免 asyncio.run() 在子线程中的问题
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        print(f"[SINA_SYNC] 创建事件循环完成", flush=True)
        try:
            result = loop.run_until_complete(_fetch_all_stocks_async())
            print(f"[SINA_SYNC] run_until_complete 完成, result={len(result) if result is not None else None}", flush=True)
            if result is not None:
                log.debug(f"[_fetch_sina_sync] 获取完成: result={type(result)}, len={len(result)}")
            else:
                log.debug("[_fetch_sina_sync] 获取完成: result is None")
            return result
        finally:
            loop.close()
            print(f"[SINA_SYNC] 事件循环已关闭", flush=True)
    except Exception as e:
        print(f"[SINA_SYNC] 异常: {e}", flush=True)
        log.error(f"[_fetch_sina_sync] 异常: {e}")
        import traceback
        log.error(traceback.format_exc())
        return None


@dataclass
class FetchConfig:
    """获取配置"""
    base_high_interval: float = 5.0
    base_medium_interval: float = 10.0
    base_low_interval: float = 60.0
    enable_market_data: bool = True
    force_trading_mode: bool = False
    playback_mode: bool = False
    playback_speed: float = 10.0


SNAPSHOT_CONFIG_KEY = "realtime_data_fetcher_snapshot"


class RealtimeDataFetcher:
    """
    实盘数据获取器 - 热点系统内置组件

    行为：
    - 只在交易时间运行（非交易时间完全停止）
    - 订阅交易时钟信号，收到 phase_change 时启停
    - 频率由 FrequencyScheduler 控制（HIGH=5s, MEDIUM=10s, LOW=60s）
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
        hotspot_system,
        config: Optional[FetchConfig] = None
    ):
        self.hotspot_system = hotspot_system
        if hasattr(hotspot_system, 'hotspot_system'):
            self._hotspot_system_inner = hotspot_system.hotspot_system  # MarketHotspotSystem
        else:
            self._hotspot_system_inner = hotspot_system  # MarketHotspotSystem
        self.config = config or FetchConfig()

        self._running = False
        self._fetch_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._last_high_fetch = 0.0
        self._cn_last_medium_fetch = 0.0
        self._cn_last_low_fetch = 0.0
        self._us_last_medium_fetch = 0.0
        self._us_last_low_fetch = 0.0
        self._us_last_fetch = 0.0
        self._us_fetching = False

        self._fetch_count = 0
        self._us_fetch_count = 0
        self._error_count = 0
        self._last_error: Optional[str] = None

        self._cn_active: bool = False
        self._cn_last_fetch: float = 0.0
        self._cn_fetching: bool = False
        self._us_active: bool = False
        self._us_last_fetch: float = 0.0
        self._us_fetching: bool = False
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

        # 确保交易时钟已注册并启动
        try:
            from deva.naja.register import ensure_trading_clocks
            ensure_trading_clocks()
        except Exception as e:
            log.warning(f"[RealtimeDataFetcher] 交易时钟初始化失败: {e}")

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

                tc = SR('trading_clock')
                us_tc = SR('us_trading_clock')

                tc.subscribe(self._on_cn_clock_signal)
                us_tc.subscribe(self._on_us_clock_signal)
                log.info("[RealtimeDataFetcher] 已订阅 A股/美股 交易时钟 (使用 subscribe)")

                cn_initial = tc.get_current_signal()
                us_initial = us_tc.get_current_signal()
                log.info(f"[RealtimeDataFetcher] 手动触发初始信号: cn_phase={cn_initial.get('phase')}, us_phase={us_initial.get('phase')}")
                self._on_cn_clock_signal(cn_initial)
                self._on_us_clock_signal(us_initial)
            except Exception as e:
                import traceback
                log.warning(f"[RealtimeDataFetcher] 订阅交易时钟失败: {e}，改用 STREAM.sink")
                TRADING_CLOCK_STREAM.sink(self._on_trading_clock_signal)
                USTRADING_CLOCK_STREAM.sink(self._on_trading_clock_signal)
                # 确保 initial 信号被触发
                try:
                    us_tc = SR('us_trading_clock')
                    us_initial = us_tc.get_current_signal()
                    log.info(f"[RealtimeDataFetcher] 通过 sink 触发初始信号: us_phase={us_initial.get('phase')}")
                    self._on_us_clock_signal(us_initial)
                except Exception as e2:
                    log.warning(f"[RealtimeDataFetcher] 触发初始信号失败: {e2}")
            log.info("[RealtimeDataFetcher] 已启动，等待 A股/美股 交易信号...")

        self._fetch_thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self._fetch_thread.start()

    def _resolve_inner_system(self):
        """从 hotspot_system 中获取内部组件
        
        设置:
        - self.fs: FrequencyScheduler (档位调度器)
        - self.focus_tracker: FocusTracker (焦点追踪器)
        - self.cn_tc: A股交易时钟
        - self.us_tc: 美股交易时钟
        """
        if getattr(self, '_inner_resolved', False):
            return
        
        try:
            # 获取 FrequencyScheduler (档位调度器)
            self.fs = getattr(self._hotspot_system_inner, 'frequency_scheduler', None)
            
            # 获取焦点追踪器
            if hasattr(self._hotspot_system_inner, '_focus_tracker'):
                self.focus_tracker = self._hotspot_system_inner._focus_tracker
            elif hasattr(self._hotspot_system_inner, 'focus_tracker'):
                self.focus_tracker = self._hotspot_system_inner.focus_tracker
            else:
                self.focus_tracker = None
            
            # 获取交易时钟
            try:
                self.cn_tc = SR('trading_clock')
                self.us_tc = SR('us_trading_clock')
            except:
                self.cn_tc = None
                self.us_tc = None
            
            self._inner_resolved = True
        except Exception as e:
            log.warning(f"[RealtimeDataFetcher] _resolve_inner_system 失败: {e}")
            self._inner_resolved = False

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
            log.debug(f"[RealtimeDataFetcher] 调用 _update_us_state: signal_type={signal_type}, phase={phase}")
            self._update_us_state(signal_type, phase)

    def _on_cn_clock_signal(self, signal: Dict[str, Any]):
        """处理A股交易时钟信号（通过 direct subscribe 使用）"""
        from deva.naja.market_hotspot.data.global_market_futures import _DEBUG_MARKET_MODE
        if _DEBUG_MARKET_MODE == 'a_share':
            signal = {'type': 'current_state', 'phase': 'trading', 'market': 'CN'}
        log.debug(f"[RealtimeDataFetcher] 收到A股信号: {signal}")
        self._update_cn_state(signal.get('type'), signal.get('phase'))

    def _on_us_clock_signal(self, signal: Dict[str, Any]):
        """处理美股交易时钟信号（通过 direct subscribe 使用）"""
        from deva.naja.market_hotspot.data.global_market_futures import _DEBUG_MARKET_MODE
        if _DEBUG_MARKET_MODE == 'a_share':
            signal = {'type': 'current_state', 'phase': 'closed', 'market': 'US'}
        signal_type = signal.get('type', 'unknown')
        phase = signal.get('phase', 'unknown')
        market = signal.get('market', 'US')
        timestamp = signal.get('timestamp', time.time())
        log.info(f"[RealtimeDataFetcher] _on_us_clock_signal: type={signal_type}, phase={phase}, timestamp={timestamp}")
        self._update_us_state(signal_type, phase)

    def _update_cn_state(self, signal_type: str, phase: str):
        """更新 A股 状态"""
        old_active = self._cn_active

        if signal_type == 'current_state':
            self._cn_active = phase in ('trading', 'pre_market')
            log.debug(f"[RealtimeDataFetcher] A股 current_state: phase={phase}, active={self._cn_active}")

            if self._cn_active and not self._cn_fetching:
                self._cn_fetching = True
                self._cn_last_fetch = 0
                log.debug(f"[RealtimeDataFetcher] 触发A股数据获取: _cn_active={self._cn_active}")
                self._run_async_in_thread(self._fetch_and_sync_cn())

        elif signal_type == 'phase_change':
            old_phase = phase
            self._cn_active = phase in ('trading', 'pre_market')
            log.debug(f"[RealtimeDataFetcher] A股 phase_change: {old_phase} -> {phase}")

            if self._cn_active and not old_active:
                log.info(f"[RealtimeDataFetcher] A股开盘")
                if not self._cn_fetching:
                    self._cn_fetching = True
                    self._cn_last_fetch = 0
                    self._run_async_in_thread(self._fetch_and_sync_cn())

        self._update_overall_active()

    def _update_us_state(self, signal_type: str, phase: str):
        """更新 美股 状态"""
        old_active = self._us_active
        log.info(f"[RealtimeDataFetcher] _update_us_state: type={signal_type}, phase={phase}, old_active={old_active}")

        if signal_type == 'current_state':
            self._us_active = phase in ('trading', 'pre_market')
            log.debug(f"[RealtimeDataFetcher] 美股 current_state: phase={phase}, active={self._us_active}")

            if self._us_active and not self._us_fetching:
                self._us_fetching = True
                self._us_last_fetch = 0
                log.debug(f"[RealtimeDataFetcher] 触发美股数据获取: _us_active={self._us_active}")
                self._run_async_in_thread(self._fetch_and_sync_us())

        elif signal_type == 'phase_change':
            old_phase = phase
            self._us_active = phase in ('trading', 'pre_market')
            log.debug(f"[RealtimeDataFetcher] 美股 phase_change: {old_phase} -> {phase}")

            if self._us_active and not old_active and not self._us_fetching:
                self._us_fetching = True
                self._us_last_fetch = 0
                log.debug(f"[RealtimeDataFetcher] 美股开盘，开始获取数据")
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

    async def _fetch_and_sync_cn(self):
        """获取A股全量数据并同步到热点系统"""
        log.debug(f"[RealtimeDataFetcher] _fetch_and_sync_cn 开始, _cn_active={self._cn_active}")
        try:
            # 使用 _fetch_sina_sync 获取全量A股数据
            cn_df = _fetch_sina_sync(force_trading=False)
            log.debug(f"[RealtimeDataFetcher] _fetch_sina_sync 返回: df={type(cn_df)}, len={len(cn_df) if cn_df is not None else 'N/A'}")

            if cn_df is not None and len(cn_df) > 0:
                # 过滤噪音
                cn_df = self._apply_noise_filter_at_source(cn_df)
                log.debug(f"[RealtimeDataFetcher] A股全量数据: 原始{len(_fetch_sina_sync(None)) if _fetch_sina_sync(None) is not None else 0} -> 过滤后{len(cn_df)}")

                # 同步到热点系统
                self._process_cn_hotspot(cn_df)

                try:
                    from deva.naja.market_hotspot.integration import process_data_with_hotspots
                    hotspot_system = SR('hotspot_system')
                    if hotspot_system is not None:
                        cn_state = getattr(hotspot_system, 'global_state', {}) or {}
                    else:
                        cn_state = {}
                    context = {
                        'market': 'CN',
                        'timestamp': time.time(),
                        'global_hotspot': cn_state.get('global_hotspot', 0.5),
                        'activity': cn_state.get('activity', 0.5),
                        'block_weights': cn_state.get('block_hotspot', {}),
                        'symbol_weights': cn_state.get('symbol_weights', {}),
                    }
                    process_data_with_hotspots(cn_df, context)
                except Exception as e:
                    log.warning(f"[RealtimeDataFetcher] A股策略处理失败: {e}")

        except Exception as e:
            log.error(f"[RealtimeDataFetcher] 获取A股数据异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._cn_fetching = False

    def _process_cn_hotspot(self, df: pd.DataFrame):
        """处理A股数据到热点系统"""
        try:
            if df is None or len(df) == 0:
                return

            hotspot_system = SR('hotspot_system')
            if hotspot_system is None:
                return

            # 准备数据
            if 'code' not in df.columns and df.index is not None:
                df = df.copy()
                df['code'] = df.index

            # 注册新符号到热点系统
            new_symbols = 0
            for _, row in df.iterrows():
                symbol = str(row.get('code', ''))
                name = row.get('name', symbol)
                if symbol and len(symbol) >= 6:  # A股代码至少6位
                    try:
                        hotspot_system.register_symbol(symbol, ['A股'])
                        new_symbols += 1
                    except Exception:
                        pass

            if new_symbols > 0:
                log.info(f"[RealtimeDataFetcher] A股注册新符号: {new_symbols} 只")

            # 处理数据
            hotspot_system.process_data(df)

        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] _process_cn_hotspot 失败: {e}")

    async def _fetch_and_sync_us(self):
        """获取美股数据并同步到热点系统"""
        log.info(f"[RealtimeDataFetcher] _fetch_and_sync_us 开始执行")
        try:
            log.info(f"[RealtimeDataFetcher] 调用 _fetch_us_stocks...")
            us_data = await self._fetch_us_stocks()
            log.info(f"[RealtimeDataFetcher] _fetch_us_stocks 返回: {len(us_data) if us_data else 0} 只")
            if us_data:
                self._sync_us_prices_to_portfolio(us_data)
                us_df = self._convert_us_to_dataframe(us_data)
                log.debug(f"[RealtimeDataFetcher] _convert_us_to_dataframe 返回: {us_df}, 类型: {type(us_df)}, 长度: {len(us_df) if us_df is not None else 'N/A'}")
                if us_df is not None and len(us_df) > 0:
                    log.debug(f"[RealtimeDataFetcher] 调用 process_data (US)")
                    self._hotspot_system_inner.process_data(us_df, market='US')
                    log.debug(f"[RealtimeDataFetcher] process_data (US) 完成")
                    try:
                        from deva.naja.market_hotspot.integration import process_data_with_hotspots
                        hotspot_system = SR('hotspot_system')
                        if hotspot_system is not None:
                            us_state = getattr(hotspot_system, 'global_state', {}) or {}
                        else:
                            us_state = {}
                        context = {
                            'market': 'US',
                            'timestamp': time.time(),
                            'global_hotspot': us_state.get('global_hotspot', 0.5),
                            'activity': us_state.get('activity', 0.5),
                            'block_weights': us_state.get('block_hotspot', {}),
                            'symbol_weights': us_state.get('symbol_weights', {}),
                        }
                        process_data_with_hotspots(us_df, context)
                    except Exception as e:
                        log.warning(f"[RealtimeDataFetcher] US 策略处理失败: {e}")

            indices_data = await self._fetch_indices()
            if indices_data:
                self._sync_indices_to_hotspot_system(indices_data)

        except Exception as e:
            log.error(f"[RealtimeDataFetcher] 获取美股数据异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._us_fetching = False

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
        self._cn_last_medium_fetch = time.time()
        self._cn_last_low_fetch = time.time()
        self._us_last_medium_fetch = time.time()
        self._us_last_low_fetch = time.time()

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
        """一次tick - 根据活跃市场分别处理"""
        log.debug(f"[RealtimeDataFetcher] _tick: _is_active={self._is_active}, _us_active={self._us_active}, _cn_active={self._cn_active}")

        self._inner_resolved = False
        self._resolve_inner_system()

        # 根据活跃市场分别处理
        if self._us_active:
            self._tick_market(current_time, 'US')
        if self._cn_active:
            self._tick_market(current_time, 'CN')
        if not self._us_active and not self._cn_active:
            log.debug(f"[RealtimeDataFetcher] 两个市场都不活跃，跳过")

    def _tick_market(self, current_time: float, market: str):
        """处理单个市场的tick"""
        log.debug(f"[RealtimeDataFetcher] _tick_market: market={market}")

        # 获取对应市场的 context
        if market == 'US':
            ctx = self._get_market_context('US')
            fetching_flag = '_us_fetching'
            last_fetch_var = '_us_last_fetch'
            medium_fetch_var = '_us_last_medium_fetch'
            low_fetch_var = '_us_last_low_fetch'
        else:
            ctx = self._get_market_context('CN')
            fetching_flag = '_cn_fetching'
            last_fetch_var = '_cn_last_fetch'
            medium_fetch_var = '_cn_last_medium_fetch'
            low_fetch_var = '_cn_last_low_fetch'

        if ctx is None:
            log.warning(f"[RealtimeDataFetcher] [{market}] context 未初始化，跳过")
            return

        fs = ctx.frequency_scheduler

        high_symbols = []
        medium_symbols = []
        low_symbols = []

        if fs:
            for symbol, idx in fs._symbol_to_idx.items():
                level = fs.get_symbol_level(symbol)
                if level.value == 2:  # HIGH
                    high_symbols.append(symbol)
                elif level.value == 1:  # MEDIUM
                    medium_symbols.append(symbol)
                else:  # LOW
                    low_symbols.append(symbol)

        log.debug(f"[RealtimeDataFetcher] [{market}] 档位: high={len(high_symbols)}, medium={len(medium_symbols)}, low={len(low_symbols)}")

        # 获取全量 symbols 用于首次获取
        if not high_symbols and not medium_symbols and not low_symbols:
            log.info(f"[RealtimeDataFetcher] [{market}] 无分级数据，触发全量获取")
            if self.config.force_trading_mode:
                self._fetch_and_process_market([], "HIGH", market)
            if getattr(self, fetching_flag, False):
                return
            log.info(f"[RealtimeDataFetcher] [{market}] 触发全量获取")
            setattr(self, fetching_flag, True)
            if market == 'US':
                self._run_async_in_thread(self._fetch_and_sync_us())
            else:
                self._run_async_in_thread(self._fetch_and_sync_cn())
            return

        speed = self.config.playback_speed if self.config.playback_mode else 1.0
        high_interval = self.config.base_high_interval / speed
        medium_interval = self.config.base_medium_interval / speed
        low_interval = self.config.base_low_interval / speed

        # 检查是否需要触发首次获取
        last_fetch = getattr(self, last_fetch_var, 0)
        if last_fetch == 0 and not getattr(self, fetching_flag, False):
            log.info(f"[RealtimeDataFetcher] [{market}] 首次获取触发")
            setattr(self, fetching_flag, True)
            setattr(self, last_fetch_var, current_time)
            if market == 'US':
                self._run_async_in_thread(self._fetch_and_sync_us())
            else:
                self._run_async_in_thread(self._fetch_and_sync_cn())
            return

        # 检查周期获取
        if getattr(self, fetching_flag, False):
            log.debug(f"[RealtimeDataFetcher] [{market}] 正在获取中，跳过")
            return

        if current_time - last_fetch >= high_interval and high_symbols:
            self._fetch_and_process_market(high_symbols, "HIGH", market)
            setattr(self, last_fetch_var, current_time)

        if current_time - getattr(self, medium_fetch_var, 0) >= medium_interval and medium_symbols:
            self._fetch_and_process_market(medium_symbols, "MEDIUM", market)
            setattr(self, medium_fetch_var, current_time)

        if current_time - getattr(self, low_fetch_var, 0) >= low_interval and low_symbols:
            self._fetch_and_process_market(low_symbols, "LOW", market)
            setattr(self, low_fetch_var, current_time)

    def _get_market_context(self, market: str):
        """获取市场对应的 context"""
        try:
            hotspot_system = SR('hotspot_system')
            if hotspot_system:
                return hotspot_system._get_context(market)
        except Exception:
            pass
        return None

    def _fetch_and_process(self, symbols: List[str], level: str):
        """获取并处理数据"""
        try:
            log.debug(f"[RealtimeDataFetcher] _fetch_and_process: level={level}, symbols={len(symbols)}")
            data = self._fetch_realtime_data(symbols)
            log.debug(f"[RealtimeDataFetcher] _fetch_realtime_data 返回: data={type(data)}, len={len(data) if data is not None else 'None'}")

            if data is not None and len(data) > 0:
                log.debug(f"[RealtimeDataFetcher] 调用 hotspot_system.process_data, data行数={len(data)}, columns={list(data.columns)}")
                self._hotspot_system_inner.process_data(data)
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

    def _fetch_and_process_market(self, symbols: List[str], level: str, market: str):
        """获取并处理指定市场的数据"""
        try:
            log.debug(f"[RealtimeDataFetcher] [{market}] _fetch_and_process: level={level}, symbols={len(symbols)}")

            if market == 'US':
                # 美股使用 _fetch_us_stocks（如需分档，先拉取再过滤）
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    us_data = loop.run_until_complete(self._fetch_us_stocks(symbols if symbols else None))
                    if us_data:
                        us_df = self._convert_us_to_dataframe(us_data)
                        if us_df is not None and len(us_df) > 0:
                            if symbols:
                                symbols_str = str(symbols)
                                if 'US_' not in symbols_str and 'hf_' not in symbols_str:
                                    wanted = set(symbols)
                                    us_df = us_df[us_df.index.astype(str).isin(wanted)]
                            if not us_df.empty:
                                self._hotspot_system_inner.process_data(us_df, market='US')
                                self._write_to_market_data_bus(us_df)
                                self._fetch_count += 1
                                self._us_fetch_count += 1
                                if level == "LOW" and self._save_snapshot_enabled:
                                    self._save_market_snapshot(us_df)
                                log.debug(f"[RealtimeDataFetcher] [{market}] 获取 {len(us_df)} 条数据，累计 {self._fetch_count} 批")
                    return
                finally:
                    loop.close()

            # A股使用现有逻辑
            data = self._fetch_realtime_data(symbols)
            log.debug(f"[RealtimeDataFetcher] [{market}] _fetch_realtime_data 返回: data={type(data)}, len={len(data) if data is not None else 'None'}")

            if data is not None and len(data) > 0:
                log.debug(f"[RealtimeDataFetcher] [{market}] 调用 hotspot_system.process_data, data行数={len(data)}")
                self._hotspot_system_inner.process_data(data, market=market)
                self._fetch_count += 1

                self._write_to_market_data_bus(data)

                if level == "LOW" and self._save_snapshot_enabled:
                    self._save_market_snapshot(data)

                log.info(f"[RealtimeDataFetcher] [{market}] [{level}] 获取 {len(data)} 条数据，累计 {self._fetch_count} 批")
            else:
                log.debug(f"[RealtimeDataFetcher] [{market}] 无数据返回")

        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            log.error(f"[RealtimeDataFetcher] [{market}] 获取 {level} 数据失败: {e}")

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
            import os as _os
            print(f"[RT_FETCHER] _fetch_realtime_data PID={_os.getpid()}, symbols={symbols[:5] if symbols else 'empty'}", flush=True)
            df = _fetch_sina_sync(force_trading=self.config.force_trading_mode)
            print(f"[RT_FETCHER] _fetch_sina_sync 返回: df={type(df)}, empty={df.empty if df is not None else 'N/A'}", flush=True)

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
            from deva.naja.market_hotspot.processing.noise_filter import get_noise_filter
            from deva.naja.market_hotspot.processing.block_noise_detector import BlockNoiseDetector

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
                log.debug(f"[RealtimeDataFetcher] 源头噪音过滤: 原始{original_count}条 -> 过滤后{len(filtered_df)}条 (过滤{original_count - len(filtered_df)}条, 过滤率{(original_count - len(filtered_df))/original_count*100:.1f}%)")

            return filtered_df

        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 源头噪音过滤失败: {e}")
            return df

    async def _fetch_us_stocks(self, symbols: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """获取股票数据（根据市场自动切换）

        根据当前市场状态自动切换：
        - 美股盘：从 StockRegistry 获取美股
        - A股盘：从 StockRegistry 获取A股

        Returns:
            {
                'code': {'price': float, 'prev_close': float, 'change': float, 'change_pct': float, 'volume': int},
                ...
            }
        """
        try:
            from deva.naja.market_hotspot.data.global_market_futures import (
                GlobalMarketAPI, _get_current_market, get_current_stock_codes
            )

            market = _get_current_market()
            stock_codes = get_current_stock_codes()

            if symbols:
                requested = {str(s) for s in symbols if s}
                symbols_str = str(requested)
                if 'US_' in symbols_str or 'hf_' in symbols_str:
                    symbols = None
                    log.debug(f"[RealtimeDataFetcher] symbols are futures indices, fetching all stocks")
                else:
                    stock_codes = {code: name for code, name in stock_codes.items() if code in requested}

            log.debug(f"[RealtimeDataFetcher] 当前市场: {market}, 股票池: {len(stock_codes)} 只")

            if not stock_codes:
                log.debug(f"[RealtimeDataFetcher] 当前市场无股票池，返回空")
                return {}

            api = GlobalMarketAPI()
            data = await api.fetch(list(stock_codes.keys()))

            result = {}
            for sina_code, market_data in data.items():
                result[sina_code] = {
                    'price': market_data.current,
                    'prev_close': market_data.prev_close,
                    'change': market_data.change,
                    'change_pct': market_data.change_pct,
                    'volume': market_data.volume,
                    'high': market_data.high,
                    'low': market_data.low,
                    'name': stock_codes.get(sina_code) or market_data.name,
                    'market': market,
                }

            if result:
                log.debug(f"[RealtimeDataFetcher] 获取 {len(result)} 只股票数据 (市场={market})")
            return result

        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 获取股票数据失败: {e}")
            return None

    async def _fetch_indices(self) -> Optional[Dict[str, Any]]:
        """获取A股指数和美股期货指数

        返回格式：
        {
            'CN': {'SH': {price, change_pct}, 'HS300': {...}, 'CHINEXT': {...}},
            'US': {'NQ': {price, change_pct}, 'ES': {...}, 'YM': {...}}
        }
        """
        try:
            import urllib.request
            import json

            result = {'CN': {}, 'US': {}}

            cn_url = "https://hq.sinajs.cn/list=sh000001,s_sh000300,sz399006"
            us_url = "https://hq.sinajs.cn/list=hf_NQ,hf_ES,hf_YM"
            headers = {
                "Referer": "https://finance.sina.com.cn",
                "User-Agent": "Mozilla/5.0"
            }

            for url, market in [(cn_url, 'CN'), (us_url, 'US')]:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = resp.read().decode('gbk', errors='replace')

                for line in data.split('\n'):
                    if not line or '="' not in line:
                        continue

                    parts = line.split('"')
                    if len(parts) < 2:
                        continue

                    raw_code = parts[0].split('_')[-1]
                    fields = parts[1].split(',')

                    if market == 'CN':
                        if raw_code == 'sh000001' and len(fields) > 2:
                            try:
                                cur, prev = float(fields[1]), float(fields[2])
                                pct = round((cur - prev) / prev * 100, 2) if prev else 0
                                result['CN']['SH'] = {'price': cur, 'change_pct': pct}
                            except: pass
                        elif raw_code == 's_sh000300' and len(fields) > 3:
                            try:
                                result['CN']['HS300'] = {'price': float(fields[1]), 'change_pct': float(fields[3])}
                            except: pass
                        elif raw_code == 'sz399006' and len(fields) > 2:
                            try:
                                cur, prev = float(fields[1]), float(fields[2])
                                pct = round((cur - prev) / prev * 100, 2) if prev else 0
                                result['CN']['CHINEXT'] = {'price': cur, 'change_pct': pct}
                            except: pass
                    elif market == 'US':
                        if raw_code == 'hf_NQ' and len(fields) > 9:
                            try:
                                cur, prev = float(fields[0]), float(fields[8])
                                pct = round((cur - prev) / prev * 100, 2) if prev else 0
                                result['US']['NQ'] = {'price': cur, 'change_pct': pct}
                            except: pass
                        elif raw_code == 'hf_ES' and len(fields) > 9:
                            try:
                                cur, prev = float(fields[0]), float(fields[8])
                                pct = round((cur - prev) / prev * 100, 2) if prev else 0
                                result['US']['ES'] = {'price': cur, 'change_pct': pct}
                            except: pass
                        elif raw_code == 'hf_YM' and len(fields) > 9:
                            try:
                                cur, prev = float(fields[0]), float(fields[8])
                                pct = round((cur - prev) / prev * 100, 2) if prev else 0
                                result['US']['YM'] = {'price': cur, 'change_pct': pct}
                            except: pass

            log.debug(f"[RealtimeDataFetcher] 获取指数数据: CN={result['CN']}, US={result['US']}")
            return result

        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 获取指数数据失败: {e}")
            return None

    def _sync_indices_to_hotspot_system(self, indices_data: Dict[str, Any]):
        """同步指数数据到热点系统缓存"""
        if not indices_data:
            return

        try:
            if self.hotspot_system:
                cn_data = indices_data.get('CN', {})
                us_data = indices_data.get('US', {})

                if cn_data:
                    self.hotspot_system._cn_index_cache = {
                        'SH': cn_data.get('SH', {}).get('change_pct'),
                        'HS300': cn_data.get('HS300', {}).get('change_pct'),
                        'CHINEXT': cn_data.get('CHINEXT', {}).get('change_pct'),
                    }
                    self.hotspot_system._cn_index_cache_time = time.time()

                if us_data:
                    self.hotspot_system._us_futures_cache = {
                        'NQ': us_data.get('NQ', {}).get('change_pct'),
                        'ES': us_data.get('ES', {}).get('change_pct'),
                        'YM': us_data.get('YM', {}).get('change_pct'),
                    }
                    self.hotspot_system._us_futures_cache_time = time.time()

                log.debug(f"[RealtimeDataFetcher] 同步指数到缓存: CN={self.hotspot_system._cn_index_cache}, US={self.hotspot_system._us_futures_cache}")
        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 同步指数到缓存失败: {e}")

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
        """将美股数据转换为热点系统可处理的DataFrame格式

        字段映射：
        - code: 股票代码（如 nvda, aapl）
        - name: 股票名称
        - now: 当前价 (price)
        - close: 昨收价 (prev_close)
        - p_change: 涨跌幅 (change_pct)
        - volume: 成交量
        - high: 最高价
        - low: 最低价
        - block: 主要题材 ID（从US_STOCK_BLOCKS映射）
        - blocks: 题材关键词列表（完整叙事标签）
        - narrative: 核心叙事标签
        - market: 市场标识 'US'
        """
        if not us_data:
            return None

        try:
            from deva.naja.bandit.stock_block_map import US_STOCK_BLOCKS

            records = []
            for symbol, info in us_data.items():
                stock_info = US_STOCK_BLOCKS.get(symbol, {})
                blocks = stock_info.get("blocks", [])
                block = stock_info.get("industry_code", "other")
                narrative = stock_info.get("narrative", blocks[0] if blocks else block)
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
                    'block': block,
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

    def _process_us_hotspot(self, us_df: pd.DataFrame):
        """处理美股热点数据

        将美股数据送入热点系统进行计算：
        1. 计算美股全局热点
        2. 计算美股题材热点
        3. 更新美股个股权重
        """
        if us_df is None or us_df.empty:
            log.debug(f"[RealtimeDataFetcher] _process_us_hotspot: us_df 为空或 None")
            return

        try:
            hotspot_system = self._hotspot_system_inner
            if hotspot_system is None:
                log.debug(f"[RealtimeDataFetcher] hotspot_system 为 None，跳过美股热点处理")
                return

            if not hasattr(hotspot_system, '_initialized') or not hotspot_system._initialized:
                log.debug(f"[RealtimeDataFetcher] hotspot_system 未初始化 (_initialized={getattr(hotspot_system, '_initialized', 'N/A')})，跳过美股热点处理")
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

            block_ids = us_df['block'].values if 'block' in us_df.columns else np.array(['其他'] * len(us_df))

            timestamp = time.time()

            has_method = hasattr(hotspot_system, 'process_snapshot')
            log.debug(f"[RealtimeDataFetcher] has process_snapshot: {has_method}")

            if has_method:
                log.info(f"[RealtimeDataFetcher] 开始处理美股热点: {len(symbols)} 只股票, symbols={list(symbols)[:5]}")
                result = hotspot_system.process_snapshot(
                    symbols=symbols,
                    returns=returns,
                    volumes=volumes,
                    prices=prices,
                    block_ids=block_ids,
                    timestamp=timestamp,
                    market='US',
                )
                log.info(f"[RealtimeDataFetcher] 美股热点处理完成: global_hotspot={result.get('global_hotspot', 'N/A')}, block_count={len(result.get('block_hotspot', {}))}")

                # 事件已通过 MarketHotspotSystem._publish_hotspot_event() 自动发布
                # AttentionOS 会通过事件总线订阅并处理
            else:
                log.debug(f"[RealtimeDataFetcher] hotspot_system 不支持 process_us_snapshot 方法")
                log.debug(f"[RealtimeDataFetcher] hotspot_system 方法列表: {[m for m in dir(self.hotspot_system) if not m.startswith('_')]}")

        except Exception as e:
            log.debug(f"[RealtimeDataFetcher] 处理美股热点失败: {e}")

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
            self._resolve_inner_system()

            from deva.naja.market_hotspot.data.global_market_futures import _DEBUG_MARKET_MODE
            log.warning(f"[RealtimeDataFetcher] get_stats _DEBUG_MARKET_MODE={_DEBUG_MARKET_MODE}")

            cn_signal = self.cn_tc.get_current_signal()
            us_signal = self.us_tc.get_current_signal()

            if _DEBUG_MARKET_MODE == 'a_share':
                cn_signal = {'type': 'current_state', 'phase': 'trading', 'market': 'CN', 'next_phase': 'closed'}
                us_signal = {'type': 'current_state', 'phase': 'closed', 'market': 'US'}
                log.warning("[RealtimeDataFetcher] DEBUG MODE: A股强制交易中")

            cn_phase = cn_signal.get('phase', 'closed')
            us_phase = us_signal.get('phase', 'closed')
            log.debug(f"[RealtimeDataFetcher] get_stats: cn_phase={cn_phase}, us_phase={us_phase}")

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

        # 计算A股档位统计
        high_count = 0
        medium_count = 0
        low_count = 0
        try:
            fs = self._hotspot_system_inner.frequency_scheduler
            if fs:
                for symbol, idx in fs._symbol_to_idx.items():
                    if symbol.startswith('CN_'):
                        level = fs.get_symbol_level(symbol)
                        if level.value == 2:
                            high_count += 1
                        elif level.value == 1:
                            medium_count += 1
                        else:
                            low_count += 1
                log.debug(f"[RealtimeDataFetcher] get_stats: fs._symbol_to_idx={len(fs._symbol_to_idx)}, CN[high={high_count}, med={medium_count}, low={low_count}]")
        except Exception as e:
            log.warning(f"[RealtimeDataFetcher] get_stats 计算A股档位失败: {e}")

        # 计算美股档位统计（基于 symbol_weights 的权重）
        us_high_count = 0
        us_medium_count = 0
        us_low_count = 0
        try:
            us_state = self._hotspot_system_inner.get_us_hotspot_state()
            symbol_weights = us_state.get('symbol_weights', {})
            futures = us_state.get('futures_indices', {})
            us_stock_count = len(self._us_last_symbols) if hasattr(self, '_us_last_symbols') else 0
            log.debug(f"[RealtimeDataFetcher] get_stats: symbol_weights={len(symbol_weights)}, futures={len(futures) if futures else 0}, us_stock_count={us_stock_count}")
            for weight in symbol_weights.values():
                if weight >= 2.5:
                    us_high_count += 1
                elif weight >= 1.0:
                    us_medium_count += 1
                else:
                    us_low_count += 1
            if futures:
                us_high_count += len(futures)  # 纳指、标普、道指
        except Exception as e:
            log.warning(f"[RealtimeDataFetcher] get_stats 计算美股档位失败: {e}")

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
            'high_count': high_count,
            'medium_count': medium_count,
            'low_count': low_count,
            'us_high_count': us_high_count,
            'us_medium_count': us_medium_count,
            'us_low_count': us_low_count,
            'us_stock_count': len(self._us_last_symbols) if hasattr(self, '_us_last_symbols') else 0,
            'us_fetch_count': self._us_fetch_count,
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

    def __init__(self, hotspot_system, config: Optional[FetchConfig] = None):
        self.hotspot_system = hotspot_system
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
    from deva.naja.register import SR
    return SR('realtime_data_fetcher')
