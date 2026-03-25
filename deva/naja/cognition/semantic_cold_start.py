"""Semantic cold-start utilities for building a seed-based semantic graph."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


DEFAULT_PROMPT_TEMPLATE = (
    "你是一个金融语义图谱助手。请基于给定的种子关键词扩展出一级、二级关联词，"
    "并输出 JSON，禁止输出额外解释。\n\n"
    "输入种子词: {seeds}\n\n"
    "输出 JSON schema:\n"
    "{{\n"
    "  \"seeds\": [\"AI\", \"算力\"],\n"
    "  \"nodes\": [\n"
    "    {{\"term\": \"GPU\", \"level\": 1, \"relation\": \"supply_chain\", \"confidence\": 0.78}},\n"
    "    {{\"term\": \"CPO\", \"level\": 1, \"relation\": \"tech_stack\", \"confidence\": 0.72}},\n"
    "    {{\"term\": \"液冷\", \"level\": 2, \"relation\": \"infrastructure\", \"confidence\": 0.62}}\n"
    "  ],\n"
    "  \"edges\": [\n"
    "    {{\"from\": \"算力\", \"to\": \"GPU\", \"type\": \"enables\"}},\n"
    "    {{\"from\": \"CPO\", \"to\": \"液冷\", \"type\": \"depends_on\"}}\n"
    "  ],\n"
    "  \"industry_decay\": [\n"
    "    {{\"term\": \"电力\", \"lambda\": 0.002}},\n"
    "    {{\"term\": \"AI\", \"lambda\": 0.01}}\n"
    "  ]\n"
    "}}\n"
)


@dataclass
class SemanticNode:
    term: str
    level: int = 0
    relation: str = ""
    confidence: float = 0.0
    weight: float = 0.0
    decay_lambda: float = 0.0
    last_seen_ts: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SemanticEdge:
    src: str
    dst: str
    relation: str = "related"
    weight: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)


class SemanticColdStart:
    """Build and maintain a semantic graph from seed terms."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.enabled = bool(cfg.get("semantic_cold_start_enabled", True))
        self.seeds: List[str] = list(cfg.get("semantic_seed_terms", []) or [])
        self.default_lambda = float(cfg.get("semantic_default_lambda", 0.005))
        self.industry_lambdas: Dict[str, float] = dict(cfg.get("semantic_industry_lambdas", {}) or {})
        self.prompt_template = str(cfg.get("semantic_cold_start_prompt", DEFAULT_PROMPT_TEMPLATE))
        self.graph: Dict[str, Any] = {
            "seeds": list(self.seeds),
            "nodes": [],
            "edges": [],
            "industry_decay": [],
            "created_at": time.time(),
        }

    def build_prompt(self, seeds: Optional[List[str]] = None) -> str:
        if seeds is None:
            seeds = self.seeds
        seed_str = ", ".join(seeds) if seeds else ""
        return self.prompt_template.format(seeds=seed_str)

    def apply_graph_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize LLM output into internal graph with weights and decay."""
        import logging
        logger = logging.getLogger(__name__)

        if not payload:
            return self.graph

        backup_graph = dict(self.graph)

        try:
            seeds = payload.get("seeds") or self.seeds
            nodes_payload = payload.get("nodes") or []
            edges_payload = payload.get("edges") or []
            decay_payload = payload.get("industry_decay") or []

            decay_map = {d.get("term"): float(d.get("lambda", self.default_lambda)) for d in decay_payload if d.get("term")}
            decay_map.update(self.industry_lambdas)

            nodes: List[Dict[str, Any]] = []
            now_ts = time.time()
            for item in nodes_payload:
                term = str(item.get("term", "")).strip()
                if not term:
                    continue
                confidence = float(item.get("confidence", 0.0) or 0.0)
                historical = float(item.get("historical_relevance", 0.3) or 0.3)
                weight = 0.6 * historical + 0.4 * confidence
                decay_lambda = float(decay_map.get(term, self.default_lambda))
                node = SemanticNode(
                    term=term,
                    level=int(item.get("level", 0) or 0),
                    relation=str(item.get("relation", "")),
                    confidence=confidence,
                    weight=round(weight, 4),
                    decay_lambda=decay_lambda,
                    last_seen_ts=now_ts,
                    meta={k: v for k, v in item.items() if k not in {"term", "level", "relation", "confidence", "historical_relevance"}},
                )
                nodes.append(node.__dict__)

            edges: List[Dict[str, Any]] = []
            for item in edges_payload:
                src = str(item.get("from", "")).strip()
                dst = str(item.get("to", "")).strip()
                if not src or not dst:
                    continue
                edge = SemanticEdge(
                    src=src,
                    dst=dst,
                    relation=str(item.get("type", item.get("relation", "related"))),
                    weight=float(item.get("weight", 0.3) or 0.3),
                    meta={k: v for k, v in item.items() if k not in {"from", "to", "type", "relation", "weight"}},
                )
                edges.append(edge.__dict__)

            self.graph = {
                "seeds": list(seeds),
                "nodes": nodes,
                "edges": edges,
                "industry_decay": [{"term": k, "lambda": v} for k, v in decay_map.items()],
                "created_at": payload.get("created_at", now_ts),
            }
            return self.graph
        except Exception as e:
            logger.warning(f"[SemanticColdStart] 解析图谱 payload 失败，恢复之前的图谱: {e}")
            self.graph = backup_graph
            return self.graph

    def get_summary(self, limit: int = 10) -> Dict[str, Any]:
        nodes = list(self.graph.get("nodes", []))
        nodes_sorted = sorted(nodes, key=lambda n: n.get("weight", 0.0), reverse=True)
        return {
            "seeds": self.graph.get("seeds", []),
            "top_nodes": nodes_sorted[:limit],
            "node_count": len(nodes),
            "edge_count": len(self.graph.get("edges", [])),
        }
