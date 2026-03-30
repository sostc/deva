"""
MetaEvolution - 元进化层

系统的自我观察、自我学习和自我改进机制

核心功能：
1. SelfObserver: 观察系统自身的决策表现
2. PerformanceTracker: 追踪各模块的性能指标
3. AdaptationEngine: 根据反馈调整系统参数
4. EvolutionRecorder: 记录进化历史

层级定位：
- 位于意识层之上，属于"妙观察智"
- 不直接做决策，而是观察决策
- 发现问题后，通过调整参数来进化
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

log = logging.getLogger(__name__)


class EvolutionPhase(Enum):
    """进化阶段"""
    OBSERVING = "observing"           # 观察中
    HYPOTHESIZING = "hypothesizing"  # 假设中
    TESTING = "testing"              # 测试中
    STABILIZING = "stabilizing"      # 稳定中
    EVOLVED = "evolved"              # 已进化


class PerformanceTrend(Enum):
    """性能趋势"""
    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"
    UNKNOWN = "unknown"


@dataclass
class DecisionRecord:
    """决策记录"""
    timestamp: float
    decision_type: str
    context: Dict[str, Any]
    decision: str
    outcome: Optional[float] = None
    success: Optional[bool] = None


@dataclass
class ModulePerformance:
    """模块性能指标"""
    module_name: str
    call_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    last_call_time: float = 0.0
    trend: PerformanceTrend = PerformanceTrend.UNKNOWN
    recent_outcomes: List[bool] = field(default_factory=lambda: deque(maxlen=20))


@dataclass
class EvolutionInsight:
    """进化洞察"""
    insight_type: str
    description: str
    confidence: float
    suggested_action: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class SelfObserver:
    """
    自我观察器

    持续观察系统的决策过程和结果，不干预只记录
    """

    def __init__(self):
        self._decision_records: deque = deque(maxlen=1000)
        self._module_performances: Dict[str, ModulePerformance] = {}
        self._start_time = time.time()

    def record_decision(
        self,
        decision_type: str,
        context: Dict[str, Any],
        decision: str,
        outcome: Optional[float] = None,
        success: Optional[bool] = None
    ):
        """记录一次决策"""
        record = DecisionRecord(
            timestamp=time.time(),
            decision_type=decision_type,
            context=context,
            decision=decision,
            outcome=outcome,
            success=success
        )
        self._decision_records.append(record)

    def record_outcome(self, decision_type: str, success: bool, latency_ms: float = 0):
        """记录决策结果"""
        for record in reversed(self._decision_records):
            if record.decision_type == decision_type and record.success is None:
                record.success = success
                if latency_ms > 0:
                    record.outcome = latency_ms
                break

        self._update_module_performance(decision_type, success, latency_ms)

    def _update_module_performance(self, module_name: str, success: bool, latency_ms: float):
        """更新模块性能"""
        if module_name not in self._module_performances:
            self._module_performances[module_name] = ModulePerformance(module_name=module_name)

        perf = self._module_performances[module_name]
        perf.call_count += 1
        perf.total_latency_ms += latency_ms
        perf.avg_latency_ms = perf.total_latency_ms / perf.call_count
        perf.last_call_time = time.time()

        if success:
            perf.success_count += 1
        else:
            perf.failure_count += 1

        perf.recent_outcomes.append(success)
        perf.trend = self._calculate_trend(perf.recent_outcomes)

    def _calculate_trend(self, outcomes: List[bool]) -> PerformanceTrend:
        """计算性能趋势"""
        if len(outcomes) < 10:
            return PerformanceTrend.UNKNOWN

        recent = list(outcomes)[-10:]
        first_half = recent[:5]
        second_half = recent[5:]

        if not second_half:
            return PerformanceTrend.UNKNOWN

        first_success_rate = sum(first_half) / len(first_half)
        second_success_rate = sum(second_half) / len(second_half)

        diff = second_success_rate - first_success_rate

        if diff > 0.1:
            return PerformanceTrend.IMPROVING
        elif diff < -0.1:
            return PerformanceTrend.DEGRADING
        else:
            return PerformanceTrend.STABLE

    def get_module_insights(self) -> List[EvolutionInsight]:
        """获取模块洞察"""
        insights = []

        for name, perf in self._module_performances.items():
            if perf.call_count < 10:
                continue

            success_rate = perf.success_count / perf.call_count if perf.call_count > 0 else 0

            if perf.trend == PerformanceTrend.DEGRADING:
                insights.append(EvolutionInsight(
                    insight_type="performance_degradation",
                    description=f"{name} 性能下降: 成功率 {success_rate:.1%}, 趋势 {perf.trend.value}",
                    confidence=0.8,
                    suggested_action=f"检查 {name} 模块，可能需要调整参数或重新训练"
                ))

            if perf.avg_latency_ms > 1000 and perf.call_count > 20:
                insights.append(EvolutionInsight(
                    insight_type="latency_warning",
                    description=f"{name} 延迟较高: {perf.avg_latency_ms:.1f}ms",
                    confidence=0.7,
                    suggested_action=f"优化 {name} 模块性能"
                ))

        return insights

    def get_summary(self) -> Dict[str, Any]:
        """获取观察摘要"""
        total_decisions = len(self._decision_records)
        successful = sum(1 for r in self._decision_records if r.success is True)
        failed = sum(1 for r in self._decision_records if r.success is False)
        pending = sum(1 for r in self._decision_records if r.success is None)

        return {
            "total_decisions": total_decisions,
            "successful": successful,
            "failed": failed,
            "pending": pending,
            "success_rate": successful / max(successful + failed, 1),
            "uptime_seconds": time.time() - self._start_time,
            "modules": {
                name: {
                    "call_count": p.call_count,
                    "success_rate": p.success_count / max(p.call_count, 1),
                    "avg_latency_ms": p.avg_latency_ms,
                    "trend": p.trend.value
                }
                for name, p in self._module_performances.items()
            }
        }


class MetaEvolution:
    """
    元进化引擎

    根据观察结果，自动调整系统参数或提出改进建议

    工作流程：
    1. 观察（SelfObserver）→ 收集数据
    2. 分析 → 识别问题/机会
    3. 假设 → 形成改进假设
    4. 测试 → 小范围验证
    5. 进化 → 如果成功则推广
    """

    def __init__(self):
        self._observer = SelfObserver()
        self._phase = EvolutionPhase.OBSERVING
        self._evolution_history: List[EvolutionInsight] = []
        self._hypotheses: List[Dict[str, Any]] = []
        self._test_results: Dict[str, bool] = {}
        self._enabled = True

    @property
    def observer(self) -> SelfObserver:
        """获取自我观察器"""
        return self._observer

    def set_enabled(self, enabled: bool):
        """设置是否启用"""
        self._enabled = enabled

    def record_decision(self, decision_type: str, context: Dict[str, Any], decision: str):
        """记录一次决策"""
        if not self._enabled:
            return
        self._observer.record_decision(decision_type, context, decision)

    def record_outcome(self, decision_type: str, success: bool, latency_ms: float = 0):
        """记录决策结果"""
        if not self._enabled:
            return
        self._observer.record_outcome(decision_type, success, latency_ms)

    def think(self) -> List[EvolutionInsight]:
        """
        元认知思考

        定期调用，检查是否需要进化
        """
        if not self._enabled:
            return []

        insights = self._observer.get_module_insights()

        for insight in insights:
            if insight.suggested_action:
                log.info(f"[MetaEvolution] {insight.insight_type}: {insight.description}")
                log.info(f"[MetaEvolution] 建议: {insight.suggested_action}")
                self._evolution_history.append(insight)

        self._analyze_and_evolve()

        return insights

    def _analyze_and_evolve(self):
        """分析并进化"""
        if self._phase == EvolutionPhase.OBSERVING:
            self._update_phase_to_hypothesizing()

        elif self._phase == EvolutionPhase.HYPOTHESIZING:
            if len(self._hypotheses) >= 3:
                self._phase = EvolutionPhase.TESTING

        elif self._phase == EvolutionPhase.TESTING:
            successful_tests = sum(1 for v in self._test_results.values() if v)
            if successful_tests >= 2:
                self._phase = EvolutionPhase.EVOLVED
            elif len(self._test_results) >= 5:
                self._phase = EvolutionPhase.STABILIZING

    def _update_phase_to_hypothesizing(self):
        """更新到假设阶段"""
        summary = self._observer.get_summary()

        if summary["modules"]:
            for module_name, module_stats in summary["modules"].items():
                if module_stats["success_rate"] < 0.6:
                    self._hypotheses.append({
                        "module": module_name,
                        "problem": "success_rate_low",
                        "rate": module_stats["success_rate"]
                    })

        if self._hypotheses:
            self._phase = EvolutionPhase.HYPOTHESIZING
            log.info(f"[MetaEvolution] 进入假设阶段，发现 {len(self._hypotheses)} 个潜在问题")

    def get_phase(self) -> EvolutionPhase:
        """获取当前进化阶段"""
        return self._phase

    def get_evolution_history(self) -> List[EvolutionInsight]:
        """获取进化历史"""
        return self._evolution_history

    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "enabled": self._enabled,
            "phase": self._phase.value,
            "hypotheses_count": len(self._hypotheses),
            "tests_count": len(self._test_results),
            "evolution_insights": len(self._evolution_history),
            "observer_summary": self._observer.get_summary()
        }


_global_meta_evolution: Optional[MetaEvolution] = None


def get_meta_evolution() -> MetaEvolution:
    """获取元进化引擎单例"""
    global _global_meta_evolution
    if _global_meta_evolution is None:
        _global_meta_evolution = MetaEvolution()
    return _global_meta_evolution


def initialize_meta_evolution() -> MetaEvolution:
    """初始化元进化引擎"""
    evo = get_meta_evolution()
    log.info("[MetaEvolution] 元进化引擎已初始化")
    return evo