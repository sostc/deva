"""Position Monitor - 持仓监控系统

被动接收市场 tick 推送 + 定时主动获取，确保持仓价格必更新。

核心功能:
- 被动接收市场 tick 推送，实时更新持仓价格
- 定时主动获取持仓价格（fallback，确保不断联）
- 计算收益/变化率指标
- 触发价格更新回调给 AttentionTracker

数据源:
- 被动: 市场 tick 数据源 (MarketDataObserver 机制)
- 主动: NB("naja_realtime_quotes") 缓存获取

更新策略:
- 被动优先: 收到 tick 则立即更新
- 主动保底: 定时主动获取，确保所有持仓不断联
- 统一频率: 所有持仓同等对待
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from collections import deque

log = logging.getLogger(__name__)

POSITION_MONITOR_CONFIG_TABLE = "naja_position_monitor_config"


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


class PositionMonitor:
    """
    持仓监控系统

    职责:
    - 被动接收市场 tick 推送，实时更新持仓价格
    - 定时主动获取持仓价格（fallback）
    - 计算实时性能指标
    - 触发价格更新回调

    数据源:
    - 被动: 市场 tick 数据源 (运行时订阅流)
    - 主动: NB("naja_realtime_quotes") 缓存 (备用)

    更新策略:
    - 被动优先: 收到 tick 则立即更新
    - 主动保底: 定时主动获取，确保不断联
    - 统一频率: 所有持仓同等对待
    """

    def __init__(
        self,
        update_interval: float = 10.0,
    ):
        self._update_interval = update_interval

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
            db = NB(POSITION_MONITOR_CONFIG_TABLE)
            config = db.get("monitor_config")
            if config:
                self._update_interval = config.get("update_interval", 10.0)
                self._max_fetch_errors = config.get("max_fetch_errors", 5)
        except Exception:
            pass

    def _save_config(self):
        """保存配置"""
        try:
            from deva import NB
            db = NB(POSITION_MONITOR_CONFIG_TABLE)
            db["monitor_config"] = {
                "update_interval": self._update_interval,
                "max_fetch_errors": self._max_fetch_errors,
            }
        except Exception:
            pass

    def track_position(
        self,
        symbol: str,
        entry_price: float,
        entry_time: Optional[float] = None,
    ):
        """开始跟踪一个持仓"""
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
            log.debug(f"[PositionMonitor] 添加持仓: {symbol} 入场价={entry_price}")

    def untrack_position(self, symbol: str):
        """停止跟踪一个持仓"""
        if symbol in self._tracked:
            del self._tracked[symbol]
            log.debug(f"[PositionMonitor] 移除持仓: {symbol}")

    def on_tick(self, symbol: str, price: float, timestamp: float):
        """被动接收 tick 数据，立即更新"""
        if symbol not in self._tracked:
            return

        item = self._tracked[symbol]
        item.current_price = price
        item.last_update_time = timestamp

        is_new_high = price > item.highest_price
        is_new_low = price < item.lowest_price

        if is_new_high:
            item.highest_price = price
        if is_new_low:
            item.lowest_price = price

        self._price_history[symbol].append({
            'price': price,
            'timestamp': timestamp,
        })

        metrics = self._calculate_metrics(symbol, price)
        if metrics:
            self._notify_callbacks([metrics])

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
            log.debug(f"[PositionMonitor] 处理数据失败: {e}")

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
                log.debug(f"[PositionMonitor] 处理 {stock_code} 失败: {e}")

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
            log.debug(f"[PositionMonitor] 处理单条数据失败: {e}")

    def _update_price(self, stock_code: str, price: float) -> Optional[PerformanceMetrics]:
        """更新价格并返回性能指标

        如果入场价还未设置（为0），用首次价格作为入场价
        这支持回放模式下信号先于价格数据到达的情况
        """
        if stock_code not in self._tracked:
            return None

        item = self._tracked[stock_code]

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
                log.error(f"[PositionMonitor] 回调失败: {e}")

    def _fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """主动获取价格（fallback）

        从 MarketDataBus 获取价格:
        1. 优先从 MarketDataBus 缓存获取（共享行情数据）
        2. 备用从 NB("naja_realtime_quotes") 缓存获取

        Returns:
            Dict[symbol, price]
        """
        prices = {}

        if not symbols:
            return prices

        market_data_bus_available = False
        try:
            from deva.naja.bandit.market_data_bus import get_market_data_bus
            bus = get_market_data_bus()
            prices = bus.get_prices(symbols)
            if prices:
                market_data_bus_available = True
                log.debug(f"[PositionMonitor] MarketDataBus 获取价格: {len(prices)} 个")
        except Exception as e:
            log.debug(f"[PositionMonitor] MarketDataBus 不可用: {e}")

        if not market_data_bus_available:
            log.debug("[PositionMonitor] 使用备用价格获取: NB(naja_realtime_quotes)")

        for symbol in symbols:
            if symbol not in prices or prices.get(symbol, 0) <= 0:
                price = self._fetch_from_realtime_cache(symbol)
                if price > 0:
                    prices[symbol] = price
                else:
                    log.debug(f"[PositionMonitor] 无法获取 {symbol} 价格")

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
            log.debug(f"[PositionMonitor] 从缓存获取 {symbol} 失败: {e}")
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
        """主动获取所有持仓价格（fallback）"""
        if not self._tracked:
            return []

        symbols = list(self._tracked.keys())
        prices = self._fetch_prices(symbols)

        signals = []
        for symbol, current_price in prices.items():
            if symbol not in self._tracked:
                continue

            metrics = self._update_price(symbol, current_price)
            if metrics:
                signals.append(metrics)

        return signals

    def _connect_to_datasource(self):
        """连接到数据源"""
        try:
            from deva.naja.strategy import get_strategy_manager
            mgr = get_strategy_manager()
            experiment_info = mgr.get_experiment_info()
            datasource_id = experiment_info.get("datasource_id") if experiment_info.get("active", False) else None
        except Exception:
            datasource_id = None

        if datasource_id is None:
            datasource_id = '189e3042171a'

        try:
            from deva.naja.datasource import get_datasource_manager
            mgr = get_datasource_manager()
            mgr.load_from_db()
            ds = mgr.get(datasource_id)
        except Exception as e:
            log.debug(f"[PositionMonitor] 获取数据源失败: {e}")
            return

        if ds is None:
            return

        self._current_datasource = ds

        if hasattr(ds, 'is_running') and ds.is_running:
            try:
                stream = ds.get_stream()
                if stream:
                    self._stream_subscription = stream.sink(self._on_data_received)
                    log.debug(f"[PositionMonitor] 已订阅数据源流: {ds.name}")
                    return
            except Exception as e:
                log.debug(f"[PositionMonitor] 订阅流失败: {e}")

        log.debug(f"[PositionMonitor] 数据源未运行，使用主动获取模式: {ds.name}")

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
        log.info(f"[PositionMonitor] 已启动 (更新间隔: {self._update_interval}s)")

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

        log.info("[PositionMonitor] 已停止")

    def _run_loop(self):
        """主循环: 定时主动获取所有持仓价格（fallback）"""
        while self._running and not self._stop_event.is_set():
            try:
                signals = self._process_update()

                if signals:
                    self._notify_callbacks(signals)
            except Exception as e:
                log.error(f"[PositionMonitor] 处理错误: {e}")

            self._stop_event.wait(self._update_interval)

    def register_callback(self, callback: Callable[[List[PerformanceMetrics]], None]):
        """注册更新回调"""
        self._callbacks.append(callback)

    def get_metrics(self, symbol: str) -> Optional[PerformanceMetrics]:
        """获取指定持仓的收益指标"""
        if symbol in self._tracked:
            return self._calculate_metrics(symbol, self._tracked[symbol].current_price)
        return None

    def get_all_metrics(self) -> List[PerformanceMetrics]:
        """获取所有持仓的收益指标"""
        results = []
        for symbol in self._tracked:
            metrics = self._calculate_metrics(symbol, self._tracked[symbol].current_price)
            if metrics:
                results.append(metrics)
        return results

    def get_status(self) -> dict:
        """获取状态"""
        return {
            "running": self._running,
            "tracked_count": len(self._tracked),
            "update_interval": self._update_interval,
            "last_fetch_time": self._last_fetch_time,
            "fetch_errors": self._fetch_errors,
            "subscribed": self._stream_subscription is not None,
        }


_position_monitor: Optional[PositionMonitor] = None
_monitor_lock = threading.Lock()


def get_position_monitor(update_interval: float = 10.0) -> PositionMonitor:
    """获取 PositionMonitor 单例"""
    global _position_monitor
    if _position_monitor is None:
        with _monitor_lock:
            if _position_monitor is None:
                _position_monitor = PositionMonitor(update_interval=update_interval)
    return _position_monitor


def ensure_position_monitor(update_interval: float = 10.0) -> PositionMonitor:
    """确保 PositionMonitor 已初始化"""
    global _position_monitor
    if _position_monitor is None:
        with _monitor_lock:
            if _position_monitor is None:
                _position_monitor = PositionMonitor(update_interval=update_interval)
    if not _position_monitor._running:
        _position_monitor.start()
    return _position_monitor
