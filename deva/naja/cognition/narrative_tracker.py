"""Narrative tracker for thematic lifecycle, attention, and graph relationships."""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple


DEFAULT_NARRATIVE_KEYWORDS: Dict[str, List[str]] = {
    "AI": [
        "AI", "AIGC", "人工智能", "大模型", "多模态", "生成式", "GPT", "ChatGPT", "Sora",
        "算力", "智能体", "机器人", "自动驾驶", "NLP", "语音", "视觉",
        "LLM", "Agent", "RAG", "向量数据库", "Embedding",
        "OpenAI", "Anthropic", "Claude", "Gemini",
        "文心一言", "通义千问", "Kimi", "豆包", "智谱清言", "百川", "零一",
        "昇腾", "昆仑", "寒武纪", "燧原",
        "AI手机", "AI PC", "端侧AI", "边缘AI", "AI应用",
    ],
    "芯片": [
        "芯片", "半导体", "集成电路", "晶圆", "光刻", "EDA", "封测", "制程", "GPU", "CPU",
        "HBM", "DRAM", "NAND", "SoC", "ASIC", "FPGA", "存储",
        "先进封装", "CoWoS", "HBM3", "HBM3e",
        "英伟达", "AMD", "英特尔", "高通", "联发科", "博通",
        "台积电", "三星", "中芯国际", "华虹半导体",
    ],
    "新能源": [
        "新能源", "光伏", "风电", "储能", "锂电", "电池", "充电桩", "氢能", "碳中和", "碳达峰",
        "新能源车", "电动车", "逆变器", "光伏逆变器",
        "宁德时代", "比亚迪", "亿纬锂能", "国轩高科",
        "隆基绿能", "通威股份", "阳光电源", "晶澳科技",
        "特斯拉", "理想汽车", "蔚来汽车", "小鹏汽车",
    ],
    "医药": [
        "医药", "生物医药", "创新药", "疫苗", "医疗", "医疗器械", "临床", "试验", "基因",
        "细胞治疗", "CXO", "医院", "药品", "药企",
        "创新药", "仿制药", "中药", "生物药", "ADC", "双抗", "CAR-T",
        "恒瑞医药", "百济神州", "君实生物", "信达生物",
    ],
    "华为": [
        "华为", "昇腾", "鸿蒙", "HarmonyOS", "Harmony", "麒麟芯片",
        "鲲鹏", "昇思", "华为云", "HiCar", "智能驾驶",
        "Mate", "P系列", "问界", "智界",
    ],
    "中美关系": [
        "关税", "制裁", "贸易战", "出口管制", "实体清单", "黑名单",
        "美国商务部", "BIS", "EAR", "FDPR",
        "中美关系", "中美贸易", "美中", "中美会谈", "战略对话",
    ],
    "地缘政治": [
        "伊朗", "以色列", "中东", "霍尔木兹海峡", "红海",
        "俄乌", "乌克兰", "俄罗斯", "北约",
        "朝鲜", "朝鲜半岛", "韩朝", "台海",
        "巴以", "加沙", "耶路撒冷", "联合国安理会",
    ],
}


@dataclass
class NarrativeState:
    name: str
    stage: str = "萌芽"
    attention_score: float = 0.0
    total_count: int = 0
    recent_count: int = 0
    trend: float = 0.0
    last_updated: float = 0.0
    last_stage_change: float = 0.0
    hits: Deque[Tuple[float, float, List[str]]] = field(default_factory=deque)
    last_keywords: List[str] = field(default_factory=list)
    last_emit: Dict[str, float] = field(default_factory=dict)


class NarrativeTracker:
    """Track narrative lifecycle, attention, and relationship graph."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.enabled = bool(cfg.get("narrative_enabled", True))
        self._keywords = cfg.get("narrative_keywords") or DEFAULT_NARRATIVE_KEYWORDS
        self._recent_window = float(cfg.get("narrative_recent_window_seconds", 6 * 3600))
        self._prev_window = float(cfg.get("narrative_prev_window_seconds", 6 * 3600))
        self._history_window = float(cfg.get("narrative_history_window_seconds", 72 * 3600))
        self._graph_window = float(cfg.get("narrative_graph_window_seconds", 6 * 3600))
        self._count_scale = float(cfg.get("narrative_count_scale", 8.0))
        self._peak_score = float(cfg.get("narrative_peak_score", 0.8))
        self._spread_score = float(cfg.get("narrative_spread_score", 0.55))
        self._fade_score = float(cfg.get("narrative_fade_score", 0.25))
        self._peak_count = int(cfg.get("narrative_peak_count", 8))
        self._spread_count = int(cfg.get("narrative_spread_count", 4))
        self._fade_count = int(cfg.get("narrative_fade_count", 1))
        self._trend_threshold = float(cfg.get("narrative_trend_threshold", 0.5))
        self._spike_threshold = float(cfg.get("narrative_attention_spike_threshold", 0.75))
        self._spike_delta = float(cfg.get("narrative_spike_delta", 0.15))
        self._emit_cooldown = float(cfg.get("narrative_emit_cooldown_seconds", 120))
        self._graph_same_weight = float(cfg.get("narrative_graph_same_event_weight", 1.0))
        self._graph_temporal_weight = float(cfg.get("narrative_graph_temporal_weight", 0.3))

        self._states: Dict[str, NarrativeState] = {}
        self._graph_edges: Dict[Tuple[str, str], float] = defaultdict(float)
        self._recent_hits: Deque[Tuple[float, List[str]]] = deque()

    def detect_narratives(self, event: Any) -> Dict[str, List[str]]:
        if not self.enabled:
            return {}

        texts = self._collect_texts(event)
        if not texts:
            return {}

        combined = " ".join(t for t in texts if t)
        combined_lower = combined.lower()
        matches: Dict[str, List[str]] = {}

        for narrative, keywords in self._keywords.items():
            hit_keywords: List[str] = []
            for keyword in keywords:
                if self._keyword_in_text(keyword, combined, combined_lower):
                    hit_keywords.append(keyword)
            if hit_keywords:
                matches[narrative] = hit_keywords

        return matches

    def ingest_event(self, event: Any) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []

        matches = self.detect_narratives(event)
        if not matches:
            return []

        now_ts = self._get_timestamp(event)
        attention = self._clamp_score(getattr(event, "attention_score", 0.0))
        results: List[Dict[str, Any]] = []

        narratives = list(matches.keys())
        self._update_graph(now_ts, narratives)

        for narrative, keywords in matches.items():
            state = self._states.get(narrative)
            if state is None:
                state = NarrativeState(name=narrative, last_stage_change=now_ts)
                self._states[narrative] = state

            state.hits.append((now_ts, attention, keywords))
            state.total_count += 1
            state.last_keywords = keywords
            state.last_updated = now_ts

            self._prune_hits(state, now_ts)
            metrics = self._compute_metrics(state, now_ts)
            new_stage = self._determine_stage(metrics)
            new_score = metrics["attention_score"]

            stage_changed = new_stage != state.stage
            spike = new_score >= self._spike_threshold and (new_score - state.attention_score) >= self._spike_delta

            state.recent_count = metrics["recent_count"]
            state.trend = metrics["trend"]
            state.attention_score = new_score

            if stage_changed:
                state.stage = new_stage
                state.last_stage_change = now_ts
                event_payload = self._build_event_payload(
                    narrative=narrative,
                    event_type="narrative_stage_change",
                    stage=new_stage,
                    metrics=metrics,
                    keywords=keywords,
                )
                if self._should_emit(state, "stage", now_ts):
                    results.append(event_payload)

            if spike:
                event_payload = self._build_event_payload(
                    narrative=narrative,
                    event_type="narrative_attention_spike",
                    stage=new_stage,
                    metrics=metrics,
                    keywords=keywords,
                )
                if self._should_emit(state, "spike", now_ts):
                    results.append(event_payload)

        return results

    def get_summary(self, limit: int = 10) -> List[Dict[str, Any]]:
        if not self._states:
            return []
        sorted_states = sorted(self._states.values(), key=lambda s: s.attention_score, reverse=True)
        summary = []
        for state in sorted_states[:limit]:
            summary.append({
                "narrative": state.name,
                "stage": state.stage,
                "attention_score": round(state.attention_score, 3),
                "recent_count": state.recent_count,
                "trend": round(state.trend, 3),
                "last_updated": state.last_updated,
                "keywords": state.last_keywords,
            })
        return summary

    def get_graph(self, min_weight: float = 0.2) -> Dict[str, Any]:
        nodes = []
        for state in self._states.values():
            nodes.append({
                "id": state.name,
                "stage": state.stage,
                "attention_score": round(state.attention_score, 3),
                "recent_count": state.recent_count,
            })

        edges = []
        for (left, right), weight in self._graph_edges.items():
            if weight < min_weight:
                continue
            edges.append({
                "source": left,
                "target": right,
                "weight": round(weight, 3),
            })

        return {"nodes": nodes, "edges": edges}

    def get_linked_sectors(self, narrative: str) -> List[str]:
        """获取叙事主题关联的板块列表

        这是叙事-板块联动的关键接口：
        NarrativeTracker 识别叙事主题后，通过此方法获取关联的 sector_id，
        从而实现"舆情 → 板块轮动"的联动。

        Args:
            narrative: 叙事主题名称，如 "AI"、"芯片"、"新能源"

        Returns:
            关联的 sector_id 列表
        """
        from .narrative_sector_mapping import get_linked_sectors as _get_linked_sectors
        return _get_linked_sectors(narrative)

    def get_narrative_with_sectors(self) -> List[Dict[str, Any]]:
        """获取所有叙事主题及其关联板块

        Returns:
            包含 narrative 和 linked_sectors 的字典列表
        """
        from .narrative_sector_mapping import get_linked_sectors as _get_linked_sectors

        result = []
        for state in self._states.values():
            result.append({
                "narrative": state.name,
                "stage": state.stage,
                "attention_score": round(state.attention_score, 3),
                "linked_sectors": _get_linked_sectors(state.name),
            })
        return result

    def _collect_texts(self, event: Any) -> List[str]:
        texts: List[str] = []
        if event is None:
            return texts
        content = getattr(event, "content", None)
        if content:
            texts.append(str(content))
        meta = getattr(event, "meta", {}) or {}

        for key in ("title", "topic", "sector", "industry", "theme", "summary"):
            val = meta.get(key)
            if val:
                texts.append(str(val))

        for key in ("tags", "keywords", "narratives", "narrative"):
            val = meta.get(key)
            if isinstance(val, list):
                texts.extend([str(v) for v in val])
            elif val:
                texts.append(str(val))

        return texts

    def _keyword_in_text(self, keyword: str, text: str, text_lower: str) -> bool:
        if not keyword:
            return False
        if keyword.isascii():
            return keyword.lower() in text_lower
        return keyword in text

    def _get_timestamp(self, event: Any) -> float:
        ts = getattr(event, "timestamp", None)
        if ts is None:
            return time.time()
        if hasattr(ts, "timestamp"):
            try:
                return float(ts.timestamp())
            except Exception:
                return time.time()
        try:
            return float(ts)
        except Exception:
            return time.time()

    def _clamp_score(self, score: Any) -> float:
        try:
            value = float(score)
        except Exception:
            return 0.0
        if value < 0:
            return 0.0
        if value <= 1.0:
            return value
        return min(1.0, value / 5.0)

    def _prune_hits(self, state: NarrativeState, now_ts: float) -> None:
        cutoff = now_ts - self._history_window
        while state.hits and state.hits[0][0] < cutoff:
            state.hits.popleft()

    def _compute_metrics(self, state: NarrativeState, now_ts: float) -> Dict[str, Any]:
        recent_cutoff = now_ts - self._recent_window
        prev_cutoff = recent_cutoff - self._prev_window
        recent_hits = [h for h in state.hits if h[0] >= recent_cutoff]
        prev_hits = [h for h in state.hits if prev_cutoff <= h[0] < recent_cutoff]

        recent_count = len(recent_hits)
        prev_count = len(prev_hits)
        recent_attention = sum(h[1] for h in recent_hits) / recent_count if recent_hits else 0.0
        count_score = 1.0 - math.exp(-recent_count / max(self._count_scale, 1e-6))
        attention_score = 0.6 * count_score + 0.4 * recent_attention
        trend = (recent_count - prev_count) / max(prev_count, 1)

        return {
            "recent_count": recent_count,
            "prev_count": prev_count,
            "attention_score": attention_score,
            "recent_attention": recent_attention,
            "trend": trend,
        }

    def _determine_stage(self, metrics: Dict[str, Any]) -> str:
        recent_count = metrics["recent_count"]
        attention_score = metrics["attention_score"]
        trend = metrics["trend"]

        if recent_count <= self._fade_count and attention_score <= self._fade_score:
            return "消退"
        if recent_count >= self._peak_count or attention_score >= self._peak_score:
            return "高潮"
        if recent_count >= self._spread_count or trend >= self._trend_threshold or attention_score >= self._spread_score:
            return "扩散"
        return "萌芽"

    def _should_emit(self, state: NarrativeState, key: str, now_ts: float) -> bool:
        last_ts = state.last_emit.get(key, 0.0)
        if now_ts - last_ts < self._emit_cooldown:
            return False
        state.last_emit[key] = now_ts
        return True

    def _build_event_payload(
        self,
        *,
        narrative: str,
        event_type: str,
        stage: str,
        metrics: Dict[str, Any],
        keywords: List[str],
    ) -> Dict[str, Any]:
        payload = {
            "type": event_type,
            "event_type": event_type,
            "narrative": narrative,
            "stage": stage,
            "attention_score": round(metrics["attention_score"], 3),
            "recent_count": metrics["recent_count"],
            "prev_count": metrics["prev_count"],
            "trend": round(metrics["trend"], 3),
            "keywords": keywords,
            "linked_sectors": self.get_linked_sectors(narrative),
            "timestamp": time.time(),
        }
        return payload

    def _update_graph(self, now_ts: float, narratives: List[str]) -> None:
        cutoff = now_ts - self._graph_window
        while self._recent_hits and self._recent_hits[0][0] < cutoff:
            self._recent_hits.popleft()

        if len(narratives) > 1:
            pairs = self._pairs(narratives)
            for left, right in pairs:
                key = self._edge_key(left, right)
                self._graph_edges[key] += self._graph_same_weight

        for hit_ts, hit_list in self._recent_hits:
            if now_ts - hit_ts > self._graph_window:
                continue
            for left in narratives:
                for right in hit_list:
                    if left == right:
                        continue
                    key = self._edge_key(left, right)
                    self._graph_edges[key] += self._graph_temporal_weight

        self._recent_hits.append((now_ts, narratives))

    @staticmethod
    def _edge_key(left: str, right: str) -> Tuple[str, str]:
        return tuple(sorted((left, right)))

    @staticmethod
    def _pairs(items: Iterable[str]) -> List[Tuple[str, str]]:
        unique = list(dict.fromkeys(items))
        pairs: List[Tuple[str, str]] = []
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                pairs.append((unique[i], unique[j]))
        return pairs
