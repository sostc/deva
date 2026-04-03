"""
USStockPriceManager - 智能美股价格管理器

特性：
- 开盘时间：从新浪/雪球获取实时价格
- 休市时间：使用持久化的最后价格
- 自动持久化
- 统一表存储（所有股票存在一个表）
"""

import time
import asyncio
import logging
import aiohttp
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict

from deva import NB

log = logging.getLogger(__name__)


@dataclass
class PriceSnapshot:
    """价格快照"""
    code: str
    current: float
    prev_close: float
    update_time: float


class USStockPriceManager:
    """
    智能美股价格管理器

    规则：
    1. 开盘时间（trading phase）：从新浪获取实时价格
    2. 休市时间（pre_market/post_market/closed）：使用持久化的最后价格
    3. 自动持久化最新价格到 NB（统一表存储）
    4. 订阅美股交易时钟信号自动更新价格
    """

    PRICE_TABLE = "us_stock_prices"
    LAST_UPDATE_KEY = "us_stock_price_last_update"

    def __init__(self):
        self._last_prices: Dict[str, float] = {}
        self._last_prev_closes: Dict[str, float] = {}
        self._last_update_time: float = 0.0
        self._initialized = False
        self._price_db: Optional[NB] = None

    def _get_price_db(self) -> NB:
        """获取价格数据库（延迟初始化）"""
        if self._price_db is None:
            self._price_db = NB(self.PRICE_TABLE)
        return self._price_db

    def is_market_open(self) -> bool:
        """检查美股是否开盘（只考虑 trading 阶段）"""
        try:
            from deva.naja.radar.global_market_config import get_market_session_manager
            mgr = get_market_session_manager()
            phase = mgr.get_us_trading_phase()
            is_open = phase == "trading"
            log.debug(f"[PriceManager] 美股阶段: {phase}, 开盘: {is_open}")
            return is_open
        except Exception as e:
            log.warning(f"[PriceManager] 检查开盘状态失败: {e}")
            return False

    def _get_market_phase(self) -> str:
        """获取美股市场阶段"""
        try:
            from deva.naja.radar.global_market_config import get_market_session_manager
            mgr = get_market_session_manager()
            return mgr.get_us_trading_phase()
        except:
            return "unknown"

    def get_price_map(self) -> Dict[str, float]:
        """获取当前价格映射"""
        return self._last_prices.copy()

    def get_prev_close_map(self) -> Dict[str, float]:
        """获取昨收价映射"""
        return self._last_prev_closes.copy()

    def get_snapshot(self, code: str) -> Optional[PriceSnapshot]:
        """获取单个股票价格快照"""
        if code not in self._last_prices:
            return None
        return PriceSnapshot(
            code=code,
            current=self._last_prices[code],
            prev_close=self._last_prev_closes.get(code, 0.0),
            update_time=self._last_update_time
        )

    def get_stale_duration(self) -> float:
        """获取价格过期时长（秒）"""
        if self._last_update_time == 0:
            return float('inf')
        return time.time() - self._last_update_time

    def ingest_prices(self, price_map: Dict[str, float], prev_close_map: Optional[Dict[str, float]] = None):
        """从外部实时链路注入价格并持久化"""
        if not price_map:
            return

        prev_close_map = prev_close_map or {}
        now_ts = time.time()

        for code, current in price_map.items():
            prev_close = prev_close_map.get(code, current)
            self._last_prices[code] = float(current)
            self._last_prev_closes[code] = float(prev_close) if prev_close is not None else float(current)
            self._last_update_time = max(self._last_update_time, now_ts)

        self._persist_all_prices()

    def _persist_all_prices(self):
        """持久化所有股票价格到统一表"""
        try:
            db = self._get_price_db()
            now_ts = time.time()

            all_prices = {}
            for code in self._last_prices:
                all_prices[code] = {
                    "current": self._last_prices[code],
                    "prev_close": self._last_prev_closes.get(code, self._last_prices[code]),
                    "update_time": now_ts
                }

            db["prices"] = all_prices
            db[self.LAST_UPDATE_KEY] = now_ts

            log.debug(f"[PriceManager] 持久化 {len(all_prices)} 个股票价格到统一表")
        except Exception as e:
            log.warning(f"[PriceManager] 持久化价格失败: {e}")

    def _load_persisted_prices(self) -> Dict[str, PriceSnapshot]:
        """从统一表加载所有股票价格"""
        results = {}
        try:
            db = self._get_price_db()
            all_prices = db.get("prices", {})

            if not all_prices:
                return results

            for code, data in all_prices.items():
                if isinstance(data, dict):
                    snapshot = PriceSnapshot(
                        code=code,
                        current=float(data.get("current", 0)),
                        prev_close=float(data.get("prev_close", 0)),
                        update_time=float(data.get("update_time", 0))
                    )
                    results[code] = snapshot

        except Exception as e:
            log.debug(f"[PriceManager] 加载持久化价格失败: {e}")
        return results

    def load_persisted_prices(self, stock_codes: List[str]):
        """从持久化加载指定股票价格"""
        all_snapshots = self._load_persisted_prices()

        for code in stock_codes:
            if code in all_snapshots:
                snapshot = all_snapshots[code]
                self._last_prices[code] = snapshot.current
                self._last_prev_closes[code] = snapshot.prev_close
                self._last_update_time = max(self._last_update_time, snapshot.update_time)

        if self._last_prices:
            log.info(f"[PriceManager] 从持久化加载 {len(self._last_prices)} 个股票价格")

    async def fetch_from_sina(self, stock_codes: List[str]) -> Dict[str, PriceSnapshot]:
        """从新浪获取价格"""
        from deva.naja.attention.data.global_market_futures import GlobalMarketAPI

        results = {}
        sina_codes = [f"gb_{code}" for code in stock_codes]

        try:
            api = GlobalMarketAPI()
            data = await api.fetch(sina_codes)

            for code in stock_codes:
                if code in data:
                    md = data[code]
                    snapshot = PriceSnapshot(
                        code=code,
                        current=md.current,
                        prev_close=md.prev_close,
                        update_time=time.time()
                    )
                    results[code] = snapshot
                    log.debug(f"[PriceManager] 新浪获取 {code}: ${md.current:.2f}")
        except Exception as e:
            log.warning(f"[PriceManager] 新浪获取价格失败: {e}")

        return results

    async def fetch_from_xueqiu(self, stock_codes: List[str]) -> Dict[str, PriceSnapshot]:
        """从雪球获取价格（备用）"""
        results = {}

        try:
            for code in stock_codes:
                result = await self._fetch_single_from_xueqiu(code)
                if result:
                    results[code] = result
        except Exception as e:
            log.warning(f"[PriceManager] 雪球获取价格失败: {e}")

        return results

    async def _fetch_single_from_xueqiu(self, code: str) -> Optional[PriceSnapshot]:
        """从雪球获取单个股票价格"""
        try:
            import os
            token = os.environ.get("XUEQIU_TOKEN", "")
            if not token:
                return None

            url = f"https://stock.xueqiu.com/v5/stock/quote.json?symbol={code.upper()}&extend=detail"
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Cookie": token,
                "Referer": "https://xueqiu.com",
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data and "data" in data and "quote" in data["data"]:
                            quote = data["data"]["quote"]
                            return PriceSnapshot(
                                code=code,
                                current=float(quote["current"]),
                                prev_close=float(quote.get("last_close", quote["current"])),
                                update_time=time.time()
                            )
        except Exception:
            pass

        return None

    async def update_prices(
        self,
        stock_codes: List[str],
        force: bool = False
    ) -> Dict[str, PriceSnapshot]:
        """
        更新价格（智能策略）

        Args:
            stock_codes: 股票代码列表
            force: 是否强制刷新（忽略市场状态）

        Returns:
            价格快照字典
        """
        results = {}

        phase = self._get_market_phase()
        is_open = phase == "trading"

        if is_open or force:
            log.debug(f"[PriceManager] 开盘时间，从新浪获取价格 (阶段: {phase})")
            results = await self.fetch_from_sina(stock_codes)

            if not results:
                log.debug(f"[PriceManager] 新浪获取失败，尝试雪球")
                results = await self.fetch_from_xueqiu(stock_codes)
        else:
            log.debug(f"[PriceManager] 休市时间 (阶段: {phase})，使用持久化价格")
            self.load_persisted_prices(stock_codes)

            for code in stock_codes:
                if code in self._last_prices:
                    results[code] = PriceSnapshot(
                        code=code,
                        current=self._last_prices[code],
                        prev_close=self._last_prev_closes.get(code, self._last_prices[code]),
                        update_time=self._last_update_time
                    )

        if results:
            for code, snapshot in results.items():
                self._last_prices[code] = snapshot.current
                self._last_prev_closes[code] = snapshot.prev_close
                self._last_update_time = max(self._last_update_time, snapshot.update_time)
            self._persist_all_prices()

        stale_duration = self.get_stale_duration()
        if stale_duration > 300:
            log.warning(f"[PriceManager] 价格数据过期 {stale_duration:.0f} 秒未更新")

        return results


_price_manager: Optional[USStockPriceManager] = None


def get_us_stock_price_manager() -> USStockPriceManager:
    """获取美股价格管理器（单例）"""
    global _price_manager
    if _price_manager is None:
        _price_manager = USStockPriceManager()
    return _price_manager


async def smart_update_us_prices(stock_codes: List[str]) -> Dict[str, PriceSnapshot]:
    """智能更新美股价格（便捷函数）"""
    manager = get_us_stock_price_manager()
    return await manager.update_prices(stock_codes)