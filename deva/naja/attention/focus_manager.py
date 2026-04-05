"""
AttentionFocusManager - 主动关注统一管理器

三层分离架构的"我们的价值追求"层统一入口

提供统一的接口来主动关注：
1. 叙事（narrative）："我想关注 AI/芯片"
2. 板块（block）："我想关注 semiconductor 板块"
3. 股票（stock）："我想关注 NVDA"

每种关注都会自动：
- 更新 Portfolio 的持仓/自选
- 更新 NarrativeBlockLinker 的叙事映射
- 更新 BlockRegistry 的 block 元数据
- 计算融合层的注意力权重

作者: AI
日期: 2026-04-05
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
    """关注的单项"""
    focus_type: str
    focus_id: str
    display_name: str
    source: str
    priority: float
    linked_blocks: List[str] = field(default_factory=list)
    linked_stocks: List[str] = field(default_factory=list)
    add_time: float = field(default_factory=time.time)
    status: str = "active"


@dataclass
class FocusSummary:
    """关注汇总"""
    narratives: List[FocusItem]
    blocks: List[FocusItem]
    stocks: List[FocusItem]

    all_narrative_ids: Set[str]
    all_block_ids: Set[str]
    all_stock_codes: Set[str]


class AttentionFocusManager:
    """
    主动关注统一管理器

    使用方式:

        fm = AttentionFocusManager()

        # 方式1: 关注叙事
        fm.follow_narrative("AI", priority=0.9)

        # 方式2: 关注板块
        fm.follow_block("semiconductor", priority=0.8)

        # 方式3: 关注股票（加入自选）
        fm.follow_stock("NVDA", stock_name="英伟达")

        # 获取完整关注列表
        summary = fm.get_summary()

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
        config = nb.all() or {}

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
            narrative: 叙事名称，如 "AI", "芯片", "新能源"
            priority: 关注优先级 0.0-1.0
            source: 来源标识
            blocks: 可选，手动指定关联的 block（不指定则自动从 NarrativeBlockLinker 获取）
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

        self._registry.link_narrative_to_block(narrative, linked_blocks[0] if linked_blocks else "")
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
            block_id: 板块标识，如 "semiconductor", "AI", "新能源"
            priority: 关注优先级 0.0-1.0
            source: 来源标识
            block_name: 可选，板块中文名
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
        主动关注一只股票（加入自选或持仓）

        Args:
            stock_code: 股票代码，如 "NVDA", "nvda"
            stock_name: 股票名称（可选）
            priority: 关注优先级
            source: 来源标识
            as_watchlist: True=加入自选，False=标记为持仓
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
            self._update_narrative_link_to_block(narrative, linked_blocks[0] if linked_blocks else "", priority)

        if as_watchlist:
            self._add_to_watchlist(stock_code, stock_name)

        self._save_to_storage()
        return item

    def _update_block_link_to_narrative(self, block_id: str, narrative: str, priority: float) -> None:
        """更新 block → narrative 的关联"""
        desc = self._registry.get(block_id)
        if desc and narrative not in desc.narrative_tags:
            desc.add_narrative_tag(narrative)

    def _update_narrative_link_to_block(self, narrative: str, block_id: str, priority: float) -> None:
        """更新 narrative → block 的关联"""
        if block_id:
            self._registry.link_narrative_to_block(narrative, block_id)

    def _update_block_link_to_stock(self, block_id: str, stock_code: str, priority: float) -> None:
        """更新 block → stock 的关联"""
        self._registry.link_symbol_to_block(stock_code, block_id)

    def _add_to_watchlist(self, stock_code: str, stock_name: str) -> None:
        """添加到自选股列表"""
        nb = NB("naja_watchlist")
        data = nb.all() or {}
        if "stocks" not in data:
            data["stocks"] = []
        existing_codes = {s["code"] for s in data.get("stocks", []) if isinstance(s, dict)}
        if stock_code not in existing_codes:
            data["stocks"].append({"code": stock_code, "name": stock_name, "add_time": time.time()})
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
        data = nb.all() or {}
        if "stocks" in data:
            data["stocks"] = [s for s in data["stocks"] if isinstance(s, dict) and s.get("code") != stock_code]
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
        """清除所有关注（谨慎使用）"""
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
