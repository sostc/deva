"""
AttentionFocusManager - 主动关注统一管理器

═══════════════════════════════════════════════════════════════════════════
                              架 构 定 位
═══════════════════════════════════════════════════════════════════════════

【执行层】AttentionFocusManager 是"注意力→行动"的执行入口

    注意力在哪里，执行就跟到哪里
    - NarrativeTracker 发现的叙事 → follow_narrative()
    - BlindSpotInvestigator 的 resolver → follow_stock()
    - ConvictionValidator 的共识 → 可以 follow()
    - 用户主动意图 → follow_xxx()

═══════════════════════════════════════════════════════════════════════════
                              核 心 职 能
═══════════════════════════════════════════════════════════════════════════

提供统一的接口来主动关注：
    叙事（narrative）  : "我想关注 AI/芯片"
    板块（block）      : "我想关注 semiconductor 板块"
    股票（stock）      : "我想关注 NVDA"

每种关注都会自动：
    - 更新 Portfolio 的持仓/自选
    - 更新 NarrativeBlockLinker 的叙事映射
    - 更新 BlockRegistry 的 block 元数据
    - 持久化到 naja_focus_config（NB）

═══════════════════════════════════════════════════════════════════════════
                              与其他模块的关系
═══════════════════════════════════════════════════════════════════════════

BlindSpotInvestigator → 探究结果 → FocusManager.follow_stock()
    外部热但没关注 → resolver → 自动 follow

NarrativeTracker → 天道发现 → FocusManager.follow_narrative()
    我们认定的价值 → 主动 follow

用户意图 → FocusManager.follow_xxx()
    人为决策 → 直接 follow

═══════════════════════════════════════════════════════════════════════════
                              持 久 化
═══════════════════════════════════════════════════════════════════════════

所有关注配置持久化到 NB("naja_focus_config"):
    {
        "narratives": [{"focus_id": "AI", "source": "user", ...}, ...],
        "blocks": [...],
        "stocks": [...],
    }

关注来源 source:
    "user"          = 用户主动关注
    "investigation" = BlindSpotInvestigator 自动关注
    "value_signals" = NarrativeTracker 天道信号触发
"""

from __future__ import annotations
import time
from typing import Dict, List, Optional, Set, Any, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from deva.naja.attention.portfolio import Portfolio
    from deva.naja.attention.narrative_block_linker import NarrativeBlockLinker
    from deva.naja.attention.block_registry import BlockRegistry, BlockDescriptor

from deva import NB


FOCUS_CONFIG_TABLE = "naja_focus_config"


@dataclass
class FocusItem:
    """
    [Execution Layer] Single focus item

    Fields:
        focus_type: type = narrative / block / stock
        focus_id: focus identifier
        display_name: display name
        source: source = user / investigation / value_signals
        priority: priority (0-1)
        linked_blocks: linked block list
        linked_stocks: linked stock list
        add_time: add timestamp
        status: status = active / inactive
    """
    focus_type: str                           # 【标识】类型
    focus_id: str                             # 【标识】ID
    display_name: str                          # 【显示】名称
    source: str                               # 【来源】user/investigation/value_signals
    priority: float                           # 【权重】优先级
    linked_blocks: List[str] = field(default_factory=list)   # 【关联】block
    linked_stocks: List[str] = field(default_factory=list)  # 【关联】stock
    add_time: float = field(default_factory=time.time)       # 【时间】添加时间
    status: str = "active"                    # 【状态】active/inactive


@dataclass
class FocusSummary:
    """
    【执行层】关注汇总

    汇总所有类型的关注，提供统一的视图
    """
    narratives: List[FocusItem]              # 【叙事】关注的叙事
    blocks: List[FocusItem]                  # 【板块】关注的板块
    stocks: List[FocusItem]                 # 【股票】关注的股票

    all_narrative_ids: Set[str]              # 【汇总】所有叙事ID
    all_block_ids: Set[str]                  # 【汇总】所有block ID
    all_stock_codes: Set[str]                # 【汇总】所有股票代码


class AttentionFocusManager:
    """
    【执行层】主动关注统一管理器

    注意力在哪里，执行就跟到哪里

    使用方式:

        fm = AttentionFocusManager()

        # 方式1: 关注叙事（天道发现 / 用户主动）
        fm.follow_narrative("AI", priority=0.9)

        # 方式2: 关注板块
        fm.follow_block("semiconductor", priority=0.8)

        # 方式3: 关注股票（BlindSpotInvestigator resolver 自动调用）
        fm.follow_stock("NVDA", stock_name="英伟达")

        # 获取完整关注列表
        summary = fm.get_summary()
        print(f"叙事: {summary.all_narrative_ids}")
        print(f"股票: {summary.all_stock_codes}")

        # 获取供融合层使用的关注权重
        watched_weights = fm.get_watched_attention_weights()

    """

    _instance: Optional["AttentionFocusManager"] = None

    def __new__(cls) -> "AttentionFocusManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        from deva.naja.attention.portfolio import get_portfolio
        from deva.naja.attention.narrative_block_linker import get_narrative_block_linker
        from deva.naja.attention.block_registry import get_block_registry

        self._portfolio = get_portfolio()
        self._linker = get_narrative_block_linker()
        self._registry = get_block_registry()

        self._narrative_focus: Dict[str, FocusItem] = {}
        self._block_focus: Dict[str, FocusItem] = {}
        self._stock_focus: Dict[str, FocusItem] = {}

        self._load_from_storage()
        self._initialized = True

    def _load_from_storage(self) -> None:
        """从持久化存储加载关注配置"""
        nb = NB(FOCUS_CONFIG_TABLE)
        config = dict(nb) if len(nb) > 0 else {}

        self._narrative_focus.clear()
        self._block_focus.clear()
        self._stock_focus.clear()

        for item_data in config.get("narratives", []):
            item = FocusItem(**item_data)
            self._narrative_focus[item.focus_id] = item

        for item_data in config.get("blocks", []):
            item = FocusItem(**item_data)
            self._block_focus[item.focus_id] = item

        for item_data in config.get("stocks", []):
            item = FocusItem(**item_data)
            self._stock_focus[item.focus_id] = item

    def _save_to_storage(self) -> None:
        """持久化关注配置"""
        nb = NB(FOCUS_CONFIG_TABLE)
        nb["narratives"] = [vars(item) for item in self._narrative_focus.values()]
        nb["blocks"] = [vars(item) for item in self._block_focus.values()]
        nb["stocks"] = [vars(item) for item in self._stock_focus.values()]
        nb["update_time"] = time.time()

    def follow_narrative(
        self,
        narrative: str,
        priority: float = 0.7,
        source: str = "manual",
        blocks: Optional[List[str]] = None,
    ) -> FocusItem:
        """
        主动关注一个叙事主题

        Args:
            narrative: narrative name, e.g. "AI", "chip", "new_energy"
            priority: focus priority 0.0-1.0
            source: source identifier
            blocks: optional, manually specify linked blocks
        """
        linked_blocks = blocks or self._linker.get_linked_blocks(narrative)

        item = FocusItem(
            focus_type="narrative",
            focus_id=narrative,
            display_name=narrative,
            source=source,
            priority=priority,
            linked_blocks=linked_blocks,
        )
        self._narrative_focus[narrative] = item

        for block_id in linked_blocks:
            self._update_block_link_to_narrative(block_id, narrative, priority)

        self._registry.link_narrative_to_block(
            narrative, linked_blocks[0] if linked_blocks else "")
        self._save_to_storage()

        return item

    def follow_block(
        self,
        block_id: str,
        priority: float = 0.7,
        source: str = "manual",
        block_name: Optional[str] = None,
    ) -> FocusItem:
        """
        主动关注一个板块

        Args:
            block_id: block identifier, e.g. "semiconductor", "AI"
            priority: focus priority 0.0-1.0
            source: source identifier
            block_name: optional, block display name
        """
        desc = self._registry.get(block_id)
        display_name = block_name or (desc.name if desc else block_id)

        linked_narratives = []
        if desc:
            linked_narratives = desc.narrative_tags
        else:
            linked_narratives = self._linker.suggest_narratives_for_block(block_id)
            linked_narratives = [n for n, _ in linked_narratives]

        item = FocusItem(
            focus_type="block",
            focus_id=block_id,
            display_name=display_name,
            source=source,
            priority=priority,
            linked_blocks=[block_id],
            linked_stocks=list(desc.symbols) if desc else [],
        )
        self._block_focus[block_id] = item

        for narrative in linked_narratives:
            self._update_narrative_link_to_block(narrative, block_id, priority)

        self._save_to_storage()
        return item

    def follow_stock(
        self,
        stock_code: str,
        stock_name: Optional[str] = None,
        priority: float = 0.6,
        source: str = "manual",
        as_watchlist: bool = True,
    ) -> FocusItem:
        """
        Follow a stock (add to watchlist or mark as holding)

        Args:
            stock_code: stock code, e.g. "NVDA", "nvda"
            stock_name: stock name (optional)
            priority: focus priority
            source: source identifier
            as_watchlist: True=add to watchlist, False=mark as holding
        """
        stock_code = stock_code.lower()

        stock_name = stock_name or stock_code.upper()

        linked_blocks = []
        linked_narratives = []

        from deva.naja.bandit.stock_sector_map import get_stock_sector_map
        sm = get_stock_sector_map()

        metadata = sm.get_metadata(stock_code)
        if metadata:
            stock_name = metadata.name or stock_name
            linked_blocks = metadata.blocks
            linked_narratives = [metadata.narrative] if metadata.narrative else []
        else:
            blocks_list = sm.get_stock_blocks(stock_code)
            linked_blocks = blocks_list

        item = FocusItem(
            focus_type="stock",
            focus_id=stock_code,
            display_name=stock_name,
            source=source,
            priority=priority,
            linked_blocks=linked_blocks,
            linked_stocks=[stock_code],
        )
        self._stock_focus[stock_code] = item

        for block_id in linked_blocks:
            self._update_block_link_to_stock(block_id, stock_code, priority)

        for narrative in linked_narratives:
            self._update_narrative_link_to_block(
                narrative, linked_blocks[0] if linked_blocks else "", priority)

        if as_watchlist:
            self._add_to_watchlist(stock_code, stock_name)

        self._save_to_storage()
        return item

    def _update_block_link_to_narrative(self, block_id: str, narrative: str, priority: float) -> None:
        """Update block -> narrative link"""
        desc = self._registry.get(block_id)
        if desc and narrative not in desc.narrative_tags:
            desc.add_narrative_tag(narrative)

    def _update_narrative_link_to_block(self, narrative: str, block_id: str, priority: float) -> None:
        """Update narrative -> block link"""
        if block_id:
            self._registry.link_narrative_to_block(narrative, block_id)

    def _update_block_link_to_stock(self, block_id: str, stock_code: str, priority: float) -> None:
        """Update block -> stock link"""
        self._registry.link_symbol_to_block(stock_code, block_id)

    def _add_to_watchlist(self, stock_code: str, stock_name: str) -> None:
        """添加到自选股列表"""
        nb = NB("naja_watchlist")
        data = dict(nb) if len(nb) > 0 else {}
        if "stocks" not in data:
            data["stocks"] = []
        existing_codes = {s["code"] for s in data.get("stocks", []) if isinstance(s, dict)}
        if stock_code not in existing_codes:
            data["stocks"].append(
                {"code": stock_code, "name": stock_name, "add_time": time.time()})
        nb.update(data)
        self._portfolio.invalidate_cache()

    def unfollow_narrative(self, narrative: str) -> None:
        """取消关注叙事"""
        if narrative in self._narrative_focus:
            del self._narrative_focus[narrative]
            self._save_to_storage()

    def unfollow_block(self, block_id: str) -> None:
        """取消关注板块"""
        if block_id in self._block_focus:
            del self._block_focus[block_id]
            self._save_to_storage()

    def unfollow_stock(self, stock_code: str) -> None:
        """取消关注股票"""
        stock_code = stock_code.lower()
        if stock_code in self._stock_focus:
            del self._stock_focus[stock_code]
        self._remove_from_watchlist(stock_code)
        self._save_to_storage()

    def _remove_from_watchlist(self, stock_code: str) -> None:
        """从自选股列表移除"""
        nb = NB("naja_watchlist")
        data = dict(nb) if len(nb) > 0 else {}
        if "stocks" in data:
            data["stocks"] = [s for s in data["stocks"] if isinstance(
                s, dict) and s.get("code") != stock_code]
            nb.update(data)
        self._portfolio.invalidate_cache()

    def get_summary(self) -> FocusSummary:
        """获取完整关注汇总"""
        narratives = list(self._narrative_focus.values())
        blocks = list(self._block_focus.values())
        stocks = list(self._stock_focus.values())

        return FocusSummary(
            narratives=narratives,
            blocks=blocks,
            stocks=stocks,
            all_narrative_ids={n.focus_id for n in narratives},
            all_block_ids={b.focus_id for b in blocks},
            all_stock_codes={s.focus_id for s in stocks},
        )

    def get_watched_attention_weights(self) -> Dict[str, float]:
        """
        获取供融合层使用的关注权重

        Returns:
            {
                "narrative:AI": 0.9,
                "block:semiconductor": 0.8,
                "stock:nvda": 0.7,
                ...
            }
        """
        weights: Dict[str, float] = {}

        for narrative, item in self._narrative_focus.items():
            weights[f"narrative:{narrative}"] = item.priority

        for block_id, item in self._block_focus.items():
            weights[f"block:{block_id}"] = item.priority

        for stock_code, item in self._stock_focus.items():
            weights[f"stock:{stock_code}"] = item.priority

        return weights

    def get_watched_narratives(self) -> List[str]:
        """获取所有关注的叙事列表"""
        return list(self._narrative_focus.keys())

    def get_watched_blocks(self) -> List[str]:
        """获取所有关注的板块列表"""
        return list(self._block_focus.keys())

    def get_watched_stocks(self) -> List[str]:
        """获取所有关注的股票列表"""
        return list(self._stock_focus.keys())

    def get_narrative_priority(self, narrative: str) -> float:
        """获取叙事的关注优先级"""
        item = self._narrative_focus.get(narrative)
        return item.priority if item else 0.0

    def get_block_priority(self, block_id: str) -> float:
        """获取板块的关注优先级"""
        item = self._block_focus.get(block_id)
        return item.priority if item else 0.0

    def is_watched_narrative(self, narrative: str) -> bool:
        return narrative in self._narrative_focus

    def is_watched_block(self, block_id: str) -> bool:
        return block_id in self._block_focus

    def is_watched_stock(self, stock_code: str) -> bool:
        return stock_code.lower() in self._stock_focus

    def clear_all(self) -> None:
        """Clear all focus (use with caution)"""
        self._narrative_focus.clear()
        self._block_focus.clear()
        self._stock_focus.clear()
        self._save_to_storage()


_focus_manager_instance: Optional[AttentionFocusManager] = None


def get_attention_focus_manager() -> AttentionFocusManager:
    """获取 AttentionFocusManager 单例"""
    global _focus_manager_instance
    if _focus_manager_instance is None:
        _focus_manager_instance = AttentionFocusManager()
    return _focus_manager_instance
