"""市场数据观察器

从数据源获取实时价格，更新虚拟持仓。
与策略管理器的实验模式保持一致：
- 交易模式：订阅 realtime_tick_5s 数据源
- 实验/回测模式：订阅策略实验模式使用的数据源
- 智能切换：数据源运行时订阅流，停止时主动获取
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Callable

from deva import NB

from ..radar.trading_clock import TRADING_CLOCK_STREAM

log = logging.getLogger(__name__)

MARKET_DATA_CONFIG_TABLE = "naja_bandit_market_config"

# 默认数据源配置
DEFAULT_TRADING_DATASOURCE = '189e3042171a'  # realtime_tick_5s


class MarketDataObserver:
    """市场数据观察器

    智能数据获取策略：
    1. 数据源运行中：订阅数据流（被动接收推送）
    2. 数据源已停止：主动获取最新数据
    3. 数据源无推送：主动轮询获取数据
    """

    def __init__(self):
        self._running = False

        self._db = NB(MARKET_DATA_CONFIG_TABLE)

        self._tracked_stocks: Set[str] = set()
        self._last_prices: Dict[str, float] = {}

        self._price_callbacks: List[Callable[[str, float], None]] = []

        self._stream_subscription = None
        self._current_datasource_id: Optional[str] = None
        self._current_datasource = None

        self._fetch_thread: Optional[threading.Thread] = None
        self._fetch_stop_event = threading.Event()
        self._fetch_interval = 5.0
        self._last_data_time = 0
        self._data_timeout = 10.0

        self._experiment_monitor_thread: Optional[threading.Thread] = None
        self._experiment_monitor_stop_event = threading.Event()

        self._current_phase: str = 'closed'
        self._force_mode: bool = False

        self._low_power_mode = False
        self._normal_fetch_interval = 5.0
        self._low_power_fetch_interval = 60.0
        self._last_datasource_available = True

        self._errors = {"config_load": 0, "config_save": 0, "datasource_acquire": 0, "process_data": 0}

        self._load_config()

    def _load_config(self):
        """加载配置"""
        import os
        log.info(f"[MarketObserver] _load_config 被调用")
        try:
            config = self._db.get("observer_config")
            if config:
                tracked_stocks = config.get("tracked_stocks", [])
                if tracked_stocks:
                    self._tracked_stocks = set(tracked_stocks)
                    log.debug(f"[MarketObserver] 已恢复 {len(tracked_stocks)} 个跟踪股票")
                was_running = config.get("was_running", False)
                if was_running:
                    self._running = True
                    log.debug("[MarketObserver] 上次运行中，将自动恢复")
            # 始终加载自选股（无论是否 LAB 模式）
            self._load_watchlist_stocks()
        except Exception as e:
            self._errors["config_load"] += 1
            log.warning(f"[MarketObserver] 配置加载失败 (累计{self._errors['config_load']}次): {e}")

    def _load_watchlist_stocks(self):
        """从 NB 数据库加载自选股"""
        import json
        import os
        log.info(f"[MarketObserver] _load_watchlist_stocks 被调用")
        try:
            from deva.naja.tables import get_table_data
            watchlist_data = get_table_data("naja_watchlist")
            log.info(f"[MarketObserver] 自选股数据: type={type(watchlist_data)}")
            if watchlist_data is None:
                log.info("[MarketObserver] 自选股为空，使用默认股票池")
                return
            
            all_codes = []
            
            # others 的结构是 [('ai_stocks', {...}), ('stocks', [...])]
            others = watchlist_data.get("others", [])
            if others:
                for item in others:
                    if not isinstance(item, tuple) or len(item) < 2:
                        continue
                    key, value = item[0], item[1]
                    
                    if key == "ai_stocks":
                        # ai_stocks 格式: {'stocks': [...], 'updated_at': ...}
                        if isinstance(value, dict):
                            stocks = value.get("stocks", [])
                            codes = [s["code"] for s in stocks if isinstance(s, dict) and "code" in s]
                            all_codes.extend(codes)
                            log.info(f"[MarketObserver] 从 ai_stocks 加载了 {len(codes)} 只股票")
                    
                    elif key == "stocks":
                        # stocks 格式: [{'code': '...', ...}, ...]
                        if isinstance(value, list):
                            codes = [s["code"] for s in value if isinstance(s, dict) and "code" in s]
                            all_codes.extend(codes)
                            log.info(f"[MarketObserver] 从 stocks 加载了 {len(codes)} 只股票")
            
            # 去重
            all_codes = list(set(all_codes))
            
            if all_codes:
                self._tracked_stocks = set(all_codes)
                log.info(f"[MarketObserver] 从自选股共加载了 {len(all_codes)} 只股票: {all_codes}")
            else:
                log.info("[MarketObserver] 自选股为空，使用默认股票池")
        except Exception as e:
            log.warning(f"[MarketObserver] 加载自选股失败: {e}")
            import traceback
            log.warning(f"[MarketObserver] 详细错误: {traceback.format_exc()}")

    def _save_config(self):
        """保存配置"""
        try:
            self._db["observer_config"] = {
                "tracked_stocks": list(self._tracked_stocks),
                "was_running": self._running
            }
        except Exception as e:
            self._errors["config_save"] += 1
            log.warning(f"[MarketObserver] 配置保存失败 (累计{self._errors['config_save']}次): {e}")

    def _get_strategy_experiment_info(self) -> dict:
        """获取策略管理器的实验模式信息"""
        try:
            from deva.naja.strategy import get_strategy_manager
            mgr = get_strategy_manager()
            return mgr.get_experiment_info()
        except Exception as e:
            log.debug(f"[MarketObserver] 获取实验模式信息失败: {e}")
            return {"active": False}

    def _get_active_datasource_id(self) -> str:
        """获取当前活跃的数据源ID"""
        import os
        if os.environ.get('NAJA_LAB_MODE'):
            from deva.naja.replay.replay_scheduler import get_running_replay_id
            replay_id = get_running_replay_id()
            if replay_id:
                return replay_id

        experiment_info = self._get_strategy_experiment_info()

        if experiment_info.get("active", False):
            datasource_id = experiment_info.get("datasource_id")
            if datasource_id:
                return datasource_id

        return DEFAULT_TRADING_DATASOURCE

    def _is_experiment_mode(self) -> bool:
        """检查是否处于实验模式"""
        experiment_info = self._get_strategy_experiment_info()
        return experiment_info.get("active", False)

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
            self._errors["datasource_acquire"] += 1
            log.error(f"[MarketObserver] 获取数据源失败 (累计{self._errors['datasource_acquire']}次): {e}")
            return None

    def _is_datasource_running(self, ds) -> bool:
        """检查数据源是否正在运行"""
        if ds is None:
            return False
        # 检查数据源的 is_running 属性或方法
        if hasattr(ds, 'is_running'):
            return ds.is_running
        if hasattr(ds, '_running'):
            return ds._running
        return False

    def _start_experiment_monitor(self):
        """启动实验模式监控线程"""
        if self._experiment_monitor_thread and self._experiment_monitor_thread.is_alive():
            return

        self._experiment_monitor_stop_event.clear()
        self._experiment_monitor_thread = threading.Thread(
            target=self._experiment_monitor_loop,
            daemon=True
        )
        self._experiment_monitor_thread.start()
        log.debug("[MarketObserver] 实验模式监控已启动")

    def _stop_experiment_monitor(self):
        """停止实验模式监控线程"""
        self._experiment_monitor_stop_event.set()
        if self._experiment_monitor_thread:
            self._experiment_monitor_thread.join(timeout=2)
        log.debug("[MarketObserver] 实验模式监控已停止")

    def _experiment_monitor_loop(self):
        """实验模式监控循环"""
        while not self._experiment_monitor_stop_event.is_set():
            try:
                current_datasource_id = self._get_active_datasource_id()

                # 如果数据源发生变化，重新连接
                if current_datasource_id != self._current_datasource_id:
                    log.debug(f"[MarketObserver] 数据源变化: {self._current_datasource_id} -> {current_datasource_id}")
                    self._reconnect_datasource(current_datasource_id)

            except Exception as e:
                log.debug(f"[MarketObserver] 实验模式监控异常: {e}")

            self._experiment_monitor_stop_event.wait(2)

    def _reconnect_datasource(self, datasource_id: str = None):
        """重新连接数据源

        根据数据源状态决定连接方式：
        1. 数据源运行中：订阅数据流
        2. 数据源已停止：主动获取模式
        3. Lab 模式：使用 ReplayScheduler 的数据推送
        """
        import os
        log.info(f"[MarketObserver] _reconnect_datasource called: NAJA_LAB_MODE={os.environ.get('NAJA_LAB_MODE')}")

        # Lab 模式：使用 ReplayScheduler
        if os.environ.get('NAJA_LAB_MODE'):
            try:
                scheduler = SR('replay_scheduler')
                if scheduler is None:
                    log.info("[MarketObserver] Lab 模式：scheduler is None")
                    return False
                elif not hasattr(scheduler, '_running'):
                    log.info("[MarketObserver] Lab 模式：scheduler 没有 _running 属性")
                    return False
                elif not scheduler._running:
                    log.info(f"[MarketObserver] Lab 模式：scheduler._running={scheduler._running}")
                    return False
                else:
                    self._current_datasource = scheduler
                    self._current_datasource_id = "lab_replay"
                    log.info("[MarketObserver] Lab 模式：使用 ReplayScheduler 成功")
                    return True
            except Exception as e:
                log.warning(f"[MarketObserver] 无法获取 ReplayScheduler: {e}")
                return False

        if datasource_id is None:
            datasource_id = self._get_active_datasource_id()

        # 先断开当前连接
        self._disconnect_datasource()

        # 获取数据源对象
        ds = self._get_datasource(datasource_id)
        if not ds:
            log.warning(f"[MarketObserver] 未找到数据源 {datasource_id}")
            return False

        self._current_datasource = ds
        self._current_datasource_id = datasource_id

        # 检查数据源是否运行中
        is_running = self._is_datasource_running(ds)

        if is_running:
            # 数据源运行中，尝试订阅数据流
            if self._subscribe_stream(ds):
                log.debug(f"[MarketObserver] 已订阅数据源流: {ds.name}")
                return True
            else:
                log.debug(f"[MarketObserver] 订阅流失败，切换到主动获取模式: {ds.name}")
        else:
            log.debug(f"[MarketObserver] 数据源未运行，使用主动获取模式: {ds.name}")

        return True  # 返回True表示连接成功（即使使用主动获取模式）

    def _disconnect_datasource(self):
        """断开数据源连接"""
        log.info("[MarketObserver] _disconnect_datasource ENTER")
        # 取消订阅流
        if self._stream_subscription:
            try:
                self._stream_subscription.destroy()
            except Exception:
                pass
            self._stream_subscription = None
            log.info("[MarketObserver] _disconnect_datasource: stream destroyed")

        self._current_datasource = None
        self._current_datasource_id = None
        log.debug("[MarketObserver] 已断开数据源连接")

    def _subscribe_stream(self, ds) -> bool:
        """订阅数据源流"""
        try:
            stream = ds.get_stream()
            if stream:
                self._stream_subscription = stream.sink(self._on_data_received)
                return True
        except Exception as e:
            log.debug(f"[MarketObserver] 订阅流失败: {e}")
        return False

    def _on_data_received(self, data: Any):
        """收到数据源数据时的回调"""
        self._last_data_time = time.time()  # 更新最后收到数据的时间

        try:
            import pandas as pd

            if isinstance(data, pd.DataFrame):
                self._process_dataframe(data)
            elif isinstance(data, list):
                for item in data:
                    self._process_single_item(item)
            elif isinstance(data, dict):
                self._process_single_item(data)
            else:
                log.debug(f"[MarketObserver] 未知数据类型: {type(data)}")

        except Exception as e:
            log.error(f"[MarketObserver] 处理数据失败: {e}")

    def _process_dataframe(self, df):
        """处理 DataFrame 格式的数据"""
        if df is None or df.empty:
            return

        tracked = list(self._tracked_stocks)

        for stock_code in tracked:
            try:
                matches = df[df['code'] == stock_code]

                if not matches.empty:
                    row = matches.iloc[0]
                    price = float(row.get('now', row.get('price', row.get('current', 0))))
                    if price > 0:
                        self._update_price(stock_code, price)
            except Exception as e:
                log.debug(f"[MarketObserver] 处理 {stock_code} 失败: {e}")

    def _process_single_item(self, item: dict):
        """处理单条数据"""
        if not isinstance(item, dict):
            return

        try:
            stock_code = str(item.get('code', item.get('stock_code', '')))
            if stock_code and stock_code in self._tracked_stocks:
                price = float(item.get('now', item.get('price', item.get('current', 0))))
                if price > 0:
                    self._update_price(stock_code, price)
        except Exception as e:
            log.debug(f"[MarketObserver] 处理单条数据失败: {e}")

    def _update_price(self, stock_code: str, price: float):
        """更新价格并触发回调"""
        self._last_prices[stock_code] = price
        log.debug(f"[MarketObserver] 📈 价格更新: {stock_code} @ {price}")

        for callback in self._price_callbacks:
            try:
                callback(stock_code, price)
            except Exception as e:
                log.debug(f"[MarketObserver] 回调失败: {e}")

    def _start_fetch_loop(self):
        """启动数据获取轮询线程"""
        log.info(f"[MarketObserver] _start_fetch_loop called, running={self._running}")
        if self._fetch_thread and self._fetch_thread.is_alive():
            log.info("[MarketObserver] Fetch thread already alive")
            return

        self._fetch_stop_event.clear()
        self._fetch_thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self._fetch_thread.start()
        log.info("[MarketObserver] 数据获取轮询已启动")

    def _stop_fetch_loop(self):
        """停止数据获取轮询线程"""
        self._fetch_stop_event.set()
        if self._fetch_thread:
            self._fetch_thread.join(timeout=2)
        log.info("[MarketObserver] 数据获取轮询已停止")

    def _fetch_loop(self):
        """数据获取轮询循环

        两种情况下会主动获取数据：
        1. 数据源未运行（已停止）
        2. 数据源运行但长时间未推送数据（超过 _data_timeout）

        低功耗模式：
        - 当数据源不可用时，自动进入低功耗模式，增大轮询间隔
        - 当数据源恢复时，自动退出低功耗模式，恢复正常间隔
        """
        import os
        log.info(f"[MarketObserver] _fetch_loop started: NAJA_LAB_MODE={os.environ.get('NAJA_LAB_MODE')}, _current_phase={self._current_phase}")
        log.info(f"[MarketObserver] _fetch_loop: entering main loop, stop_event_is_set={self._fetch_stop_event.is_set()}")
        iteration = 0
        while True:
            iteration += 1
            if iteration == 1 or iteration % 10 == 0:
                log.info(f"[MarketObserver] _fetch_loop iteration {iteration}, stop_event_is_set={self._fetch_stop_event.is_set()}")
            if self._fetch_stop_event.is_set():
                log.info("[MarketObserver] _fetch_loop: stop event set, exiting")
                break
            allowed = self._is_allowed_to_run()
            if iteration == 1 or iteration % 10 == 0:
                log.info(f"[MarketObserver] _fetch_loop: allowed={allowed}, running={self._running}, datasource={'None' if not self._current_datasource else 'exists'}")
            try:
                if allowed:
                    need_fetch = False
                    is_running = False
                    datasource_available = False

                    if self._current_datasource:
                        is_running = self._is_datasource_running(self._current_datasource)
                        time_since_data = time.time() - self._last_data_time
                        datasource_available = is_running
                        log.info(f"[MarketObserver] _fetch_loop check: is_running={is_running}, time_since_data={time_since_data:.1f}s, timeout={self._data_timeout}s, tracked={len(self._tracked_stocks)}")

                        if not is_running:
                            need_fetch = True
                            log.info(f"[MarketObserver] 数据源已停止，主动获取数据, tracked={len(self._tracked_stocks)}")
                        elif time_since_data > self._data_timeout:
                            need_fetch = True
                            log.info(f"[MarketObserver] 数据源无推送(time={time_since_data:.1f}s > {self._data_timeout}s)，主动获取数据")
                    else:
                        if os.environ.get('NAJA_LAB_MODE'):
                            need_fetch = True
                            datasource_available = True
                        elif self._tracked_stocks:
                            market_open = self._is_market_open_now()
                            if market_open:
                                need_fetch = True
                                datasource_available = True
                            else:
                                need_fetch = False
                                datasource_available = False
                                if iteration == 1 or iteration % 20 == 0:
                                    log.info(f"[MarketObserver] 市场休市中，跳过主动获取")

                    if need_fetch:
                        log.info(f"[MarketObserver] 主动获取数据，跟踪股票: {len(self._tracked_stocks)} 个")
                        self._fetch_prices_from_datasource()
                    elif self._tracked_stocks and self._current_datasource:
                        log.info(f"[MarketObserver] 等待数据推送...")

                    # 低功耗模式管理：检测数据源可用性变化
                    if not datasource_available:
                        if not self._low_power_mode:
                            self._low_power_mode = True
                            self._fetch_interval = self._low_power_fetch_interval
                            log.info(f"[MarketObserver] 数据源不可用，进入低功耗模式，间隔: {self._fetch_interval}s")
                        self._last_datasource_available = False
                    else:
                        if self._low_power_mode:
                            self._low_power_mode = False
                            self._fetch_interval = self._normal_fetch_interval
                            log.info(f"[MarketObserver] 数据源恢复，退出低功耗模式，间隔恢复: {self._fetch_interval}s")
                        self._last_datasource_available = True

            except Exception as e:
                log.debug(f"[MarketObserver] 数据获取异常: {e}")

            self._fetch_stop_event.wait(self._fetch_interval)

    def _fetch_prices_from_datasource(self):
        """主动从数据源获取最新价格"""
        import os
        log.info(f"[MarketObserver] _fetch_prices_from_datasource: tracked={len(self._tracked_stocks) if self._tracked_stocks else 0}, datasource={'None' if not self._current_datasource else 'exists'}")

        # Lab 模式：确保自选股已加载
        if os.environ.get('NAJA_LAB_MODE'):
            if not self._tracked_stocks or len(self._tracked_stocks) > 30:
                self._load_watchlist_stocks()

            try:
                scheduler = SR('replay_scheduler')
                log.info(f"[MarketObserver] Lab 模式：scheduler={type(scheduler)}, has_latest_data={hasattr(scheduler, '_latest_sent_data')}")
                if scheduler and hasattr(scheduler, '_latest_sent_data') and scheduler._latest_sent_data is not None:
                    latest = scheduler._latest_sent_data
                    import pandas as pd
                    if isinstance(latest, pd.DataFrame):
                        for stock_code in list(self._tracked_stocks):
                            matches = latest[latest['code'] == stock_code]
                            if not matches.empty:
                                row = matches.iloc[0]
                                price = float(row.get('now', row.get('price', row.get('current', 0))))
                                if price > 0:
                                    self._update_price(stock_code, price)
                        log.info(f"[MarketObserver] Lab 模式：获取到 {len(latest)} 条数据")
                        return
                    elif isinstance(latest, dict):
                        symbols = latest.get('symbols', {})
                        for stock_code in list(self._tracked_stocks):
                            if stock_code in symbols:
                                stock_data = symbols[stock_code]
                                price = float(stock_data.get('price', 0))
                                if price > 0:
                                    self._update_price(stock_code, price)
                        log.info(f"[MarketObserver] Lab 模式：获取到 {len(symbols)} 只股票数据")
                        return
                else:
                    log.info(f"[MarketObserver] Lab 模式：_latest_sent_data={getattr(scheduler, '_latest_sent_data', 'N/A')}")
            except Exception as e:
                log.warning(f"[MarketObserver] Lab 模式获取数据失败: {e}")

        if not self._tracked_stocks:
            return

        if self._current_datasource:
            try:
                latest = self._current_datasource.get_latest_data()
                if latest is None:
                    return

                import pandas as pd
                if isinstance(latest, pd.DataFrame):
                    for stock_code in list(self._tracked_stocks):
                        matches = latest[latest['code'] == stock_code]
                        if not matches.empty:
                            row = matches.iloc[0]
                            price = float(row.get('now', row.get('price', row.get('current', 0))))
                            if price > 0:
                                self._update_price(stock_code, price)

            except Exception as e:
                log.debug(f"[MarketObserver] 主动获取价格失败: {e}")

        else:
            try:
                from deva.naja.bandit.market_data_bus import get_market_data_bus
                bus = get_market_data_bus()
                prices = bus.fetch(list(self._tracked_stocks))
                for stock_code, price in prices.items():
                    if price > 0:
                        self._update_price(stock_code, price)
            except Exception as e:
                log.debug(f"[MarketObserver] MarketDataBus 获取失败: {e}")

    def track_stocks_batch(self, stock_codes: List[str]):
        """批量跟踪股票

        Args:
            stock_codes: 股票代码列表
        """
        if not stock_codes:
            return

        original_count = len(self._tracked_stocks)
        for code in stock_codes:
            self._tracked_stocks.add(code)
        new_count = len(self._tracked_stocks)
        added_count = new_count - original_count

        self._save_config()
        log.info(f"[MarketObserver] 批量跟踪股票完成: 新增 {added_count} 只, 当前共 {new_count} 只")

        import os
        lab_mode = os.environ.get('NAJA_LAB_MODE')

        if lab_mode:
            self._running = True
            self._last_data_time = time.time()
            self._load_watchlist_stocks()
            try:
                scheduler = SR('replay_scheduler')
                if scheduler:
                    scheduler.set_downstream_callback(self._on_replay_data)
                    log.info("[MarketObserver] Lab 模式：已注册 ReplayScheduler 回调")
            except Exception as e:
                log.warning(f"[MarketObserver] 无法注册 ReplayScheduler 回调: {e}")
            self._start_fetch_loop()
            return

        if not self._running:
            self._running = True
            self._start_fetch_loop()

    def track_stock(self, stock_code: str):
        """跟踪股票"""
        if stock_code in self._tracked_stocks:
            return
        self._tracked_stocks.add(stock_code)
        self._save_config()
        log.debug(f"[MarketObserver] 开始跟踪股票: {stock_code}, 当前跟踪: {len(self._tracked_stocks)} 个")

        import os
        lab_mode = os.environ.get('NAJA_LAB_MODE')

        if lab_mode:
            self._running = True
            self._last_data_time = time.time()
            try:
                scheduler = SR('replay_scheduler')
                if scheduler:
                    scheduler.set_downstream_callback(self._on_replay_data)
                    log.info("[MarketObserver] Lab 模式：已注册 ReplayScheduler 回调")
            except Exception as e:
                log.warning(f"[MarketObserver] 无法注册 ReplayScheduler 回调: {e}")
            self._start_fetch_loop()
            return

        if not self._running:
            self._running = True
            self._last_data_time = time.time()
            TRADING_CLOCK_STREAM.sink(self._on_trading_clock_signal)
            log.info("[MarketObserver] 已订阅交易时钟信号")
            datasource_id = self._get_active_datasource_id()
            self._reconnect_datasource(datasource_id)
            self._start_fetch_loop()

        elif not self._fetch_thread or not self._fetch_thread.is_alive():
            self._start_fetch_loop()

    def untrack_stock(self, stock_code: str):
        """取消跟踪"""
        self._tracked_stocks.discard(stock_code)
        self._save_config()
        log.debug(f"[MarketObserver] 取消跟踪股票: {stock_code}")

    def register_price_callback(self, callback: Callable[[str, float], None]):
        """注册价格更新回调"""
        self._price_callbacks.append(callback)

    def adjust_interval(self, interval: float, reason: str = ""):
        """调整数据获取间隔（供 AutoTuner 调用）

        Args:
            interval: 新的间隔秒数
            reason: 调整原因
        """
        old_interval = self._fetch_interval
        new_interval = max(1.0, min(interval, 300.0))

        if self._low_power_mode and new_interval > self._normal_fetch_interval:
            self._low_power_fetch_interval = new_interval
            if abs(old_interval - self._fetch_interval) > 0.5:
                log.info(f"[MarketObserver] 低功耗间隔调整: {old_interval}s → {self._fetch_interval}s ({reason})")
        else:
            if not self._low_power_mode:
                self._normal_fetch_interval = new_interval
            self._fetch_interval = new_interval
            if abs(old_interval - self._fetch_interval) > 0.5:
                log.info(f"[MarketObserver] 间隔调整: {old_interval}s → {self._fetch_interval}s ({reason})")

    def start(self):
        """启动观察"""
        log.info(f"[MarketObserver] start() called, current _running={self._running}")
        if self._running and self._fetch_thread and self._fetch_thread.is_alive():
            log.debug("[MarketObserver] 已在运行")
            return

        import os
        lab_mode = os.environ.get('NAJA_LAB_MODE')

        if lab_mode:
            self._running = True
            self._last_data_time = time.time()
            try:
                scheduler = SR('replay_scheduler')
                if scheduler:
                    scheduler.set_downstream_callback(self._on_replay_data)
                    log.info("[MarketObserver] Lab 模式：已注册 ReplayScheduler 回调")
            except Exception as e:
                log.warning(f"[MarketObserver] 无法注册 ReplayScheduler 回调: {e}")
            self._start_fetch_loop()
            self._save_config()
            log.info("[MarketObserver] Lab 模式已启动")
            return

        if not self._running:
            self._running = True
            self._last_data_time = time.time()
            TRADING_CLOCK_STREAM.sink(self._on_trading_clock_signal)
            datasource_id = self._get_active_datasource_id()
            self._reconnect_datasource(datasource_id)
            log.info("[MarketObserver] 已订阅交易时钟信号")
            self._start_experiment_monitor()

        self._start_fetch_loop()
        self._save_config()
        log.info("[MarketObserver] 已启动")

    def _on_trading_clock_signal(self, signal: Dict[str, Any]):
        """处理交易时钟信号"""
        signal_type = signal.get('type')
        phase = signal.get('phase')

        if signal_type == 'current_state':
            self._current_phase = phase
        elif signal_type == 'phase_change':
            self._current_phase = phase
            if phase in ('trading', 'pre_market', 'call_auction'):
                log.debug(f"[MarketObserver] 进入交易时段")
            else:
                log.debug(f"[MarketObserver] 退出交易时段")

    def _on_replay_data(self, data):
        """处理 ReplayScheduler 的数据回调"""
        import pandas as pd
        log.info(f"[MarketObserver] Lab 模式：收到回放数据 {len(data) if isinstance(data, pd.DataFrame) else type(data)}")
        try:
            if isinstance(data, pd.DataFrame):
                for stock_code in list(self._tracked_stocks):
                    matches = data[data['code'] == stock_code]
                    if not matches.empty:
                        row = matches.iloc[0]
                        price = float(row.get('now', row.get('price', row.get('current', 0))))
                        if price > 0:
                            self._update_price(stock_code, price)

                try:
                    from deva.naja.attention.trading_center import get_trading_center
                    tc = get_trading_center()
                    tc.attention_os.market_scheduler.schedule(data)
                    log.info(f"[MarketObserver] Lab 模式：已发送 {len(data)} 条数据到 TradingCenter")
                except Exception as e:
                    log.warning(f"[MarketObserver] 发送数据到 TradingCenter 失败: {e}")

                self._last_data_time = time.time()
                log.info(f"[MarketObserver] Lab 模式：处理了 {len(data)} 条数据")

            elif isinstance(data, dict):
                symbols = data.get('symbols', {})
                for stock_code in list(self._tracked_stocks):
                    if stock_code in symbols:
                        stock_data = symbols[stock_code]
                        price = float(stock_data.get('price', 0))
                        if price > 0:
                            self._update_price(stock_code, price)

                try:
                    from deva.naja.attention.trading_center import get_trading_center
                    tc = get_trading_center()
                    tc.attention_os.market_scheduler.schedule(data)
                    log.info(f"[MarketObserver] Lab 模式：已发送 {len(symbols)} 只股票数据到 TradingCenter")
                except Exception as e:
                    log.warning(f"[MarketObserver] 发送数据到 TradingCenter 失败: {e}")

                self._last_data_time = time.time()
                log.info(f"[MarketObserver] Lab 模式：处理了 {len(symbols)} 只股票数据")
        except Exception as e:
            log.warning(f"[MarketObserver] Lab 模式处理回放数据失败: {e}")

    def _is_allowed_to_run(self) -> bool:
        """检查是否允许运行"""
        import os as os_module
        env_lab = os_module.environ.get('NAJA_LAB_MODE') or os_module.environ.get('LAB_MODE')
        result = (self._force_mode or self._is_experiment_mode() or env_lab or
                  self._current_phase in ('trading', 'pre_market', 'call_auction'))
        if not result:
            log.info(f"[MarketObserver] _is_allowed_to_run=False: force={self._force_mode}, experiment={self._is_experiment_mode()}, env_lab={env_lab}, phase={self._current_phase}")
        return result

    def stop(self):
        """停止观察"""
        if not self._running:
            return

        self._running = False

        # 停止实验模式监控
        self._stop_experiment_monitor()

        # 断开数据源连接
        self._disconnect_datasource()

        # 停止数据获取轮询
        self._stop_fetch_loop()

        self._save_config()

        log.debug("[MarketObserver] 已停止")

    def get_price(self, stock_code: str) -> float:
        """获取股票当前价格"""
        return self._last_prices.get(stock_code, 0.0)

    def get_all_prices(self) -> Dict[str, float]:
        """获取所有跟踪股票的价格"""
        return dict(self._last_prices)

    def get_status(self) -> dict:
        """获取状态"""
        experiment_info = self._get_strategy_experiment_info()
        ds_running = self._is_datasource_running(self._current_datasource) if self._current_datasource else False

        return {
            "running": self._running,
            "mode": "experiment" if experiment_info.get("active", False) else "trading",
            "datasource_id": self._current_datasource_id,
            "datasource_running": ds_running,
            "data_source": "stream" if self._stream_subscription else "fetch",
            "tracked_stocks": list(self._tracked_stocks),
            "prices": self._last_prices,
            "errors": dict(self._errors),
        }

    def get_errors(self) -> dict:
        """获取错误统计"""
        return dict(self._errors)


_observer: Optional[MarketDataObserver] = None
_observer_lock = threading.Lock()


def get_market_observer() -> MarketDataObserver:
    from deva.naja.register import SR
    return SR('market_observer')
