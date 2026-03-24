"""Price Monitor - 价格监控服务

持续监控跟踪标的价格变化，与 AttentionTracker 配合形成反馈。

核心功能:
- 从市场 tick 数据源获取价格
- 计算收益/变化率
- 触发价格更新回调
- 自动管理跟踪列表
- 与注意力系统 FrequencyScheduler 对接实现动态频率调度

数据源:
- 优先使用市场 tick 数据源 (MarketDataObserver 机制)
- 备用从 NB("naja_realtime_quotes") 缓存获取

频率调度:
- 通过 FrequencyScheduler 实现个股级别的动态更新频率
- HIGH: 高注意力标的，每1秒更新
- MEDIUM: 中注意力标的，每10秒更新
- LOW: 低注意力标的，每60秒更新
- AdaptiveFrequencyController 根据 global_attention 动态调整
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, TYPE_CHECKING
from collections import deque

if TYPE_CHECKING:
    from .tracker import AttentionTracker, TrackedAttention, PriceUpdateSignal

log = logging.getLogger(__name__)

PRICE_MONITOR_CONFIG_TABLE = "naja_price_monitor_config"


@dataclass
class MonitoredItem:
    """监控项"""
    symbol: str
    entry_price: float
    entry_time: float
    last_update_time: float
    current_price: float
    highest_price: float
    lowest_price: float


@dataclass
class PerformanceMetrics:
    """性能指标"""
    symbol: str
    current_price: float
    entry_price: float
    return_pct: float
    holding_seconds: float
    max_favorable_move: float
    max_adverse_move: float
    price_velocity: float
    volatility: float

    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'current_price': self.current_price,
            'entry_price': self.entry_price,
            'return_pct': self.return_pct,
            'holding_seconds': self.holding_seconds,
            'max_favorable_move': self.max_favorable_move,
            'max_adverse_move': self.max_adverse_move,
            'price_velocity': self.price_velocity,
            'volatility': self.volatility,
        }


class PriceMonitor:
    """
    价格监控服务

    职责:
    - 从市场 tick 数据源获取跟踪标的价格
    - 计算实时性能指标
    - 触发价格更新回调
    - 与 AttentionTracker 集成
    - 与 FrequencyScheduler 集成实现动态频率调度

    数据源优先级:
    1. 市场 tick 数据源 (运行时订阅流)
    2. NB("naja_realtime_quotes") 缓存 (备用)

    频率调度:
    - 通过 FrequencyScheduler 实现个股级别的动态更新频率
    - HIGH: 高注意力标的，每1秒更新
    - MEDIUM: 中注意力标的，每10秒更新
    - LOW: 低注意力标的，每60秒更新
    """

    DEFAULT_TRADING_DATASOURCE = '189e3042171a'

    def __init__(
        self,
        update_interval: float = 60.0,
        price_fetch_timeout: float = 10.0,
        frequency_scheduler=None,
        adaptive_frequency_controller=None,
    ):
        self._update_interval = update_interval
        self._price_fetch_timeout = price_fetch_timeout
        self._frequency_scheduler = frequency_scheduler
        self._adaptive_freq_controller = adaptive_frequency_controller

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._tracked: Dict[str, MonitoredItem] = {}
        self._price_history: Dict[str, deque] = {}
        self._max_history_len = 100

        self._callbacks: List[Callable[[List[PerformanceMetrics]], None]] = []

        self._last_fetch_time = 0.0
        self._fetch_errors = 0
        self._max_fetch_errors = 5

        self._stream_subscription = None
        self._current_datasource = None

        self._load_config()

    def _load_config(self):
        """加载配置"""
        try:
            from deva import NB
            db = NB(PRICE_MONITOR_CONFIG_TABLE)
            config = db.get("monitor_config")
            if config:
                self._update_interval = config.get("update_interval", 60.0)
                self._max_fetch_errors = config.get("max_fetch_errors", 5)
        except Exception:
            pass

    def _save_config(self):
        """保存配置"""
        try:
            from deva import NB
            db = NB(PRICE_MONITOR_CONFIG_TABLE)
            db["monitor_config"] = {
                "update_interval": self._update_interval,
                "max_fetch_errors": self._max_fetch_errors,
            }
        except Exception:
            pass

    def add_tracked(
        self,
        symbol: str,
        entry_price: float,
        entry_time: Optional[float] = None,
    ):
        """添加监控标的"""
        if entry_time is None:
            entry_time = time.time()

        if symbol not in self._price_history:
            self._price_history[symbol] = deque(maxlen=self._max_history_len)

        if symbol not in self._tracked:
            self._tracked[symbol] = MonitoredItem(
                symbol=symbol,
                entry_price=entry_price,
                entry_time=entry_time,
                last_update_time=entry_time,
                current_price=entry_price,
                highest_price=entry_price,
                lowest_price=entry_price,
            )
            log.debug(f"添加监控: {symbol} 入场价={entry_price}")

    def remove_tracked(self, symbol: str):
        """移除监控标的"""
        if symbol in self._tracked:
            del self._tracked[symbol]
            log.debug(f"移除监控: {symbol}")

    def _get_active_datasource_id(self) -> str:
        """获取当前活跃的数据源ID"""
        try:
            from deva.naja.strategy import get_strategy_manager
            mgr = get_strategy_manager()
            experiment_info = mgr.get_experiment_info()
            if experiment_info.get("active", False):
                datasource_id = experiment_info.get("datasource_id")
                if datasource_id:
                    return datasource_id
        except Exception:
            pass
        return self.DEFAULT_TRADING_DATASOURCE

    def _get_datasource(self, datasource_id: str = None):
        """获取数据源对象"""
        if datasource_id is None:
            datasource_id = self._get_active_datasource_id()

        try:
            from deva.naja.datasource import get_datasource_manager
            mgr = get_datasource_manager()
            mgr.load_from_db()
            return mgr.get(datasource_id)
        except Exception as e:
            log.debug(f"[PriceMonitor] 获取数据源失败: {e}")
            return None

    def _is_datasource_running(self, ds) -> bool:
        """检查数据源是否正在运行"""
        if ds is None:
            return False
        if hasattr(ds, 'is_running'):
            return ds.is_running
        if hasattr(ds, '_running'):
            return ds._running
        return False

    def _subscribe_stream(self, ds) -> bool:
        """订阅数据源流"""
        try:
            stream = ds.get_stream()
            if stream:
                self._stream_subscription = stream.sink(self._on_data_received)
                log.debug(f"[PriceMonitor] 已订阅数据源流: {ds.name}")
                return True
        except Exception as e:
            log.debug(f"[PriceMonitor] 订阅流失败: {e}")
        return False

    def _on_data_received(self, data: Any):
        """收到数据源数据时的回调"""
        try:
            import pandas as pd

            if isinstance(data, pd.DataFrame):
                self._process_dataframe(data)
            elif isinstance(data, list):
                for item in data:
                    self._process_single_item(item)
            elif isinstance(data, dict):
                self._process_single_item(data)
        except Exception as e:
            log.debug(f"[PriceMonitor] 处理数据失败: {e}")

    def _process_dataframe(self, df):
        """处理 DataFrame 格式的数据"""
        if df is None or df.empty:
            return

        tracked = list(self._tracked.keys())
        signals = []

        for stock_code in tracked:
            try:
                matches = df[df['code'] == stock_code]

                if not matches.empty:
                    row = matches.iloc[0]
                    price = float(row.get('now', row.get('price', row.get('current', 0))))
                    if price > 0:
                        signal = self._update_price(stock_code, price)
                        if signal:
                            signals.append(signal)
            except Exception as e:
                log.debug(f"[PriceMonitor] 处理 {stock_code} 失败: {e}")

        if signals:
            self._notify_callbacks(signals)

    def _process_single_item(self, item: dict):
        """处理单条数据"""
        if not isinstance(item, dict):
            return

        try:
            stock_code = str(item.get('code', item.get('stock_code', '')))
            if stock_code and stock_code in self._tracked:
                price = float(item.get('now', item.get('price', item.get('current', 0))))
                if price > 0:
                    signal = self._update_price(stock_code, price)
                    if signal:
                        self._notify_callbacks([signal])
        except Exception as e:
            log.debug(f"[PriceMonitor] 处理单条数据失败: {e}")

    def _update_price(self, stock_code: str, price: float) -> Optional[PerformanceMetrics]:
        """更新价格并返回性能指标

        如果入场价还未设置（为0），用首次价格作为入场价
        这支持回放模式下信号先于价格数据到达的情况
        """
        if stock_code not in self._tracked:
            return None

        item = self._tracked[stock_code]

        # 如果入场价未设置，用首次价格作为入场价
        if item.entry_price <= 0:
            item.entry_price = price
            item.highest_price = price
            item.lowest_price = price

        item.current_price = price
        item.last_update_time = time.time()

        is_new_high = price > item.highest_price
        is_new_low = price < item.lowest_price

        if is_new_high:
            item.highest_price = price
        if is_new_low:
            item.lowest_price = price

        self._price_history[stock_code].append({
            'price': price,
            'timestamp': time.time(),
        })

        return self._calculate_metrics(stock_code, price)

    def _notify_callbacks(self, signals: List[PerformanceMetrics]):
        """通知所有回调"""
        for callback in self._callbacks:
            try:
                callback(signals)
            except Exception as e:
                log.error(f"[PriceMonitor] 回调失败: {e}")

    def _fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """获取价格

        从市场 tick 数据源获取价格:
        1. 尝试从 NB("naja_realtime_quotes") 缓存获取
        2. 从数据源主动获取

        Returns:
            Dict[symbol, price]
        """
        prices = {}

        if not symbols:
            return prices

        for symbol in symbols:
            price = self._fetch_from_realtime_cache(symbol)
            if price > 0:
                prices[symbol] = price

        return prices

    def _fetch_from_realtime_cache(self, symbol: str) -> float:
        """从实时行情缓存获取价格"""
        try:
            from deva import NB
            db = NB("naja_realtime_quotes")
            quote = db.get(symbol)
            if isinstance(quote, dict):
                price = quote.get('price') or quote.get('now') or quote.get('current')
                if price:
                    return float(price)

            quotes = db.get("*")
            if isinstance(quotes, dict):
                for key, value in quotes.items():
                    if key == symbol and isinstance(value, dict):
                        price = value.get('price') or value.get('now') or value.get('current')
                        if price:
                            return float(price)
        except Exception as e:
            log.debug(f"[PriceMonitor] 从缓存获取 {symbol} 失败: {e}")
        return 0.0

    def _calculate_metrics(self, symbol: str, current_price: float) -> Optional[PerformanceMetrics]:
        """计算性能指标"""
        if symbol not in self._tracked:
            return None

        item = self._tracked[symbol]
        history = list(self._price_history.get(symbol, []))

        holding_seconds = time.time() - item.entry_time

        return_pct = (current_price - item.entry_price) / item.entry_price * 100 if item.entry_price > 0 else 0
        max_favorable = (item.highest_price - item.entry_price) / item.entry_price * 100 if item.entry_price > 0 else 0
        max_adverse = (item.lowest_price - item.entry_price) / item.entry_price * 100 if item.entry_price > 0 else 0

        price_velocity = 0.0
        volatility = 0.0

        if len(history) >= 2:
            prices = [h['price'] for h in history]
            returns = [(prices[i] - prices[i-1]) / prices[i-1] * 100 for i in range(1, len(prices))]
            if returns:
                price_velocity = sum(returns) / len(returns)
                volatility = (max(prices) - min(prices)) / min(prices) * 100 if min(prices) > 0 else 0

        return PerformanceMetrics(
            symbol=symbol,
            current_price=current_price,
            entry_price=item.entry_price,
            return_pct=return_pct,
            holding_seconds=holding_seconds,
            max_favorable_move=max_favorable,
            max_adverse_move=max_adverse,
            price_velocity=price_velocity,
            volatility=volatility,
        )

    def _process_update(self) -> List[PerformanceMetrics]:
        """处理价格更新（使用频率调度）"""
        if not self._tracked:
            return []

        current_time = time.time()
        signals = []

        if self._frequency_scheduler is not None:
            symbols_to_update = []
            for symbol in self._tracked.keys():
                if self._should_update_symbol(symbol, current_time):
                    symbols_to_update.append(symbol)

            if symbols_to_update:
                prices = self._fetch_prices(symbols_to_update)
                for symbol, current_price in prices.items():
                    if symbol in self._tracked:
                        metrics = self._update_price(symbol, current_price)
                        if metrics:
                            signals.append(metrics)
        else:
            symbols = list(self._tracked.keys())
            prices = self._fetch_prices(symbols)

            for symbol, current_price in prices.items():
                if symbol not in self._tracked:
                    continue

                metrics = self._update_price(symbol, current_price)
                if metrics:
                    signals.append(metrics)

        return signals

    def _should_update_symbol(self, symbol: str, current_time: float) -> bool:
        """判断是否应该更新该标的（基于频率调度）"""
        if self._frequency_scheduler is None:
            return True

        try:
            return self._frequency_scheduler.should_fetch(symbol, current_time)
        except Exception:
            return True

    def start(self):
        """启动监控"""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()

        self._connect_to_datasource()

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        self._save_config()
        log.info(f"PriceMonitor 已启动 (更新间隔: {self._update_interval}s)")

    def _connect_to_datasource(self):
        """连接到数据源"""
        ds = self._get_datasource()
        if not ds:
            log.debug(f"[PriceMonitor] 未找到数据源")
            return

        self._current_datasource = ds

        if self._is_datasource_running(ds):
            if self._subscribe_stream(ds):
                log.debug(f"[PriceMonitor] 已订阅数据源流: {ds.name}")
                return

        log.debug(f"[PriceMonitor] 数据源未运行，使用主动获取模式: {ds.name}")

    def stop(self):
        """停止监控"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._stream_subscription:
            try:
                self._stream_subscription.destroy()
            except Exception:
                pass
            self._stream_subscription = None

        if self._thread:
            self._thread.join(timeout=5)

        log.info("PriceMonitor 已停止")

    def _run_loop(self):
        """主循环

        当启用频率调度时，使用1秒基准间隔，让 FrequencyScheduler 决定每只股票是否更新
        """
        base_interval = 1.0 if self._frequency_scheduler is not None else self._update_interval

        while self._running and not self._stop_event.is_set():
            try:
                signals = self._process_update()

                if signals:
                    self._notify_callbacks(signals)
            except Exception as e:
                log.error(f"PriceMonitor 处理错误: {e}")

            self._stop_event.wait(base_interval)

    def register_callback(self, callback: Callable[[List[PerformanceMetrics]], None]):
        """注册更新回调"""
        self._callbacks.append(callback)

    def get_metrics(self, symbol: str) -> Optional[PerformanceMetrics]:
        """获取标的性能指标"""
        if symbol in self._tracked:
            return self._calculate_metrics(symbol, self._tracked[symbol].current_price)
        return None

    def get_all_metrics(self) -> List[PerformanceMetrics]:
        """获取所有性能指标"""
        results = []
        for symbol in self._tracked:
            metrics = self._calculate_metrics(symbol, self._tracked[symbol].current_price)
            if metrics:
                results.append(metrics)
        return results

    def get_status(self) -> dict:
        """获取状态"""
        status = {
            "running": self._running,
            "tracked_count": len(self._tracked),
            "update_interval": self._update_interval,
            "last_fetch_time": self._last_fetch_time,
            "fetch_errors": self._fetch_errors,
            "subscribed": self._stream_subscription is not None,
            "frequency_scheduling_enabled": self._frequency_scheduler is not None,
        }

        if self._frequency_scheduler is not None:
            freq_summary = self._frequency_scheduler.get_schedule_summary()
            status["frequency_summary"] = freq_summary

        return status


_price_monitor: Optional[PriceMonitor] = None
_monitor_lock = threading.Lock()


def get_price_monitor(
    update_interval: float = 60.0,
    frequency_scheduler=None,
    adaptive_frequency_controller=None,
) -> PriceMonitor:
    """获取 PriceMonitor 单例"""
    global _price_monitor
    if _price_monitor is None:
        with _monitor_lock:
            if _price_monitor is None:
                _price_monitor = PriceMonitor(
                    update_interval=update_interval,
                    frequency_scheduler=frequency_scheduler,
                    adaptive_frequency_controller=adaptive_frequency_controller,
                )
    return _price_monitor


def ensure_price_monitor(
    update_interval: float = 60.0,
    frequency_scheduler=None,
    adaptive_frequency_controller=None,
) -> PriceMonitor:
    """确保 PriceMonitor 已初始化"""
    global _price_monitor
    if _price_monitor is None:
        with _monitor_lock:
            if _price_monitor is None:
                _price_monitor = PriceMonitor(
                    update_interval=update_interval,
                    frequency_scheduler=frequency_scheduler,
                    adaptive_frequency_controller=adaptive_frequency_controller,
                )
    if not _price_monitor._running:
        _price_monitor.start()
    return _price_monitor
