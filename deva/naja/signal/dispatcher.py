"""Signal Dispatcher - 信号分发器

负责将策略执行结果分发到各个下游系统：
- SignalStream: 信号流（优先级路由）
- RadarEngine: 雷达检测
- CognitionEngine: 认知系统
- BanditOptimizer: 自适应交易

设计原则：
1. 单一职责：只负责分发，不负责存储
2. 依赖注入：通过 output_controller 控制分发目标
3. 幂等性：下游系统可独立运行，不影响主流程
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..strategy.result_store import StrategyResult

logger = logging.getLogger(__name__)

_loop_audit_log_stage = None

def _get_audit():
    global _loop_audit_log_stage
    if _loop_audit_log_stage is None:
        try:
            from ..common.loop_audit import LoopAudit
            _loop_audit_log_stage = lambda **kw: LoopAudit(**kw)
        except ImportError:
            _loop_audit_log_stage = lambda **kw: _DummyAudit()
    return _loop_audit_log_stage

class _DummyAudit:
    def __init__(self, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def record_data_out(self, *args, **kwargs): pass


class SignalDispatcher:
    """信号分发器

    统一管理策略结果到各下游系统的分发逻辑。
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._dispatch_errors = {"signal_stream": 0, "radar": 0, "cognition": 0, "bandit": 0, "output_controller": 0, "normalize": 0}
        self._total_dispatches = 0
        logger.info("SignalDispatcher 初始化完成")

    def dispatch(self, result: "StrategyResult") -> None:
        """分发策略结果到下游系统

        Args:
            result: 策略执行结果
        """
        with _get_audit()(loop_type="dataflow", stage="dispatch_start", data_in={"strategy_id": result.strategy_id, "success": result.success}) as audit:
            self._dispatch_to_signal_stream(result)
            self._dispatch_to_downstream(result)
            self._total_dispatches += 1
            audit.record_data_out({"targets_attempted": ["signal_stream", "radar", "cognition", "bandit"]})

    def _dispatch_to_signal_stream(self, result: "StrategyResult") -> None:
        """发送到信号流（热路径）"""
        try:
            from ..signal.stream import get_signal_stream
            signal_stream = get_signal_stream()
            signal_stream.update(result)
        except Exception as e:
            self._dispatch_errors["signal_stream"] += 1
            logger.warning(f"[SignalDispatcher] SignalStream 分发失败 (累计{self._dispatch_errors['signal_stream']}次): {e}")

    def _dispatch_to_downstream(self, result: "StrategyResult") -> None:
        """发送到下游处理（Radar/Cognition/Bandit）"""
        should_radar = True
        should_memory = True
        should_bandit = False

        try:
            from .output_controller import get_output_controller
            controller = get_output_controller()
            should_radar = controller.should_send_to(result.strategy_id, "radar")
            should_memory = controller.should_send_to(result.strategy_id, "memory")
            should_bandit = controller.should_send_to(result.strategy_id, "bandit")
        except Exception as e:
            self._dispatch_errors["output_controller"] += 1
            logger.warning(f"[SignalDispatcher] OutputController 获取失败 (累计{self._dispatch_errors['output_controller']}次): {e}")

        targets = set()
        if should_radar:
            targets.add("radar")
        if should_memory:
            targets.add("memory")
        if should_bandit:
            targets.add("bandit")

        normalized = {}
        try:
            from .output_schema import normalize_output
            normalized = normalize_output(result, targets)
        except Exception as e:
            self._dispatch_errors["normalize"] += 1
            logger.warning(f"[SignalDispatcher] NormalizeOutput 失败 (累计{self._dispatch_errors['normalize']}次): {e}")

        if should_radar:
            self._send_to_radar(result)

        if should_memory:
            self._send_to_cognition(result)

        if should_bandit:
            self._send_to_bandit(result, normalized)

    def _send_to_radar(self, result: "StrategyResult") -> None:
        """发送到雷达引擎"""
        try:
            from ..radar import get_radar_engine
            radar = get_radar_engine()
            radar.ingest_result(result)
        except Exception as e:
            self._dispatch_errors["radar"] += 1
            logger.warning(f"[SignalDispatcher] Radar 分发失败 (累计{self._dispatch_errors['radar']}次): {e}")

    def _send_to_cognition(self, result: "StrategyResult") -> None:
        """发送到认知系统"""
        try:
            from ..cognition.insight import get_insight_engine
            insight = get_insight_engine()
            signal = {
                "source": "strategy",
                "signal_type": result.strategy_id,
                "score": result.output_full.get("score", 0.5) if result.output_full else 0.5,
                "content": str(result.output_full)[:200] if result.output_full else "",
                "raw_data": {
                    "strategy_id": result.strategy_id,
                    "strategy_name": result.strategy_name,
                    "output": result.output_full,
                },
                "timestamp": result.ts,
                "metadata": {},
            }
            insight.ingest_signal(signal)
        except Exception as e:
            self._dispatch_errors["cognition"] += 1
            logger.warning(f"[SignalDispatcher] Cognition 分发失败 (累计{self._dispatch_errors['cognition']}次): {e}")

    def _send_to_bandit(self, result: "StrategyResult", normalized: dict) -> None:
        """发送到 Bandit 优化器"""
        try:
            from ..bandit import get_bandit_optimizer
            optimizer = get_bandit_optimizer()
            score = normalized.get("bandit", {}).get("score", 0)
            if score != 0:
                optimizer.update_reward(result.strategy_id, score)
        except Exception as e:
            self._dispatch_errors["bandit"] += 1
            logger.warning(f"[SignalDispatcher] Bandit 分发失败 (累计{self._dispatch_errors['bandit']}次): {e}")

    def get_dispatch_stats(self) -> dict:
        """获取分发统计信息"""
        total_errors = sum(self._dispatch_errors.values())
        return {
            "total_dispatches": self._total_dispatches,
            "total_errors": total_errors,
            "error_rate": total_errors / max(self._total_dispatches, 1),
            "errors_by_target": dict(self._dispatch_errors),
        }


_dispatcher: SignalDispatcher | None = None


def get_dispatcher() -> SignalDispatcher:
    """获取分发器单例"""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = SignalDispatcher()
    return _dispatcher


def dispatch_result(result: "StrategyResult") -> None:
    """便捷函数：分发策略结果"""
    get_dispatcher().dispatch(result)
