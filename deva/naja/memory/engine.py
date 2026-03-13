"""Memory engine built on the Lobster radar strategy."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

from .core import LobsterRadarStrategy
from ..config import get_memory_config


class MemoryEngine(LobsterRadarStrategy):
    """Memory engine entrypoint for platform-wide reads/writes."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config or {})
        cfg = get_memory_config()
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
        """
        Ingest a StrategyResult (or similar) into memory.

        This adapts strategy outputs into the Lobster record format.
        """
        try:
            ts = getattr(result, "ts", None) or time.time()
            strategy_name = getattr(result, "strategy_name", "") or "unknown"
            output_full = getattr(result, "output_full", None)
            output_preview = getattr(result, "output_preview", None)
            input_preview = getattr(result, "input_preview", None)

            payload = output_full or output_preview or input_preview or {}
            record: Dict[str, Any] = {
                "timestamp": ts,
                "source": f"strategy:{strategy_name}",
                "data": payload,
            }
            return self.process_record(record)
        except Exception:
            return None

    def summarize_for_llm(self, max_topics: int = 5, max_events: int = 5) -> Dict[str, Any]:
        """Return a compact memory summary for LLM prompts."""
        report = self.get_memory_report()
        top_topics = report.get("top_topics", [])[:max_topics]
        recent_events = report.get("recent_high_attention", [])[:max_events]

        return {
            "timestamp": report.get("timestamp"),
            "stats": report.get("stats", {}),
            "top_topics": top_topics,
            "recent_high_attention": recent_events,
        }

    def _auto_load_state(self) -> None:
        try:
            result = self.load_state()
            if result.get("success") and result.get("loaded"):
                print("[MemoryEngine] 已加载记忆状态")
            elif result.get("success") and not result.get("loaded"):
                print("[MemoryEngine] 未发现已保存的记忆状态")
        except Exception as e:
            print(f"[MemoryEngine] 自动加载失败: {e}")

    def _start_auto_save(self) -> None:
        if self._auto_save_thread is not None and self._auto_save_thread.is_alive():
            return
        self._stop_auto_save.clear()
        self._auto_save_thread = threading.Thread(
            target=self._auto_save_loop,
            daemon=True,
            name="memory_auto_save",
        )
        self._auto_save_thread.start()
        print(f"[MemoryEngine] 自动保存已启动，间隔 {self._auto_save_interval} 秒")

    def _auto_save_loop(self) -> None:
        while not self._stop_auto_save.is_set():
            self._stop_auto_save.wait(self._auto_save_interval)
            if self._stop_auto_save.is_set():
                break
            try:
                result = self.save_state()
                if not result.get("success"):
                    print(f"[MemoryEngine] 自动保存失败: {result.get('error')}")
            except Exception as e:
                print(f"[MemoryEngine] 自动保存异常: {e}")

    def stop_auto_save(self) -> None:
        if self._auto_save_thread is not None:
            self._stop_auto_save.set()
            self._auto_save_thread.join(timeout=5)
            print("[MemoryEngine] 自动保存已停止")


_memory_engine: Optional[MemoryEngine] = None
_memory_engine_lock = threading.Lock()


def get_memory_engine() -> MemoryEngine:
    global _memory_engine
    if _memory_engine is None:
        with _memory_engine_lock:
            if _memory_engine is None:
                _memory_engine = MemoryEngine()
    return _memory_engine
