"""Cognition Engine - 认知引擎

平台级认知输入输出入口。
注意：CognitionEngine 使用组合模式持有 NewsMindStrategy，而非继承，
以保持清晰的职责边界。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from .core import NewsMindStrategy
from ..config import get_memory_config
from deva.naja.register import SR

logger = logging.getLogger(__name__)


class CognitionEngine:
    """认知引擎 - 平台级认知输入输出入口

    使用组合模式：内部持有 NewsMindStrategy 实例，
    只暴露认知系统需要的接口，隔离策略相关的方法。

    组合优于继承：认知引擎是平台级服务，不应该继承策略类。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = get_memory_config()
        merged = dict(cfg or {})
        if config:
            merged.update(config)

        self._news_mind = NewsMindStrategy(merged)

        self._auto_save_enabled = bool(cfg.get("auto_save_enabled", True))
        self._auto_save_interval = float(cfg.get("auto_save_interval", 300))
        self._auto_load_on_start = bool(cfg.get("auto_load_on_start", True))
        self._auto_save_thread = None
        self._stop_auto_save = threading.Event()

        if self._auto_load_on_start:
            self._auto_load_state()

        if self._auto_save_enabled and self._auto_save_interval > 0:
            self._start_auto_save()

    def ingest_result(self, result: Any) -> Optional[list]:
        """摄入策略结果到认知系统。"""
        try:
            ts = getattr(result, "ts", None) or time.time()
            strategy_name = getattr(result, "strategy_name", "") or "unknown"
            output_full = getattr(result, "output_full", None)
            output_preview = getattr(result, "output_preview", None)
            input_preview = getattr(result, "input_preview", None)
            metadata = getattr(result, "metadata", {}) or {}

            payload = output_full or output_preview or input_preview or {}
            if isinstance(payload, dict):
                confidence = payload.get("confidence", payload.get("score"))
                try:
                    confidence_val = float(confidence)
                except Exception:
                    confidence_val = None
                if confidence_val is not None and confidence_val >= 0.8:
                    payload.setdefault("importance", "high")

                signal_type = str(payload.get("signal_type", "")).upper()
                if signal_type in {"BUY", "SELL"}:
                    payload.setdefault("importance", "high")

                if "global_attention" in metadata:
                    payload.setdefault("global_attention", metadata.get("global_attention"))
                if "attention" in metadata:
                    payload.setdefault("attention", metadata.get("attention"))

            record: Dict[str, Any] = {
                "timestamp": ts,
                "source": f"strategy:{strategy_name}",
                "data": payload,
            }
            return self._news_mind.process_record(record)
        except Exception:
            return None

    def process_record(self, record: Dict[str, Any]) -> Optional[list]:
        """委托给内部 NewsMindStrategy 处理记录（兼容接口）"""
        return self._news_mind.process_record(record)

    def summarize_for_llm(self, max_topics: int = 5, max_events: int = 5) -> Dict[str, Any]:
        """返回紧凑的认知摘要，用于 LLM prompts。"""
        report = self._news_mind.get_memory_report()
        top_topics = report.get("top_topics", [])[:max_topics]
        recent_events = report.get("recent_high_attention", [])[:max_events]

        return {
            "timestamp": report.get("timestamp"),
            "stats": report.get("stats", {}),
            "top_topics": top_topics,
            "recent_high_attention": recent_events,
        }

    def get_memory_report(self) -> Dict[str, Any]:
        """获取完整记忆报告。"""
        return self._news_mind.get_memory_report()

    def save_state(self) -> dict:
        """保存认知状态。"""
        return self._news_mind.save_state()

    def load_state(self) -> dict:
        """加载认知状态。"""
        return self._news_mind.load_state()

    def clear_saved_state(self) -> dict:
        """清除保存的认知状态。"""
        return self._news_mind.clear_saved_state()

    def _auto_load_state(self) -> None:
        try:
            result = self.load_state()
            if result.get("success") and result.get("loaded"):
                logger.debug("[CognitionEngine] 已加载认知状态")
            elif result.get("success") and not result.get("loaded"):
                logger.debug("[CognitionEngine] 未发现已保存的认知状态")
        except Exception as e:
            logger.debug(f"[CognitionEngine] 自动加载失败: {e}")

    def _start_auto_save(self) -> None:
        if self._auto_save_thread is not None and self._auto_save_thread.is_alive():
            return
        self._stop_auto_save.clear()
        self._auto_save_thread = threading.Thread(
            target=self._auto_save_loop,
            daemon=True,
            name="cognition_auto_save",
        )
        self._auto_save_thread.start()
        logger.debug(f"[CognitionEngine] 自动保存已启动，间隔 {self._auto_save_interval} 秒")

    def _auto_save_loop(self) -> None:
        while not self._stop_auto_save.is_set():
            self._stop_auto_save.wait(self._auto_save_interval)
            if self._stop_auto_save.is_set():
                break
            try:
                result = self.save_state()
                if not result.get("success"):
                    logger.debug(f"[CognitionEngine] 自动保存失败: {result.get('error')}")
            except Exception as e:
                logger.debug(f"[CognitionEngine] 自动保存异常: {e}")

    def stop_auto_save(self) -> None:
        if self._auto_save_thread is not None:
            self._stop_auto_save.set()
            self._auto_save_thread.join(timeout=5)
            logger.debug("[CognitionEngine] 自动保存已停止")

    def get_liquidity_stats(self) -> Dict[str, Any]:
        """获取流动性预测统计（公共API，供UI层使用）"""
        try:
            from .liquidity import get_liquidity_cognition
            lc = get_liquidity_cognition()
            if not lc:
                return {}
            tracker = lc.get_prediction_tracker()
            if not tracker:
                return {}
            return {
                "total_created": tracker._stats.get("total_created", 0),
                "total_confirmed": tracker._stats.get("total_confirmed", 0),
                "total_denied": tracker._stats.get("total_denied", 0),
                "total_cancelled": tracker._stats.get("total_cancelled", 0),
                "active_count": len(tracker._predictions_by_status.get("pending", [])),
                "total_predictions": len(tracker._predictions),
                "prediction_rate": tracker.get_prediction_rate(),
            }
        except Exception:
            return {}

    def get_liquidity_predictions(self) -> List[Dict[str, Any]]:
        """获取活跃的流动性预测列表（公共API，供UI层使用）"""
        try:
            from .liquidity import get_liquidity_cognition
            lc = get_liquidity_cognition()
            if not lc:
                return []
            predictions = lc.get_active_predictions()
            return [pred.to_dict() for pred in predictions]
        except Exception:
            return []

    def get_attention_hints(self, lookback: int = 200) -> Dict[str, Any]:
        """获取注意力提示（公共API，供UI层使用）"""
        return self._news_mind.get_attention_hints(lookback=lookback)


# 向后兼容别名
def get_memory_engine():
    from deva.naja.register import SR
    return SR('cognition_engine')
