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

    def _run_reflection(self, min_signals: int = None) -> Optional[Reflection]:
        from ..narrative_tracker import DEFAULT_NARRATIVE_KEYWORDS
        import logging
        log = logging.getLogger(__name__)

        now = time.time()
        self._last_run_ts = now

        signals = self._collect_signals()
        required = min_signals if min_signals is not None else self._min_signals
        if len(signals) < required:
            log.warning(f"[LLMReflection] 信号不足: 当前{len(signals)}条, 需要{required}条")
            return None

        narratives = self._collect_narratives()
        themes = self._extract_themes(signals)
        symbols = self._extract_symbols(signals)
        sectors = self._extract_sectors(signals)

        log.info(f"[LLMReflection] 开始反思: {len(signals)}个信号, {len(narratives)}个叙事, {len(themes)}个主题")
        try:
            result = self._call_llm(signals, narratives, themes)
        except Exception as e:
            log.error(f"[LLMReflection] LLM 调用失败: {e}", exc_info=True)
            return None

        if not result:
            log.warning("[LLMReflection] LLM 返回空结果")
            return None

        log.info(f"[LLMReflection] 反思生成成功: {result.get('theme', 'N/A')}")

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

        self._emit_to_insight(reflection)

        return reflection

    def _collect_signals(self) -> List[Dict[str, Any]]:
        from ..insight.engine import get_insight_pool

        pool = get_insight_pool()
        recent = pool.get_recent_insights(limit=self._max_signals)
        return recent

    def _collect_narratives(self) -> List[Dict[str, Any]]:
        """收集叙事数据，包含趋势和阶段信息"""
        from ..engine import get_cognition_engine

        try:
            engine = get_cognition_engine()
            report = engine.get_memory_report()
            narratives = report.get("narratives", {})
            summary = narratives.get("summary", [])
            result = []
            for n in summary:
                narrative = n.get("narrative", "")
                if narrative:
                    result.append({
                        "narrative": narrative,
                        "stage": n.get("stage", "萌芽"),
                        "trend": n.get("trend", 0),
                        "attention_score": n.get("attention_score", 0),
                        "recent_count": n.get("recent_count", 0),
                    })
            return result
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

    def _categorize_signals(self, signals: List[Dict[str, Any]]) -> Dict[str, List[Dict]]:
        """按来源分类信号"""
        categories = {
            "radar": [],      # 雷达事件 (pattern, drift, anomaly, sector_anomaly, news_topic)
            "attention": [],  # 注意力事件 (global_attention_shift, market_state_shift, sector_hotspot等)
            "cross_signal": [],  # 共振信号
            "feedback": [],   # 实验反馈 (experiment_feedback_summary, bandit_learning_analysis)
            "effectiveness": [],  # 有效性分析 (effective_pattern, ineffective_pattern)
            "llm_reflection": [],  # 之前的反思
            "other": []       # 其他
        }

        radar_types = {'pattern', 'drift', 'anomaly', 'sector_anomaly', 'news_topic'}
        attention_types = {'global_attention_shift', 'market_activity_shift', 'sector_concentration_shift',
                          'sector_hotspot', 'symbol_attention_change', 'market_state_shift'}
        feedback_types = {'experiment_feedback_summary', 'bandit_learning_analysis'}
        effectiveness_types = {'effective_pattern', 'ineffective_pattern'}

        for sig in signals:
            source = sig.get('source', '')
            signal_type = sig.get('signal_type', '')

            if source in ('market', 'radar', 'radar_news') or signal_type in radar_types:
                categories['radar'].append(sig)
            elif source == 'cross_signal' or 'resonance' in signal_type:
                categories['cross_signal'].append(sig)
            elif source == 'attention' or signal_type in attention_types:
                categories['attention'].append(sig)
            elif source == 'feedback_experiment' or signal_type in feedback_types:
                categories['feedback'].append(sig)
            elif source == 'attention_effectiveness' or signal_type in effectiveness_types:
                categories['effectiveness'].append(sig)
            elif source.startswith('llm_reflection') or signal_type == 'llm_reflection':
                categories['llm_reflection'].append(sig)
            else:
                categories['other'].append(sig)

        for cat in categories:
            categories[cat].sort(key=lambda x: x.get('ts', x.get('timestamp', 0)), reverse=True)

        return categories

    @staticmethod
    def _format_ts(ts: float) -> str:
        """格式化时间戳为可读时间"""
        from datetime import datetime
        if not ts:
            return ""
        dt = datetime.fromtimestamp(ts)
        now = datetime.now()
        diff = (now - dt).total_seconds()
        if diff < 60:
            return "刚刚"
        elif diff < 3600:
            return f"{int(diff // 60)}分钟前"
        elif diff < 86400:
            return f"{int(diff // 3600)}小时前"
        else:
            return dt.strftime("%m-%d %H:%M")

    def _format_signal_for_prompt(self, sig: Dict[str, Any], max_len: int = 80) -> str:
        """格式化单个信号为可读文本"""
        ts = sig.get('ts', sig.get('timestamp', 0))
        time_str = self._format_ts(ts)

        theme = sig.get('theme', '-')[:35]
        summary = sig.get('summary', '')
        if isinstance(summary, dict):
            summary = str(summary)[:max_len]
        elif isinstance(summary, str) and summary.startswith('{'):
            try:
                import ast
                parsed = ast.literal_eval(summary)
                if isinstance(parsed, dict):
                    parts = [f"{k}={v}" for k, v in list(parsed.items())[:3] if isinstance(v, (int, float, str)) and len(str(v)) < 30]
                    summary = ' | '.join(parts) if parts else str(parsed)[:max_len]
                else:
                    summary = str(summary)[:max_len]
            except Exception:
                summary = summary[:max_len]
        else:
            summary = str(summary)[:max_len] if summary else ''

        source = sig.get('source', '')
        signal_type = sig.get('signal_type', '')
        score = sig.get('system_attention', sig.get('score', 0))

        time_prefix = f"[{time_str}]" if time_str else ""
        return f"{time_prefix}[{source}/{signal_type}]({score:.2f}) {theme}: {summary}"

    async def _call_llm_async(
        self,
        signals: List[Dict[str, Any]],
        narratives: List[Dict[str, Any]],
        themes: List[str],
    ) -> Optional[Dict[str, Any]]:
        cfg = get_llm_config()

        prompt = self._build_reflection_prompt(signals, narratives, themes)
        import logging
        log = logging.getLogger(__name__)
        log.info(f"[LLMReflection] Prompt长度: {len(prompt)} 字符")

        try:
            from deva.llm import GPT
            model_type = cfg.get("model_type", "deepseek")
            gpt = GPT(model_type=model_type)
            log.info(f"[LLMReflection] 使用模型: {model_type}, API配置: base_url={gpt.base_url}, model={gpt.model}")
            response = await gpt.async_query(prompt)
        except Exception as e:
            log.error(f"[LLMReflection] LLM调用异常: {e}")
            raise RuntimeError(f"LLM 调用失败: {e}") from e

        return self._parse_llm_response(response)

    def _call_llm(self, signals, narratives, themes) -> Optional[Dict[str, Any]]:
        import logging
        log = logging.getLogger(__name__)
        try:
            import asyncio
            import concurrent.futures

            async def call_async():
                return await self._call_llm_async(signals, narratives, themes)

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                def run_in_new_loop():
                    try:
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            return new_loop.run_until_complete(call_async())
                        finally:
                            new_loop.close()
                    except Exception as e:
                        log.error(f"[LLMReflection] ThreadPool中的LLM调用失败: {e}")
                        return None

                future = executor.submit(run_in_new_loop)
                result = future.result(timeout=120)
                if result is None:
                    return None
                return result
        except Exception as e:
            log.error(f"[LLMReflection] Sync call failed: {e}", exc_info=True)
            return None

    def _build_reflection_prompt(
        self,
        signals: List[Dict[str, Any]],
        narratives: List[Dict[str, Any]],
        themes: List[str],
    ) -> str:
        categorized = self._categorize_signals(signals)

        def _format_time_line(signals_list: List[Dict], max_items: int = 8) -> str:
            if not signals_list:
                return "暂无"
            lines = []
            for s in signals_list[:max_items]:
                ts = s.get('ts', s.get('timestamp', 0))
                time_str = self._format_ts(ts)
                signal_type = s.get('signal_type', '')
                theme = s.get('theme', '-')[:25]
                score = s.get('system_attention', s.get('score', 0))
                lines.append(f"{time_str} | {signal_type} | {theme} | 分数{score:.2f}")
            return "\n".join(lines)

        radar_text = _format_time_line(categorized['radar'], 6)
        attention_text = _format_time_line(categorized['attention'], 6)
        cross_text = _format_time_line(categorized['cross_signal'], 4)
        feedback_text = _format_time_line(categorized['feedback'], 3)
        effectiveness_text = _format_time_line(categorized['effectiveness'], 3)
        previous_reflections_text = _format_time_line(categorized['llm_reflection'], 3)
        other_text = _format_time_line(categorized['other'], 4)

        def _format_narrative(n: Dict[str, Any]) -> str:
            narrative = n.get('narrative', '-')
            stage = n.get('stage', '萌芽')
            trend = n.get('trend', 0)
            ts = n.get('last_updated', 0)
            time_str = self._format_ts(ts) if ts else ""
            trend_icon = "📈" if trend > 0.3 else "📉" if trend < -0.3 else "➡️"
            trend_str = f"{trend:+.1%}" if isinstance(trend, float) else str(trend)
            time_prefix = f"[{time_str}]" if time_str else ""
            return f"{time_prefix}{narrative} [{stage}{trend_icon}{trend_str}]"

        narratives_text = "\n".join([_format_narrative(n) for n in narratives[:8]]) if narratives else "暂无叙事数据"

        narratives_active = [n for n in narratives if n.get('stage') in ('高潮', '扩散')] if narratives else []
        narratives_fading = [n for n in narratives if n.get('stage') in ('消退', '萌芽')] if narratives else []

        themes_text = "\n".join([f"- {t}" for t in themes[:10]]) if themes else "暂无主题"

        total_signals = len(signals)
        earliest_ts = min([s.get('ts', s.get('timestamp', 0)) for s in signals] or [0])
        latest_ts = max([s.get('ts', s.get('timestamp', 0)) for s in signals] or [0])
        time_range = f"{self._format_ts(earliest_ts)} ~ {self._format_ts(latest_ts)}" if earliest_ts and latest_ts else "时间范围未知"

        return f"""你是资深金融市场分析师。请基于多源异构数据进行深度市场反思。

## ⏱️ 数据时间范围
数据覆盖: {time_range}
总信号数: {total_signals}

## 📊 叙事变化趋势（按时间排序）
{narratives_text}
### 重点叙事
{" | ".join([f"{n['narrative']}({n['stage']})" for n in narratives_active[:3]]) if narratives_active else "无明显活跃叙事"}
{" | ".join([f"{n['narrative']}({n['stage']})" for n in narratives_fading[:3]]) if narratives_fading else "无消退叙事"}

## 📡 雷达事件（市场异常检测）
{radar_text}

## 👁️ 注意力事件（市场关注度变化）
{attention_text}

## 🔄 共振信号（新闻与注意力共振）
{cross_text}

## 📊 实验反馈（注意力系统学习结果）
{feedback_text}

## ✅ 有效性分析（哪些模式有效/无效）
{effectiveness_text}

## 🤖 历史反思（之前的反思结论）
{previous_reflections_text}

## 📋 其他信号
{other_text}

## 核心主题
{themes_text}

请生成深度市场反思，要求：
1. 重点分析叙事变化趋势，判断哪些叙事正在升温/消退
2. 结合时间线，分析事件发生的先后顺序和因果关系
3. 结合雷达异常和注意力事件，验证叙事变化的真实性
4. 评估共振信号与叙事趋势的匹配度
5. 结合实验反馈和有效性分析，判断当前策略的有效性
6. 给出形势判断（2-3句话）和可执行建议

仅返回 JSON 格式：
{{
    "theme": "反思主题（一句话，精炼）",
    "summary": "深度反思内容（150-300字，包含叙事趋势判断、形势分析和可执行建议）",
    "confidence": 0.0-1.0（判断置信度，基于信号数量和质量），
    "actionability": 0.0-1.0（可执行性，结论是否可直接指导行动），
    "novelty": 0.0-1.0（新颖程度，相比历史反思是否有新发现）
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

    def _emit_to_insight(self, reflection: Reflection) -> None:
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

    def trigger_now(self, min_signals: int = 1) -> Optional[Reflection]:
        """手动触发一次反思

        Args:
            min_signals: 最少需要的信号数，默认1（手动触发时降低要求）
        """
        return self._run_reflection(min_signals=min_signals)

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
