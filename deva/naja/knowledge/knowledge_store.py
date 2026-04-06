"""
Knowledge Store - 知识存储模块

统一管理学习层所有知识的存储，使用项目目录便于 AI Agent 读取
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


class KnowledgeState(Enum):
    OBSERVING = "observing"
    VALIDATING = "validating"
    QUALIFIED = "qualified"
    EXPIRED = "expired"


@dataclass
class KnowledgeEntry:
    id: str
    cause: str
    effect: str
    base_confidence: float
    source: str
    original_title: str
    extracted_at: str
    category: str
    status: str
    adjusted_confidence: float
    evidence_count: int
    quality_score: float
    last_updated: str = ""
    last_seen: str = ""
    mechanism: str = ""
    timeframe: str = ""
    manual_override: bool = False
    manual_note: str = ""

    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = self.extracted_at
        if not self.last_seen:
            self.last_seen = self.extracted_at

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeEntry":
        return cls(**data)


class KnowledgeStore:
    """
    知识存储模块

    存储位置：deva/naja/knowledge/
    便于 AI Agent 大模型读取和分析
    """

    BASE_DIR = Path(__file__).parent
    KNOWLEDGE_FILE = BASE_DIR / "causality_knowledge.json"
    NARRATIVES_FILE = BASE_DIR / "narratives.json"
    ARTICLES_FILE = BASE_DIR / "learned_articles.json"
    DAILY_REPORTS_FILE = BASE_DIR / "daily_reports.json"
    STATS_FILE = BASE_DIR / "knowledge_stats.json"

    def __init__(self):
        self._entries: List[KnowledgeEntry] = []
        self._load()

    def _ensure_dir(self):
        self.BASE_DIR.mkdir(parents=True, exist_ok=True)

    def _load(self):
        """加载已有知识"""
        if self.KNOWLEDGE_FILE.exists():
            try:
                with open(self.KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._entries = [KnowledgeEntry.from_dict(e) for e in data.get("knowledge", [])]
                print(f"[KnowledgeStore] 加载了 {len(self._entries)} 条知识")
            except Exception as e:
                print(f"[KnowledgeStore] 加载失败: {e}")
                self._entries = []
        else:
            self._entries = []
            self._ensure_dir()

    def _save(self):
        """保存知识"""
        self._ensure_dir()
        data = {
            "version": "2.0",
            "last_updated": datetime.now().isoformat(),
            "knowledge_count": len(self._entries),
            "knowledge": [e.to_dict() for e in self._entries]
        }
        with open(self.KNOWLEDGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add(self, entry: KnowledgeEntry) -> bool:
        """添加新知识"""
        existing = self.get_by_cause(entry.cause)
        if existing:
            return self.update(existing.id, entry)
        self._entries.append(entry)
        self._save()
        return True

    def update(self, entry_id: str, new_data: KnowledgeEntry) -> bool:
        """更新知识"""
        for i, e in enumerate(self._entries):
            if e.id == entry_id:
                self._entries[i] = new_data
                self._save()
                return True
        return False

    def get(self, entry_id: str) -> Optional[KnowledgeEntry]:
        """获取单条知识"""
        for e in self._entries:
            if e.id == entry_id:
                return e
        return None

    def get_by_cause(self, cause: str) -> Optional[KnowledgeEntry]:
        """根据 cause 查找知识"""
        for e in self._entries:
            if e.cause.lower() == cause.lower():
                return e
        return None

    def get_by_state(self, state: KnowledgeState) -> List[KnowledgeEntry]:
        """获取指定状态的知识"""
        return [e for e in self._entries if e.status == state.value]

    def get_all(self) -> List[KnowledgeEntry]:
        """获取所有知识"""
        return self._entries

    def delete(self, entry_id: str) -> bool:
        """删除知识"""
        for i, e in enumerate(self._entries):
            if e.id == entry_id:
                del self._entries[i]
                self._save()
                return True
        return False

    def manual_override(self, entry_id: str, new_status: KnowledgeState,
                       note: str = "") -> bool:
        """手动干预知识状态"""
        entry = self.get(entry_id)
        if not entry:
            return False
        entry.status = new_status.value
        entry.manual_override = True
        entry.manual_note = note
        entry.last_updated = datetime.now().isoformat()
        self._save()
        return True

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        states = {s.value: 0 for s in KnowledgeState}
        categories = {}
        total_confidence = 0
        qualified_count = 0

        for e in self._entries:
            states[e.status] = states.get(e.status, 0) + 1
            categories[e.category] = categories.get(e.category, 0) + 1
            total_confidence += e.adjusted_confidence
            if e.status == KnowledgeState.QUALIFIED.value:
                qualified_count += 1

        avg_confidence = total_confidence / len(self._entries) if self._entries else 0

        return {
            "total": len(self._entries),
            "by_state": states,
            "by_category": categories,
            "avg_confidence": round(avg_confidence, 3),
            "qualified_count": qualified_count,
            "last_updated": datetime.now().isoformat()
        }

    def get_for_trading(self) -> Dict[str, List[Dict]]:
        """获取可用于交易决策的知识"""
        qualified = []
        validating = []

        for e in self._entries:
            item = {
                "id": e.id,
                "cause": e.cause,
                "effect": e.effect,
                "confidence": e.adjusted_confidence,
                "evidence_count": e.evidence_count,
                "days_tracked": (datetime.now() - datetime.fromisoformat(e.extracted_at)).days,
                "source": e.source
            }
            if e.status == KnowledgeState.QUALIFIED.value:
                qualified.append(item)
            elif e.status == KnowledgeState.VALIDATING.value:
                validating.append(item)

        return {
            "qualified": qualified,
            "validating": validating,
            "qualified_count": len(qualified),
            "validating_count": len(validating),
            "observing_count": states.get(KnowledgeState.OBSERVING.value, 0)
        }

    def save_narratives(self, narratives: Dict[str, Any]):
        """保存叙事库"""
        self._ensure_dir()
        with open(self.NARRATIVES_FILE, 'w', encoding='utf-8') as f:
            json.dump(narratives, f, ensure_ascii=False, indent=2)

    def load_narratives(self) -> Dict[str, Any]:
        """加载叙事库"""
        if self.NARRATIVES_FILE.exists():
            with open(self.NARRATIVES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"narratives": []}

    def save_article(self, article_data: Dict[str, Any]):
        """保存已学习的文章"""
        self._ensure_dir()
        articles = []
        if self.ARTICLES_FILE.exists():
            with open(self.ARTICLES_FILE, 'r', encoding='utf-8') as f:
                articles = json.load(f)
        articles.append(article_data)
        articles = articles[-100:]
        with open(self.ARTICLES_FILE, 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)

    def save_daily_report(self, report_data: Dict[str, Any]):
        """保存每日报告"""
        self._ensure_dir()
        reports = []
        if self.DAILY_REPORTS_FILE.exists():
            with open(self.DAILY_REPORTS_FILE, 'r', encoding='utf-8') as f:
                reports = json.load(f)
        reports.append(report_data)
        reports = reports[-30:]
        with open(self.DAILY_REPORTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(reports, f, ensure_ascii=False, indent=2)


_knowledge_store: Optional[KnowledgeStore] = None


def get_knowledge_store() -> KnowledgeStore:
    global _knowledge_store
    if _knowledge_store is None:
        _knowledge_store = KnowledgeStore()
    return _knowledge_store