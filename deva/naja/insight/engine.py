"""Insight Engine - 思考层：存储 + LLM反思"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from ..config import get_insight_config


class InsightEngine:
    """
    洞察引擎 - 思考层

    职责：
    1. 接收 Radar 所有输出（叙事信号 + 行情信号）
    2. 统一存储到三层记忆
    3. LLM 慢思考（周期性反思总结）
    4. 输出注意力建议

    这是大脑，不是感知器
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        cfg = get_insight_config()
        self.config = cfg

        self._auto_save_enabled = bool(cfg.get("auto_save_enabled", True))
        self._auto_save_interval = float(cfg.get("auto_save_interval", 300))
        self._auto_load_on_start = bool(cfg.get("auto_load_on_start", True))
        self._auto_save_thread = None
        self._stop_auto_save = threading.Event()

        self._short_memory: List[Dict] = []
        self._mid_memory: List[Dict] = []
        self._long_memory: List[Dict] = []
        self._signal_buffer: List[Dict] = []

        self._llm_reflect_interval = float(cfg.get("llm_reflect_interval", 3600))
        self._last_llm_reflect_time = 0.0
        self._llm_reflect_window = float(cfg.get("llm_reflect_window", 7200))

        self._last_save_time = 0.0

        if self._auto_load_on_start:
            self._auto_load_state()

        if self._auto_save_enabled and self._auto_save_interval > 0:
            self._start_auto_save()

        self._initialized = True

    def ingest_signal(self, signal: Dict[str, Any]) -> None:
        """
        接收 Radar 发来的信号

        Args:
            signal: {
                "source": "narrative" | "market",
                "signal_type": "narrative_spread" | "sector_anomaly" | ...,
                "score": 0.8,
                "content": "描述内容",
                "raw_data": {...},
                "timestamp": ...,
                "metadata": {...}
            }
        """
        normalized = self._normalize_signal(signal)
        self._signal_buffer.append(normalized)
        self._short_memory.append(normalized)

        if len(self._short_memory) > 1000:
            self._short_memory = self._short_memory[-1000:]

        if normalized.get("score", 0) >= 0.6:
            self._mid_memory.append(normalized)

        if len(self._mid_memory) > 5000:
            self._mid_memory = self._mid_memory[-5000:]

    def _normalize_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """标准化信号格式"""
        return {
            "id": signal.get("id", f"sig_{int(time.time() * 1000)}"),
            "source": signal.get("source", "unknown"),
            "signal_type": signal.get("signal_type", "unknown"),
            "score": float(signal.get("score", 0.5)),
            "content": str(signal.get("content", "")),
            "raw_data": signal.get("raw_data", {}),
            "timestamp": signal.get("timestamp", time.time()),
            "metadata": signal.get("metadata", {}),
        }

    def ingest_batch(self, signals: List[Dict[str, Any]]) -> None:
        """批量接收信号"""
        for sig in signals:
            self.ingest_signal(sig)

    def should_llm_reflect(self) -> bool:
        """判断是否应该触发 LLM 反思"""
        now = time.time()
        if now - self._last_llm_reflect_time >= self._llm_reflect_interval:
            return True
        return False

    def trigger_llm_reflect(self) -> Dict[str, Any]:
        """
        触发 LLM 反思

        Returns:
            LLM 生成的洞察报告
        """
        self._last_llm_reflect_time = time.time()

        window_start = time.time() - self._llm_reflect_window
        window_signals = [s for s in self._signal_buffer if s.get("timestamp", 0) >= window_start]

        narrative_signals = [s for s in window_signals if s.get("source") == "narrative"]
        market_signals = [s for s in window_signals if s.get("source") == "market"]

        high_score_signals = sorted(
            window_signals,
            key=lambda x: x.get("score", 0),
            reverse=True
        )[:10]

        summary = self._generate_summary_text(window_signals, narrative_signals, market_signals)

        reflection = {
            "timestamp": time.time(),
            "window_seconds": self._llm_reflect_window,
            "total_signals": len(window_signals),
            "narrative_count": len(narrative_signals),
            "market_count": len(market_signals),
            "top_signals": high_score_signals,
            "summary": summary,
            "narratives": self._summarize_narratives(narrative_signals),
            "market_events": self._summarize_market(market_signals),
        }

        self._long_memory.append(reflection)
        if len(self._long_memory) > 30:
            self._long_memory = self._long_memory[-30:]

        return reflection

    def _generate_summary_text(
        self,
        window_signals: List[Dict],
        narrative_signals: List[Dict],
        market_signals: List[Dict]
    ) -> str:
        """生成总结文本（未来可接入 LLM）"""
        if not window_signals:
            return "近期无显著信号"

        high_score = [s for s in window_signals if s.get("score", 0) >= 0.7]
        narrative_types = set(s.get("signal_type") for s in narrative_signals)
        market_types = set(s.get("signal_type") for s in market_signals)

        lines = [
            f"近期共捕获 {len(window_signals)} 个信号",
            f"其中高价值信号 {len(high_score)} 个",
        ]

        if narrative_signals:
            lines.append(f"叙事类信号 {len(narrative_signals)} 个，类型：{', '.join(narrative_types)}")
        if market_signals:
            lines.append(f"行情类信号 {len(market_signals)} 个，类型：{', '.join(market_types)}")

        return "; ".join(lines)

    def _summarize_narratives(self, signals: List[Dict]) -> List[Dict]:
        """汇总叙事信号"""
        if not signals:
            return []

        by_type: Dict[str, List[Dict]] = {}
        for s in signals:
            stype = s.get("signal_type", "unknown")
            if stype not in by_type:
                by_type[stype] = []
            by_type[stype].append(s)

        summary = []
        for stype, sigs in by_type.items():
            avg_score = sum(s.get("score", 0) for s in sigs) / len(sigs)
            summary.append({
                "type": stype,
                "count": len(sigs),
                "avg_score": round(avg_score, 3),
                "samples": [s.get("content", "")[:50] for s in sigs[:3]]
            })

        return sorted(summary, key=lambda x: x["avg_score"], reverse=True)

    def _summarize_market(self, signals: List[Dict]) -> List[Dict]:
        """汇总行情信号"""
        if not signals:
            return []

        by_type: Dict[str, List[Dict]] = {}
        for s in signals:
            stype = s.get("signal_type", "unknown")
            if stype not in by_type:
                by_type[stype] = []
            by_type[stype].append(s)

        summary = []
        for stype, sigs in by_type.items():
            avg_score = sum(s.get("score", 0) for s in sigs) / len(sigs)
            summary.append({
                "type": stype,
                "count": len(sigs),
                "avg_score": round(avg_score, 3),
                "samples": [s.get("content", "")[:50] for s in sigs[:3]]
            })

        return sorted(summary, key=lambda x: x["avg_score"], reverse=True)

    def get_attention_hints(self, lookback: int = 200) -> Dict[str, Any]:
        """
        获取注意力建议（供调度系统使用）

        Returns:
            {
                "symbols": {"SYMBOL": weight, ...},
                "sectors": {"SECTOR": weight, ...},
                "narratives": ["AI", "芯片", ...],
                "insight_level": 0.8,
            }
        """
        recent_signals = list(self._signal_buffer)[-max(1, lookback):]

        symbol_scores: Dict[str, List[float]] = {}
        sector_scores: Dict[str, List[float]] = {}
        narrative_scores: Dict[str, List[float]] = {}

        for sig in recent_signals:
            score = sig.get("score", 0.5)
            raw_data = sig.get("raw_data", {})
            metadata = sig.get("metadata", {})

            for key in ("symbol", "code", "ticker", "stock"):
                val = raw_data.get(key) or metadata.get(key)
                if val:
                    sym = str(val)
                    if sym not in symbol_scores:
                        symbol_scores[sym] = []
                    symbol_scores[sym].append(score)

            for key in ("sector", "industry", "sector_id"):
                val = raw_data.get(key) or metadata.get(key)
                if val:
                    sec = str(val)
                    if sec not in sector_scores:
                        sector_scores[sec] = []
                    sector_scores[sec].append(score)

            if sig.get("source") == "narrative":
                content = sig.get("content", "")
                narrative_scores[content[:30]] = narrative_scores.get(content[:30], [])
                narrative_scores[content[:30]].append(score)

        def compute_weight(scores: List[float]) -> float:
            if not scores:
                return 0.0
            avg_attention = sum(scores) / len(scores)
            frequency_factor = min(1.0, len(scores) / 10.0)
            return avg_attention * 0.7 + frequency_factor * 0.3

        return {
            "symbols": {sym: compute_weight(scores) for sym, scores in symbol_scores.items()},
            "sectors": {sec: compute_weight(scores) for sec, scores in sector_scores.items()},
            "narratives": [
                nar for nar, scores in narrative_scores.items()
                if compute_weight(scores) > 0.5
            ],
            "insight_level": compute_weight([s.get("score", 0.5) for s in recent_signals]),
        }

    def get_summary(self) -> Dict[str, Any]:
        """获取当前洞察摘要"""
        return {
            "timestamp": time.time(),
            "short_memory_size": len(self._short_memory),
            "mid_memory_size": len(self._mid_memory),
            "long_memory_size": len(self._long_memory),
            "signal_buffer_size": len(self._signal_buffer),
            "recent_signals": list(self._signal_buffer)[-10:],
        }

    def summarize_for_llm(self, max_signals: int = 10) -> Dict[str, Any]:
        """Return a compact insight summary for LLM prompts."""
        recent = list(self._signal_buffer)[-max_signals * 2:] if self._signal_buffer else []
        high_score = sorted(recent, key=lambda x: x.get("score", 0), reverse=True)[:max_signals]

        narratives = [s.get("content", "")[:50] for s in recent if s.get("source") == "narrative"]
        market_events = [s.get("content", "")[:50] for s in recent if s.get("source") == "market"]

        return {
            "timestamp": time.time(),
            "stats": {
                "total_signals": len(self._signal_buffer),
                "short_memory_size": len(self._short_memory),
                "long_memory_reflections": len(self._long_memory),
            },
            "high_score_signals": [
                {
                    "source": s.get("source"),
                    "signal_type": s.get("signal_type"),
                    "score": s.get("score"),
                    "content": s.get("content", "")[:100],
                }
                for s in high_score
            ],
            "narratives": narratives[:5],
            "market_events": market_events[:5],
        }

    def get_insight_report(self) -> Dict[str, Any]:
        """获取完整洞察报告"""
        recent_signals = list(self._signal_buffer)[-200:]

        return {
            "timestamp": time.time(),
            "short_memory": {
                "size": len(self._short_memory),
                "recent": list(self._short_memory)[-10:],
            },
            "mid_memory": {
                "size": len(self._mid_memory),
                "high_score": sorted(
                    self._mid_memory,
                    key=lambda x: x.get("score", 0),
                    reverse=True
                )[:20],
            },
            "long_memory": {
                "size": len(self._long_memory),
                "reflections": list(self._long_memory)[-5:],
            },
            "attention_hints": self.get_attention_hints(),
        }

    def _start_auto_save(self) -> None:
        """启动自动保存"""
        if self._auto_save_thread is not None and self._auto_save_thread.is_alive():
            return
        self._stop_auto_save.clear()
        self._auto_save_thread = threading.Thread(
            target=self._auto_save_loop,
            daemon=True,
            name="insight_auto_save",
        )
        self._auto_save_thread.start()
        print(f"[InsightEngine] 自动保存已启动，间隔 {self._auto_save_interval} 秒")

    def _auto_save_loop(self) -> None:
        """自动保存循环"""
        while not self._stop_auto_save.is_set():
            self._stop_auto_save.wait(self._auto_save_interval)
            if self._stop_auto_save.is_set():
                break
            try:
                self._save_state()
            except Exception as e:
                print(f"[InsightEngine] 自动保存异常: {e}")

    def _save_state(self) -> dict:
        """保存状态"""
        try:
            from deva import NB
            db = NB("naja_insight_state")
            state = {
                "timestamp": time.time(),
                "short_memory": self._short_memory[-500:],
                "mid_memory": self._mid_memory[-1000:],
                "long_memory": self._long_memory[-30:],
                "signal_buffer": self._signal_buffer[-1000:],
            }
            db["insight_main"] = state
            self._last_save_time = time.time()
            print(f"[InsightEngine] 状态已保存")
            return {"success": True}
        except Exception as e:
            print(f"[InsightEngine] 保存失败: {e}")
            return {"success": False, "error": str(e)}

    def _auto_load_state(self) -> None:
        """自动加载状态"""
        try:
            from deva import NB
            db = NB("naja_insight_state")
            if "insight_main" in db:
                state = db["insight_main"]
                self._short_memory = state.get("short_memory", [])
                self._mid_memory = state.get("mid_memory", [])
                self._long_memory = state.get("long_memory", [])
                self._signal_buffer = state.get("signal_buffer", [])
                print(f"[InsightEngine] 已加载记忆状态")
            else:
                print(f"[InsightEngine] 未发现已保存的记忆状态")
        except Exception as e:
            print(f"[InsightEngine] 自动加载失败: {e}")

    def stop_auto_save(self) -> None:
        """停止自动保存"""
        if self._auto_save_thread is not None:
            self._stop_auto_save.set()
            self._auto_save_thread.join(timeout=5)
            print("[InsightEngine] 自动保存已停止")


_insight_engine: Optional[InsightEngine] = None
_insight_engine_lock = threading.Lock()


def get_insight_engine() -> InsightEngine:
    """获取 InsightEngine 单例"""
    global _insight_engine
    if _insight_engine is None:
        with _insight_engine_lock:
            if _insight_engine is None:
                _insight_engine = InsightEngine()
    return _insight_engine
