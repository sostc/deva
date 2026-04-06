"""
Knowledge Exporter - 知识导出器

将手动确认的 QUALIFIED 知识导出为 CAUSAL_KNOWLEDGE 格式
供 BlindSpotInvestigator 等模块使用
"""

import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

from .knowledge_store import KnowledgeStore, KnowledgeEntry, KnowledgeState, get_knowledge_store
from .state_manager import KnowledgeStateManager, get_state_manager


class KnowledgeExporter:
    """
    知识导出器

    功能：
    1. 将 QUALIFIED 知识导出为 CAUSAL_KNOWLEDGE 格式
    2. 合并预定义知识和动态知识
    3. 供 BlindSpotInvestigator 等模块使用
    """

    CAUSAL_FORMAT = {
        "root_cause": str,
        "causal_chain": list,
        "resolvers": list,
        "investigation_prompt": str,
    }

    def __init__(self,
                 store: Optional[KnowledgeStore] = None,
                 state_manager: Optional[KnowledgeStateManager] = None):
        self.store = store or get_knowledge_store()
        self.state_manager = state_manager or get_state_manager()

        self._predefined_knowledge: Dict[str, Dict[str, Any]] = {}
        self._merged_knowledge: Dict[str, Dict[str, Any]] = {}

    def load_predefined(self, predefined: Dict[str, Dict[str, Any]]):
        """加载预定义知识"""
        self._predefined_knowledge = predefined
        self.merge()

    def _entry_to_causal_format(self, entry: KnowledgeEntry) -> Dict[str, Any]:
        """将知识条目转换为 CAUSAL_KNOWLEDGE 格式"""
        return {
            "root_cause": entry.cause,
            "causal_chain": [entry.cause, entry.effect],
            "resolvers": [],
            "investigation_prompt": f"为什么 {entry.cause} 会导致 {entry.effect}？背后的逻辑是什么？",
            "_knowledge_id": entry.id,
            "_source": entry.source,
            "_confidence": entry.adjusted_confidence,
            "_category": entry.category,
            "_manual_override": entry.manual_override,
        }

    def merge(self):
        """合并预定义知识和动态知识"""
        self._merged_knowledge = dict(self._predefined_knowledge)

        for entry in self.store.get_by_state(KnowledgeState.QUALIFIED):
            causal = self._entry_to_causal_format(entry)

            key = entry.cause
            if key in self._merged_knowledge:
                existing = self._merged_knowledge[key]
                if not entry.manual_override:
                    if existing.get("_confidence", 0) >= entry.adjusted_confidence:
                        continue
                self._merged_knowledge[key] = causal
            else:
                self._merged_knowledge[key] = causal

    def get_causal_knowledge(self) -> Dict[str, Dict[str, Any]]:
        """获取合并后的因果知识"""
        self.merge()
        return self._merged_knowledge

    def get_by_narrative(self, narrative: str) -> Optional[Dict[str, Any]]:
        """根据叙事名称获取因果知识"""
        knowledge = self.get_causal_knowledge()

        narrative_lower = narrative.lower()
        if narrative in knowledge:
            return knowledge[narrative]

        for key, value in knowledge.items():
            if key.lower() == narrative_lower:
                return value
            if key in narrative or narrative in key:
                return value

        return None

    def export_to_file(self, filepath: Optional[Path] = None) -> Path:
        """导出到文件"""
        if filepath is None:
            filepath = self.store.BASE_DIR / "causal_knowledge_export.json"

        knowledge = self.get_causal_knowledge()

        data = {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "knowledge_count": len(knowledge),
            "knowledge": knowledge
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return filepath

    def get_summary(self) -> Dict[str, Any]:
        """获取知识汇总"""
        qualified = self.store.get_by_state(KnowledgeState.QUALIFIED)
        predefined_count = len(self._predefined_knowledge)
        dynamic_count = len(qualified)

        return {
            "predefined_count": predefined_count,
            "dynamic_count": dynamic_count,
            "total_count": predefined_count + dynamic_count,
            "qualified_count": dynamic_count,
            "merged_count": len(self._merged_knowledge)
        }


_knowledge_exporter: Optional[KnowledgeExporter] = None


def get_knowledge_exporter() -> KnowledgeExporter:
    global _knowledge_exporter
    if _knowledge_exporter is None:
        _knowledge_exporter = KnowledgeExporter()
    return _knowledge_exporter