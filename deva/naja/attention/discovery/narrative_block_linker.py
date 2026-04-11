"""
NarrativeBlockLinker - 叙事-题材联动器

替代 narrative_block_mapping.py，提供：
1. 配置驱动的精确映射（NARRATIVE_TO_BLOCK_LINK）
2. Tag 匹配的回退查找
3. Embedding 语义相似度（中期）
4. 反馈学习接口（中期）
"""

from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .block_registry import BlockRegistry, BlockDescriptor


from deva.naja.cognition.narrative.block_mapping import (
    NARRATIVE_TO_BLOCK_LINK,
    NARRATIVE_TO_MARKET_LINK,
    MARKET_TO_NARRATIVE_LINK,
    MARKET_INDEX_CONFIG,
)


def get_linked_blocks(narrative: str) -> List[str]:
    """
    获取叙事关联的题材列表（配置优先）

    这是 narrative_block_mapping.py 的原有接口，
    现在委托给 NarrativeBlockLinker.get_linked_blocks()
    """
    return NarrativeBlockLinker.get_linked_blocks(narrative)


def get_linked_markets(narrative: str) -> List[str]:
    """获取叙事关联的市场指数"""
    return NARRATIVE_TO_MARKET_LINK.get(narrative, [])


def get_market_config(market_id: str) -> Optional[Dict[str, str]]:
    """获取市场指数配置"""
    from deva.naja.cognition.narrative.block_mapping import MARKET_INDEX_CONFIG
    return MARKET_INDEX_CONFIG.get(market_id)


class NarrativeBlockLinker:
    """
    叙事-题材联动器

    获取叙事关联题材的优先级：
    1. NARRATIVE_TO_BLOCK_LINK 配置映射（精确，人工维护）
    2. BlockRegistry 的 narrative_tags 匹配
    3. BlockRegistry 的语义相似度（需要 embedding）

    使用方式：
        linker = NarrativeBlockLinker(registry=block_registry)
        blocks = linker.get_linked_blocks("AI")
    """

    _config_loaded = False

    def __init__(self, registry: Optional["BlockRegistry"] = None):
        from .block_registry import get_block_registry
        self.registry = registry or get_block_registry()
        self._ensure_config_loaded()

    def _ensure_config_loaded(self) -> None:
        """确保配置映射已加载到 BlockRegistry"""
        if not NarrativeBlockLinker._config_loaded:
            self.registry.merge_narrative_block_link(NARRATIVE_TO_BLOCK_LINK)
            NarrativeBlockLinker._config_loaded = True

    def get_linked_blocks(self, narrative: str) -> List[str]:
        """
        获取叙事关联的题材列表

        优先级：
        1. NARRATIVE_TO_BLOCK_LINK 配置
        2. BlockRegistry 的 narrative_tags
        """
        if not narrative:
            return []

        if narrative in NARRATIVE_TO_BLOCK_LINK:
            return NARRATIVE_TO_BLOCK_LINK[narrative]

        blocks_from_registry = self.registry.get_blocks_for_narrative(narrative)
        if blocks_from_registry:
            return [b.block_id for b in blocks_from_registry]

        return []

    def get_linked_blocks_with_confidence(
        self, narrative: str
    ) -> List[Tuple[str, float]]:
        """
        获取叙事关联的题材（带置信度）

        Returns:
            [(block_id, confidence), ...]
            confidence: 0.0-1.0
        """
        if not narrative:
            return []

        if narrative in NARRATIVE_TO_BLOCK_LINK:
            return [(bid, 1.0) for bid in NARRATIVE_TO_BLOCK_LINK[narrative]]

        similar = self.registry.get_similar_blocks_by_narrative(narrative, top_k=5)
        if similar:
            return [(b.block_id, score) for b, score in similar]

        return []

    def get_linked_markets(self, narrative: str) -> List[str]:
        """获取叙事关联的市场指数"""
        return NARRATIVE_TO_MARKET_LINK.get(narrative, [])

    def get_markets_for_block(self, block_id: str) -> List[str]:
        """获取题材关联的市场指数（通过叙事反向查找）"""
        narratives = self.registry.get_narratives_for_block(block_id)
        markets = set()
        for narrative in narratives:
            markets.update(get_linked_markets(narrative))
        return list(markets)

    def learn_narrative_block_link(
        self, narrative: str, block_id: str, weight: float = 1.0
    ) -> None:
        """
        根据实际市场表现，强化叙事→题材的关联

        中期接口：可用于存储反馈，用于后续学习
        目前只是更新 BlockRegistry
        """
        if weight >= 0.5:
            self.registry.link_narrative_to_block(narrative, block_id)

    def get_block_narrative_matrix(
        self, block_ids: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        获取题材-叙事关联矩阵

        Returns:
            {block_id: {narrative: confidence, ...}, ...}
        """
        target_blocks = block_ids or self.registry.get_block_ids()

        matrix: Dict[str, Dict[str, float]] = {
            bid: {} for bid in target_blocks
        }

        for narrative, linked_blocks in NARRATIVE_TO_BLOCK_LINK.items():
            for bid in linked_blocks:
                if bid in matrix:
                    matrix[bid][narrative] = 1.0

        for bid in target_blocks:
            desc = self.registry.get(bid)
            if desc:
                for tag in desc.narrative_tags:
                    if tag not in matrix[bid]:
                        matrix[bid][tag] = matrix[bid].get(tag, 0.0) + 0.5

        return matrix

    def suggest_narratives_for_block(self, block_id: str, top_k: int = 3) -> List[Tuple[str, float]]:
        """
        为题材推荐关联叙事

        基于：
        1. NARRATIVE_TO_BLOCK_LINK 逆查
        2. BlockRegistry 的 narrative_tags
        3. Block name/description 模糊匹配
        """
        result: Dict[str, float] = {}

        for narrative, linked_blocks in NARRATIVE_TO_BLOCK_LINK.items():
            if block_id in linked_blocks:
                result[narrative] = 1.0

        desc = self.registry.get(block_id)
        if desc:
            for narrative in desc.narrative_tags:
                result[narrative] = result.get(narrative, 0.0) + 0.5

            name_lower = desc.name.lower()
            for narrative, linked_blocks in NARRATIVE_TO_BLOCK_LINK.items():
                if any(
                    narrative.lower() in block_id.lower() or
                    block_id.lower() in narrative.lower()
                    for _ in [1]
                ):
                    result[narrative] = result.get(narrative, 0.0) + 0.3

        sorted_result = sorted(result.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return sorted_result


_linker: Optional[NarrativeBlockLinker] = None


def get_narrative_block_linker() -> NarrativeBlockLinker:
    """获取 NarrativeBlockLinker 单例"""
    global _linker
    if _linker is None:
        _linker = NarrativeBlockLinker()
    return _linker
