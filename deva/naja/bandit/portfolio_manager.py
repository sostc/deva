"""PortfolioManager - Bandit系统/持仓管理/仓位

别名/关键词: 持仓管理、美股持仓、仓位、portfolio manager

多账户持仓管理器

支持多账户、多市场的持仓管理：
- A股账户（虚拟测试）：使用 VirtualPortfolio
- 美股账户（Spark、Cutie）：使用 USStockPortfolio

用法:
    pm = get_portfolio_manager()

    # 获取账户
    spark = pm.get_account("Spark")
    cutie = pm.get_account("Cutie")
    a股 = pm.get_account("虚拟测试")

    # 获取持仓
    positions = spark.get_all_positions()
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

from deva import NB

log = logging.getLogger(__name__)

PORTFOLIO_MANAGER_TABLE = "naja_bandit_portfolio_manager"
UNIFIED_POSITIONS_TABLE = "naja_bandit_positions"


@dataclass
class USStockPosition:
    """美股持仓"""
    position_id: str
    account_name: str
    stock_code: str
    stock_name: str
    entry_price: float
    current_price: float
    quantity: float
    entry_time: float
    last_update_time: float
    status: str = "OPEN"
    exit_price: float = 0.0
    exit_time: float = 0.0
    prev_close: float = 0.0

    @property
    def return_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price * 100

    @property
    def profit_loss(self) -> float:
        return (self.current_price - self.entry_price) * self.quantity

    @property
    def market_value(self) -> float:
        return self.current_price * self.quantity

    @property
    def today_profit_loss(self) -> float:
        if self.prev_close <= 0:
            return 0.0
        return (self.current_price - self.prev_close) * self.quantity

    @property
    def today_return_pct(self) -> float:
        if self.prev_close <= 0:
            return 0.0
        return (self.current_price - self.prev_close) / self.prev_close * 100

    @property
    def holding_days(self) -> float:
        return (time.time() - self.entry_time) / 86400


class USStockPortfolio:
    """美股组合（简化版，无止盈止损）

    特点：
    - 无止盈止损逻辑（长期持有）
    - 无策略关联（自主/手动交易）
    - 支持价格批量更新
    - 支持融资账户（总资产、融资负债）
    - 使用统一持仓表 naja_bandit_positions
    """

    def __init__(self, account_name: str):
        self.account_name = account_name
        self._positions: Dict[str, USStockPosition] = {}
        self._lock = threading.RLock()
        self._db = NB(UNIFIED_POSITIONS_TABLE)
        self._position_callbacks: List[Callable[[str, USStockPosition], None]] = []
        self._equity = 0.0
        self._load_positions()

    def _load_positions(self):
        try:
            accounts_data = self._db.get("accounts", {})
            account_data = accounts_data.get(self.account_name, {})
            positions_data = account_data.get("positions", {})

            for pos_id, pos_data in positions_data.items():
                if isinstance(pos_data, dict):
                    self._positions[pos_id] = USStockPosition(**pos_data)

            self._equity = account_data.get("equity", 0.0)
            log.info(f"[{self.account_name}] 加载 {len(self._positions)} 个持仓, 净资产=${self._equity:.2f}")
        except Exception as e:
            log.error(f"[{self.account_name}] 加载持仓失败: {e}")

    def _load_account_info(self):
        try:
            accounts_data = self._db.get("accounts", {})
            account_data = accounts_data.get(self.account_name, {})
            self._equity = account_data.get("equity", 0.0)
            log.info(f"[{self.account_name}] 加载账户信息: 净资产=${self._equity:.2f}")
        except Exception as e:
            log.error(f"[{self.account_name}] 加载账户信息失败: {e}")

    def _save_account_info(self):
        try:
            accounts_data = self._db.get("accounts", {})
            if self.account_name not in accounts_data:
                accounts_data[self.account_name] = {}
            accounts_data[self.account_name]["equity"] = self._equity
            accounts_data[self.account_name]["account_type"] = "us"
            self._db["accounts"] = accounts_data
        except Exception as e:
            log.error(f"[{self.account_name}] 保存账户信息失败: {e}")

    def _save_positions(self):
        try:
            accounts_data = self._db.get("accounts", {})
            if self.account_name not in accounts_data:
                accounts_data[self.account_name] = {"account_type": "us", "equity": self._equity}

            positions_data = {pos_id: vars(pos) for pos_id, pos in self._positions.items()}
            accounts_data[self.account_name]["positions"] = positions_data
            self._db["accounts"] = accounts_data
        except Exception as e:
            log.error(f"[{self.account_name}] 保存持仓失败: {e}")

    def register_position_callback(self, callback: Callable[[str, USStockPosition], None]):
        self._position_callbacks.append(callback)

    def add_position(
        self,
        stock_code: str,
        stock_name: str,
        price: float,
        quantity: float,
        entry_time: float = None,
    ) -> Optional[USStockPosition]:
        with self._lock:
            if quantity <= 0:
                log.warning(f"[{self.account_name}] 无效参数: quantity={quantity}")
                return None

            if price < 0:
                log.warning(f"[{self.account_name}] 无效参数: price={price}")
                return None

            position_id = f"US_{self.account_name}_{stock_code}_{int(time.time() * 1000)}"
            now = entry_time or time.time()

            position = USStockPosition(
                position_id=position_id,
                account_name=self.account_name,
                stock_code=stock_code,
                stock_name=stock_name,
                entry_price=price,
                current_price=price,
                quantity=quantity,
                entry_time=now,
                last_update_time=now,
                status="OPEN",
            )

            self._positions[position_id] = position
            self._save_positions()

            if price > 0:
                log.info(f"[{self.account_name}] 添加持仓: {stock_name}({stock_code}) x{quantity} @ ${price:.2f}")
            else:
                log.info(f"[{self.account_name}] 添加持仓: {stock_name}({stock_code}) x{quantity} (价格待更新)")

            return position

    def update_price(self, stock_code: str, current_price: float, prev_close: float = 0.0) -> List[USStockPosition]:
        with self._lock:
            updated = []
            for pos_id, pos in self._positions.items():
                if pos.stock_code == stock_code and pos.status == "OPEN":
                    pos.current_price = current_price
                    if prev_close > 0:
                        pos.prev_close = prev_close
                    pos.last_update_time = time.time()
                    updated.append(pos)

                    for callback in self._position_callbacks:
                        try:
                            callback(pos_id, pos)
                        except Exception as e:
                            log.error(f"[{self.account_name}] 回调失败: {e}")

            if updated:
                self._save_positions()
                log.debug(f"[{self.account_name}] 更新 {stock_code} @ ${current_price:.2f}")

            return updated

    def update_prices_batch(self, price_map: Dict[str, float], prev_close_map: Dict[str, float] = None) -> int:
        count = 0
        prev_map = prev_close_map or {}
        for stock_code, price in price_map.items():
            prev = prev_map.get(stock_code, 0)
            if self.update_price(stock_code, price, prev):
                count += 1
        return count

    def sell_position(self, position_id: str, exit_price: float) -> Optional[USStockPosition]:
        with self._lock:
            position = self._positions.get(position_id)
            if not position or position.status != "OPEN":
                return None

            position.exit_price = exit_price
            position.current_price = exit_price
            position.status = "CLOSED"
            position.exit_time = time.time()

            self._save_positions()
            log.info(f"[{self.account_name}] 卖出: {position.stock_name}({position.stock_code}) "
                    f"收益率={position.return_pct:.2f}%")

            return position

    def get_position(self, position_id: str) -> Optional[USStockPosition]:
        return self._positions.get(position_id)

    def get_positions_by_stock(self, stock_code: str) -> List[USStockPosition]:
        return [p for p in self._positions.values()
                if p.stock_code == stock_code and p.status == "OPEN"]

    def get_all_positions(self, status: Optional[str] = None) -> List[USStockPosition]:
        if status is None:
            return list(self._positions.values())
        return [p for p in self._positions.values() if p.status == status]

    def get_open_positions(self) -> List[USStockPosition]:
        return self.get_all_positions(status="OPEN")

    def get_summary(self) -> dict:
        positions = self.get_open_positions()

        total_value = sum(p.market_value for p in positions) if positions else 0.0
        total_cost = sum(p.entry_price * p.quantity for p in positions) if positions else 0.0
        total_profit_loss = sum(p.profit_loss for p in positions) if positions else 0.0
        today_profit_loss = sum(p.today_profit_loss for p in positions) if positions else 0.0

        equity = self._equity
        margin_debt = max(0, total_value - equity)

        if positions:
            total_return_pct = (total_value - total_cost) / total_cost * 100 if total_cost > 0 else 0
        else:
            total_return_pct = 0.0

        return {
            "account_name": self.account_name,
            "total_value": total_value,
            "total_cost": total_cost,
            "total_profit_loss": total_profit_loss,
            "total_return_pct": total_return_pct,
            "today_profit_loss": today_profit_loss,
            "position_count": len(positions),
            "equity": equity,
            "margin_debt": margin_debt,
        }

    def set_equity(self, equity: float):
        """设置净资产"""
        self._equity = equity
        self._save_account_info()
        log.info(f"[{self.account_name}] 设置净资产: ${equity:.2f}")


class PortfolioManager:
    """多账户持仓管理器

    管理多个账户：
    - A股账户：使用 VirtualPortfolio（现有）
    - 美股账户：使用 USStockPortfolio（新）
    """

    def __init__(self):
        self._accounts: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._db = NB(PORTFOLIO_MANAGER_TABLE)
        self._us_portfolios: Dict[str, USStockPortfolio] = {}

        self._init_accounts()

    def _init_accounts(self):
        try:
            account_names = self._db.get("account_names", [])
            if not account_names:
                account_names = ["虚拟测试", "Spark", "Cutie"]
                self._db["account_names"] = account_names

            for name in account_names:
                if name == "虚拟测试":
                    from .virtual_portfolio import get_virtual_portfolio
                    self._accounts[name] = get_virtual_portfolio()
                else:
                    self._us_portfolios[name] = USStockPortfolio(name)
                    self._accounts[name] = self._us_portfolios[name]

            log.info(f"已初始化 {len(self._accounts)} 个账户: {list(self._accounts.keys())}")
        except Exception as e:
            log.error(f"初始化账户失败: {e}")

    def get_account(self, account_name: str) -> Optional[Any]:
        return self._accounts.get(account_name)

    def get_us_portfolio(self, account_name: str) -> Optional[USStockPortfolio]:
        return self._us_portfolios.get(account_name)

    def get_all_account_names(self) -> List[str]:
        return list(self._accounts.keys())

    def get_all_summaries(self) -> Dict[str, dict]:
        result = {}
        for name, account in self._accounts.items():
            if hasattr(account, 'get_summary'):
                result[name] = account.get_summary()
            else:
                result[name] = {"account_name": name, "type": "unknown"}
        return result

    def update_us_prices(self, price_map: Dict[str, float], prev_close_map: Dict[str, float] = None) -> Dict[str, int]:
        result = {}
        for name, portfolio in self._us_portfolios.items():
            count = portfolio.update_prices_batch(price_map, prev_close_map)
            if count > 0:
                result[name] = count
        return result

    async def smart_update_us_prices(self, force: bool = False) -> Dict[str, int]:
        """智能更新所有美股账户的价格

        使用 USStockPriceManager 根据市场状态智能获取价格

        Args:
            force: 是否强制获取（忽略市场状态）

        Returns:
            包含每个账户更新持仓数量的字典
        """
        from .us_stock_price_manager import get_us_stock_price_manager

        manager = get_us_stock_price_manager()

        all_codes = set()
        for portfolio in self._us_portfolios.values():
            for pos in portfolio.get_open_positions():
                all_codes.add(pos.stock_code)

        if not all_codes:
            return {}

        await manager.update_prices(list(all_codes), force=force)

        price_map = manager.get_price_map()
        prev_close_map = manager.get_prev_close_map()

        return self.update_us_prices(price_map, prev_close_map)

    def start_price_auto_update(self):
        """持仓价格自动更新已废弃

        美股价格更新已统一由 RealtimeDataFetcher 在美股交易时段自动获取并同步。
        无需单独调用此方法。
        """
        log.info("[PortfolioManager] 持仓价格更新已由 RealtimeDataFetcher 统一管理")


_portfolio_manager: Optional[PortfolioManager] = None
_portfolio_manager_lock = threading.Lock()


def get_portfolio_manager() -> PortfolioManager:
    global _portfolio_manager
    if _portfolio_manager is None:
        with _portfolio_manager_lock:
            if _portfolio_manager is None:
                _portfolio_manager = PortfolioManager()
    return _portfolio_manager


async def fetch_us_stock_price_xueqiu(stock_code: str) -> Optional[tuple]:
    """从雪球获取美股价格和昨收价"""
    try:
        import aiohttp
        import os

        token = os.environ.get("XUEQIU_TOKEN", "")
        if not token:
            log.debug(f"雪球 TOKEN 未设置，跳过 {stock_code}")
            return None

        url = f"https://stock.xueqiu.com/v5/stock/quote.json?symbol={stock_code.upper()}&extend=detail"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Cookie": token,
            "Referer": "https://xueqiu.com",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and "data" in data and "quote" in data["data"]:
                        quote = data["data"]["quote"]
                        current = float(quote["current"])
                        prev_close = float(quote.get("last_close", current))
                        return (current, prev_close)
    except Exception as e:
        log.debug(f"雪球获取 {stock_code} 失败: {e}")
    return None


async def fetch_us_stock_price_sina(stock_code: str) -> Optional[tuple]:
    """从新浪获取美股价格和昨收价"""
    try:
        from deva.naja.attention.data.global_market_futures import GlobalMarketAPI
        api = GlobalMarketAPI()
        code_map = {
            "nvda": "gb_nvda",
            "aapl": "gb_aapl",
            "tsla": "gb_tsla",
            "baba": "gb_baba",
            "msft": "gb_msft",
            "googl": "gb_googl",
            "amzn": "gb_amzn",
            "meta": "gb_meta",
        }
        sina_code = code_map.get(stock_code.lower())
        if not sina_code:
            return None
        data = await api.fetch([sina_code])
        if data:
            for md in data.values():
                return (md.current, md.prev_close)
    except Exception as e:
        log.warning(f"新浪获取 {stock_code} 失败: {e}")
    return None


async def fetch_us_stock_price(stock_code: str) -> Optional[tuple]:
    """获取美股价格和昨收价（优先雪球，其次新浪）"""
    result = await fetch_us_stock_price_xueqiu(stock_code)
    if result:
        return result
    return await fetch_us_stock_price_sina(stock_code)


def init_us_portfolios():
    """初始化美股账户持仓

    Spark: NVDA 2380股 (成本$168), CRWV 540股 (成本$102)，净资产 $193,495.26
    Cutie: BABA 100股 (成本$90)

    使用 USStockPriceManager 智能获取价格（根据市场状态）
    """
    pm = get_portfolio_manager()

    spark = pm.get_us_portfolio("Spark")
    cutie = pm.get_us_portfolio("Cutie")

    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    price_map = {}
    prev_close_map = {}

    from .us_stock_price_manager import get_us_stock_price_manager
    price_manager = get_us_stock_price_manager()

    stock_codes = ["nvda", "crwv", "baba"]
    loop.run_until_complete(price_manager.update_prices(stock_codes, force=True))
    price_map = price_manager.get_price_map()
    prev_close_map = price_manager.get_prev_close_map()

    if spark:
        if not spark.get_positions_by_stock("nvda"):
            spark.add_position("nvda", "英伟达", 168.0, 2380)
        if not spark.get_positions_by_stock("crwv"):
            spark.add_position("crwv", "CoreWeave", 102.0, 540)
        spark.set_equity(193495.26)
        spark.update_prices_batch(price_map, prev_close_map)
        log.info(f"[Spark] 初始化完成: {len(spark.get_all_positions())} 个持仓, 净资产=${193495.26:.2f}")

    if cutie:
        if not cutie.get_positions_by_stock("baba"):
            cutie.add_position("baba", "阿里巴巴", 90.0, 100)
        cutie.update_prices_batch(price_map, prev_close_map)
        log.info(f"[Cutie] 初始化完成: {len(cutie.get_all_positions())} 个持仓")
