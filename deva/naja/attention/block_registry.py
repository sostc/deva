"""
BlockRegistry - 题材的统一语义注册中心

职责：
- 所有 block 的唯一语义注册表
- 叙事(narrative) → 题材(block) 的双向映射
- 股票(symbol) → 题材(block) 的映射查询
- 题材描述的 embedding 向量存储（中期）

三层概念分离：
- block_id:    题材标识符 "semiconductor", "AI", "新能源"
- industry:    传统行业分类 "ai_chip", "cloud_ai" (来自 stock_block_map)
- narrative:   叙事主题 "AI", "芯片国产替代", "新能源"
"""

from __future__ import annotations
import time
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import numpy as np


@dataclass
class BlockDescriptor:
    """题材语义描述符 - Block 的统一身份层"""
    block_id: str
    name: str
    industry_code: str = ""
    industry_name: str = ""
    narrative_tags: List[str] = field(default_factory=list)
    description: str = ""
    source: str = "manual"
    symbols: Set[str] = field(default_factory=set)
    embedding: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __hash__(self):
        return hash(self.block_id)

    def has_narrative(self, narrative: str) -> bool:
        return narrative in self.narrative_tags

    def add_narrative_tag(self, narrative: str) -> None:
        if narrative not in self.narrative_tags:
            self.narrative_tags.append(narrative)

    def add_symbol(self, symbol: str) -> None:
        self.symbols.add(symbol)


class BlockRegistry:
    """
    题材的统一语义注册中心

    单一数据源原则：
    - 所有 block 元信息只在这里定义/查询
    - 叙事→题材的映射通过 NarrativeBlockLinker 处理
    - 股票→题材的映射通过 register_symbol_block 注入
    """

    _instance: Optional["BlockRegistry"] = None

    def __new__(cls) -> "BlockRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._blocks: Dict[str, BlockDescriptor] = {}
        self._symbol_to_blocks: Dict[str, Set[str]] = defaultdict(set)
        self._narrative_to_blocks: Dict[str, Set[str]] = defaultdict(set)
        self._block_to_narratives: Dict[str, Set[str]] = defaultdict(set)
        self._industry_to_blocks: Dict[str, Set[str]] = defaultdict(set)
        self._embedding_index: Optional[np.ndarray] = None
        self._embedding_block_ids: List[str] = []
        self._last_rebuild_time: float = 0.0
        self._initialized = True

    def register(self, descriptor: BlockDescriptor) -> None:
        """注册题材"""
        block_id = descriptor.block_id
        is_new = block_id not in self._blocks

        self._blocks[block_id] = descriptor

        for narrative in descriptor.narrative_tags:
            self._narrative_to_blocks[narrative].add(block_id)
            self._block_to_narratives[block_id].add(narrative)

        if descriptor.industry_code:
            self._industry_to_blocks[descriptor.industry_code].add(block_id)

        for symbol in descriptor.symbols:
            self._symbol_to_blocks[symbol].add(block_id)

    def register_block(
        self,
        block_id: str,
        name: str,
        industry_code: str = "",
        industry_name: str = "",
        narrative_tags: Optional[List[str]] = None,
        description: str = "",
        source: str = "manual",
        symbols: Optional[Set[str]] = None,
    ) -> BlockDescriptor:
        """注册题材（便捷方法）"""
        descriptor = BlockDescriptor(
            block_id=block_id,
            name=name,
            industry_code=industry_code,
            industry_name=industry_name,
            narrative_tags=narrative_tags or [],
            description=description,
            source=source,
            symbols=symbols or set(),
        )
        self.register(descriptor)
        return descriptor

    def get(self, block_id: str) -> Optional[BlockDescriptor]:
        """获取题材描述符"""
        return self._blocks.get(block_id)

    def exists(self, block_id: str) -> bool:
        return block_id in self._blocks

    def get_all_blocks(self) -> List[BlockDescriptor]:
        return list(self._blocks.values())

    def get_block_ids(self) -> List[str]:
        return list(self._blocks.keys())

    def get_blocks_for_symbol(self, symbol: str) -> List[BlockDescriptor]:
        """获取股票所属的题材列表"""
        block_ids = self._symbol_to_blocks.get(symbol, set())
        return [self._blocks[bid] for bid in block_ids if bid in self._blocks]

    def get_block_ids_for_symbol(self, symbol: str) -> List[str]:
        """获取股票所属的题材ID列表"""
        return list(self._symbol_to_blocks.get(symbol, set()))

    def get_blocks_for_industry(self, industry_code: str) -> List[BlockDescriptor]:
        """获取某传统行业分类下的所有题材"""
        block_ids = self._industry_to_blocks.get(industry_code, set())
        return [self._blocks[bid] for bid in block_ids if bid in self._blocks]

    def link_symbol_to_block(self, symbol: str, block_id: str) -> None:
        """建立股票→题材的映射关系"""
        self._symbol_to_blocks[symbol].add(block_id)
        if block_id in self._blocks:
            self._blocks[block_id].add_symbol(symbol)

    def link_narrative_to_block(self, narrative: str, block_id: str) -> None:
        """建立叙事→题材的映射关系（支持多对多）"""
        if block_id not in self._blocks:
            self.register_block(block_id, block_id, narrative_tags=[narrative])
        else:
            self._blocks[block_id].add_narrative_tag(narrative)
        self._narrative_to_blocks[narrative].add(block_id)
        self._block_to_narratives[block_id].add(narrative)

    def get_blocks_for_narrative(self, narrative: str) -> List[BlockDescriptor]:
        """获取叙事关联的题材（精确匹配）"""
        block_ids = self._narrative_to_blocks.get(narrative, set())
        return [self._blocks[bid] for bid in block_ids if bid in self._blocks]

    def get_narratives_for_block(self, block_id: str) -> List[str]:
        """获取题材关联的叙事"""
        return list(self._block_to_narratives.get(block_id, set()))

    def get_similar_blocks_by_narrative(
        self, narrative: str, top_k: int = 5
    ) -> List[Tuple[BlockDescriptor, float]]:
        """
        基于叙事标签相似度获取题材（不依赖 embedding）

        匹配策略：
        1. 精确匹配 narrative_tags
        2. 子串匹配（narrative 是 block description 的子串）
        3. 回退到行业相关
        """
        if not narrative:
            return []

        results: Dict[str, float] = {}

        for block_id, desc in self._blocks.items():
            score = 0.0
            if desc.has_narrative(narrative):
                score = 1.0
            elif narrative.lower() in desc.description.lower():
                score = 0.6
            elif narrative.lower() in desc.name.lower():
                score = 0.5
            elif any(n.lower() in narrative.lower() or narrative.lower() in n.lower()
                     for n in desc.narrative_tags):
                score = 0.4
            if score > 0:
                results[block_id] = score

        sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [(self._blocks[bid], score) for bid, score in sorted_results if bid in self._blocks]

    def merge_narrative_block_link(
        self, narrative_to_blocks: Dict[str, List[str]]
    ) -> None:
        """
        批量导入叙事→题材的配置映射

        用于从原有的 narrative_block_mapping.py 迁移
        """
        for narrative, block_ids in narrative_to_blocks.items():
            for block_id in block_ids:
                if block_id not in self._blocks:
                    self.register_block(block_id, block_id, narrative_tags=[narrative])
                else:
                    self._blocks[block_id].add_narrative_tag(narrative)
                self._narrative_to_blocks[narrative].add(block_id)
                self._block_to_narratives[block_id].add(narrative)

    def build_embedding_index(self) -> None:
        """建立 block embedding 索引（需要 embedding 向量）"""
        blocks_with_embedding = [
            (bid, desc.embedding)
            for bid, desc in self._blocks.items()
            if desc.embedding is not None
        ]
        if not blocks_with_embedding:
            return

        self._embedding_block_ids = [bid for bid, _ in blocks_with_embedding]
        self._embedding_index = np.vstack([emb for _, emb in blocks_with_embedding])
        self._last_rebuild_time = time.time()

    def get_similar_blocks_by_embedding(
        self, narrative_embedding: np.ndarray, top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """
        基于 embedding 余弦相似度找到相似题材

        需要先调用 build_embedding_index()
        """
        if self._embedding_index is None or len(self._embedding_block_ids) == 0:
            return []

        narrative_embedding = narrative_embedding.reshape(1, -1)
        similarities = np.dot(self._embedding_index, narrative_embedding.T).flatten()
        norm_product = (
            np.linalg.norm(self._embedding_index, axis=1) *
            np.linalg.norm(narrative_embedding)
        )
        cos_similarities = similarities / (norm_product + 1e-8)

        top_indices = np.argsort(cos_similarities)[::-1][:top_k]
        return [
            (self._embedding_block_ids[i], float(cos_similarities[i]))
            for i in top_indices
        ]

    def get_stats(self) -> Dict[str, Any]:
        """获取注册表统计信息"""
        return {
            "total_blocks": len(self._blocks),
            "total_narratives": len(self._narrative_to_blocks),
            "total_symbols": len(self._symbol_to_blocks),
            "total_industries": len(self._industry_to_blocks),
            "blocks_with_embeddings": sum(
                1 for d in self._blocks.values() if d.embedding is not None
            ),
        }

    def clear(self) -> None:
        """清空注册表（主要用于测试）"""
        self._blocks.clear()
        self._symbol_to_blocks.clear()
        self._narrative_to_blocks.clear()
        self._block_to_narratives.clear()
        self._industry_to_blocks.clear()
        self._embedding_index = None
        self._embedding_block_ids.clear()


_block_registry: Optional[BlockRegistry] = None


def get_block_registry() -> BlockRegistry:
    """获取 BlockRegistry 单例"""
    global _block_registry
    if _block_registry is None:
        _block_registry = BlockRegistry()
    return _block_registry


def reset_block_registry() -> None:
    """重置 BlockRegistry（主要用于测试）"""
    global _block_registry
    _block_registry = None
