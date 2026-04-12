"""
异步实盘数据获取器 + 全局实例工厂

AsyncRealtimeDataFetcher: 供 HotspotSystem 使用的异步版本
get_data_fetcher(): 获取全局 RealtimeDataFetcher 实例
"""

import asyncio
import logging
from typing import Optional

from .fetch_config import FetchConfig

log = logging.getLogger(__name__)


class AsyncRealtimeDataFetcher:
    """
    异步实盘数据获取器 - 供 HotspotSystem 使用

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


def get_data_fetcher():
    """获取全局 RealtimeDataFetcher 实例"""
    from deva.naja.register import SR
    return SR('realtime_data_fetcher')
