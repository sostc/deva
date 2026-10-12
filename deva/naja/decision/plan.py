"""决策产物契约：``DecisionPlan``。

权威链（见 ``docs/naja/decision_action_center_design.md`` §3）::

    ManasEngine（判断：要不要动 / 为什么 / 多确信 / 多危险）
        ↓  action_type 的唯一权威
    DecisionOrchestrator + DecisionFusion（决策：融合外部洞察，产出 DecisionPlan）
        ↓  单一出口
    Bandit / AdaptiveCycle（执行：按 DecisionPlan 定量建仓 / 调仓 / 离场）

设计要点：

- ``action_type`` 是**四档严格程度**的指令，不是自由文本。其权威定义在
  ``ManasEngine.ActionType``；本模块只提供排序与"只能下调"的收敛工具，
  不重新定义档位。
- 融合层**可以下调**（更保守）档位，**不可上调**——上调必须由判断层给，
  否则等于给决策层偷偷加仓权限。
- ``size_hint`` 是 0~1 的**仓位乘子**，由 ``decision.sizing`` 单一口径产出，
  执行层不再自己拍一个固定数。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

# 行动档位的严格程度：数值越大越激进。0 = 不动。
ACTION_SEVERITY: Dict[str, int] = {
    "hold": 0,
    "act_minimally": 1,
    "act_carefully": 2,
    "act_fully": 3,
}


def action_severity(action_type: Any) -> int:
    """把 ``action_type``（str 或带 ``.value`` 的枚举）映射为严格程度。

    未知值一律当 ``hold``（0）——保守失败，绝不让"没见过的档位"变成加仓理由。
    """
    if action_type is None:
        return 0
    value = getattr(action_type, "value", action_type)
    return ACTION_SEVERITY.get(str(value), 0)


def more_conservative(action_type: Any, other: Any) -> Any:
    """在两档之间取更保守的那个（severity 更小者）。

    用于「融合层只能下调」——调用方不再各自写 if/else 比档位。
    """
    return action_type if action_severity(action_type) <= action_severity(other) else other


@dataclass
class DecisionPlan:
    """一条决策的完整产物：动什么、怎么动、动多大、为什么。

    这是"决策层"对外唯一的产物契约。执行层只读它，不读散落的
    ``final_confidence`` / ``harmony_strength`` 之类中间量。
    """

    symbol: str = ""
    side: str = "none"                 # buy / sell / hold / none
    action_type: str = "hold"          # 权威来自 ManasEngine
    size_hint: float = 0.0             # 0~1 仓位乘子（decision.sizing 单一口径）
    confidence: float = 0.0            # 融合置信度
    risk_temperature: float = 1.0      # Manas 风险温度
    gate_reason: str = ""              # Manas 的行动门理由（为什么不动 / 为什么只轻仓）
    should_act: bool = False
    reasons: List[str] = field(default_factory=list)
    source_signal: Dict[str, Any] = field(default_factory=dict)

    def is_actionable(self) -> bool:
        """是否是一条"真的会动手"的计划。"""
        return (
            bool(self.should_act)
            and action_severity(self.action_type) > 0
            and self.size_hint > 0.0
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "action_type": self.action_type,
            "size_hint": self.size_hint,
            "confidence": self.confidence,
            "risk_temperature": self.risk_temperature,
            "gate_reason": self.gate_reason,
            "should_act": self.should_act,
            "reasons": self.reasons,
            "source_signal": self.source_signal,
        }

    @classmethod
    def from_fusion(
        cls,
        fusion: Any,
        *,
        symbol: str = "",
        side: str = "none",
        source_signal: Dict[str, Any] | None = None,
        size_hint: float = 0.0,
    ) -> "DecisionPlan":
        """从融合层输出（``FusionOutput``）构造决策计划。

        只做字段搬运与口径归一，不做任何判断——判断应该已经发生在
        manas / fusion 里。``size_hint`` 由调用方传入（``decision.sizing`` 产出）。
        """
        return cls(
            symbol=symbol,
            side=side,
            action_type=str(getattr(fusion, "action_type", "hold")),
            size_hint=float(size_hint),
            confidence=float(getattr(fusion, "fused_confidence", 0.0)),
            risk_temperature=float(getattr(fusion, "risk_temperature", 1.0)),
            gate_reason=str(getattr(fusion, "gate_reason", "") or ""),
            should_act=bool(getattr(fusion, "should_act", False)),
            reasons=list(getattr(fusion, "final_decision", {}).get("reasoning", []) or []),
            source_signal=dict(source_signal or {}),
        )


def side_from_signal_type(signal_type: Any) -> str:
    """把策略信号的 ``signal_type`` 归一为 ``buy`` / ``sell`` / ``none``。"""
    text = str(signal_type or "").upper()
    if "BUY" in text or "买入" in text:
        return "buy"
    if "SELL" in text or "卖出" in text:
        return "sell"
    return "none"


__all__ = [
    "ACTION_SEVERITY",
    "DecisionPlan",
    "action_severity",
    "more_conservative",
    "side_from_signal_type",
]
