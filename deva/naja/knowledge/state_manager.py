"""
Knowledge State Manager - 知识状态管理器

管理知识的生命周期状态转换：
OBSERVING → VALIDATING → QUALIFIED → EXPIRED

冷静期机制：
- 观察期：默认 7 天，用于积累初始证据
- 验证期：继续积累证据，需要多源验证
- 正式期：参与决策，影响注意力系统
- 过期：长时间无新证据，自动过期
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
from enum import Enum

from .knowledge_store import KnowledgeStore, KnowledgeEntry, KnowledgeState, get_knowledge_store


class StateTransition(Enum):
    AUTO = "auto"           # 自动转换
    MANUAL = "manual"        # 手动干预
    EVIDENCE = "evidence"    # 证据驱动


@dataclass
class StateTransitionLog:
    entry_id: str
    from_state: str
    to_state: str
    reason: str
    transition_type: str
    timestamp: str
    manual_note: str = ""

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
            "transition_type": self.transition_type,
            "timestamp": self.timestamp,
            "manual_note": self.manual_note
        }


class KnowledgeStateManager:
    """
    知识状态管理器

    核心职责：
    1. 管理知识状态转换
    2. 计算冷静期
    3. 触发状态变化通知
    4. 记录状态转换历史
    """

    OBSERVING_DAYS = 7
    VALIDATING_DAYS = 7
    QUALIFIED_DAYS = 30
    EXPIRED_DAYS = 60

    MIN_EVIDENCE_FOR_VALIDATING = 2
    MIN_EVIDENCE_FOR_QUALIFIED = 3
    MIN_CONFIDENCE_THRESHOLD = 0.5

    def __init__(self, store: Optional[KnowledgeStore] = None):
        self.store = store or get_knowledge_store()
        self._transition_logs: List[StateTransitionLog] = []
        self._listeners: List[Callable[[str, KnowledgeState, KnowledgeState], None]] = []
        self._load_transition_logs()

    def _load_transition_logs(self):
        """加载状态转换日志"""
        log_file = self.store.BASE_DIR / "state_transitions.json"
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._transition_logs = [StateTransitionLog(**t) for t in data.get("logs", [])]
            except Exception as e:
                print(f"[StateManager] 加载转换日志失败: {e}")

    def _save_transition_logs(self):
        """保存状态转换日志"""
        log_file = self.store.BASE_DIR / "state_transitions.json"
        self.store._ensure_dir()
        data = {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "logs": [t.to_dict() for t in self._transition_logs]
        }
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_listener(self, callback: Callable[[str, KnowledgeState, KnowledgeState], None]):
        """添加状态转换监听器"""
        self._listeners.append(callback)

    def _notify_listeners(self, entry_id: str, old_state: KnowledgeState, new_state: KnowledgeState):
        """通知监听器"""
        for listener in self._listeners:
            try:
                listener(entry_id, old_state, new_state)
            except Exception as e:
                print(f"[StateManager] 通知失败: {e}")

    def can_transition_to(self, entry: KnowledgeEntry, target_state: KnowledgeState) -> tuple[bool, str]:
        """
        检查是否可以转换到目标状态

        Returns:
            (can_transition, reason)
        """
        current_state = KnowledgeState(entry.status)

        if current_state == KnowledgeState.EXPIRED:
            return False, "已过期知识不能再转换"

        if current_state == target_state:
            return False, "已经是目标状态"

        if target_state == KnowledgeState.OBSERVING:
            return False, "不能回退到观察期"

        if target_state == KnowledgeState.VALIDATING:
            if current_state != KnowledgeState.OBSERVING:
                return False, "只能从观察期转入验证期"
            if entry.evidence_count < self.MIN_EVIDENCE_FOR_VALIDATING:
                return False, f"需要至少 {self.MIN_EVIDENCE_FOR_VALIDATING} 个证据"
            days_since_start = (datetime.now() - datetime.fromisoformat(entry.extracted_at)).days
            if days_since_start < self.OBSERVING_DAYS:
                return False, f"观察期需要 {self.OBSERVING_DAYS} 天"
            return True, "满足验证期条件"

        if target_state == KnowledgeState.QUALIFIED:
            if current_state not in [KnowledgeState.OBSERVING, KnowledgeState.VALIDATING]:
                return False, "需要经过验证期"
            if entry.evidence_count < self.MIN_EVIDENCE_FOR_QUALIFIED:
                return False, f"需要至少 {self.MIN_EVIDENCE_FOR_QUALIFIED} 个证据"
            if entry.adjusted_confidence < self.MIN_CONFIDENCE_THRESHOLD:
                return False, f"置信度需要 >= {self.MIN_CONFIDENCE_THRESHOLD}"
            return True, "满足正式期条件"

        if target_state == KnowledgeState.EXPIRED:
            return True, "可以标记为过期"

        return False, "未知状态"

    def transition(self, entry_id: str, target_state: KnowledgeState,
                   reason: str = "", manual_note: str = "") -> bool:
        """
        执行状态转换
        """
        entry = self.store.get(entry_id)
        if not entry:
            return False

        old_state = KnowledgeState(entry.status)
        can_transition, check_reason = self.can_transition_to(entry, target_state)

        if not can_transition:
            print(f"[StateManager] 状态转换失败: {check_reason}")
            return False

        is_manual = bool(manual_note)
        transition_type = StateTransition.MANUAL.value if is_manual else StateTransition.AUTO.value

        entry.status = target_state.value
        entry.last_updated = datetime.now().isoformat()
        if is_manual:
            entry.manual_override = True
            entry.manual_note = manual_note

        self.store.update(entry_id, entry)

        log = StateTransitionLog(
            entry_id=entry_id,
            from_state=old_state.value,
            to_state=target_state.value,
            reason=reason or check_reason,
            transition_type=transition_type,
            timestamp=datetime.now().isoformat(),
            manual_note=manual_note
        )
        self._transition_logs.append(log)
        self._save_transition_logs()

        self._notify_listeners(entry_id, old_state, target_state)

        print(f"[StateManager] 知识 {entry_id} 从 {old_state.value} 转换到 {target_state.value}")
        return True

    def process_auto_transitions(self) -> Dict[str, Any]:
        """
        处理自动状态转换（定时任务调用）
        """
        now = datetime.now()
        results = {
            "checked": 0,
            "transitions": [],
            "errors": []
        }

        for entry in self.store.get_all():
            results["checked"] += 1
            current_state = KnowledgeState(entry.status)

            if current_state == KnowledgeState.OBSERVING:
                days_since_start = (now - datetime.fromisoformat(entry.extracted_at)).days
                if days_since_start >= self.OBSERVING_DAYS:
                    success = self.transition(
                        entry.id,
                        KnowledgeState.VALIDATING,
                        reason=f"观察期结束 ({self.OBSERVING_DAYS}天)"
                    )
                    if success:
                        results["transitions"].append({
                            "id": entry.id,
                            "from": KnowledgeState.OBSERVING.value,
                            "to": KnowledgeState.VALIDATING.value
                        })

            elif current_state == KnowledgeState.VALIDATING:
                days_since_last_update = (now - datetime.fromisoformat(entry.last_updated)).days
                if days_since_last_update >= self.VALIDATING_DAYS:
                    if entry.evidence_count >= self.MIN_EVIDENCE_FOR_QUALIFIED and \
                       entry.adjusted_confidence >= self.MIN_CONFIDENCE_THRESHOLD:
                        success = self.transition(
                            entry.id,
                            KnowledgeState.QUALIFIED,
                            reason=f"验证期结束，满足条件"
                        )
                        if success:
                            results["transitions"].append({
                                "id": entry.id,
                                "from": KnowledgeState.VALIDATING.value,
                                "to": KnowledgeState.QUALIFIED.value
                            })
                    else:
                        success = self.transition(
                            entry.id,
                            KnowledgeState.EXPIRED,
                            reason=f"验证期结束，未满足条件"
                        )
                        if success:
                            results["transitions"].append({
                                "id": entry.id,
                                "from": KnowledgeState.VALIDATING.value,
                                "to": KnowledgeState.EXPIRED.value
                            })

            elif current_state == KnowledgeState.QUALIFIED:
                days_since_last_seen = (now - datetime.fromisoformat(entry.last_seen)).days
                if days_since_last_seen >= self.EXPIRED_DAYS:
                    success = self.transition(
                        entry.id,
                        KnowledgeState.EXPIRED,
                        reason=f"长期未更新 ({days_since_last_seen}天)"
                    )
                    if success:
                        results["transitions"].append({
                            "id": entry.id,
                            "from": KnowledgeState.QUALIFIED.value,
                            "to": KnowledgeState.EXPIRED.value
                        })

        return results

    def get_cooldown_info(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """
        获取知识的冷静期信息

        Returns:
            {
                "remaining_days": int,
                "can_force_qualify": bool,
                "reasons": List[str]
            }
        """
        entry = self.store.get(entry_id)
        if not entry:
            return None

        current_state = KnowledgeState(entry.status)
        now = datetime.now()

        reasons = []
        can_force = False

        if current_state == KnowledgeState.OBSERVING:
            days_since_start = (now - datetime.fromisoformat(entry.extracted_at)).days
            remaining = self.OBSERVING_DAYS - days_since_start
            reasons.append(f"观察期剩余 {remaining} 天")
            if entry.evidence_count >= self.MIN_EVIDENCE_FOR_VALIDATING:
                reasons.append("✓ 证据数量已满足")
                can_force = True

        elif current_state == KnowledgeState.VALIDATING:
            days_since_last_update = (now - datetime.fromisoformat(entry.last_updated)).days
            remaining = self.VALIDATING_DAYS - days_since_last_update
            reasons.append(f"验证期剩余 {remaining} 天")
            if entry.evidence_count >= self.MIN_EVIDENCE_FOR_QUALIFIED and \
               entry.adjusted_confidence >= self.MIN_CONFIDENCE_THRESHOLD:
                reasons.append("✓ 证据和置信度已满足")
                can_force = True

        elif current_state == KnowledgeState.QUALIFIED:
            reasons.append("已正式参与决策")
            can_force = False

        elif current_state == KnowledgeState.EXPIRED:
            reasons.append("已过期，需要重新学习")
            can_force = False

        return {
            "entry_id": entry_id,
            "current_state": current_state.value,
            "remaining_days": max(0, remaining) if 'remaining' in dir() else 0,
            "can_force_qualify": can_force,
            "reasons": reasons
        }

    def get_transition_history(self, entry_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取状态转换历史"""
        if entry_id:
            return [t.to_dict() for t in self._transition_logs if t.entry_id == entry_id]
        return [t.to_dict() for t in self._transition_logs]

    def reset_to_observation(self, entry_id: str, note: str = "") -> bool:
        """重置知识到观察期（手动干预）"""
        return self.transition(entry_id, KnowledgeState.OBSERVING, reason="手动重置", manual_note=note)


_state_manager: Optional[KnowledgeStateManager] = None


def get_state_manager() -> KnowledgeStateManager:
    global _state_manager
    if _state_manager is None:
        _state_manager = KnowledgeStateManager()
    return _state_manager