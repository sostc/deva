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
    2. 从持仓/自选 → 关联的 block（通过 StockBlockMap）
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


def position_to_dict(pos: Any) -> Dict[str, Any]:
    """持仓对象 → 纯 dict（供 UI 消费，不把 dataclass 漏出去）。"""
    return {
        "position_id": getattr(pos, "position_id", ""),
        "stock_code": getattr(pos, "stock_code", ""),
        "stock_name": getattr(pos, "stock_name", ""),
        "account": getattr(pos, "account_name", ""),
        "entry_price": round(float(getattr(pos, "entry_price", 0.0) or 0.0), 4),
        "current_price": round(float(getattr(pos, "current_price", 0.0) or 0.0), 4),
        "quantity": float(getattr(pos, "quantity", 0.0) or 0.0),
        "return_pct": round(float(getattr(pos, "return_pct", 0.0) or 0.0), 2),
        "entry_time": float(getattr(pos, "entry_time", 0.0) or 0.0),
        "status": getattr(pos, "status", ""),
    }


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
        """获取**指定账户**的持仓股票列表。

        注意：账户不存在时返回 ``[]``——这与"该账户真的没有持仓"**不可区分**。
        需要判断到底是哪种情况，请用 :meth:`get_account_status`；
        要拿"我全部券商账户的持仓"，请用 :meth:`get_all_holdings`。
        """
        pm = self._get_pm()
        portfolio = pm.get_us_portfolio(account)
        if not portfolio:
            log.warning(
                "[Portfolio] 账户 %s 未初始化，持仓读作空 —— "
                "这与「真的没有持仓」不可区分，请用 get_account_status() 确认",
                account,
            )
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

    def get_all_holdings(self) -> List[StockInfo]:
        """合并**所有已初始化券商账户**的持仓（不含"虚拟测试"模拟盘）。

        钱通常散在多个账户里（实测：Spark 2 只 + FutuReal 9 只）——
        只看默认账户会漏掉大半持仓，新闻筛选就会把"我真正持有的票"的新闻
        错当成"外部机会"。同一标的跨账户出现时按 (code, account) 去重保留，
        不去合并数量（本方法只服务"我持有什么"的匹配，不做估值）。
        """
        pm = self._get_pm()
        get_brokerage = getattr(pm, "get_brokerage_portfolios", None)
        portfolios = get_brokerage() if callable(get_brokerage) else {}
        if not portfolios:
            # 退化：至少把默认账户读出来（并已在 get_holdings 里留痕）
            return self.get_holdings()

        merged: List[StockInfo] = []
        for name, portfolio in sorted(portfolios.items()):
            for pos in portfolio.get_open_positions():
                merged.append(StockInfo(
                    code=pos.stock_code,
                    name=pos.stock_name,
                    account=name,
                    source="portfolio",
                    entry_price=pos.entry_price,
                    current_price=pos.current_price,
                    quantity=pos.quantity,
                    return_pct=pos.return_pct,
                ))
        return merged

    def get_account_status(self) -> Dict[str, Any]:
        """账户名册状态（反静默出口）：区分「账户没建起来」与「账户真的为空」。"""
        try:
            return self._get_pm().get_account_status()
        except Exception as e:
            log.warning("[Portfolio] 账户状态读取失败: %s", e)
            return {"error": f"{type(e).__name__}: {e}"}

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

    # ── 自选股（watchlist：用户可手动增删改）────────────────────────────
    #
    # 写的是 ``naja_watchlist`` 的 ``stocks`` 键，读用 ``get_watchlist()``。
    # **只碰 stocks / others 两个键**——``ai_stocks`` 是预设的 AI 股票池
    # （manas 与 market_observer 在用），不属于「用户自选」，不能被这里误删。
    #
    # 写后必须 ``invalidate_cache()``：``_load_watchlist`` 有 5 分钟缓存，
    # 不失效会出现「UI 加了、报告 5 分钟后才看到」这类假故障。

    _WATCHLIST_BUCKETS = ("stocks", "others")

    def _save_watchlist(self, data: Dict[str, Any]) -> None:
        """把整份自选数据写回落盘表，并让 5 分钟缓存立即失效。"""
        nb = NB(WATCHLIST_TABLE)
        nb.update(data)
        self.invalidate_cache()

    def list_watchlist_items(self) -> List[Dict[str, Any]]:
        """自选股原始项（纯 dict：code/name/add_time/bucket），供管理 UI 用。

        同一代码在 ``stocks`` 与 ``others`` 都出现时按先 ``stocks`` 去重。
        ``ai_stocks``（预设股票池）**不在**自选管理范围内，故不返回。
        """
        data = self._load_watchlist()
        seen: Dict[str, Dict[str, Any]] = {}
        for bucket in self._WATCHLIST_BUCKETS:
            for item in (data.get(bucket) or []):
                if not isinstance(item, dict):
                    continue
                code = str(item.get("code") or "").strip()
                if not code:
                    continue
                seen.setdefault(code.lower(), {
                    "code": code,
                    "name": str(item.get("name") or code),
                    "add_time": float(item.get("add_time") or 0.0),
                    "bucket": bucket,
                })
        # 最近加入的排前面，其次按代码字典序（稳定、可复现）
        return sorted(seen.values(), key=lambda r: (-r["add_time"], r["code"].lower()))

    def add_watchlist_item(self, code: str, name: str = "") -> Dict[str, Any]:
        """新增一个自选（只写 ``stocks``）。已存在则拒绝，不静默改写成新名称。"""
        code = str(code or "").strip()
        if not code:
            return {"ok": False, "reason": "股票代码/名称不能为空"}
        name = str(name or "").strip() or code

        data = dict(self._load_watchlist())
        stocks = [s for s in (data.get("stocks") or []) if isinstance(s, dict)]
        lower = {str(s.get("code") or "").strip().lower() for s in stocks}
        for bucket in self._WATCHLIST_BUCKETS:
            if bucket == "stocks":
                continue
            for s in (data.get(bucket) or []):
                if isinstance(s, dict):
                    lower.add(str(s.get("code") or "").strip().lower())
        if code.lower() in lower:
            return {"ok": False, "reason": f"自选「{code}」已存在"}

        stocks.append({"code": code, "name": name, "add_time": time.time()})
        data["stocks"] = stocks
        try:
            self._save_watchlist(data)
        except Exception as e:
            return {"ok": False, "reason": f"写入失败（{type(e).__name__}: {e}）"}
        return {"ok": True, "reason": "",
                "item": {"code": code, "name": name, "bucket": "stocks"}}

    def update_watchlist_item(self, code: str, name: Optional[str] = None) -> Dict[str, Any]:
        """修改自选的展示名（代码是标识，不作为可改字段）。"""
        code = str(code or "").strip()
        if not code:
            return {"ok": False, "reason": "股票代码不能为空"}
        if name is None:
            return {"ok": False, "reason": "没有要修改的字段（当前仅支持 name）"}
        name = str(name).strip()
        if not name:
            return {"ok": False, "reason": "名称不能为空"}

        data = dict(self._load_watchlist())
        hit = False
        bucket_hit = ""
        for bucket in self._WATCHLIST_BUCKETS:
            for item in (data.get(bucket) or []):
                if (isinstance(item, dict)
                        and str(item.get("code") or "").strip().lower() == code.lower()):
                    item["name"] = name
                    hit = True
                    bucket_hit = bucket_hit or bucket
        if not hit:
            return {"ok": False, "reason": f"自选「{code}」不存在"}
        try:
            self._save_watchlist(data)
        except Exception as e:
            return {"ok": False, "reason": f"写入失败（{type(e).__name__}: {e}）"}
        return {"ok": True, "reason": "",
                "item": {"code": code, "name": name, "bucket": bucket_hit}}

    def remove_watchlist_item(self, code: str) -> Dict[str, Any]:
        """移除一个自选（物理删除——自选只是"在看的票"，无持仓那样的历史价值）。"""
        code = str(code or "").strip()
        if not code:
            return {"ok": False, "reason": "股票代码不能为空"}

        data = dict(self._load_watchlist())
        removed = 0
        for bucket in self._WATCHLIST_BUCKETS:
            arr = data.get(bucket)
            if not isinstance(arr, list):
                continue
            kept = [
                i for i in arr
                if not (isinstance(i, dict)
                        and str(i.get("code") or "").strip().lower() == code.lower())
            ]
            removed += len(arr) - len(kept)
            data[bucket] = kept
        if not removed:
            return {"ok": False, "reason": f"自选「{code}」不存在"}
        try:
            self._save_watchlist(data)
        except Exception as e:
            return {"ok": False, "reason": f"写入失败（{type(e).__name__}: {e}）"}
        return {"ok": True, "reason": "", "removed": code}

    # ── 手动持仓（「手动」账户：用户手填的真实仓位）──────────────────────
    def _manual_portfolio(self, create: bool = False) -> Optional[Any]:
        """取「手动」账户。

        ``create=False`` 且账户不存在时返回 ``None`` —— **不产生副作用**。
        展示 / 健康检查一律走这条路（本项目铁律：只读检查不许顺手创建东西）。
        """
        pm = self._get_pm()
        if create:
            ensure = getattr(pm, "get_or_create_manual_account", None)
            return ensure() if callable(ensure) else None
        from deva.naja.bandit.portfolio_manager import MANUAL_ACCOUNT
        getter = getattr(pm, "get_us_portfolio", None)
        return getter(MANUAL_ACCOUNT) if callable(getter) else None

    def get_manual_holdings(self, create: bool = False) -> List[StockInfo]:
        """「手动」账户的持仓（用户手填的真实仓位）。"""
        from deva.naja.bandit.portfolio_manager import MANUAL_ACCOUNT
        portfolio = self._manual_portfolio(create=create)
        if portfolio is None:
            return []
        return [
            StockInfo(
                code=pos.stock_code,
                name=pos.stock_name,
                account=MANUAL_ACCOUNT,
                source="portfolio",
                entry_price=pos.entry_price,
                current_price=pos.current_price,
                quantity=pos.quantity,
                return_pct=pos.return_pct,
            )
            for pos in portfolio.get_open_positions()
        ]

    def list_manual_positions(self) -> List[Dict[str, Any]]:
        """「手动」账户的持仓（纯 dict，含 position_id，供 UI 增删改）。"""
        portfolio = self._manual_portfolio(create=False)
        if portfolio is None:
            return []
        return [position_to_dict(p) for p in portfolio.get_open_positions()]

    def add_manual_position(
        self,
        code: str,
        name: str = "",
        price: float = 0.0,
        quantity: float = 0.0,
        entry_time: Optional[float] = None,
    ) -> Dict[str, Any]:
        """在「手动」账户新增持仓。返回 ``{"ok": bool, ...}`` 纯 dict。"""
        code = str(code or "").strip().lower()
        if not code:
            return {"ok": False, "reason": "股票代码不能为空"}
        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            return {"ok": False, "reason": f"数量非法: {quantity!r}"}
        if quantity <= 0:
            return {"ok": False, "reason": "数量必须为正数"}
        try:
            price = float(price or 0.0)
        except (TypeError, ValueError):
            return {"ok": False, "reason": f"价格非法: {price!r}"}
        if price < 0:
            return {"ok": False, "reason": "价格不能为负"}

        portfolio = self._manual_portfolio(create=True)
        if portfolio is None:
            return {"ok": False, "reason": "手动账户不可用（PortfolioManager 不支持）"}
        pos = portfolio.add_position(code, str(name or code), price, quantity, entry_time)
        if pos is None:
            return {"ok": False, "reason": "写入被底层拒绝（检查参数）"}
        return {"ok": True, "position": position_to_dict(pos)}

    def update_manual_position(self, position_id: str, **fields) -> Dict[str, Any]:
        """修改「手动」账户的一个持仓（只改传进来的字段）。"""
        portfolio = self._manual_portfolio(create=False)
        if portfolio is None:
            return {"ok": False, "reason": "手动账户不存在"}
        updater = getattr(portfolio, "update_position", None)
        if not callable(updater):
            return {"ok": False, "reason": "底层不支持修改持仓"}
        allowed = {"quantity", "entry_price", "stock_name", "current_price"}
        unknown = set(fields) - allowed
        if unknown:
            return {"ok": False, "reason": f"不支持的字段: {sorted(unknown)}"}
        try:
            pos = updater(position_id, **fields)
        except TypeError as e:
            return {"ok": False, "reason": f"字段类型不正确: {e}"}
        if pos is None:
            return {"ok": False, "reason": "持仓不存在、已平仓，或参数非法"}
        return {"ok": True, "position": position_to_dict(pos)}

    def remove_manual_position(self, position_id: str, exit_price: float = 0.0) -> Dict[str, Any]:
        """移除「手动」账户的一个持仓。

        **软删除**：复用 ``sell_position`` 置为 CLOSED 并保留历史。
        手填错了也能从记录里找回来，不做物理删除。
        """
        portfolio = self._manual_portfolio(create=False)
        if portfolio is None:
            return {"ok": False, "reason": "手动账户不存在"}
        pos = portfolio.get_position(position_id)
        if pos is None:
            return {"ok": False, "reason": f"持仓不存在: {position_id}"}
        price = float(exit_price or pos.current_price or pos.entry_price or 0.0)
        done = portfolio.sell_position(position_id, price)
        if done is None:
            return {"ok": False, "reason": "该持仓已平仓"}
        return {"ok": True, "position": position_to_dict(done)}

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
