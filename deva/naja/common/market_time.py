"""
MarketTimeService - 市场时间服务

提供统一的市场时间访问接口：
- 实盘模式：返回系统当前时间
- 回测/实验模式：返回回放数据的时间

使用方式：
    >>> from deva.naja.common.market_time import get_market_time_service
    >>> mts = get_market_time_service()
    >>> market_time = mts.get_market_time()
    >>> market_dt = mts.get_market_datetime()
"""

import threading
import time
from datetime import datetime
from typing import Optional

log = __import__('logging').getLogger(__name__)


class MarketTimeService:
    """
    全局市场时间服务（单例）

    在回测/实验模式下，数据来自历史回放，此时：
    - 市场时间 = 回放数据的时间戳
    - 所有交易记录应使用市场时间

    在实盘模式下：
    - 市场时间 = 系统当前时间
    """

    _instance: Optional['MarketTimeService'] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return

        self._market_time: float = 0.0
        self._is_replay_mode: bool = False
        self._system_start_time: float = time.time()
        self._last_update_time: float = 0.0

        self._initialized = True
        log.info("[MarketTimeService] 市场时间服务初始化完成")

    def set_market_time(self, timestamp: float):
        """由数据源（ReplayScheduler）调用，更新当前市场时间"""
        self._market_time = timestamp
        self._last_update_time = time.time()
        log.debug(f"[MarketTimeService] 市场时间更新: {datetime.fromtimestamp(timestamp)}")

    def get_market_time(self) -> float:
        """
        获取当前市场时间戳

        回测/实验模式：返回回放数据的时间戳
        实盘模式：返回系统当前时间
        """
        if self._is_replay_mode:
            return self._market_time if self._market_time > 0 else time.time()
        return time.time()

    def get_market_datetime(self) -> datetime:
        """获取当前市场时间的 datetime 对象"""
        return datetime.fromtimestamp(self.get_market_time())

    def get_system_time(self) -> float:
        """获取系统时间（始终返回真实的系统时间）"""
        return time.time()

    def get_system_datetime(self) -> datetime:
        """获取系统时间的 datetime 对象"""
        return datetime.fromtimestamp(self.get_system_time())

    def set_replay_mode(self, enabled: bool):
        """设置回放模式"""
        old_mode = self._is_replay_mode
        self._is_replay_mode = enabled
        if old_mode != enabled:
            log.info(f"[MarketTimeService] 回放模式: {old_mode} -> {enabled}")

    def is_replay_mode(self) -> bool:
        """检查是否处于回放模式"""
        return self._is_replay_mode

    def get_info(self) -> dict:
        """获取状态信息"""
        return {
            "is_replay_mode": self._is_replay_mode,
            "market_time": self._market_time,
            "market_datetime": datetime.fromtimestamp(self._market_time).isoformat() if self._market_time > 0 else None,
            "system_time": self._system_start_time,
            "last_update": self._last_update_time,
        }


_market_time_service: Optional[MarketTimeService] = None
_market_time_service_lock = threading.Lock()


def get_market_time_service() -> MarketTimeService:
    """获取市场时间服务单例"""
    global _market_time_service
    if _market_time_service is None:
        with _market_time_service_lock:
            if _market_time_service is None:
                _market_time_service = MarketTimeService()
    return _market_time_service


def get_market_time() -> float:
    """快捷函数：获取当前市场时间"""
    return get_market_time_service().get_market_time()


def get_market_datetime() -> datetime:
    """快捷函数：获取当前市场时间（datetime）"""
    return get_market_time_service().get_market_datetime()


def set_replay_mode(enabled: bool):
    """快捷函数：设置回放模式"""
    get_market_time_service().set_replay_mode(enabled)
