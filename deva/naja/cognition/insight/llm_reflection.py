"""LLM Reflection Engine - Generates deep insights from signals using LLM."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from deva import NB

from ...config import get_llm_config


LLM_REFLECTION_TABLE = "naja_llm_reflections"


@dataclass
class Reflection:
    id: str
    ts: float
    theme: str
    summary: str
    signals_count: int
    narratives: List[str] = field(default_factory=list)
    symbols: List[str] = field(default_factory=list)
    sectors: List[str] = field(default_factory=list)
    confidence: float = 0.5
    actionability: float = 0.5
    novelty: float = 0.5
    source: str = "llm_reflection"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "theme": self.theme,
            "summary": self.summary,
            "signals_count": self.signals_count,
            "narratives": self.narratives,
            "symbols": self.symbols,
            "sectors": self.sectors,
            "confidence": self.confidence,
            "actionability": self.actionability,
            "novelty": self.novelty,
            "source": self.source,
        }


class LLMReflectionEngine:
    """LLM 反思引擎 - 定期调用 LLM 生成深度洞察"""

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

        self._db = NB(LLM_REFLECTION_TABLE)
        cfg = get_llm_config()

        self._enabled = bool(cfg.get("reflection_enabled", True))
        self._interval_seconds = float(cfg.get("reflection_interval_seconds", 3600))
        self._min_signals = int(cfg.get("reflection_min_signals", 5))
        self._max_signals = int(cfg.get("reflection_max_signals", 50))

        self._last_run_ts = time.time()
        self._last_success_ts = 0.0
        self._reflections_count = 0
        self._running_reflections: List[Reflection] = []

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        if self._enabled:
            self._start_timer_thread()

        self._initialized = True

    def _start_timer_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._timer_loop,
            daemon=True,
            name="llm_reflection_timer",
        )
        self._thread.start()

    def _timer_loop(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            if now - self._last_run_ts >= self._interval_seconds:
                self._run_reflection()

            self._stop_event.wait(min(30, self._interval_seconds))

    def _run_reflection(self) -> Optional[Reflection]:
        from ..narrative_tracker import DEFAULT_NARRATIVE_KEYWORDS

        now = time.time()
        self._last_run_ts = now

        signals = self._collect_signals()
        if len(signals) < self._min_signals:
            return None

        narratives = self._collect_narratives()
        themes = self._extract_themes(signals)
        symbols = self._extract_symbols(signals)
        sectors = self._extract_sectors(signals)

        try:
            result = self._call_llm(signals, narratives, themes)
        except Exception as e:
            print(f"[LLMReflection] LLM 调用失败: {e}")
            return None

        if not result:
            return None

        reflection = Reflection(
            id=f"refl_{int(now * 1000)}",
            ts=now,
            theme=result.get("theme", "市场反思"),
            summary=result.get("summary", ""),
            signals_count=len(signals),
            narratives=narratives[:5],
            symbols=symbols[:10],
            sectors=sectors[:5],
            confidence=float(result.get("confidence", 0.5)),
            actionability=float(result.get("actionability", 0.5)),
            novelty=float(result.get("novelty", 0.5)),
            source="llm_reflection",
        )

        self._save_reflection(reflection)
        self._last_success_ts = now
        self._reflections_count += 1

        self._push_to_insight_pool(reflection)

        return reflection

    def _collect_signals(self) -> List[Dict[str, Any]]:
        from ..insight.engine import get_insight_pool

        pool = get_insight_pool()
        recent = pool.get_recent_insights(limit=self._max_signals)
        return recent

    def _collect_narratives(self) -> List[str]:
        from ..core import get_cognition_engine

        try:
            engine = get_cognition_engine()
            report = engine.get_memory_report()
            narratives = report.get("narratives", {})
            summary = narratives.get("summary", [])
            return [n.get("narrative", "") for n in summary if n.get("narrative")]
        except Exception:
            return []

    def _extract_themes(self, signals: List[Dict[str, Any]]) -> List[str]:
        themes = []
        for sig in signals:
            theme = sig.get("theme", "")
            if theme and theme not in themes:
                themes.append(theme)
        return themes[:10]

    def _extract_symbols(self, signals: List[Dict[str, Any]]) -> List[str]:
        symbols = set()
        for sig in signals:
            for s in sig.get("symbols", []):
                symbols.add(str(s))
        return list(symbols)[:20]

    def _extract_sectors(self, signals: List[Dict[str, Any]]) -> List[str]:
        sectors = set()
        for sig in signals:
            for s in sig.get("sectors", []):
                sectors.add(str(s))
        return list(sectors)[:10]

    async def _call_llm_async(
        self,
        signals: List[Dict[str, Any]],
        narratives: List[str],
        themes: List[str],
    ) -> Optional[Dict[str, Any]]:
        cfg = get_llm_config()

        prompt = self._build_reflection_prompt(signals, narratives, themes)

        try:
            from deva.llm import GPT
            model_type = cfg.get("model_type", "deepseek")
            gpt = GPT(model_type=model_type)
            response = await gpt.async_query(prompt)
        except Exception as e:
            raise RuntimeError(f"LLM 调用失败: {e}") from e

        return self._parse_llm_response(response)

    def _call_llm(self, signals, narratives, themes) -> Optional[Dict[str, Any]]:
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._call_llm_async(signals, narratives, themes))
            loop.close()
            return result
        except Exception as e:
            print(f"[LLMReflection] Sync call failed: {e}")
            return None

    def _build_reflection_prompt(
        self,
        signals: List[Dict[str, Any]],
        narratives: List[str],
        themes: List[str],
    ) -> str:
        signals_json = json.dumps(signals[: self._max_signals], ensure_ascii=False, indent=2)
        narratives_json = json.dumps(narratives, ensure_ascii=False)
        themes_json = json.dumps(themes, ensure_ascii=False)

        return f"""你是金融市场分析师。请基于以下信号生成深度市场反思。

## 当前叙事主题
{narratives_json}

## 检测到的主题
{themes_json}

## 近期信号（按时间倒序）
{signals_json}

请生成一段市场反思，要求：
1. 识别当前市场的主要矛盾和核心驱动因素
2. 判断叙事主题之间的关联和演变趋势
3. 给出简短的形势判断（2-3句话）

仅返回 JSON 格式：
{{
    "theme": "反思主题（一句话）",
    "summary": "深度反思内容（100-200字）",
    "confidence": 0.0-1.0（判断置信度），
    "actionability": 0.0-1.0（可执行性评分），
    "novelty": 0.0-1.0（新颖程度）
}}

只返回 JSON，不要其他内容。"""

    def _parse_llm_response(self, response: str) -> Optional[Dict[str, Any]]:
        if not response:
            return None

        try:
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                for i, line in enumerate(lines):
                    if line.strip().startswith("```"):
                        lines[i] = ""
                    elif i > 0 and lines[i - 1].strip().startswith("```"):
                        lines[i] = ""
                response = "\n".join(lines).strip()

            for marker in ["```json", "```JSON", "```"]:
                if marker in response:
                    parts = response.split(marker)
                    for part in parts:
                        part = part.strip()
                        if part.startswith("{") or part.startswith("["):
                            response = part
                            break

            data = json.loads(response)
            if not isinstance(data, dict):
                return None

            return {
                "theme": str(data.get("theme", "市场反思")),
                "summary": str(data.get("summary", "")),
                "confidence": float(data.get("confidence", 0.5)),
                "actionability": float(data.get("actionability", 0.5)),
                "novelty": float(data.get("novelty", 0.5)),
            }
        except json.JSONDecodeError as e:
            print(f"[LLMReflection] JSON 解析失败: {e}, response: {response[:200]}")
            return None

    def _save_reflection(self, reflection: Reflection) -> None:
        try:
            self._db[reflection.id] = reflection.to_dict()
        except Exception:
            pass

    def _push_to_insight_pool(self, reflection: Reflection) -> None:
        from ..insight.engine import get_insight_pool

        try:
            pool = get_insight_pool()
            insight_data = {
                "theme": reflection.theme,
                "summary": reflection.summary,
                "symbols": reflection.symbols,
                "sectors": reflection.sectors,
                "confidence": reflection.confidence,
                "actionability": reflection.actionability,
                "system_attention": reflection.novelty,
                "source": f"llm_reflection:{reflection.id}",
                "signal_type": "llm_reflection",
                "payload": reflection.to_dict(),
            }
            pool.ingest_attention_event(insight_data)
        except Exception as e:
            print(f"[LLMReflection] 推送到洞察池失败: {e}")

    def trigger_now(self) -> Optional[Reflection]:
        """手动触发一次反思"""
        return self._run_reflection()

    def get_stats(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "interval_seconds": self._interval_seconds,
            "last_run_ts": self._last_run_ts,
            "last_success_ts": self._last_success_ts,
            "reflections_count": self._reflections_count,
            "pending_signals": len(self._collect_signals()),
        }

    def get_recent_reflections(self, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            items = list(self._db.items())
            items.sort(key=lambda x: float(x[1].get("ts", 0)) if isinstance(x[1], dict) else 0, reverse=True)
            return [item[1] for item in items[:limit] if isinstance(item[1], dict)]
        except Exception:
            return []

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)


_llm_reflection_engine: Optional[LLMReflectionEngine] = None
_llm_reflection_lock = threading.Lock()


def get_llm_reflection_engine() -> LLMReflectionEngine:
    global _llm_reflection_engine
    if _llm_reflection_engine is None:
        with _llm_reflection_lock:
            if _llm_reflection_engine is None:
                _llm_reflection_engine = LLMReflectionEngine()
    return _llm_reflection_engine
