"""
Portfolio - 持仓与自选股统一入口

Layer 2: 我们的价值追求层核心数据结构

整合：
- 持仓 (Portfolio holdings): 实际持有的股票
- 自选股 (Watchlist): 我们关注但未持有的股票

职责：
- 提供持仓和自选股的统一查询接口
- 从持仓/自选 → 关联的 block 和 narrative
- 计算持仓/自选的行业配置

作者: AI
日期: 2026-04-05
"""

from __future__ import annotations
import time
from typing import Dict, List, Optional, Set, Any, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from deva.naja.bandit.portfolio_manager import Portfolio, PortfolioManager

from deva import NB


WATCHLIST_TABLE = "naja_watchlist"


@dataclass
class StockInfo:
    """股票信息"""
    code: str
    name: str
    account: str = ""
    source: str = "portfolio"
    entry_price: float = 0.0
    current_price: float = 0.0
    quantity: float = 0.0
    return_pct: float = 0.0


@dataclass
class PortfolioSummary:
    """持仓/自选汇总"""
    holdings: List[StockInfo]
    watchlist: List[StockInfo]
    all_codes: Set[str]
    holding_codes: Set[str]
    watchlist_codes: Set[str]
    industry_alloc: Dict[str, float]
    block_alloc: Dict[str, float]


class Portfolio:
    """
    持仓与自选股统一视图

    使用方式:

        pf = Portfolio()

        # 获取汇总
        summary = pf.get_summary()
        print(f"持仓: {summary.holding_codes}")
        print(f"自选: {summary.watchlist_codes}")

        # 获取持仓关联的block
        holding_blocks = pf.get_holding_blocks()
        print(f"持仓关联的block: {holding_blocks}")

        # 获取自选股关联的block
        watchlist_blocks = pf.get_watchlist_blocks()
        print(f"自选关联的block: {watchlist_blocks}")
    """

    _instance: Optional["Portfolio"] = None

    def __new__(cls) -> "Portfolio":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._pm: Optional["PortfolioManager"] = None
        self._watchlist_cache: Optional[Dict[str, Any]] = None
        self._watchlist_load_time: float = 0.0
        self._initialized = True

    def _get_pm(self) -> "PortfolioManager":
        """延迟导入 PortfolioManager"""
        if self._pm is None:
            from deva.naja.bandit.portfolio_manager import get_portfolio_manager
            self._pm = get_portfolio_manager()
        return self._pm

    def _load_watchlist(self) -> Dict[str, Any]:
        """加载自选股数据（带缓存，5分钟过期）"""
        now = time.time()
        if self._watchlist_cache and (now - self._watchlist_load_time) < 300:
            return self._watchlist_cache

        watchlist_data = NB(WATCHLIST_TABLE).all() or {}
        self._watchlist_cache = watchlist_data
        self._watchlist_load_time = now
        return watchlist_data

    def get_holdings(self, account: str = "Spark") -> List[StockInfo]:
        """获取持仓股票列表"""
        pm = self._get_pm()
        portfolio = pm.get_us_portfolio(account)
        if not portfolio:
            return []

        holdings = []
        for pos in portfolio.get_open_positions():
            holdings.append(StockInfo(
                code=pos.stock_code,
                name=pos.stock_name,
                account=account,
                source="portfolio",
                entry_price=pos.entry_price,
                current_price=pos.current_price,
                quantity=pos.quantity,
                return_pct=pos.return_pct,
            ))
        return holdings

    def get_watchlist(self) -> List[StockInfo]:
        """获取自选股列表"""
        watchlist_data = self._load_watchlist()
        watchlist = []

        stocks = watchlist_data.get("stocks", [])
        for item in stocks:
            if isinstance(item, dict) and "code" in item:
                watchlist.append(StockInfo(
                    code=item["code"],
                    name=item.get("name", item["code"]),
                    account="",
                    source="watchlist",
                ))

        others = watchlist_data.get("others", [])
        for item in others:
            if isinstance(item, dict) and "code" in item:
                watchlist.append(StockInfo(
                    code=item["code"],
                    name=item.get("name", item["code"]),
                    account="",
                    source="watchlist",
                ))

        return watchlist

    def get_all_codes(self) -> Set[str]:
        """获取所有关注股票代码（持仓+自选）"""
        holdings = self.get_holdings()
        watchlist = self.get_watchlist()
        return {s.code for s in holdings} | {s.code for s in watchlist}

    def get_holding_codes(self) -> Set[str]:
        """获取持仓股票代码"""
        return {s.code for s in self.get_holdings()}

    def get_watchlist_codes(self) -> Set[str]:
        """获取自选股代码"""
        return {s.code for s in self.get_watchlist()}

    def get_summary(self) -> PortfolioSummary:
        """获取完整的持仓+自选汇总"""
        holdings = self.get_holdings()
        watchlist = self.get_watchlist()
        holding_codes = {s.code for s in holdings}
        watchlist_codes = {s.code for s in watchlist}
        all_codes = holding_codes | watchlist_codes

        from deva.naja.bandit.stock_sector_map import get_stock_sector_map
        sm = get_stock_sector_map()

        industry_alloc: Dict[str, float] = {}
        block_alloc: Dict[str, float] = {}
        total_value = 0.0

        for holding in holdings:
            value = holding.quantity * holding.current_price
            if value <= 0:
                continue
            total_value += value

            metadata = sm.get_metadata(holding.code)
            if metadata:
                ic = metadata.industry_code
                industry_alloc[ic] = industry_alloc.get(ic, 0.0) + value
                for block in metadata.blocks:
                    block_alloc[block] = block_alloc.get(block, 0.0) + value

        if total_value > 0:
            industry_alloc = {k: v / total_value for k, v in industry_alloc.items()}
            block_alloc = {k: v / total_value for k, v in block_alloc.items()}

        return PortfolioSummary(
            holdings=holdings,
            watchlist=watchlist,
            all_codes=all_codes,
            holding_codes=holding_codes,
            watchlist_codes=watchlist_codes,
            industry_alloc=industry_alloc,
            block_alloc=block_alloc,
        )

    def get_holding_blocks(self) -> Set[str]:
        """获取持仓关联的block"""
        summary = self.get_summary()
        return set(summary.block_alloc.keys())

    def get_watchlist_blocks(self) -> Set[str]:
        """获取自选股关联的block"""
        from deva.naja.bandit.stock_sector_map import get_stock_sector_map
        sm = get_stock_sector_map()
        blocks: Set[str] = set()
        for code in self.get_watchlist_codes():
            blocks_list = sm.get_stock_blocks(code)
            blocks.update(blocks_list)
        return blocks

    def get_all_blocks(self) -> Set[str]:
        """获取所有持仓+自选关联的block"""
        return self.get_holding_blocks() | self.get_watchlist_blocks()

    def get_holding_narratives(self) -> Dict[str, float]:
        """获取持仓关联的叙事（按叙事→权重）"""
        from deva.naja.bandit.stock_sector_map import get_stock_sector_map
        sm = get_stock_sector_map()
        narrative_weights: Dict[str, float] = {}
        for code in self.get_holding_codes():
            narrative = sm.get_stock_narrative(code)
            if narrative:
                narrative_weights[narrative] = narrative_weights.get(narrative, 0.0) + 1.0
        if narrative_weights:
            max_w = max(narrative_weights.values())
            narrative_weights = {k: v / max_w for k, v in narrative_weights.items()}
        return narrative_weights

    def get_watchlist_narratives(self) -> Dict[str, float]:
        """获取自选股关联的叙事"""
        from deva.naja.bandit.stock_sector_map import get_stock_sector_map
        sm = get_stock_sector_map()
        narrative_weights: Dict[str, float] = {}
        for code in self.get_watchlist_codes():
            narrative = sm.get_stock_narrative(code)
            if narrative:
                narrative_weights[narrative] = narrative_weights.get(narrative, 0.0) + 1.0
        if narrative_weights:
            max_w = max(narrative_weights.values())
            narrative_weights = {k: v / max_w for k, v in narrative_weights.items()}
        return narrative_weights

    def get_all_narratives(self) -> Dict[str, float]:
        """获取所有持仓+自选关联的叙事"""
        all_narratives: Dict[str, float] = {}
        for d in [self.get_holding_narratives(), self.get_watchlist_narratives()]:
            for k, v in d.items():
                all_narratives[k] = all_narratives.get(k, 0.0) + v
        if all_narratives:
            max_w = max(all_narratives.values())
            all_narratives = {k: v / max_w for k, v in all_narratives.items()}
        return all_narratives

    def invalidate_cache(self) -> None:
        """使缓存失效，下次调用时重新加载"""
        self._watchlist_cache = None


_portfolio_instance: Optional[Portfolio] = None


def get_portfolio() -> Portfolio:
    """获取Portfolio单例"""
    global _portfolio_instance
    if _portfolio_instance is None:
        _portfolio_instance = Portfolio()
    return _portfolio_instance
