"""市场数据观察器

从数据源获取实时价格，更新虚拟持仓。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Set

from deva import NB

log = logging.getLogger(__name__)

MARKET_DATA_CONFIG_TABLE = "naja_bandit_market_config"


class MarketDataObserver:
    """市场数据观察器
    
    从数据源获取实时价格：
    1. 跟踪持仓中的股票
    2. 定期获取最新价格
    3. 更新虚拟持仓
    4. 触发止盈止损检查
    """
    
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        self._db = NB(MARKET_DATA_CONFIG_TABLE)
        
        self._tracked_stocks: Set[str] = set()
        self._last_prices: Dict[str, float] = {}
        
        self._update_interval = 5.0
        
        self._price_callbacks: List[Callable[[str, float], None]] = []
        
        self._load_config()
    
    def _load_config(self):
        """加载配置"""
        try:
            config = self._db.get("observer_config")
            if config:
                self._update_interval = config.get("update_interval", 5.0)
        except Exception:
            pass
    
    def _save_config(self):
        """保存配置"""
        try:
            self._db["observer_config"] = {
                "update_interval": self._update_interval
            }
        except Exception:
            pass
    
    def track_stock(self, stock_code: str):
        """跟踪股票"""
        self._tracked_stocks.add(stock_code)
        log.info(f"开始跟踪股票: {stock_code}")
    
    def untrack_stock(self, stock_code: str):
        """取消跟踪"""
        self._tracked_stocks.discard(stock_code)
        log.info(f"取消跟踪股票: {stock_code}")
    
    def register_price_callback(self, callback: Callable[[str, float], None]):
        """注册价格更新回调"""
        self._price_callbacks.append(callback)
    
    def start(self):
        """启动观察"""
        if self._running:
            log.warning("MarketDataObserver 已在运行")
            return
        
        self._running = True
        self._stop_event.clear()
        
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        log.info(f"MarketDataObserver 已启动 (更新间隔: {self._update_interval}s)")
    
    def stop(self):
        """停止观察"""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=5)
        
        log.info("MarketDataObserver 已停止")
    
    def _run_loop(self):
        """主循环"""
        while self._running and not self._stop_event.is_set():
            try:
                self._update_prices()
            except Exception as e:
                log.error(f"更新价格失败: {e}")
            
            self._stop_event.wait(self._update_interval)
    
    def _update_prices(self):
        """更新所有跟踪股票的价格"""
        if not self._tracked_stocks:
            return
        
        for stock_code in list(self._tracked_stocks):
            price = self._fetch_price(stock_code)
            if price > 0:
                self._last_prices[stock_code] = price
                
                for callback in self._price_callbacks:
                    try:
                        callback(stock_code, price)
                    except Exception as e:
                        log.error(f"价格回调失败: {e}")
    
    def _fetch_price(self, stock_code: str) -> float:
        """获取股票价格
        
        尝试多种方式获取价格：
        1. 从雪球 MCP 获取
        2. 从数据源获取
        3. 使用模拟价格
        """
        try:
            from deva.naja.datasource import get_datasource_manager
            
            mgr = get_datasource_manager()
            datasources = mgr.list_all()
            
            for ds in datasources:
                try:
                    if hasattr(ds, 'get_latest_price'):
                        price = ds.get_latest_price(stock_code)
                        if price and price > 0:
                            return price
                except Exception:
                    continue
        
        except Exception as e:
            log.debug(f"从数据源获取价格失败: {e}")
        
        try:
            from deva import xueqiu
            quote = xueqiu.get_quote(stock_code)
            if quote and quote.get('current'):
                return float(quote.get('current'))
        except Exception:
            pass
        
        last = self._last_prices.get(stock_code)
        if last:
            return last * (1 + (time.time() % 100 - 50) / 10000)
        
        return 0.0
    
    def get_price(self, stock_code: str) -> float:
        """获取股票当前价格"""
        return self._last_prices.get(stock_code, 0.0)
    
    def get_all_prices(self) -> Dict[str, float]:
        """获取所有跟踪股票的价格"""
        return dict(self._last_prices)
    
    def set_update_interval(self, seconds: float):
        """设置更新间隔"""
        self._update_interval = max(1.0, seconds)
        self._save_config()
    
    def get_status(self) -> dict:
        """获取状态"""
        return {
            "running": self._running,
            "update_interval": self._update_interval,
            "tracked_stocks": list(self._tracked_stocks),
            "prices": self._last_prices
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


from typing import Callable
