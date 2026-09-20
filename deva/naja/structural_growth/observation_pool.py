"""观察池 - 持续追踪已验证行业

职责：
- 管理被纳入观察的行业列表
- 对每个行业运行完整三 Agent 链 + 状态机
- 提供按状态分组的汇总
- 支持状态持久化（save_state / load_state / save_to_file / load_from_file）

不自动交易，只输出研究结论与状态。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .industry_state import IndustryState, FactorState, HistoryPoint, FactorTrend
from .valuation_state import ValuationPhase, ValuationStateMachine, StateTransition
from .evidence import Evidence, EvidenceType, EvidenceStatus, FACTOR_DIMENSIONS
from .agents.discovery_agent import DiscoveryAgent, GrowthHypothesis, HypothesisType
from .agents.verification_agent import VerificationAgent, VerificationResult, VerificationVerdict, EvidenceChain
from .agents.valuation_agent import ValuationAgent, ValuationAnalysis, ValuationScenario, ScenarioType


@dataclass
class TrackedIndustry:
    """观察池中的单个行业"""
    state: IndustryState
    state_machine: ValuationStateMachine = field(default_factory=ValuationStateMachine)
    last_verifications: List = field(default_factory=list)
    last_valuation: Optional[ValuationAnalysis] = None
    last_run_at: Optional[float] = None

    @property
    def industry_id(self) -> str:
        return self.state.industry_id

    @property
    def name(self) -> str:
        return self.state.name

    @property
    def phase(self) -> ValuationPhase:
        return self.state_machine.current

    def to_dict(self) -> Dict:
        return {
            "industry_id": self.industry_id,
            "name": self.name,
            "phase": self.phase.value,
            "phase_name": self.phase.display_name,
            "is_early_stage": self.phase.is_early_stage,
            "is_key_stage": self.phase.is_key_stage,
            "last_run_at": self.last_run_at,
            "valuation": self.last_valuation.to_dict() if self.last_valuation else None,
            "last_verifications": [r.to_dict() for r in self.last_verifications] if self.last_verifications else [],
            "state": self.state.to_dict(),
            "state_machine": self.state_machine.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "TrackedIndustry":
        """从字典重建 TrackedIndustry"""
        state = _rebuild_industry_state(d["state"])
        sm = _rebuild_state_machine(d.get("state_machine", {}))
        last_verifs = _rebuild_verifications(d.get("last_verifications", []))
        last_val = _rebuild_valuation(d.get("last_valuation"))
        return cls(
            state=state,
            state_machine=sm,
            last_verifications=last_verifs,
            last_valuation=last_val,
            last_run_at=d.get("last_run_at"),
        )


# ---- 重建辅助函数 ----

def _rebuild_history_point(d: Dict) -> HistoryPoint:
    return HistoryPoint(
        value=float(d["value"]),
        timestamp=float(d["timestamp"]),
        source=d.get("source", ""),
    )


def _rebuild_factor_state(d: Dict) -> FactorState:
    fs = FactorState(dimension=d["dimension"])
    fs.current_value = d.get("current_value")
    fs.unit = d.get("unit", "")
    fs.confidence = float(d.get("confidence", 0.0))
    fs.sources = list(d.get("sources", []))
    fs.last_updated = float(d.get("last_updated", time.time()))
    fs.history = [_rebuild_history_point(p) for p in d.get("history", [])]
    return fs


def _rebuild_evidence(d: Dict) -> Evidence:
    return Evidence(
        id=d.get("id", ""),
        content=d.get("content", ""),
        source=d.get("source", ""),
        type=EvidenceType(d["type"]) if d.get("type") else EvidenceType.OTHER,
        status=EvidenceStatus(d["status"]) if d.get("status") else EvidenceStatus.NEUTRAL,
        dimension=d.get("dimension", ""),
        timestamp=float(d.get("timestamp", time.time())),
        confidence=float(d.get("confidence", 0.5)),
        raw_value=d.get("raw_value"),
        raw_unit=d.get("raw_unit", ""),
        metadata=dict(d.get("metadata", {})),
    )


def _rebuild_industry_state(d: Dict) -> IndustryState:
    state = IndustryState(industry_id=d["industry_id"], name=d.get("name", ""))
    state.updated_at = float(d.get("updated_at", time.time()))
    # 重建六维度
    factors = d.get("factors", {})
    for dim in FACTOR_DIMENSIONS:
        if dim in factors:
            setattr(state, dim, _rebuild_factor_state(factors[dim]))
    # 重建证据
    state.evidence = [_rebuild_evidence(e) for e in d.get("evidence", [])]
    state.counter_evidence = [_rebuild_evidence(e) for e in d.get("counter_evidence", [])]
    state.companies = list(d.get("companies", []))
    return state


def _rebuild_state_machine(d: Dict) -> ValuationStateMachine:
    sm = ValuationStateMachine()
    current = d.get("current_state", "S0")
    for phase in ValuationPhase:
        if phase.value == current:
            sm._current = phase
            break
    for tr in d.get("history", []):
        from_phase = None
        if tr.get("from_state"):
            for phase in ValuationPhase:
                if phase.value == tr["from_state"]:
                    from_phase = phase
                    break
        to_phase = ValuationPhase.S0_CYCLICAL
        for phase in ValuationPhase:
            if phase.value == tr.get("to_state", "S0"):
                to_phase = phase
                break
        sm._history.append(StateTransition(
            from_state=from_phase,
            to_state=to_phase,
            timestamp=float(tr.get("timestamp", time.time())),
            reason=tr.get("reason", ""),
            triggered_by=list(tr.get("triggered_by", [])),
        ))
    return sm


def _rebuild_evidence_chain(d: Dict) -> EvidenceChain:
    chain = EvidenceChain(hypothesis_id=d.get("hypothesis_id", ""))
    for item in d.get("items", []):
        chain.add(_rebuild_evidence(item))
    return chain


def _rebuild_verifications(data: List[Dict]) -> List[VerificationResult]:
    results = []
    for d in data:
        verdict_str = d.get("verdict", "inconclusive")
        try:
            verdict = VerificationVerdict(verdict_str)
        except ValueError:
            verdict = VerificationVerdict.INCONCLUSIVE
        results.append(VerificationResult(
            hypothesis_id=d.get("hypothesis_id", ""),
            hypothesis_type=d.get("hypothesis_type", ""),
            verdict=verdict,
            confidence=float(d.get("confidence", 0.0)),
            support_score=float(d.get("support_score", 0.0)),
            support_ratio=float(d.get("support_ratio", 0.5)),
            evidence_chain=_rebuild_evidence_chain(d.get("evidence", {})),
            weakening_factors=list(d.get("weakening_factors", [])),
            data_gaps=list(d.get("data_gaps", [])),
            cross_checks=list(d.get("cross_checks", [])),
        ))
    return results


def _rebuild_valuation(d: Optional[Dict]) -> Optional[ValuationAnalysis]:
    if not d:
        return None
    scenarios = []
    for s in d.get("scenarios", []):
        try:
            stype = ScenarioType(s.get("type", "base"))
        except ValueError:
            stype = ScenarioType.BASE
        scenarios.append(ValuationScenario(
            type=stype,
            name=s.get("name", ""),
            description=s.get("description", ""),
            margin_current=float(s.get("margin_current", 0.0)),
            margin_assumed=float(s.get("margin_assumed", 0.0)),
            margin_change_pp=float(s.get("margin_change_pp", 0.0)),
            profit_growth_rate=float(s.get("profit_growth_rate", 0.0)),
            implied_pe=float(s.get("implied_pe", 0.0)),
            assumptions=list(s.get("assumptions", [])),
        ))
    return ValuationAnalysis(
        industry_id=d.get("industry_id", ""),
        industry_name=d.get("industry_name", ""),
        scenarios=scenarios,
        expectation_gap=float(d.get("expectation_gap_pct", 0.0)),
        expectation_gap_signal=d.get("expectation_gap_signal", ""),
        recommendation=d.get("recommendation", ""),
        key_uncertainties=list(d.get("key_uncertainties", [])),
        verified_hypotheses=list(d.get("verified_hypotheses", [])),
        vetoed_hypotheses=list(d.get("vetoed_hypotheses", [])),
    )


class ObservationPool:
    """观察池：追踪多个行业的结构性增长状态"""

    def __init__(self, discovery: Optional[DiscoveryAgent] = None,
                 verification: Optional[VerificationAgent] = None,
                 valuation: Optional[ValuationAgent] = None):
        self._discovery = discovery or DiscoveryAgent()
        self._verification = verification or VerificationAgent()
        self._valuation = valuation or ValuationAgent()
        self._industries: Dict[str, TrackedIndustry] = {}

    # ---- 管理 ----
    def add(self, state: IndustryState) -> TrackedIndustry:
        """加入观察池"""
        tracked = TrackedIndustry(state=state)
        self._industries[state.industry_id] = tracked
        return tracked

    def remove(self, industry_id: str) -> bool:
        if industry_id in self._industries:
            del self._industries[industry_id]
            return True
        return False

    def get(self, industry_id: str) -> Optional[TrackedIndustry]:
        return self._industries.get(industry_id)

    def list(self) -> List[TrackedIndustry]:
        return list(self._industries.values())

    def __len__(self) -> int:
        return len(self._industries)

    def __contains__(self, industry_id: str) -> bool:
        return industry_id in self._industries

    # ---- 运行 ----
    def run(self, industry_id: Optional[str] = None) -> List[TrackedIndustry]:
        """运行三 Agent 链 + 状态机

        industry_id=None 时运行全部观察行业。
        运行后自动持久化状态并追加历史快照。
        """
        targets = [self._industries[industry_id]] if industry_id else list(self._industries.values())
        for tracked in targets:
            self._run_one(tracked)
        # 自动持久化
        self.save_to_file()
        self.append_history_snapshot()
        return targets

    def _run_one(self, tracked: TrackedIndustry) -> None:
        state = tracked.state
        hypotheses = self._discovery.discover(state)
        verifications = self._verification.verify_many(state, hypotheses)
        valuation = self._valuation.analyze(state, verifications)
        tracked.state_machine.evaluate(state, verifications, valuation)
        tracked.last_verifications = verifications
        tracked.last_valuation = valuation
        tracked.last_run_at = time.time()

    # ---- 汇总 ----
    def summary(self) -> Dict:
        """按状态分组的汇总"""
        counts = {p.value: 0 for p in ValuationPhase}
        names = {p.value: [] for p in ValuationPhase}
        for t in self._industries.values():
            counts[t.phase.value] += 1
            names[t.phase.value].append(t.name)
        return {
            "total": len(self._industries),
            "by_phase": counts,
            "names_by_phase": names,
            "candidates": [t.name for t in self._industries.values()
                           if t.phase == ValuationPhase.S4_REVALUATION_CANDIDATE],
            "key_stage": [t.name for t in self._industries.values()
                          if t.phase == ValuationPhase.S3_PROFIT_MATERIALIZE],
        }

    # ---- 持久化 ----
    def save_state(self) -> Dict:
        """保存观察池状态（供持久化）"""
        return {
            "industries": {
                tid: {
                    "state": t.state.to_dict(),
                    "phase": t.phase.value,
                    "state_machine": t.state_machine.to_dict(),
                    "last_verifications": [r.to_dict() for r in t.last_verifications] if t.last_verifications else [],
                    "last_valuation": t.last_valuation.to_dict() if t.last_valuation else None,
                    "last_run_at": t.last_run_at,
                }
                for tid, t in self._industries.items()
            },
            "saved_at": time.time(),
        }

    def load_state(self, data: Dict) -> None:
        """从字典恢复观察池状态"""
        industries = data.get("industries", {})
        self._industries.clear()
        for tid, idata in industries.items():
            tracked = TrackedIndustry.from_dict(idata)
            self._industries[tid] = tracked

    # ---- 文件持久化 ----
    _STATE_FILE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "structural_growth_state.json"
    )
    _HISTORY_FILE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "structural_growth_history.jsonl"
    )

    def save_to_file(self) -> bool:
        """将观察池状态保存到 JSON 文件"""
        try:
            os.makedirs(os.path.dirname(self._STATE_FILE), exist_ok=True)
            state = self.save_state()
            with open(self._STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, default=str)
            return True
        except Exception:
            return False

    def load_from_file(self) -> bool:
        """从 JSON 文件恢复观察池状态"""
        try:
            if not os.path.exists(self._STATE_FILE):
                return False
            with open(self._STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            self.load_state(state)
            return True
        except Exception:
            return False

    def append_history_snapshot(self) -> bool:
        """追加一条运行历史快照到 JSONL 文件"""
        try:
            os.makedirs(os.path.dirname(self._HISTORY_FILE), exist_ok=True)
            snapshot = {
                "timestamp": time.time(),
                "total": len(self._industries),
                "industries": {},
            }
            for tid, t in self._industries.items():
                val = t.last_valuation
                snapshot["industries"][tid] = {
                    "name": t.name,
                    "phase": t.phase.value,
                    "evidence_count": len(t.state.evidence),
                    "counter_evidence_count": len(t.state.counter_evidence),
                    "expectation_gap_pct": val.expectation_gap if val else None,
                    "expectation_gap_signal": val.expectation_gap_signal if val else "",
                    "verified_hypotheses": val.verified_hypotheses if val else [],
                    "vetoed_hypotheses": val.vetoed_hypotheses if val else [],
                    "recommendation": val.recommendation if val else "",
                }
            with open(self._HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(snapshot, ensure_ascii=False, default=str) + "\n")
            return True
        except Exception:
            return False

    def get_history(self, limit: int = 20) -> List[Dict]:
        """读取最近的运行历史快照"""
        try:
            if not os.path.exists(self._HISTORY_FILE):
                return []
            snapshots = []
            with open(self._HISTORY_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        snapshots.append(json.loads(line))
            return snapshots[-limit:] if len(snapshots) > limit else snapshots
        except Exception:
            return []

    def to_dict(self) -> Dict:
        return {
            "total": len(self._industries),
            "summary": self.summary(),
            "industries": [t.to_dict() for t in self._industries.values()],
        }
