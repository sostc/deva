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

from deva.naja.radar.trading_clock import (
    TRADING_CLOCK_STREAM,
    is_trading_time as is_trading_time_clock,
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
    from deva.naja.common.tradetime import is_tradedate, is_tradetime

    now = datetime.now()
    if not force_trading and (not is_tradedate(now) or not is_tradetime(now)):
        log.debug(f"[_fetch_sina_sync] 非交易时间，跳过 (force={force_trading})")
        return None

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

        self._fetch_count = 0
        self._error_count = 0
        self._last_error: Optional[str] = None

        self._symbol_levels: Dict[str, str] = {}

        self._current_phase: str = 'closed'
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

        log.debug(f"[RealtimeDataFetcher] 收到交易时钟信号: type={signal_type}, phase={phase}")

        if signal_type == 'current_state':
            self._current_phase = phase
            log.debug(f"[RealtimeDataFetcher] current_state: phase={phase}, force_trading_mode={self.config.force_trading_mode}")
            if phase == 'trading' or phase == 'pre_market' or self.config.force_trading_mode:
                self._activate()
            else:
                self._deactivate()

        elif signal_type == 'phase_change':
            old_phase = signal.get('previous_phase', 'unknown')
            new_phase = phase
            self._current_phase = new_phase
            log.debug(f"[RealtimeDataFetcher] phase_change: {old_phase} -> {new_phase}")

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
        """
        try:
            df = _fetch_sina_sync(force_trading=self.config.force_trading_mode)

            if df is None or df.empty:
                return None

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
                    "p_change": row.get("p_change", 0),
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
            is_trading = is_trading_time_clock()
        except Exception:
            is_trading = False
        is_force_mode = self.config.force_trading_mode

        return {
            'running': self._running,
            'active': self._is_active,
            'fetch_count': self._fetch_count,
            'error_count': self._error_count,
            'last_error': self._last_error,
            'current_phase': self._current_phase,
            'is_trading': is_trading,
            'is_force_trading_mode': is_force_mode,
            'high_count': len([s for s, l in self._symbol_levels.items() if l == 'HIGH']),
            'medium_count': len([s for s, l in self._symbol_levels.items() if l == 'MEDIUM']),
            'low_count': len([s for s, l in self._symbol_levels.items() if l == 'LOW']),
            'save_snapshot_enabled': self._save_snapshot_enabled,
            'snapshot_save_count': self._snapshot_save_count,
            'last_snapshot_save_time': self._last_snapshot_save_time,
            'data_fetcher_mode': self._current_phase,
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
    return _fetcher_instance


def set_data_fetcher(fetcher: RealtimeDataFetcher):
    """设置全局 RealtimeDataFetcher 实例"""
    global _fetcher_instance
    _fetcher_instance = fetcher
