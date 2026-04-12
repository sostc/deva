"""
SignalExecutor - 信号执行模块

职责：
- 信号执行
- 反馈到觉醒系统
- 策略结果通知

从 AttentionOrchestrator 拆分出来
"""

import time
import logging
from typing import Dict, Any, List, Optional

from deva.naja.register import SR

log = logging.getLogger(__name__)


class SignalExecutor:
    """
    信号执行器

    负责：
    - 将信号传递给信号流
    - 反馈到觉醒系统
    - 通知调参器
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            import threading
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance._init_lock = threading.Lock()
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        with self._init_lock:
            if getattr(self, '_initialized', False):
                return
            self._ensure_initialized()

    def _ensure_initialized(self):
        """初始化"""
        self._initialized = True
        log.info("SignalExecutor 初始化完成")

    def execute_signals(self, signals):
        """将信号传递给 Bandit 的 SignalListener 执行"""
        try:
            from deva.naja.signal.stream import get_signal_stream
            from deva.naja.strategy.result_store import StrategyResult
            signal_stream = get_signal_stream()

            if not signals:
                log.debug(f"[SignalExecutor] execute_signals called with empty signals list")
                return

            log.info(f"[SignalExecutor] 🎯 execute_signals 收到 {len(signals)} 个信号")

            for signal in signals:
                log.info(f"[SignalExecutor] 🎯 信号: strategy={signal.strategy_name}, type={signal.signal_type}, symbol={signal.symbol}, confidence={signal.confidence:.3f}")
                if signal.signal_type not in ('buy', 'sell'):
                    continue

                price = 0.0
                if signal.metadata:
                    price = float(signal.metadata.get('price', signal.metadata.get('close', 0)))

                result = StrategyResult(
                    id=f"{signal.strategy_name}_{signal.symbol}_{int(signal.timestamp*1000)}",
                    strategy_id=signal.strategy_name,
                    strategy_name=signal.strategy_name,
                    ts=signal.timestamp,
                    success=True,
                    input_preview=f"{signal.symbol}: {signal.signal_type}",
                    output_preview=f"置信度: {signal.confidence:.2f}, 得分: {signal.score:.3f}",
                    output_full={
                        'signal_type': signal.signal_type.upper(),
                        'stock_code': signal.symbol,
                        'price': price,
                        'confidence': signal.confidence,
                        'score': signal.score,
                        'reason': signal.reason,
                    },
                    process_time_ms=0,
                    error="",
                    metadata={
                        'source': 'attention_center',
                        'attention_strategy': signal.strategy_name,
                        'signal_confidence': signal.confidence,
                        'signal_score': signal.score,
                        'signal_reason': signal.reason,
                    }
                )

                signal_stream.update(result, who='attention_center')

                self._notify_tuner_about_signal(result)

                self._feedback_to_awakened_systems(signal, result)

            log.info(f"[SignalExecutor] 已将 {len(signals)} 个信号添加到信号流")
        except Exception as e:
            log.error(f"[SignalExecutor] 添加信号到信号流失败: {e}")

    def _notify_tuner_about_signal(self, result):
        """通知 BanditTuner 有新信号（调参模式用）"""
        try:
            from deva.naja.bandit.tuner import get_bandit_tuner
            tuner = get_bandit_tuner()
            tuner.on_signal(result)
        except Exception:
            pass

    def _feedback_to_awakened_systems(self, signal, result):
        """
        觉醒 → 认知：反馈交易结果到觉醒系统和认知系统
        """
        try:
            symbol = signal.symbol
            strategy_name = signal.strategy_name
            signal_type = signal.signal_type
            confidence = signal.confidence
            metadata = signal.metadata or {}

            cognition_context = self._get_cognition_context()
            narratives = cognition_context.get("narratives", [])
            latest_reflection = cognition_context.get("latest_reflection", {})
            has_high_conf_insight = latest_reflection.get("confidence", 0) > 0.7

            outcome = {
                "symbol": symbol,
                "strategy": strategy_name,
                "signal_type": signal_type,
                "confidence": confidence,
                "success": result.success if hasattr(result, 'success') else True,
                "narratives": narratives,
                "has_cognition_insight": has_high_conf_insight,
                "position_multiplier": metadata.get("position_multiplier", 1.0),
                "blocked": metadata.get("blocked", False),
                "sentiment": metadata.get("sentiment", "neutral"),
                "timestamp": time.time()
            }

            self._feedback_to_alaya(symbol, signal_type, outcome)

            self._feedback_to_insight_pool(symbol, signal_type, outcome)

            self._feedback_to_meta_evolution(strategy_name, outcome)

        except Exception as e:
            log.error(f"[SignalExecutor] 反馈到觉醒系统失败: {e}")

    def _get_cognition_context(self) -> Dict[str, Any]:
        """获取认知上下文"""
        try:
            from deva.naja.cognition.narrative import NarrativeTracker
            tracker = NarrativeTracker()
            narrative_summary = tracker.get_summary(limit=10)
            return {"narratives": [s.get("narrative", "") for s in narrative_summary]}
        except Exception:
            return {"narratives": []}

    def _feedback_to_alaya(self, symbol: str, signal_type: str, outcome: Dict[str, Any]):
        """反馈到 Alaya"""
        try:
            from deva.naja.alaya.awakened_alaya import AwakenedAlaya
            alaya = AwakenedAlaya()
            if alaya:
                alaya.on_trade_feedback(symbol, signal_type, outcome)
        except Exception as e:
            log.debug(f"[SignalExecutor] 反馈到Alaya失败: {e}")

    def _feedback_to_insight_pool(self, symbol: str, signal_type: str, outcome: Dict[str, Any]):
        """反馈到 InsightPool"""
        try:
            pool = SR('insight_pool')
            if pool:
                pool.record_trade_outcome(symbol, signal_type, outcome)
        except Exception as e:
            log.debug(f"[SignalExecutor] 反馈到InsightPool失败: {e}")

    def _feedback_to_meta_evolution(self, strategy_name: str, outcome: Dict[str, Any]):
        """反馈到 MetaEvolution"""
        try:
            from deva.naja.evolution import get_meta_evolution
            meta = get_meta_evolution()
            if meta:
                meta.on_signal_outcome(strategy_name, outcome)
        except Exception:
            pass

    def _get_recent_trade_feedback(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近交易反馈"""
        try:
            from deva.naja.signal.stream import get_signal_stream
            stream = get_signal_stream()
            if stream:
                return stream.get_recent_results(limit)
        except Exception:
            pass
        return []


_signal_executor: Optional['SignalExecutor'] = None


def get_signal_executor() -> SignalExecutor:
    """获取 SignalExecutor 单例"""
    global _signal_executor
    if _signal_executor is None:
        _signal_executor = SignalExecutor()
    return _signal_executor