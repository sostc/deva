"""市场数据观察器

从数据源获取实时价格，更新虚拟持仓。
与策略管理器的实验模式保持一致：
- 交易模式：订阅 realtime_tick_5s 数据源
- 实验/回测模式：订阅策略实验模式使用的数据源
- 智能切换：数据源运行时订阅流，停止时主动获取
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Set, Callable

from deva import NB

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

        # 数据源订阅管理
        self._stream_subscription = None
        self._current_datasource_id: Optional[str] = None
        self._current_datasource = None  # 当前数据源对象

        # 主动获取机制
        self._fetch_thread: Optional[threading.Thread] = None
        self._fetch_stop_event = threading.Event()
        self._fetch_interval = 5.0  # 轮询间隔（秒）
        self._last_data_time = 0  # 上次收到数据的时间
        self._data_timeout = 10.0  # 数据超时时间（秒），超过此时间未收到数据则主动获取

        # 实验模式监控线程
        self._experiment_monitor_thread: Optional[threading.Thread] = None
        self._experiment_monitor_stop_event = threading.Event()

        self._load_config()

    def _load_config(self):
        """加载配置"""
        try:
            config = self._db.get("observer_config")
            if config:
                # 恢复跟踪的股票列表
                tracked_stocks = config.get("tracked_stocks", [])
                if tracked_stocks:
                    self._tracked_stocks = set(tracked_stocks)
                    log.info(f"[MarketObserver] 已恢复 {len(tracked_stocks)} 个跟踪股票")
                # 恢复运行状态
                was_running = config.get("was_running", False)
                if was_running:
                    self._running = True
                    log.info("[MarketObserver] 检测到上次运行中，将自动恢复")
        except Exception:
            pass

    def _save_config(self):
        """保存配置"""
        try:
            self._db["observer_config"] = {
                "tracked_stocks": list(self._tracked_stocks),
                "was_running": self._running
            }
        except Exception:
            pass

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
            log.error(f"[MarketObserver] 获取数据源失败: {e}")
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
        log.info("[MarketObserver] 实验模式监控已启动")

    def _stop_experiment_monitor(self):
        """停止实验模式监控线程"""
        self._experiment_monitor_stop_event.set()
        if self._experiment_monitor_thread:
            self._experiment_monitor_thread.join(timeout=2)
        log.info("[MarketObserver] 实验模式监控已停止")

    def _experiment_monitor_loop(self):
        """实验模式监控循环"""
        while not self._experiment_monitor_stop_event.is_set():
            try:
                current_datasource_id = self._get_active_datasource_id()

                # 如果数据源发生变化，重新连接
                if current_datasource_id != self._current_datasource_id:
                    log.info(f"[MarketObserver] 检测到数据源变化: {self._current_datasource_id} -> {current_datasource_id}")
                    self._reconnect_datasource(current_datasource_id)

            except Exception as e:
                log.debug(f"[MarketObserver] 实验模式监控异常: {e}")

            self._experiment_monitor_stop_event.wait(2)

    def _reconnect_datasource(self, datasource_id: str = None):
        """重新连接数据源

        根据数据源状态决定连接方式：
        1. 数据源运行中：订阅数据流
        2. 数据源已停止：主动获取模式
        """
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
                log.info(f"[MarketObserver] 已订阅数据源流: {ds.name}")
                return True
            else:
                log.warning(f"[MarketObserver] 订阅流失败，切换到主动获取模式: {ds.name}")
        else:
            log.info(f"[MarketObserver] 数据源未运行，使用主动获取模式: {ds.name}")

        return True  # 返回True表示连接成功（即使使用主动获取模式）

    def _disconnect_datasource(self):
        """断开数据源连接"""
        # 取消订阅流
        if self._stream_subscription:
            try:
                self._stream_subscription.destroy()
            except Exception:
                pass
            self._stream_subscription = None

        self._current_datasource = None
        self._current_datasource_id = None
        log.info("[MarketObserver] 已断开数据源连接")

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

            log.info(f"[MarketObserver] 📥 收到数据源数据: {type(data)}")

            if isinstance(data, pd.DataFrame):
                log.info(f"[MarketObserver] 📊 DataFrame 数据: {len(data)} 行, 列: {list(data.columns)}")
                log.info(f"[MarketObserver] 📊 跟踪的股票: {list(self._tracked_stocks)}")
                self._process_dataframe(data)
            elif isinstance(data, list):
                log.info(f"[MarketObserver] 📋 List 数据: {len(data)} 项")
                for item in data:
                    self._process_single_item(item)
            elif isinstance(data, dict):
                log.info(f"[MarketObserver] 📄 Dict 数据: {data.keys() if hasattr(data, 'keys') else 'N/A'}")
                self._process_single_item(data)
            else:
                log.warning(f"[MarketObserver] ⚠️ 未知数据类型: {type(data)}")

        except Exception as e:
            log.error(f"[MarketObserver] ❌ 处理数据失败: {e}")
            import traceback
            log.error(traceback.format_exc())

    def _process_dataframe(self, df):
        """处理 DataFrame 格式的数据"""
        if df is None or df.empty:
            log.warning("[MarketObserver] ⚠️ DataFrame 为空")
            return

        tracked = list(self._tracked_stocks)
        log.info(f"[MarketObserver] 🔍 处理 DataFrame，跟踪股票: {tracked}")

        for stock_code in tracked:
            try:
                matches = df[df['code'] == stock_code]
                log.info(f"[MarketObserver] 🔍 查找 {stock_code}: 找到 {len(matches)} 条匹配")

                if not matches.empty:
                    row = matches.iloc[0]
                    price = float(row.get('now', row.get('price', row.get('current', 0))))
                    log.info(f"[MarketObserver] 💰 {stock_code} 价格: {price}")
                    if price > 0:
                        self._update_price(stock_code, price)
                    else:
                        log.warning(f"[MarketObserver] ⚠️ {stock_code} 价格无效: {price}")
                else:
                    log.info(f"[MarketObserver] ⚠️ DataFrame 中未找到 {stock_code}")
                    log.info(f"[MarketObserver] 📋 DataFrame 中的股票代码: {df['code'].tolist()[:10]}...")
            except Exception as e:
                log.error(f"[MarketObserver] ❌ 处理 {stock_code} 失败: {e}")

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
        log.info(f"[MarketObserver] 💰 价格更新: {stock_code} @ {price}")
        log.info(f"[MarketObserver] 📞 回调数量: {len(self._price_callbacks)}")

        for i, callback in enumerate(self._price_callbacks):
            try:
                log.info(f"[MarketObserver] 📞 触发回调 {i+1}/{len(self._price_callbacks)}: {callback.__name__ if hasattr(callback, '__name__') else 'anonymous'}")
                callback(stock_code, price)
                log.info(f"[MarketObserver] ✅ 回调 {i+1} 成功")
            except Exception as e:
                log.error(f"[MarketObserver] ❌ 回调 {i+1} 失败: {e}")
                import traceback
                log.error(traceback.format_exc())

    def _start_fetch_loop(self):
        """启动数据获取轮询线程"""
        if self._fetch_thread and self._fetch_thread.is_alive():
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
        """
        while not self._fetch_stop_event.is_set():
            try:
                # 检查是否需要主动获取数据
                need_fetch = False

                if self._current_datasource:
                    is_running = self._is_datasource_running(self._current_datasource)

                    if not is_running:
                        # 数据源已停止，需要主动获取
                        need_fetch = True
                        log.debug("[MarketObserver] 数据源已停止，主动获取数据")
                    elif time.time() - self._last_data_time > self._data_timeout:
                        # 数据源运行但长时间未推送数据
                        need_fetch = True
                        log.debug("[MarketObserver] 数据源无推送，主动获取数据")

                if need_fetch:
                    self._fetch_prices_from_datasource()

            except Exception as e:
                log.debug(f"[MarketObserver] 数据获取异常: {e}")

            # 等待下一次轮询
            self._fetch_stop_event.wait(self._fetch_interval)

    def _fetch_prices_from_datasource(self):
        """主动从数据源获取最新价格"""
        if not self._tracked_stocks or not self._current_datasource:
            return

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

    def track_stock(self, stock_code: str):
        """跟踪股票"""
        self._tracked_stocks.add(stock_code)
        self._save_config()
        log.info(f"[MarketObserver] 开始跟踪股票: {stock_code}")

    def untrack_stock(self, stock_code: str):
        """取消跟踪"""
        self._tracked_stocks.discard(stock_code)
        self._save_config()
        log.info(f"[MarketObserver] 取消跟踪股票: {stock_code}")

    def register_price_callback(self, callback: Callable[[str, float], None]):
        """注册价格更新回调"""
        self._price_callbacks.append(callback)

    def start(self):
        """启动观察"""
        if self._running:
            log.warning("[MarketObserver] 已在运行")
            return

        self._running = True
        self._last_data_time = time.time()

        # 连接数据源（根据数据源状态自动选择订阅或主动获取）
        datasource_id = self._get_active_datasource_id()
        self._reconnect_datasource(datasource_id)

        # 启动数据获取轮询（无论数据源是否运行，都启动轮询作为备选）
        self._start_fetch_loop()

        # 启动实验模式监控
        self._start_experiment_monitor()

        self._save_config()

        log.info("[MarketObserver] 已启动")

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

        log.info("[MarketObserver] 已停止")

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
        }


_observer: Optional[MarketDataObserver] = None
_observer_lock = threading.Lock()


def get_market_observer() -> MarketDataObserver:
    global _observer
    if _observer is None:
        with _observer_lock:
            if _observer is None:
                _observer = MarketDataObserver()
    return _observer
