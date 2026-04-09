"""
Portfolio - 持仓与自选股统一入口

═══════════════════════════════════════════════════════════════════════════
                              架 构 定 位
═══════════════════════════════════════════════════════════════════════════

【我们-核心】Portfolio 是"我们的价值追求"层的核心数据入口

    Portfolio 代表：
        持仓 (holdings)    = 我们实际投了钱的地方
        自选股 (watchlist) = 我们关注但还没买的地方
        followed_blocks    = 我们主动 follow 的 block
        followed_narratives = 我们主动 follow 的叙事

    这是"我们的世界"的核心，所有其他模块都要与这个对比

═══════════════════════════════════════════════════════════════════════════
                              核 心 职 能
═══════════════════════════════════════════════════════════════════════════

    1. 提供持仓和自选股的统一查询接口
    2. 从持仓/自选 → 关联的 block（通过 StockSectorMap）
    3. 从持仓/自选 → 关联的 narrative（通过 NarrativeBlockLinker）
    4. 计算持仓/自选的行业配置和 block 配置

═══════════════════════════════════════════════════════════════════════════
                              与其他模块的关系
═══════════════════════════════════════════════════════════════════════════

    ConvictionValidator.validate(portfolio=pf.get_summary(), ...)
        → 用 Portfolio 数据检测外部世界与我们的差异

    AttentionFusion.fuse(portfolio_summary=pf.get_summary(), ...)
        → 用 Portfolio 数据做融合

    FocusManager.follow_stock() → 自动加入 watchlist
    FocusManager.follow_narrative() → 更新 followed_narratives

═══════════════════════════════════════════════════════════════════════════
                              数据来源
═══════════════════════════════════════════════════════════════════════════

    holdings    ← PortfolioManager（真实持仓）
    watchlist   ← NB("naja_watchlist")（自选股）
    followed_blocks ← NB("naja_focus_config")（主动关注的block）
    followed_narratives ← NB("naja_focus_config")（主动关注的叙事）
"""

from __future__ import annotations
import logging
import time
from typing import Dict, List, Optional, Set, Any, TYPE_CHECKING
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from deva.naja.bandit.portfolio_manager import Portfolio, PortfolioManager

from deva import NB


WATCHLIST_TABLE = "naja_watchlist"


@dataclass
class StockInfo:
    """
    【我们】股票信息

    字段说明：
        code           = 股票代码
        name           = 股票名称
        account        = 账户
        source         = 来源：portfolio持仓 / watchlist自选
        entry_price   = 入场价格
        current_price = 当前价格
        quantity       = 数量
        return_pct    = 收益率
    """
    code: str                             # 【标识】股票代码
    name: str                             # 【显示】股票名称
    account: str = ""                     # 【账户】账户
    source: str = "portfolio"             # 【来源】portfolio/watchlist
    entry_price: float = 0.0             # 【价格】入场价
    current_price: float = 0.0            # 【价格】当前价
    quantity: float = 0.0                 # 【数量】持仓数量
    return_pct: float = 0.0              # 【收益】收益率


@dataclass
class PortfolioSummary:
    """
    【我们-核心】持仓/自选汇总

    字段说明：
        holdings         = 持仓列表
        watchlist       = 自选股列表
        all_codes       = 所有股票代码
        holding_codes   = 持仓代码集合
        watchlist_codes = 自选股代码集合
        industry_alloc  = 行业配置（industry_code → 权重）
        block_alloc    = block配置（block_id → 权重）
    """
    holdings: List[StockInfo]             # 【我们】持仓列表
    watchlist: List[StockInfo]            # 【我们】自选股列表
    all_codes: Set[str]                   # 【汇总】所有代码
    holding_codes: Set[str]                # 【我们】持仓代码
    watchlist_codes: Set[str]             # 【我们】自选股代码
    industry_alloc: Dict[str, float]       # 【行业】行业配置
    block_alloc: Dict[str, float]         # 【block】block配置


class Portfolio:
    """
    【我们-核心】持仓与自选股统一视图

    使用方式:

        pf = Portfolio()

        # 获取汇总
        summary = pf.get_summary()
        log.info(f"持仓: {summary.holding_codes}")
        log.info(f"自选: {summary.watchlist_codes}")

        holding_blocks = pf.get_holding_blocks()
        log.info(f"持仓关联的block: {holding_blocks}")

        watchlist_blocks = pf.get_watchlist_blocks()
        log.info(f"自选关联的block: {watchlist_blocks}")
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

        nb = NB(WATCHLIST_TABLE)
        watchlist_data = dict(nb) if len(nb) > 0 else {}
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

        from deva.naja.bandit.stock_block_map import get_stock_block_map
        sm = get_stock_block_map()

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
        from deva.naja.bandit.stock_block_map import get_stock_block_map
        sm = get_stock_block_map()
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
        from deva.naja.bandit.stock_block_map import get_stock_block_map
        sm = get_stock_block_map()
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
        from deva.naja.bandit.stock_block_map import get_stock_block_map
        sm = get_stock_block_map()
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
