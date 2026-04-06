"""
Cognition Interface - 学习层与认知层的接口

学习层 → 认知层：
1. 注入因果知识到 NarrativeTracker
2. 更新 CrossSignalAnalyzer 的信号权重
3. 影响 Attention 系统的注意力分配

影响链条：
知识(QUALIFIED) → 冷静期结束 → 注意力系统 → 行情/新闻分析
"""

import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from .knowledge_store import KnowledgeStore, KnowledgeEntry, KnowledgeState, get_knowledge_store
from .state_manager import KnowledgeStateManager, get_state_manager


class CognitionInterface:
    """
    学习层与认知层的标准接口

    负责：
    1. 将学习到的因果知识注入认知系统
    2. 通知注意力系统调整权重
    3. 影响 Radar 感知层的阈值设置
    """

    def __init__(self,
                 store: Optional[KnowledgeStore] = None,
                 state_manager: Optional[KnowledgeStateManager] = None):
        self.store = store or get_knowledge_store()
        self.state_manager = state_manager or get_state_manager()

        self._attention_listeners: List[callable] = []
        self._radar_listeners: List[callable] = []

    def add_attention_listener(self, callback: callable):
        """添加注意力系统监听器"""
        self._attention_listeners.append(callback)

    def add_radar_listener(self, callback: callable):
        """添加雷达系统监听器"""
        self._radar_listeners.append(callback)

    def inject_causality(self, entry_id: str) -> bool:
        """
        注入单条因果知识到认知系统

        当知识状态变为 QUALIFIED 时调用此方法
        """
        entry = self.store.get(entry_id)
        if not entry:
            return False

        if KnowledgeState(entry.status) != KnowledgeState.QUALIFIED:
            return False

        knowledge_for_cognition = {
            "id": entry.id,
            "cause": entry.cause,
            "effect": entry.effect,
            "confidence": entry.adjusted_confidence,
            "evidence_count": entry.evidence_count,
            "category": entry.category,
            "injected_at": datetime.now().isoformat(),
            "source": entry.source,
            "mechanism": entry.mechanism,
            "timeframe": entry.timeframe
        }

        self._notify_attention(knowledge_for_cognition)
        self._notify_radar(knowledge_for_cognition)

        self._save_injected_knowledge(knowledge_for_cognition)

        return True

    def inject_all_qualified(self) -> Dict[str, Any]:
        """
        注入所有正式知识到认知系统

        系统启动时调用
        """
        results = {
            "injected": [],
            "failed": [],
            "skipped": []
        }

        for entry in self.store.get_by_state(KnowledgeState.QUALIFIED):
            success = self.inject_causality(entry.id)
            if success:
                results["injected"].append(entry.id)
            else:
                results["failed"].append(entry.id)

        return results

    def _notify_attention(self, knowledge: Dict[str, Any]):
        """通知注意力系统"""
        for listener in self._attention_listeners:
            try:
                listener("knowledge_qualified", knowledge)
            except Exception as e:
                print(f"[CognitionInterface] 通知注意力系统失败: {e}")

    def _notify_radar(self, knowledge: Dict[str, Any]):
        """通知雷达系统"""
        for listener in self._radar_listeners:
            try:
                listener("knowledge_updated", knowledge)
            except Exception as e:
                print(f"[CognitionInterface] 通知雷达系统失败: {e}")

    def _save_injected_knowledge(self, knowledge: Dict[str, Any]):
        """保存已注入的知识记录"""
        injected_file = self.store.BASE_DIR / "injected_knowledge.json"
        injected_list = []

        if injected_file.exists():
            try:
                with open(injected_file, 'r', encoding='utf-8') as f:
                    injected_list = json.load(f)
            except Exception:
                injected_list = []

        injected_list.append(knowledge)
        injected_list = injected_list[-100:]

        with open(injected_file, 'w', encoding='utf-8') as f:
            json.dump(injected_list, f, ensure_ascii=False, indent=2)

    def get_knowledge_for_trading(self) -> Dict[str, Any]:
        """
        获取可用于交易决策的知识

        返回给注意力系统的数据格式
        """
        qualified = []
        validating = []

        for entry in self.store.get_by_state(KnowledgeState.QUALIFIED):
            qualified.append({
                "id": entry.id,
                "cause": entry.cause,
                "effect": entry.effect,
                "confidence": entry.adjusted_confidence,
                "evidence_count": entry.evidence_count,
                "category": entry.category,
                "days_active": (datetime.now() - datetime.fromisoformat(entry.extracted_at)).days,
                "source": entry.source
            })

        for entry in self.store.get_by_state(KnowledgeState.VALIDATING):
            cooldown_info = self.state_manager.get_cooldown_info(entry.id)
            validating.append({
                "id": entry.id,
                "cause": entry.cause,
                "effect": entry.effect,
                "confidence": entry.adjusted_confidence,
                "evidence_count": entry.evidence_count,
                "category": entry.category,
                "cooldown_info": cooldown_info,
                "source": entry.source
            })

        return {
            "qualified": qualified,
            "validating": validating,
            "qualified_count": len(qualified),
            "validating_count": len(validating),
            "timestamp": datetime.now().isoformat()
        }

    def get_knowledge_summary(self) -> Dict[str, Any]:
        """获取知识汇总，用于 UI 显示"""
        stats = self.store.get_stats()

        recent_entries = sorted(
            self.store.get_all(),
            key=lambda x: x.extracted_at,
            reverse=True
        )[:10]

        recent = []
        for e in recent_entries:
            cooldown = self.state_manager.get_cooldown_info(e.id)
            recent.append({
                "id": e.id,
                "cause": e.cause,
                "effect": e.effect,
                "status": e.status,
                "confidence": e.adjusted_confidence,
                "evidence_count": e.evidence_count,
                "source": e.source,
                "extracted_at": e.extracted_at,
                "cooldown_info": cooldown,
                "manual_override": e.manual_override
            })

        return {
            "stats": stats,
            "recent": recent,
            "transition_history": self.state_manager.get_transition_history()[:20]
        }

    def create_knowledge_from_external(self,
                                       cause: str,
                                       effect: str,
                                       source: str,
                                       title: str = "",
                                       confidence: float = 0.7,
                                       category: str = "general",
                                       mechanism: str = "",
                                       timeframe: str = "") -> Optional[str]:
        """
        从外部学习（文章/日报）创建新知识

        新知识进入观察期
        """
        from .knowledge_store import KnowledgeEntry
        import uuid

        entry = KnowledgeEntry(
            id=str(uuid.uuid4())[:8],
            cause=cause,
            effect=effect,
            base_confidence=confidence,
            source=source,
            original_title=title,
            extracted_at=datetime.now().isoformat(),
            category=category,
            status=KnowledgeState.OBSERVING.value,
            adjusted_confidence=confidence,
            evidence_count=1,
            quality_score=confidence,
            mechanism=mechanism,
            timeframe=timeframe
        )

        self.store.add(entry)
        return entry.id


_cognition_interface: Optional[CognitionInterface] = None


def get_cognition_interface() -> CognitionInterface:
    global _cognition_interface
    if _cognition_interface is None:
        _cognition_interface = CognitionInterface()
    return _cognition_interface