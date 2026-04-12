"""
FirstPrinciplesMind - 认知系统/第一性原理/因果分析

别名/关键词: 第一性原理、因果分析、first_principles、causality

"妙观察智"的进阶实现 - 意识层核心

觉醒增强版：
1. CausalityTracker: 时序因果、多步推理链、反事实分析
2. ContradictionDetector: 逻辑推理、程度分级、来源可信度
3. ReasoningEngine: 演绎/归纳/类比/反事实推理
4. MarketCausalityGraph: 市场因果图谱
5. CognitiveIntegrator: 与认知系统深度整合
"""

import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Set, Tuple
from dataclasses import dataclass, field
from collections import deque, defaultdict
from enum import Enum
from itertools import combinations

log = logging.getLogger(__name__)


class ThoughtLevel(Enum):
    """思考层次"""
    SURFACE = "surface"          # 表面现象
    PATTERN = "pattern"          # 模式识别
    CAUSAL = "causal"            # 因果关系
    FIRST_PRINCIPLES = "first_principles"  # 第一性原理
    META = "meta"                # 元认知


@dataclass
class CausalityChain:
    """因果链"""
    cause: str
    effect: str
    confidence: float
    chain_length: int
    is_direct: bool
    temporal_offset: float = 0  # 时间滞后（秒）
    chain_path: List[str] = field(default_factory=list)


@dataclass
class TemporalCausality:
    """时序因果"""
    cause: str
    effect: str
    delay_seconds: float  # 延迟时间
    confidence: float
    evidence_count: int
    lag_pattern: str  # "leading", "同步", "lagging"


@dataclass
class Counterfactual:
    """反事实分析"""
    condition: str
    baseline_outcome: str
    hypothetical_outcome: str
    difference: str
    confidence: float


@dataclass
class Contradiction:
    """矛盾"""
    topic_a: str
    topic_b: str
    description: str
    severity: float  # 0-1
    resolution_hint: str
    contradiction_type: str = "semantic"  # semantic, logical, data
    evidence: List[str] = field(default_factory=list)


@dataclass
class Reasoning:
    """推理结果"""
    reasoning_type: str  # deductive, inductive, analogical, counterfactual
    premise: List[str]
    conclusion: str
    confidence: float
    intermediate_steps: List[str] = field(default_factory=list)


@dataclass
class FirstPrinciplesInsight:
    """第一性原理洞察"""
    insight_type: str
    content: str
    level: ThoughtLevel
    confidence: float
    evidence: List[str]
    timestamp: float = field(default_factory=time.time)
    actionable: bool = True
    reasoning_chain: List[str] = field(default_factory=list)


class MarketCausalityGraph:
    """
    市场因果图谱

    构建和分析市场要素之间的因果关系网络
    """

    def __init__(self):
        self._nodes: Set[str] = set()
        self._edges: Dict[Tuple[str, str], Dict] = {}
        self._adjacency: Dict[str, List[str]] = defaultdict(list)
        self._reverse_adjacency: Dict[str, List[str]] = defaultdict(list)
        self._temporal_patterns: Dict[str, List[TemporalCausality]] = defaultdict(list)
        self._node_weights: Dict[str, float] = defaultdict(float)

    def add_node(self, node: str, weight: float = 1.0):
        """添加节点"""
        self._nodes.add(node)
        self._node_weights[node] = weight

    def add_causality(
        self,
        cause: str,
        effect: str,
        confidence: float,
        temporal_offset: float = 0,
        evidence: str = ""
    ):
        """添加因果边"""
        self.add_node(cause)
        self.add_node(effect)

        edge_key = (cause, effect)
        if edge_key not in self._edges:
            self._edges[edge_key] = {
                "confidence": confidence,
                "temporal_offset": temporal_offset,
                "evidence": [],
                "count": 0
            }
            self._adjacency[cause].append(effect)
            self._reverse_adjacency[effect].append(cause)

        self._edges[edge_key]["count"] += 1
        self._edges[edge_key]["confidence"] = (
            self._edges[edge_key]["confidence"] * 0.7 + confidence * 0.3
        )
        if evidence:
            self._edges[edge_key]["evidence"].append(evidence)

        if temporal_offset != 0:
            self._temporal_patterns[cause].append(TemporalCausality(
                cause=cause,
                effect=effect,
                delay_seconds=temporal_offset,
                confidence=confidence,
                evidence_count=self._edges[edge_key]["count"],
                lag_pattern="leading" if temporal_offset < 0 else "lagging"
            ))

    def find_causal_path(self, start: str, end: str, max_length: int = 5) -> Optional[List[str]]:
        """寻找从start到end的因果路径"""
        if start not in self._nodes or end not in self._nodes:
            return None

        visited = set()
        paths = []

        def dfs(node: str, path: List[str]):
            if len(path) > max_length:
                return
            if node == end:
                paths.append(path[:])
                return

            visited.add(node)
            for neighbor in self._adjacency[node]:
                if neighbor not in visited:
                    path.append(neighbor)
                    dfs(neighbor, path)
                    path.pop()
            visited.remove(node)

        dfs(start, [start])
        return max(paths, key=len) if paths else None

    def find_all_root_causes(self, effect: str, max_depth: int = 5) -> List[Tuple[List[str], float]]:
        """找出所有根本原因及其链"""
        if effect not in self._nodes:
            return []

        results = []

        def dfs(node: str, path: List[str], accumulated_conf: float):
            if len(path) > max_depth:
                return

            causes = self._reverse_adjacency[node]
            if not causes:
                if path:
                    results.append((path[::-1], accumulated_conf))
                return

            for cause in causes:
                if cause not in path:
                    edge_conf = self._edges.get((cause, node), {}).get("confidence", 0.5)
                    dfs(cause, path + [cause], accumulated_conf * edge_conf)

        dfs(effect, [effect], 1.0)
        return sorted(results, key=lambda x: -x[1])[:5]

    def get_upstream_factors(self, node: str, depth: int = 3) -> List[Tuple[str, float, int]]:
        """获取上游因素"""
        factors = []

        def dfs(current: str, current_depth: int, acc_conf: float):
            if current_depth >= depth:
                return

            for cause in self._reverse_adjacency[current]:
                edge_conf = self._edges.get((cause, current), {}).get("confidence", 0.5)
                new_conf = acc_conf * edge_conf
                factors.append((cause, new_conf, current_depth + 1))
                dfs(cause, current_depth + 1, new_conf)

        dfs(node, 0, 1.0)
        return sorted(factors, key=lambda x: -x[1])[:10]

    def get_downstream_effects(self, node: str, depth: int = 3) -> List[Tuple[str, float, int]]:
        """获取下游效应"""
        effects = []

        def dfs(current: str, current_depth: int, acc_conf: float):
            if current_depth >= depth:
                return

            for effect in self._adjacency[current]:
                edge_conf = self._edges.get((current, effect), {}).get("confidence", 0.5)
                new_conf = acc_conf * edge_conf
                effects.append((effect, new_conf, current_depth + 1))
                dfs(effect, current_depth + 1, new_conf)

        dfs(node, 0, 1.0)
        return sorted(effects, key=lambda x: -x[1])[:10]

    def analyze_temporal_relationships(self) -> Dict[str, Any]:
        """分析时序关系"""
        leading = []
        lagging = []
        sync = []

        for cause, patterns in self._temporal_patterns.items():
            for p in patterns:
                entry = {"cause": cause, "effect": p.effect, "delay": p.delay_seconds, "conf": p.confidence}
                if p.delay_seconds < -60:
                    leading.append(entry)
                elif p.delay_seconds > 60:
                    lagging.append(entry)
                else:
                    sync.append(entry)

        return {
            "leading_indicators": leading,
            "lagging_indicators": lagging,
            "synchronous": sync
        }

    def get_graph_stats(self) -> Dict[str, Any]:
        """获取图统计"""
        return {
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "avg_degree": sum(len(v) for v in self._adjacency.values()) / max(len(self._nodes), 1),
            "temporal_patterns": sum(len(v) for v in self._temporal_patterns.values())
        }


class CausalityTracker:
    """
    因果链追踪器

    增强版：支持时序因果、多步推理、反事实分析
    """

    def __init__(self):
        self._causes: Dict[str, List[str]] = defaultdict(list)
        self._effects: Dict[str, List[str]] = defaultdict(list)
        self._chains: List[CausalityChain] = []
        self._knowledge_base: Dict[str, float] = {}
        self._causality_graph = MarketCausalityGraph()
        self._counterfactuals: List[Counterfactual] = []

    def add_knowledge(self, cause: str, effect: str, confidence: float = 0.8, temporal_offset: float = 0):
        """添加因果知识"""
        if effect not in self._causes[cause]:
            self._causes[cause].append(effect)
        if cause not in self._effects[effect]:
            self._effects[effect].append(cause)

        key = f"{cause}->{effect}"
        self._knowledge_base[key] = confidence

        chain = CausalityChain(
            cause=cause,
            effect=effect,
            confidence=confidence,
            chain_length=1,
            is_direct=True,
            temporal_offset=temporal_offset,
            chain_path=[cause, effect]
        )
        self._chains.append(chain)

        self._causality_graph.add_causality(cause, effect, confidence, temporal_offset)

    def infer_causality(self, source: str, target: str, via_intermediate: str):
        """通过中间节点推断因果"""
        key1 = f"{source}->{via_intermediate}"
        key2 = f"{via_intermediate}->{target}"

        if key1 in self._knowledge_base and key2 in self._knowledge_base:
            conf1 = self._knowledge_base[key1]
            conf2 = self._knowledge_base[key2]
            inferred_conf = conf1 * conf2 * 0.9

            path = [source, via_intermediate, target]
            chain = CausalityChain(
                cause=source,
                effect=target,
                confidence=inferred_conf,
                chain_length=2,
                is_direct=False,
                chain_path=path
            )
            self._chains.append(chain)
            self._causality_graph.add_causality(source, target, inferred_conf)

            return inferred_conf
        return 0

    def find_root_cause(self, effect: str) -> Optional[List[str]]:
        """寻找根本原因"""
        results = self._causality_graph.find_all_root_causes(effect)
        if results:
            return results[0][0]
        return None

    def find_root_causes_detailed(self, effect: str, max_depth: int = 5) -> List[Dict]:
        """寻找根本原因（详细）"""
        results = self._causality_graph.find_all_root_causes(effect, max_depth)
        detailed = []

        for path, confidence in results:
            detailed.append({
                "path": path,
                "root_cause": path[-1] if path else None,
                "confidence": confidence,
                "chain_length": len(path),
                "steps": [f"{path[i]} -> {path[i+1]}" for i in range(len(path)-1)]
            })

        return detailed

    def predict_effects(self, cause: str) -> List[str]:
        """预测效果"""
        effects = []
        visited = set()

        def dfs(node: str):
            if node in visited:
                return
            visited.add(node)
            for effect in self._causes.get(node, []):
                effects.append(effect)
                dfs(effect)

        dfs(cause)
        return effects

    def predict_effects_with_confidence(self, cause: str) -> List[Tuple[str, float]]:
        """预测效果及置信度"""
        results = self._causality_graph.get_downstream_effects(cause)
        return [(name, conf) for name, conf, _ in results]

    def analyze_counterfactual(self, condition: str, baseline_outcome: str) -> Counterfactual:
        """反事实分析"""
        alternatives = []
        for cause in self._causes:
            if cause != condition and condition in cause:
                for effect in self._causes[cause]:
                    if effect != baseline_outcome:
                        alternatives.append(effect)

        hypothetical = alternatives[0] if alternatives else "结果会不同"

        counterfactual = Counterfactual(
            condition=condition,
            baseline_outcome=baseline_outcome,
            hypothetical_outcome=hypothetical,
            difference="条件改变导致结果改变",
            confidence=0.6 if alternatives else 0.3
        )

        self._counterfactuals.append(counterfactual)
        return counterfactual

    def get_causality_summary(self) -> Dict[str, Any]:
        """获取因果摘要"""
        graph_stats = self._causality_graph.get_graph_stats()
        return {
            "known_causes": len(self._causes),
            "known_effects": len(self._effects),
            "chains": len(self._chains),
            "knowledge_size": len(self._knowledge_base),
            "graph_stats": graph_stats,
            "counterfactuals": len(self._counterfactuals)
        }


class ContradictionDetector:
    """
    矛盾检测器

    增强版：逻辑推理、程度分级、来源可信度
    """

    def __init__(self):
        self._contradictions: List[Contradiction] = []
        self._narratives: Dict[str, Dict] = {}
        self._contradiction_patterns: List[Tuple[str, str, float]] = [
            ("涨", "跌", 1.0),
            ("多头", "空头", 0.9),
            ("看多", "看空", 0.9),
            ("利好", "利空", 0.9),
            ("风险低", "风险高", 0.8),
            ("安全", "危险", 0.8),
            ("基本面好", "基本面差", 0.85),
            ("流动性充裕", "流动性紧张", 0.8),
            ("放水", "收水", 0.85),
            ("宽松", "紧缩", 0.85),
            ("牛", "熊", 0.9),
            ("买入", "卖出", 0.7),
            ("增持", "减持", 0.8),
            ("推荐", "回避", 0.8),
            ("超配", "低配", 0.7),
        ]

    def add_narrative(self, topic: str, claim: str, source: str = "unknown", credibility: float = 0.5):
        """添加叙事（带来源和可信度）"""
        self._narratives[topic] = {
            "claim": claim,
            "source": source,
            "credibility": credibility,
            "timestamp": time.time()
        }

    def check_contradiction(self, topic_a: str, topic_b: str) -> Optional[Contradiction]:
        """检查两个主题是否矛盾"""
        if topic_a not in self._narratives or topic_b not in self._narratives:
            return None

        info_a = self._narratives[topic_a]
        info_b = self._narratives[topic_b]
        claim_a = info_a["claim"].lower()
        claim_b = info_b["claim"].lower()

        max_severity = 0
        matched_pattern = None

        for pos, neg, severity in self._contradiction_patterns:
            if (pos in claim_a and neg in claim_b) or (neg in claim_a and pos in claim_b):
                if severity > max_severity:
                    max_severity = severity
                    matched_pattern = (pos, neg)

        if max_severity > 0:
            cred_factor = (info_a["credibility"] + info_b["credibility"]) / 2
            final_severity = max_severity * 0.7 + cred_factor * 0.3

            return Contradiction(
                topic_a=topic_a,
                topic_b=topic_b,
                description=f"'{info_a['claim']}' vs '{info_b['claim']}'",
                severity=final_severity,
                resolution_hint=self._generate_resolution_hint(matched_pattern),
                contradiction_type="semantic",
                evidence=[f"来源A: {info_a['source']}", f"来源B: {info_b['source']}"]
            )

        return self._check_logical_contradiction(topic_a, topic_b)

    def _check_logical_contradiction(self, topic_a: str, topic_b: str) -> Optional[Contradiction]:
        """检查逻辑矛盾"""
        info_a = self._narratives[topic_a]
        info_b = self._narratives[topic_b]

        numeric_a = self._extract_numeric(info_a["claim"])
        numeric_b = self._extract_numeric(info_b["claim"])

        if numeric_a and numeric_b:
            diff = abs(numeric_a - numeric_b)
            if diff > 0.5:
                return Contradiction(
                    topic_a=topic_a,
                    topic_b=topic_b,
                    description=f"数值差异: {numeric_a} vs {numeric_b}",
                    severity=min(diff * 0.3, 1.0),
                    resolution_hint="检查数据来源和计算方法",
                    contradiction_type="data",
                    evidence=[f"来源A: {info_a['source']}", f"来源B: {info_b['source']}"]
                )

        return None

    def _extract_numeric(self, text: str) -> Optional[float]:
        """提取数值"""
        import re
        numbers = re.findall(r'[-+]?\d*\.\d+|\d+', text)
        if numbers:
            try:
                return float(numbers[0])
            except ValueError:
                pass
        return None

    def _generate_resolution_hint(self, pattern: Optional[Tuple[str, str]]) -> str:
        """生成解决线索"""
        if not pattern:
            return "需要更多信息来判断"
        return f"检测到'{pattern[0]}'与'{pattern[1]}'矛盾，需验证数据来源和时效性"

    def detect_all_contradictions(self) -> List[Contradiction]:
        """检测所有矛盾"""
        contradictions = []
        topics = list(self._narratives.keys())

        for i, topic_a in enumerate(topics):
            for topic_b in topics[i+1:]:
                contradiction = self.check_contradiction(topic_a, topic_b)
                if contradiction:
                    contradictions.append(contradiction)

        self._contradictions = sorted(contradictions, key=lambda c: -c.severity)
        return self._contradictions

    def get_severe_contradictions(self, threshold: float = 0.7) -> List[Contradiction]:
        """获取严重矛盾"""
        return [c for c in self._contradictions if c.severity >= threshold]

    def get_contradiction_summary(self) -> Dict[str, Any]:
        """获取矛盾摘要"""
        return {
            "total_narratives": len(self._narratives),
            "contradictions_found": len(self._contradictions),
            "severe_contradictions": len([c for c in self._contradictions if c.severity > 0.7]),
            "by_type": {
                "semantic": len([c for c in self._contradictions if c.contradiction_type == "semantic"]),
                "logical": len([c for c in self._contradictions if c.contradiction_type == "logical"]),
                "data": len([c for c in self._contradictions if c.contradiction_type == "data"])
            },
            "avg_severity": sum(c.severity for c in self._contradictions) / max(len(self._contradictions), 1)
        }


class ReasoningEngine:
    """
    推理引擎

    支持演绎推理、归纳推理、类比推理、反事实推理
    """

    def __init__(self):
        self._rules: List[Dict] = []
        self._patterns: Dict[str, List[str]] = defaultdict(list)
        self._initialize_rules()

    def _initialize_rules(self):
        """初始化推理规则"""
        self._rules = [
            {"if": ["降息", "流动性增加"], "then": "股市上涨", "confidence": 0.7},
            {"if": ["加息", "流动性减少"], "then": "股市下跌", "confidence": 0.7},
            {"if": ["业绩超预期", "营收增长"], "then": "股价上涨", "confidence": 0.8},
            {"if": ["主力流入", "资金推动"], "then": "股价上涨", "confidence": 0.75},
            {"if": ["政策利好", "市场信心"], "then": "市场反弹", "confidence": 0.7},
            {"if": ["地缘政治风险", "避险情绪"], "then": "市场恐慌", "confidence": 0.8},
            {"if": ["美股下跌", "全球市场联动"], "then": "A股跟跌", "confidence": 0.6},
            {"if": ["通胀上升", "央行加息"], "then": "流动性收紧", "confidence": 0.85},
            {"if": ["流动性收紧", "无风险利率上升"], "then": "股市估值下降", "confidence": 0.75},
        ]

        self._patterns = {
            "上涨模式": ["放量上涨", "缩量上涨", "突破上涨"],
            "下跌模式": ["放量下跌", "缩量下跌", "破位下跌"],
            "盘整模式": ["缩量盘整", "震荡整理"],
            "反转模式": ["V型反转", "W底", "头肩顶"],
        }

    def deductive_reasoning(self, premises: List[str]) -> List[Reasoning]:
        """演绎推理：从一般到特殊"""
        results = []

        for rule in self._rules:
            rule_if = rule["if"]
            if all(p.lower() in [pr.lower() for pr in premises] for p in rule_if):
                results.append(Reasoning(
                    reasoning_type="deductive",
                    premise=premises + rule_if,
                    conclusion=rule["then"],
                    confidence=rule["confidence"],
                    intermediate_steps=[f"规则: {'且'.join(rule_if)} → {rule['then']}"]
                ))

        return results

    def inductive_reasoning(self, observations: List[str]) -> List[Reasoning]:
        """归纳推理：从特殊到一般"""
        results = []

        for pattern_name, pattern_cases in self._patterns.items():
            matches = [obs for obs in observations if any(p in obs for p in pattern_cases)]
            if len(matches) >= 2:
                results.append(Reasoning(
                    reasoning_type="inductive",
                    premise=observations,
                    conclusion=f"市场呈现{pattern_name}",
                    confidence=min(0.5 + len(matches) * 0.1, 0.9),
                    intermediate_steps=[f"观察到: {', '.join(matches)}"]
                ))

        if len(observations) >= 3:
            all_causes = []
            all_effects = []
            for obs in observations:
                for rule in self._rules:
                    if any(p.lower() in obs.lower() for p in rule["if"]):
                        all_causes.append(obs)
                        all_effects.append(rule["then"])

            if all_causes and all_effects:
                results.append(Reasoning(
                    reasoning_type="inductive",
                    premise=observations,
                    conclusion=f"归纳: {'; '.join(set(all_effects))}",
                    confidence=0.65,
                    intermediate_steps=[f"共同特征: {', '.join(set(all_causes))[:50]}"]
                ))

        return results

    def analogical_reasoning(self, source_case: str, target_case: str) -> Reasoning:
        """类比推理：从相似案例推断"""
        similarity_score = self._calculate_similarity(source_case, target_case)

        target_prediction = ""
        for rule in self._rules:
            if any(p.lower() in source_case.lower() for p in rule["if"]):
                target_prediction = rule["then"]
                break

        return Reasoning(
            reasoning_type="analogical",
            premise=[source_case, target_case],
            conclusion=f"类比推断: {target_prediction if target_prediction else '结果可能相似'}",
            confidence=similarity_score * 0.7,
            intermediate_steps=[
                f"源案例: {source_case[:30]}...",
                f"目标案例: {target_case[:30]}...",
                f"相似度: {similarity_score:.2f}"
            ]
        )

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) if union else 0

    def counterfactual_reasoning(self, actual_condition: str, hypothetical_change: str) -> Reasoning:
        """反事实推理：如果...会怎样"""
        actual_effect = ""
        hypothetical_effect = ""

        for rule in self._rules:
            if any(p.lower() in actual_condition.lower() for p in rule["if"]):
                actual_effect = rule["then"]
                break

        for rule in self._rules:
            if any(p.lower() in hypothetical_change.lower() for p in rule["if"]):
                hypothetical_effect = rule["then"]
                break

        return Reasoning(
            reasoning_type="counterfactual",
            premise=[actual_condition, hypothetical_change],
            conclusion=f"反事实: 实际结果={actual_effect}, 如果改变则={hypothetical_effect}",
            confidence=0.6,
            intermediate_steps=[
                f"实际情况: {actual_condition[:30]}...",
                f"假设改变: {hypothetical_change[:30]}...",
                f"结果可能改变"
            ]
        )


class CognitiveIntegrator:
    """
    认知系统整合器

    与NarrativeTracker、InsightPool、LiquidityCognition深度整合
    """

    def __init__(self):
        self._linked_narratives: List[str] = []
        self._linked_insights: List[Dict] = []
        self._liquidity_context: Dict = {}

    def integrate_narrative(self, narrative: str, context: Dict):
        """整合叙事"""
        self._linked_narratives.append(narrative)

    def integrate_insight(self, insight: Dict):
        """整合洞察"""
        self._linked_insights.append(insight)

    def set_liquidity_context(self, context: Dict):
        """设置流动性上下文"""
        self._liquidity_context = context

    def get_integrated_context(self) -> Dict[str, Any]:
        """获取整合后的上下文"""
        return {
            "narratives": self._linked_narratives[-5:],
            "insights": self._linked_insights[-5:],
            "liquidity": self._liquidity_context
        }


class FirstPrinciplesAnalyzer:
    """
    第一性原理分析器

    整合因果追踪、矛盾检测、推理引擎
    """

    # 因果知识库文件路径 — 统一使用 knowledge 目录
    CAUSALITY_KB_FILE = str(Path(__file__).parent.parent / "knowledge" / "causality_knowledge.json")
    NARRATIVES_FILE = str(Path(__file__).parent.parent / "knowledge" / "narratives.json")

    def __init__(self):
        self.causality_tracker = CausalityTracker()
        self.contradiction_detector = ContradictionDetector()
        self.reasoning_engine = ReasoningEngine()
        self.cognitive_integrator = CognitiveIntegrator()
        self._insights: deque = deque(maxlen=200)
        self._market_states: deque = deque(maxlen=50)
        self._knowledge_loaded = False  # 防止重复加载
        self._initialize_base_knowledge()

    def _load_knowledge_from_file(self):
        """从文件加载因果知识和叙事（深思熟虑版）"""
        import json
        import os

        if self._knowledge_loaded:
            return

        # 1. 加载因果知识库
        if os.path.exists(self.CAUSALITY_KB_FILE):
            try:
                with open(self.CAUSALITY_KB_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                knowledge_list = data.get("knowledge", [])
                qualified_count = 0

                for entry in knowledge_list:
                    status = entry.get("status", "observing")
                    # 只加载验证通过或验证中的知识
                    if status in ("qualified", "validating"):
                        cause = entry.get("cause", "")
                        effect = entry.get("effect", "")
                        # 验证中的知识降权50%
                        confidence = entry.get("adjusted_confidence", 0.5)
                        if status == "validating":
                            confidence *= 0.5

                        if cause and effect:
                            # 检查是否已存在
                            key = f"{cause}->{effect}"
                            if key not in self.causality_tracker._knowledge_base:
                                self.causality_tracker.add_knowledge(
                                    cause, effect, confidence, 0
                                )
                                if status == "qualified":
                                    qualified_count += 1

                log.info(f"[FirstPrinciples] 从因果知识库加载了 {qualified_count} 条正式知识")
            except Exception as e:
                log.warning(f"[FirstPrinciples] 加载因果知识库失败: {e}")

        # 2. 加载叙事库
        if os.path.exists(self.NARRATIVES_FILE):
            try:
                with open(self.NARRATIVES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                narratives = data.get("narratives", [])
                for narrative in narratives:
                    name = narrative.get("name", "")
                    strength = narrative.get("strength", 0.5)
                    if name and name != "暂无明确叙事":
                        # 将叙事添加到矛盾检测器
                        self.contradiction_detector.add_narrative(
                            topic=name,
                            claim=f"叙事强度: {strength}",
                            source="narratives.json",
                            credibility=strength
                        )

                log.info(f"[FirstPrinciples] 从叙事库加载了 {len(narratives)} 条叙事")
            except Exception as e:
                log.warning(f"[FirstPrinciples] 加载叙事库失败: {e}")

        self._knowledge_loaded = True

    def _initialize_base_knowledge(self):
        """初始化基础因果知识"""
        base_causalities = [
            ("降息", "流动性增加", 0.9, 3600),
            ("降息", "股市上涨", 0.7, 7200),
            ("通胀上升", "央行加息", 0.85, 86400),
            ("加息", "流动性减少", 0.8, 3600),
            ("加息", "股市下跌", 0.75, 7200),
            ("业绩超预期", "股价上涨", 0.85, 1800),
            ("业绩不及预期", "股价下跌", 0.85, 1800),
            ("主力流入", "股价上涨", 0.8, 300),
            ("主力流出", "股价下跌", 0.8, 300),
            ("政策利好", "市场反弹", 0.75, 3600),
            ("政策利空", "市场下跌", 0.75, 3600),
            ("地缘政治风险", "市场恐慌", 0.8, 1800),
            ("美股下跌", "A股跟跌", 0.7, 1800),
            ("美股上涨", "A股跟涨", 0.6, 1800),
            ("流动性收紧", "估值下降", 0.75, 86400),
            ("流动性宽松", "估值上升", 0.7, 86400),
            ("人民币贬值", "外资流出", 0.8, 3600),
            ("人民币升值", "外资流入", 0.8, 3600),
            ("北向资金流入", "指数上涨", 0.75, 1800),
            ("北向资金流出", "指数下跌", 0.75, 1800),
        ]

        for cause, effect, confidence, offset in base_causalities:
            self.causality_tracker.add_knowledge(cause, effect, confidence, offset)

        # 加载文件中的深思熟虑知识（异步，不阻塞初始化）
        try:
            import threading
            t = threading.Thread(target=self._load_knowledge_from_file, daemon=True)
            t.start()
        except Exception:
            pass

    def analyze(
        self,
        market_data: Dict[str, Any],
        narratives: Optional[List[str]] = None,
        signals: Optional[List[Dict[str, Any]]] = None,
        liquidity_data: Optional[Dict] = None,
        topic_signals: Optional[List[Dict[str, Any]]] = None,
        news_sentiment: Optional[str] = None,
        ai_compute_trend: Optional[Dict] = None,
        ai_positions: Optional[Dict] = None,
        problem_opportunity: Optional[Dict[str, Any]] = None
    ) -> List[FirstPrinciplesInsight]:
        """第一性原理分析"""
        insights = []

        # 确保知识已加载（如果线程还没执行完，在这里同步等待）
        if not self._knowledge_loaded:
            self._load_knowledge_from_file()

        self._market_states.append(market_data)

        if liquidity_data:
            self.cognitive_integrator.set_liquidity_context(liquidity_data)

        cause_insights = self._analyze_root_causes(market_data)
        insights.extend(cause_insights)

        if narratives:
            narrative_insights = self._analyze_narratives(narratives)
            insights.extend(narrative_insights)

        if signals:
            signal_insights = self._analyze_signals(signals)
            insights.extend(signal_insights)

        if topic_signals:
            topic_insights = self._analyze_topic_signals(topic_signals)
            insights.extend(topic_insights)

        if news_sentiment:
            sentiment_insights = self._analyze_news_sentiment(news_sentiment)
            insights.extend(sentiment_insights)

        if ai_compute_trend:
            ai_insights = self._analyze_ai_compute(ai_compute_trend, ai_positions, market_data)
            insights.extend(ai_insights)

        if problem_opportunity and problem_opportunity.get("status") == "active":
            po_insights = self._analyze_problem_opportunity(
                detected_problems=problem_opportunity.get("problems", []),
                opportunities=problem_opportunity.get("opportunities", []),
                resolvers=problem_opportunity.get("resolvers", []),
                market_data=market_data
            )
            insights.extend(po_insights)

        contradiction_insights = self._detect_contradictions(market_data)
        insights.extend(contradiction_insights)

        reasoning_insights = self._apply_reasoning(market_data)
        insights.extend(reasoning_insights)

        temporal_insights = self._analyze_temporal_patterns(market_data)
        insights.extend(temporal_insights)

        insights.sort(key=lambda x: (x.level.value if hasattr(x.level, 'value') else 0, -x.confidence), reverse=True)

        for insight in insights:
            self._insights.append(insight)

        return insights

    def _analyze_root_causes(self, market_data: Dict[str, Any]) -> List[FirstPrinciplesInsight]:
        """分析根本原因"""
        insights = []

        price_change = market_data.get("price_change", 0)
        volume_change = market_data.get("volume_change", 0)
        volatility = market_data.get("volatility", 1.0)
        symbol = market_data.get("symbol", "市场")

        if abs(price_change) > 2 or abs(volume_change) > 30:
            root_causes = self.causality_tracker.find_root_causes_detailed("股价上涨" if price_change > 0 else "股价下跌")

            if root_causes:
                primary = root_causes[0]
                insights.append(FirstPrinciplesInsight(
                    insight_type="cause",
                    content=f"{symbol}变化的根本原因链: {' -> '.join(primary['path'])} (置信度:{primary['confidence']:.2f})",
                    level=ThoughtLevel.FIRST_PRINCIPLES,
                    confidence=primary['confidence'],
                    evidence=[f"价格变化:{price_change}%"],
                    reasoning_chain=primary['steps']
                ))

        if volatility > 2.0:
            upstream = self.causality_tracker._causality_graph.get_upstream_factors("高波动", depth=3)
            if upstream:
                causes = [f"{c[0]}({c[1]:.2f})" for c in upstream[:3]]
                insights.append(FirstPrinciplesInsight(
                    insight_type="risk",
                    content=f"高波动的上游因素: {', '.join(causes)}",
                    level=ThoughtLevel.CAUSAL,
                    confidence=0.75,
                    evidence=[f"波动率: {volatility}"]
                ))
            else:
                insights.append(FirstPrinciplesInsight(
                    insight_type="risk",
                    content="市场异常高波动，可能有重大事件驱动",
                    level=ThoughtLevel.FIRST_PRINCIPLES,
                    confidence=0.75,
                    evidence=[f"波动率: {volatility}"]
                ))

        return insights

    def _analyze_narratives(self, narratives: List[str]) -> List[FirstPrinciplesInsight]:
        """分析叙事"""
        insights = []

        for i, narrative in enumerate(narratives):
            topic = f"narrative_{int(time.time())}_{i}"
            self.contradiction_detector.add_narrative(topic, narrative, "market_analysis", 0.6)

        contradictions = self.contradiction_detector.detect_all_contradictions()

        for contradiction in contradictions:
            insights.append(FirstPrinciplesInsight(
                insight_type="contradiction",
                content=f"发现矛盾({contradiction.contradiction_type}): {contradiction.description}",
                level=ThoughtLevel.CAUSAL if contradiction.severity < 0.7 else ThoughtLevel.FIRST_PRINCIPLES,
                confidence=contradiction.severity,
                evidence=contradiction.evidence,
                actionable=True
            ))

        if len(narratives) >= 3:
            insights.append(FirstPrinciplesInsight(
                insight_type="opportunity",
                content=f"多重叙事同时存在({len(narratives)}个)，市场可能进入转折期",
                level=ThoughtLevel.PATTERN,
                confidence=0.65,
                evidence=[f"叙事数量: {len(narratives)}"]
            ))

        return insights

    def _analyze_signals(self, signals: List[Dict[str, Any]]) -> List[FirstPrinciplesInsight]:
        """分析信号"""
        insights = []

        buy_signals = [s for s in signals if s.get("action") == "buy"]
        sell_signals = [s for s in signals if s.get("action") == "sell"]
        hold_signals = [s for s in signals if s.get("action") == "hold"]

        if len(buy_signals) > 5 and len(sell_signals) > 5:
            insights.append(FirstPrinciplesInsight(
                insight_type="contradiction",
                content=f"多空信号同时强烈(买:{len(buy_signals)},卖:{len(sell_signals)})，分歧巨大可能是拐点",
                level=ThoughtLevel.FIRST_PRINCIPLES,
                confidence=0.8,
                evidence=["多空信号共振"]
            ))

        if len(buy_signals) > len(sell_signals) * 2 and len(buy_signals) > 3:
            insights.append(FirstPrinciplesInsight(
                insight_type="opportunity",
                content=f"买入信号占主导({len(buy_signals)} vs {len(sell_signals)})，市场一致性看多",
                level=ThoughtLevel.PATTERN,
                confidence=0.7,
                evidence=["买入信号占主导"]
            ))

        if len(hold_signals) > len(buy_signals) + len(sell_signals):
            insights.append(FirstPrinciplesInsight(
                insight_type="risk",
                content="市场观望情绪浓厚，可能等待方向确认",
                level=ThoughtLevel.CAUSAL,
                confidence=0.6,
                evidence=["观望信号居多"]
            ))

        return insights

    def _analyze_topic_signals(self, topic_signals: List[Dict[str, Any]]) -> List[FirstPrinciplesInsight]:
        """分析新闻话题信号"""
        insights = []

        high_conf_topics = [t for t in topic_signals if t.get("confidence", 0) >= 0.7]

        if len(high_conf_topics) >= 2:
            topic_names = [t.get("topic_name", "") for t in high_conf_topics[:3]]
            insights.append(FirstPrinciplesInsight(
                insight_type="opportunity",
                content=f"多主题高置信度共振: {', '.join(topic_names)}",
                level=ThoughtLevel.FIRST_PRINCIPLES,
                confidence=0.75,
                evidence=[f"高置信度话题数: {len(high_conf_topics)}"]
            ))

        growing_topics = [t for t in topic_signals if t.get("type") == "topic_grow"]
        if growing_topics:
            topics_text = ", ".join([t.get("topic_name", "") for t in growing_topics[:2]])
            insights.append(FirstPrinciplesInsight(
                insight_type="opportunity",
                content=f"话题正在扩散: {topics_text}",
                level=ThoughtLevel.PATTERN,
                confidence=0.65,
                evidence=[f"增长话题数: {len(growing_topics)}"]
            ))

        high_attention_topics = [t for t in topic_signals if t.get("type") == "topic_high_attention"]
        if high_attention_topics:
            topics_text = ", ".join([t.get("topic_name", "") for t in high_attention_topics[:2]])
            insights.append(FirstPrinciplesInsight(
                insight_type="risk",
                content=f"高关注话题过热: {topics_text}",
                level=ThoughtLevel.CAUSAL,
                confidence=0.6,
                evidence=[f"高关注话题数: {len(high_attention_topics)}"]
            ))

        return insights

    def _analyze_news_sentiment(self, news_sentiment: str) -> List[FirstPrinciplesInsight]:
        """分析新闻情绪"""
        insights = []

        sentiment_map = {
            "bullish": ("乐观", 0.7, ThoughtLevel.CAUSAL),
            "fearful": ("恐慌", 0.7, ThoughtLevel.CAUSAL),
            "neutral": ("中性", 0.4, ThoughtLevel.SURFACE),
        }

        sentiment_info = sentiment_map.get(news_sentiment, ("中性", 0.4, ThoughtLevel.SURFACE))
        sentiment_text, base_confidence, thought_level = sentiment_info

        insights.append(FirstPrinciplesInsight(
            insight_type="market_sentiment",
            content=f"新闻情绪偏向{sentiment_text}",
            level=thought_level,
            confidence=base_confidence,
            evidence=[f"情绪源: NewsMind", f"情绪类型: {news_sentiment}"]
        ))

        if news_sentiment == "fearful":
            insights.append(FirstPrinciplesInsight(
                insight_type="risk",
                content="新闻情绪恐慌，需警惕系统性风险",
                level=ThoughtLevel.CAUSAL,
                confidence=0.75,
                evidence=["新闻情绪恐慌"]
            ))
        elif news_sentiment == "bullish":
            insights.append(FirstPrinciplesInsight(
                insight_type="opportunity",
                content="新闻情绪乐观，市场参与度高",
                level=ThoughtLevel.PATTERN,
                confidence=0.65,
                evidence=["新闻情绪乐观"]
            ))

        return insights

    def _analyze_ai_compute(
        self,
        ai_compute_trend: Dict,
        ai_positions: Optional[Dict],
        market_data: Dict
    ) -> List[FirstPrinciplesInsight]:
        """分析 AI算力趋势与持仓的背离"""
        insights = []

        trend_direction = ai_compute_trend.get("trend_direction", "unknown")
        cumulative_growth = ai_compute_trend.get("cumulative_growth", 0)
        base_strength = ai_compute_trend.get("base_strength", 0.5)
        price_change = market_data.get("price_change", 0)

        if cumulative_growth > 1.0 and price_change < -5:
            insights.append(FirstPrinciplesInsight(
                insight_type="opportunity",
                content=f"背离机会: AI算力需求累计增长{cumulative_growth*100:.0f}%但股价下跌{abs(price_change):.1f}%，基本面与价格背离",
                level=ThoughtLevel.FIRST_PRINCIPLES,
                confidence=0.75,
                evidence=[
                    f"算力需求累计增长: {cumulative_growth*100:.1f}%",
                    f"股价变动: {price_change:.1f}%",
                    f"趋势方向: {trend_direction}"
                ]
            ))

        if ai_positions and trend_direction == "rising":
            for symbol, pos_data in ai_positions.items():
                return_pct = pos_data.get("return_pct", 0)
                if return_pct < -10:
                    insights.append(FirstPrinciplesInsight(
                        insight_type="opportunity",
                        content=f"{symbol}持仓亏损{return_pct:.1f}%，但AI算力需求强劲，可能是加仓机会",
                        level=ThoughtLevel.CAUSAL,
                        confidence=0.7,
                        evidence=[
                            f"持仓亏损: {return_pct:.1f}%",
                            f"算力趋势: {trend_direction}",
                            f"累计增长: {cumulative_growth*100:.1f}%"
                        ]
                    ))

        if trend_direction == "rising" and base_strength > 0.7:
            insights.append(FirstPrinciplesInsight(
                insight_type="opportunity",
                content="AI算力需求强劲，市场可能低估算力题材基本面",
                level=ThoughtLevel.PATTERN,
                confidence=0.65,
                evidence=[f"算力需求强度: {base_strength:.2f}", f"趋势: {trend_direction}"]
            ))

        if ai_compute_trend.get("is_abnormal"):
            insights.append(FirstPrinciplesInsight(
                insight_type="risk",
                content="AI算力需求出现异常波动，需密切关注",
                level=ThoughtLevel.CAUSAL,
                confidence=0.7,
                evidence=[f"异常类型: {ai_compute_trend.get('alert_level')}"]
            ))

        return insights

    def _analyze_problem_opportunity(
        self,
        detected_problems: List[Dict[str, Any]],
        opportunities: List[Dict[str, Any]],
        resolvers: List[Dict[str, Any]],
        market_data: Dict[str, Any]
    ) -> List[FirstPrinciplesInsight]:
        """
        分析供需问题-机会-解决者

        核心分析：
        1. 因果链：这个问题为什么会发生？（根因分析）
        2. 解决者验证：这些解决者真的能解决问题吗？
        3. 时间窗口：问题会持续多久？
        4. 背离识别：问题存在但相关标的为什么不涨？
        """
        insights = []

        if not detected_problems:
            return insights

        price_change = market_data.get("price_change", 0)
        volatility = market_data.get("volatility", 1.0)

        for problem in detected_problems:
            problem_type = problem.get("type", "unknown")
            severity = problem.get("severity", "unknown")

            insight = self._analyze_problem_root_cause(problem_type, severity)
            if insight:
                insights.append(insight)

        for opp in opportunities:
            opp_type = opp.get("opportunity", "")
            beneficiaries = opp.get("beneficiaries", [])

            insight = self._analyze_opportunity_validity(opp_type, beneficiaries, resolvers)
            if insight:
                insights.append(insight)

        for resolver in resolvers:
            resolver_name = resolver.get("name", "unknown")
            progress = resolver.get("progress", "unknown")
            opportunity = resolver.get("opportunity", "")

            insight = self._analyze_resolver_progress(resolver_name, progress, opportunity, price_change)
            if insight:
                insights.append(insight)

        if len(detected_problems) >= 2 and price_change > 5:
            insights.append(FirstPrinciplesInsight(
                insight_type="opportunity",
                content=f"多重供需问题共振 + 价格上涨，可能是强趋势信号",
                level=ThoughtLevel.FIRST_PRINCIPLES,
                confidence=0.75,
                evidence=[
                    f"问题数量: {len(detected_problems)}",
                    f"价格变动: {price_change:.1f}%"
                ]
            ))

        if len(detected_problems) >= 2 and price_change < -5:
            insights.append(FirstPrinciplesInsight(
                insight_type="opportunity",
                content=f"多重供需问题存在但股价下跌，可能是错杀机会",
                level=ThoughtLevel.FIRST_PRINCIPLES,
                confidence=0.70,
                evidence=[
                    f"问题数量: {len(detected_problems)}",
                    f"价格变动: {price_change:.1f}%"
                ]
            ))

        return insights

    def _analyze_problem_root_cause(self, problem_type: str, severity: str) -> Optional[FirstPrinciplesInsight]:
        """分析问题的根本原因"""
        causal_knowledge = {
            "token供给不足": {
                "root_cause": "GPU封装产能不足（CoWoS瓶颈）+ 英伟达H100/H200交付延迟",
                "causal_chain": ["AI需求爆发", "GPU需求激增", "CoWoS封装产能满载", "交付延迟"],
                "expected_duration": "至少持续到2025年中"
            },
            "token需求爆发": {
                "root_cause": "ChatGPT/Claude等大模型用户快速增长 + API调用量指数级上升",
                "causal_chain": ["大模型发布", "用户爆发", "API调用激增", "算力供不应求"],
                "expected_duration": "需求持续增长"
            },
            "电力供给不足": {
                "root_cause": "数据中心扩张速度超过电网建设速度 + 绿色能源转型阵痛",
                "causal_chain": ["AI算力需求", "数据中心扩张", "电力需求激增", "电网超载"],
                "expected_duration": "电网升级需要2-3年"
            },
            "电力需求爆发": {
                "root_cause": "AI大模型训练和推理需要大量电力 + 比特币挖矿回潮",
                "causal_chain": ["大模型训练", "推理算力消耗", "总用电量激增"],
                "expected_duration": "长期趋势"
            },
            "芯片供给不足": {
                "root_cause": "先进制程设备（EUV）被限制出口 + 成熟制程产能扩张慢",
                "causal_chain": ["美国制裁", "EUV禁运", "先进制程受限", "国产替代缓慢"],
                "expected_duration": "突破需要3-5年"
            },
            "芯片需求爆发": {
                "root_cause": "AI芯片需求爆发 + 传统芯片需求复苏",
                "causal_chain": ["AI算力需求", "芯片订单激增", "产能供不应求"],
                "expected_duration": "至少持续到2025年"
            },
            "技术瓶颈突破": {
                "root_cause": "新架构（Chiplet/CPO）带来效率提升 + 国产技术路线突破",
                "causal_chain": ["技术研发", "量产验证", "良率提升", "规模量产"],
                "expected_duration": "技术突破后持续受益"
            },
        }

        if problem_type in causal_knowledge:
            knowledge = causal_knowledge[problem_type]
            return FirstPrinciplesInsight(
                insight_type="causal",
                content=f"【{problem_type}】根因: {knowledge['root_cause']}",
                level=ThoughtLevel.FIRST_PRINCIPLES,
                confidence=0.80,
                evidence=[
                    f"问题类型: {problem_type}",
                    f"严重程度: {severity}",
                    f"因果链: {' → '.join(knowledge['causal_chain'])}",
                    f"预计持续: {knowledge['expected_duration']}"
                ]
            )

        return None

    def _analyze_opportunity_validity(
        self,
        opportunity_type: str,
        beneficiaries: List[str],
        resolvers: List[Dict[str, Any]]
    ) -> Optional[FirstPrinciplesInsight]:
        """分析机会的有效性"""
        resolver_names = [r.get("name", "") for r in resolvers]
        covered = [b for b in beneficiaries if any(b in r for r in resolver_names)]

        if len(covered) / len(beneficiaries) < 0.5:
            return FirstPrinciplesInsight(
                insight_type="caution",
                content=f"【{opportunity_type}】机会存在，但解决者覆盖不足",
                level=ThoughtLevel.CAUSAL,
                confidence=0.65,
                evidence=[
                    f"机会类型: {opportunity_type}",
                    f"预期受益者: {beneficiaries}",
                    f"已知解决者: {resolver_names}",
                    f"覆盖度: {len(covered)}/{len(beneficiaries)}"
                ]
            )

        return None

    def _analyze_resolver_progress(
        self,
        resolver_name: str,
        progress: str,
        opportunity: str,
        price_change: float
    ) -> Optional[FirstPrinciplesInsight]:
        """分析解决者的进度"""
        progress_levels = {
            "量产级": 0.9,
            "扩产中": 0.7,
            "测试级": 0.5,
            "研发级": 0.3,
            "未知": 0.2
        }

        level = progress_levels.get(progress, 0.3)

        if "量产" in progress or "扩产" in progress:
            if price_change < -5:
                return FirstPrinciplesInsight(
                    insight_type="opportunity",
                    content=f"{resolver_name}已进入{progress}，但股价下跌，可能是错杀",
                    level=ThoughtLevel.FIRST_PRINCIPLES,
                    confidence=0.75,
                    evidence=[
                        f"解决者: {resolver_name}",
                        f"进度: {progress}",
                        f"机会: {opportunity}",
                        f"股价变动: {price_change:.1f}%"
                    ]
                )

        return None

    def _detect_contradictions(self, market_data: Dict[str, Any]) -> List[FirstPrinciplesInsight]:
        """检测矛盾"""
        insights = []

        price_change = market_data.get("price_change", 0)
        volume_change = market_data.get("volume_change", 0)

        if price_change > 2 and volume_change < -20:
            insights.append(FirstPrinciplesInsight(
                insight_type="contradiction",
                content="价涨量跌 — 虚假上涨信号，可能是主力出货",
                level=ThoughtLevel.FIRST_PRINCIPLES,
                confidence=0.85,
                evidence=["价格上涨+成交量萎缩"]
            ))
        elif price_change > 2 and volume_change > 50:
            insights.append(FirstPrinciplesInsight(
                insight_type="opportunity",
                content="价涨量增 — 健康上涨，资金持续流入",
                level=ThoughtLevel.FIRST_PRINCIPLES,
                confidence=0.8,
                evidence=["价格上涨+成交量放大"]
            ))

        if price_change < -2 and volume_change > 50:
            insights.append(FirstPrinciplesInsight(
                insight_type="opportunity",
                content="价跌量增 — 恐慌抛售，可能是抄底机会",
                level=ThoughtLevel.FIRST_PRINCIPLES,
                confidence=0.75,
                evidence=["价格下跌+恐慌放量"]
            ))
        elif price_change < -2 and volume_change < -30:
            insights.append(FirstPrinciplesInsight(
                insight_type="risk",
                content="价跌量缩 — 无量下跌，可能还有下探",
                level=ThoughtLevel.CAUSAL,
                confidence=0.65,
                evidence=["价格下跌+缩量"]
            ))

        return insights

    def _apply_reasoning(self, market_data: Dict[str, Any]) -> List[FirstPrinciplesInsight]:
        """应用推理引擎"""
        insights = []

        premises = []
        if market_data.get("price_change", 0) > 1:
            premises.append("价格上涨")
        if market_data.get("volume_change", 0) > 30:
            premises.append("成交量放大")
        if market_data.get("volatility", 1) > 1.5:
            premises.append("波动加剧")

        deductive_results = self.reasoning_engine.deductive_reasoning(premises)
        for result in deductive_results[:2]:
            insights.append(FirstPrinciplesInsight(
                insight_type="reasoning",
                content=f"[演绎] {result.conclusion}",
                level=ThoughtLevel.CAUSAL,
                confidence=result.confidence,
                evidence=result.intermediate_steps
            ))

        if len(premises) >= 2:
            inductive_results = self.reasoning_engine.inductive_reasoning(premises)
            for result in inductive_results[:2]:
                insights.append(FirstPrinciplesInsight(
                    insight_type="reasoning",
                    content=f"[归纳] {result.conclusion}",
                    level=ThoughtLevel.PATTERN,
                    confidence=result.confidence,
                    evidence=result.intermediate_steps
                ))

        return insights

    def _analyze_temporal_patterns(self, market_data: Dict[str, Any]) -> List[FirstPrinciplesInsight]:
        """分析时序模式"""
        insights = []

        if len(self._market_states) >= 3:
            recent = list(self._market_states)[-3:]

            if len(recent) == 3:
                changes = [s.get("price_change", 0) for s in recent]

                if all(c > 0 for c in changes):
                    insights.append(FirstPrinciplesInsight(
                        insight_type="pattern",
                        content="连续3日上涨，警惕回调风险",
                        level=ThoughtLevel.PATTERN,
                        confidence=0.7,
                        evidence=[f"近3日涨幅: {', '.join(f'{c:.1f}%' for c in changes)}"]
                    ))
                elif all(c < 0 for c in changes):
                    insights.append(FirstPrinciplesInsight(
                        insight_type="pattern",
                        content="连续3日下跌，留意反弹机会",
                        level=ThoughtLevel.PATTERN,
                        confidence=0.7,
                        evidence=[f"近3日跌幅: {', '.join(f'{c:.1f}%' for c in changes)}"]
                    ))

        temporal = self.causality_tracker._causality_graph.analyze_temporal_relationships()
        if temporal["leading_indicators"]:
            indicators = [f"{l['cause']}→{l['effect']}" for l in temporal["leading_indicators"][:2]]
            insights.append(FirstPrinciplesInsight(
                insight_type="opportunity",
                content=f"领先指标发现: {', '.join(indicators)}",
                level=ThoughtLevel.CAUSAL,
                confidence=0.65,
                evidence=["时序分析"]
            ))

        return insights

    def get_insights_summary(self) -> Dict[str, Any]:
        """获取洞察摘要"""
        return {
            "total_insights": len(self._insights),
            "by_type": {
                "cause": len([i for i in self._insights if i.insight_type == "cause"]),
                "contradiction": len([i for i in self._insights if i.insight_type == "contradiction"]),
                "opportunity": len([i for i in self._insights if i.insight_type == "opportunity"]),
                "risk": len([i for i in self._insights if i.insight_type == "risk"]),
                "reasoning": len([i for i in self._insights if i.insight_type == "reasoning"]),
                "pattern": len([i for i in self._insights if i.insight_type == "pattern"]),
            },
            "by_level": {
                "surface": len([i for i in self._insights if i.level == ThoughtLevel.SURFACE]),
                "pattern": len([i for i in self._insights if i.level == ThoughtLevel.PATTERN]),
                "causal": len([i for i in self._insights if i.level == ThoughtLevel.CAUSAL]),
                "first_principles": len([i for i in self._insights if i.level == ThoughtLevel.FIRST_PRINCIPLES]),
            },
            "causality": self.causality_tracker.get_causality_summary(),
            "contradictions": self.contradiction_detector.get_contradiction_summary()
        }

    def load_narratives_for_analysis(self) -> List[str]:
        """
        加载叙事库并返回叙事列表

        用于外部（如 Center.py）调用时传入 analyze() 方法
        """
        import json
        import os

        narratives = []
        if os.path.exists(self.NARRATIVES_FILE):
            try:
                with open(self.NARRATIVES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for n in data.get("narratives", []):
                    narratives.append(n.get("name", ""))
            except Exception as e:
                log.warning(f"[FirstPrinciples] 加载叙事列表失败: {e}")

        return [n for n in narratives if n and n != "暂无明确叙事"]

    def force_reload_knowledge(self):
        """强制重新加载知识库"""
        self._knowledge_loaded = False
        self._load_knowledge_from_file()


class FirstPrinciplesMind:
    """
    第一性原理思维引擎（妙观察智核心）

    整合所有增强能力：
    - MarketCausalityGraph: 因果图谱
    - CausalityTracker: 因果追踪
    - ContradictionDetector: 矛盾检测
    - ReasoningEngine: 推理引擎
    - CognitiveIntegrator: 认知整合
    """

    def __init__(self):
        self.first_principles_analyzer = FirstPrinciplesAnalyzer()
        self._thinking_depth: ThoughtLevel = ThoughtLevel.SURFACE
        self._awareness_level: float = 0.55  # 当前觉醒度

    def get_narratives(self) -> List[str]:
        """获取当前叙事列表（用于传入think方法）"""
        return self.first_principles_analyzer.load_narratives_for_analysis()

    def think(
        self,
        market_data: Dict[str, Any],
        narratives: Optional[List[str]] = None,
        signals: Optional[List[Dict[str, Any]]] = None,
        liquidity_data: Optional[Dict] = None,
        topic_signals: Optional[List[Dict[str, Any]]] = None,
        news_sentiment: Optional[str] = None,
        ai_compute_trend: Optional[Dict] = None,
        ai_positions: Optional[Dict] = None,
        problem_opportunity: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        深度思考

        Args:
            market_data: 市场数据
            narratives: 当前叙事列表
            signals: 信号列表
            liquidity_data: 流动性数据
            topic_signals: 新闻话题信号列表
            news_sentiment: 新闻情绪 (bullish/neutral/fearful)
            ai_compute_trend: AI算力趋势信号
            ai_positions: AI相关持仓
            problem_opportunity: 问题-机会-解决者分析结果

        Returns:
            思考结果
        """
        insights = self.first_principles_analyzer.analyze(
            market_data,
            narratives,
            signals,
            liquidity_data,
            topic_signals,
            news_sentiment,
            ai_compute_trend,
            ai_positions,
            problem_opportunity
        )

        self._update_thinking_depth(insights)
        self._update_awareness_level(insights)

        return {
            "insights": insights,
            "depth": self._thinking_depth.value,
            "awareness_level": self._awareness_level,
            "summary": self.first_principles_analyzer.get_insights_summary(),
            "key_insight": self._get_key_insight(insights),
            "causality_graph_stats": self.first_principles_analyzer.causality_tracker._causality_graph.get_graph_stats(),
            "contradiction_summary": self.first_principles_analyzer.contradiction_detector.get_contradiction_summary()
        }

    def _update_thinking_depth(self, insights: List[FirstPrinciplesInsight]):
        """更新思考深度"""
        if not insights:
            return

        level_order = {
            ThoughtLevel.SURFACE: 0,
            ThoughtLevel.PATTERN: 1,
            ThoughtLevel.CAUSAL: 2,
            ThoughtLevel.FIRST_PRINCIPLES: 3,
            ThoughtLevel.META: 4
        }

        max_level = max(insights, key=lambda i: level_order.get(i.level, 0)).level

        if level_order[max_level] > level_order[self._thinking_depth]:
            self._thinking_depth = max_level

    def _update_awareness_level(self, insights: List[FirstPrinciplesInsight]):
        """更新觉醒度"""
        if not insights:
            return

        level_order = {
            ThoughtLevel.SURFACE: 0.1,
            ThoughtLevel.PATTERN: 0.3,
            ThoughtLevel.CAUSAL: 0.5,
            ThoughtLevel.FIRST_PRINCIPLES: 0.7,
            ThoughtLevel.META: 0.9
        }

        fp_count = sum(1 for i in insights if i.level == ThoughtLevel.FIRST_PRINCIPLES)
        causal_count = sum(1 for i in insights if i.level == ThoughtLevel.CAUSAL)

        target_level = 0.55

        if fp_count >= 2:
            target_level = 0.75
        elif causal_count >= 3:
            target_level = 0.65
        elif causal_count >= 1:
            target_level = 0.60

        self._awareness_level = self._awareness_level * 0.7 + target_level * 0.3

    def _get_key_insight(self, insights: List[FirstPrinciplesInsight]) -> Optional[str]:
        """获取关键洞察"""
        if not insights:
            return None

        actionable = [i for i in insights if i.actionable]
        if not actionable:
            return None

        level_weight = {
            ThoughtLevel.FIRST_PRINCIPLES: 1.0,
            ThoughtLevel.CAUSAL: 0.7,
            ThoughtLevel.PATTERN: 0.5,
            ThoughtLevel.SURFACE: 0.3
        }

        scored = [(i, i.confidence * level_weight.get(i.level, 0.5)) for i in actionable]
        best = max(scored, key=lambda x: x[1])
        return best[0].content

    def get_depth(self) -> str:
        """获取当前思考深度"""
        return self._thinking_depth.value

    def get_awareness_level(self) -> float:
        """获取当前觉醒度"""
        return self._awareness_level

    def get_causality_graph(self) -> MarketCausalityGraph:
        """获取因果图谱"""
        return self.first_principles_analyzer.causality_tracker._causality_graph
