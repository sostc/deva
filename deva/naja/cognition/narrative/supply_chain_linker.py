"""NarrativeSupplyChainLinker - 叙事主题与供应链知识图谱联动

核心功能：
1. 叙事主题 ↔ 供应链公司/产品的双向映射
2. 当识别到叙事主题变化时，自动触发供应链影响分析
3. 当供应链出现风险事件时，自动调整叙事关注度

使用场景：
- 新闻/社交媒体提到 "英伟达" → 自动关联 AI 叙事 + 供应链上下游
- 供应链中出现风险（如 "中芯国际受限"）→ 自动增强 "芯片" 叙事关注度
- 叙事主题热度变化 → 驱动供应链动态权重调整
"""

from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum
import time
import logging

from deva.naja.bandit.supply_chain_graph import (
    get_supply_chain_graph,
    SupplyChainKnowledgeGraph,
    GraphNode,
    NodeType,
    SupplyChainRisk,
    SupplyChainRiskReport,
)

log = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SupplyChainImpact:
    """供应链影响评估"""
    stock_code: str
    stock_name: str
    impact_type: str
    risk_level: RiskLevel
    description: str
    upstream_risks: List[str] = field(default_factory=list)
    downstream_risks: List[str] = field(default_factory=list)
    related_narratives: List[str] = field(default_factory=list)


@dataclass
class NarrativeSupplyChainEvent:
    """叙事-供应链联动事件"""
    event_id: str
    timestamp: float
    event_type: str
    source: str
    stock_codes: List[str]
    narratives: List[str]
    risk_level: RiskLevel
    description: str
    supply_chain_impacts: List[SupplyChainImpact] = field(default_factory=list)


class NarrativeSupplyChainLinker:
    """
    叙事主题与供应链知识图谱联动器

    核心功能：
    1. 叙事主题 → 供应链公司映射
    2. 供应链风险 → 叙事关注度调整
    3. 新闻事件 → 供应链影响分析
    """

    def __init__(self):
        self._graph = get_supply_chain_graph()
        self._narrative_stock_link: Dict[str, List[str]] = {}
        self._stock_narrative_link: Dict[str, List[str]] = {}
        self._risk_event_history: List[NarrativeSupplyChainEvent] = []
        self._narrative_importance: Dict[str, float] = defaultdict(lambda: 1.0)
        self._narrative_last_boost: Dict[str, float] = {}
        self._last_update: float = time.time()
        self._decay_half_life_hours: float = 24.0
        self._decay_factor: float = 0.95
        self._last_summary_time: float = time.time()
        self._summary_interval_seconds: float = 300.0

        self._init_narrative_stock_mapping()

        # 🚀 事件订阅已迁移到 EventSubscriberRegistrar（应用层）
        # 不再在 __init__ 中自动订阅

        self._ewm_alpha: float = 0.15

    def subscribe_text_events(self, event_bus):
        """由 EventSubscriberRegistrar 调用的事件订阅方法"""
        event_bus.subscribe(
            'TextFocusedEvent',
            self._on_text_focused,
            priority=5
        )

    def _on_text_focused(self, event):
        """处理 TextFocusedEvent"""
        try:
            narratives = list(event.keywords or [])
            narratives.extend(event.topics or [])
            if getattr(event, "narrative_tags", None):
                narratives.extend(event.narrative_tags)

            self._analyze_supply_chain_impact(
                text=event.summary or event.title or event.text,
                narratives=narratives,
                importance=event.importance_score,
            )
        except Exception as e:
            log.debug(f"[SupplyChainLinker] 处理 TextFocusedEvent 失败: {e}")

    def _analyze_supply_chain_impact(self, text: str, narratives: List[str], importance: float) -> None:
        """分析文本对供应链的影响"""
        if not text or not narratives or importance < 0.3:
            return

        impacts = self.analyze_news_impact(text, narratives)

        if impacts:
            for narrative in narratives:
                self.on_narrative_boost(narrative, boost_factor=1.0 + importance * 0.3)

            self._publish_supply_chain_event(None, impacts)

        self._last_update = time.time()

    def _publish_supply_chain_event(self, event, impacts: List):
        """
        🚀 发布供应链影响事件到 NajaEventBus
        """
        try:
            from deva.naja.events import (
                get_event_bus,
                CognitiveEventType,
            )

            bus = get_event_bus()

            # 提取相关股票
            stock_codes = [impact.stock_code for impact in impacts if hasattr(impact, 'stock_code')]

            # 评估风险等级
            risk_level = "LOW"
            high_risk_count = sum(1 for impact in impacts if hasattr(impact, 'risk_level') and impact.risk_level in ['high', 'medium'])
            if high_risk_count >= 2:
                risk_level = "HIGH"
            elif high_risk_count >= 1:
                risk_level = "MEDIUM"

            from deva.naja.events import SupplyChainRiskEvent
            severity = 0.5
            if risk_level == "HIGH":
                severity = 0.8
            elif risk_level == "MEDIUM":
                severity = 0.6

            event = SupplyChainRiskEvent(
                source="SupplyChainLinker",
                risk_type="narrative_supply_link",
                impacted_symbols=stock_codes,
                severity=severity,
                expected_impact=f"叙事供应链联动事件，影响 {len(stock_codes)} 只股票",
            )
            bus.publish(event)
        except ImportError:
            pass
        except Exception as e:
            log.debug(f"SupplyChainLinker 发布认知事件失败: {e}")

    def _init_narrative_stock_mapping(self):
        """初始化叙事主题到供应链公司的映射"""

        self._narrative_stock_link = {
            "AI": [
                "nvda", "amd", "688041", "300474", "688008",
                "msft", "googl", "amzn", "smci"
            ],
            "芯片": [
                "nvda", "amd", "intc", "tsm", "asml", "mu",
                "688981", "002371", "688012", "002185", "600584",
                "603986", "002049", "688008", "688099"
            ],
            "AI芯片": [
                "nvda", "amd", "688041", "300474",
                "tsm", "688981"
            ],
            "半导体": [
                "nvda", "amd", "intc", "tsm", "asml", "mu", "skx",
                "688981", "002371", "688012", "002185", "600584",
                "688396", "600745"
            ],
            "GPU": ["nvda", "amd", "300474"],
            "HBM": ["mu", "skx", "688008"],
            "光刻机": ["asml", "002371", "688012"],
            "晶圆代工": ["tsm", "688981"],
            "封装测试": ["002185", "600584", "002156"],
            "AI服务器": ["smci", "msft", "googl", "amzn", "crwv"],
            "AI应用": ["msft", "googl", "amzn", "688111", "002230"],
            "AI基础设施": ["smci", "msft", "googl", "amzn", "688111"],
            "芯片设计": ["nvda", "amd", "688041", "300474", "688008", "603986"],
            "芯片设备": ["asml", "002371", "688012"],
            "中美关系": [
                "688981", "688041", "002371", "688012",
                "nvda", "amd", "tsm", "asml"
            ],
            "出口管制": [
                "688981", "688041", "002371", "688012",
                "tsm", "asml"
            ],
            "国产替代": [
                "688981", "688041", "002371", "688012",
                "002185", "600584"
            ],
            "大模型": [
                "nvda", "amd", "688041",
                "msft", "googl", "amzn"
            ],
            "算力": [
                "nvda", "amd", "smci", "688041",
                "tsm", "688981"
            ],
        }

        for narrative, stocks in self._narrative_stock_link.items():
            for stock in stocks:
                if stock not in self._stock_narrative_link:
                    self._stock_narrative_link[stock] = []
                self._stock_narrative_link[stock].append(narrative)

        log.info(f"[NarrativeSupplyChainLinker] 初始化完成，映射了 {len(self._narrative_stock_link)} 个叙事主题")

    def get_stocks_by_narrative(self, narrative: str) -> List[str]:
        """获取叙事主题关联的股票列表"""
        return self._narrative_stock_link.get(narrative, [])

    def get_narratives_by_stock(self, stock_code: str) -> List[str]:
        """获取股票关联的叙事主题列表"""
        return self._stock_narrative_link.get(stock_code, [])

    def get_narratives_by_stock_code(self, stock_code: str) -> List[str]:
        """通过股票代码获取关联叙事（兼容性别名）"""
        return self.get_narratives_by_stock(stock_code.lower())

    def analyze_news_impact(self, news_text: str, news_narratives: List[str]) -> List[SupplyChainImpact]:
        """
        分析新闻对供应链的影响

        Args:
            news_text: 新闻文本
            news_narratives: 新闻识别的叙事主题列表

        Returns:
            供应链影响列表
        """
        impacts = []
        related_stocks = set()

        for narrative in news_narratives:
            stocks = self.get_stocks_by_narrative(narrative)
            related_stocks.update(stocks)

        for stock_code in related_stocks:
            node = self._graph.get_stock_node(stock_code)
            if not node:
                continue

            risk_report = self._graph.analyze_supply_chain_risk(stock_code)
            if not risk_report:
                continue

            risk_level = RiskLevel.LOW
            if risk_report.overall_risk_level == "HIGH":
                risk_level = RiskLevel.HIGH
            elif risk_report.overall_risk_level == "MEDIUM":
                risk_level = RiskLevel.MEDIUM

            impact = SupplyChainImpact(
                stock_code=stock_code,
                stock_name=node.name,
                impact_type="risk_analysis",
                risk_level=risk_level,
                description=f"基于叙事 [{', '.join(news_narratives)}] 的供应链影响分析",
                upstream_risks=[r.node_name for r in risk_report.upstream_risks],
                downstream_risks=[r.node_name for r in risk_report.downstream_risks],
                related_narratives=news_narratives,
            )
            impacts.append(impact)

        return impacts

    def on_stock_risk_event(self, stock_code: str, event_description: str) -> NarrativeSupplyChainEvent:
        """
        处理股票风险事件，触发叙事-供应链联动

        Args:
            stock_code: 出问题的股票代码
            event_description: 事件描述

        Returns:
            联动事件
        """
        narratives = self.get_narratives_by_stock(stock_code)
        if not narratives:
            narratives = ["未知叙事"]

        risk_report = self._graph.analyze_supply_chain_risk(stock_code)
        risk_level = RiskLevel.MEDIUM
        if risk_report:
            if risk_report.overall_risk_level == "HIGH":
                risk_level = RiskLevel.HIGH
            elif risk_report.overall_risk_level == "CRITICAL":
                risk_level = RiskLevel.CRITICAL

        supply_chain_impacts = []
        if risk_report:
            for risk in risk_report.upstream_risks + risk_report.bottleneck_risks:
                upstream_stock = self._graph.get_stock_node(risk.node_id)
                if upstream_stock and upstream_stock.stock_code:
                    supply_chain_impacts.append(SupplyChainImpact(
                        stock_code=upstream_stock.stock_code,
                        stock_name=upstream_stock.name,
                        impact_type="upstream_propagation",
                        risk_level=RiskLevel.MEDIUM,
                        description=f"上游风险传导: {risk.description}",
                        upstream_risks=[],
                        downstream_risks=[],
                        related_narratives=narratives,
                    ))

        event = NarrativeSupplyChainEvent(
            event_id=f"risk_{stock_code}_{int(time.time())}",
            timestamp=time.time(),
            event_type="stock_risk",
            source="manas",
            stock_codes=[stock_code],
            narratives=narratives,
            risk_level=risk_level,
            description=event_description,
            supply_chain_impacts=supply_chain_impacts,
        )

        self._risk_event_history.append(event)

        self._update_narrative_importance(stock_code, narratives, risk_level)

        return event

    def on_narrative_boost(self, narrative: str, boost_factor: float = 1.5):
        """
        当叙事主题热度提升时，更新供应链关联股票的权重

        Args:
            narrative: 叙事主题
            boost_factor: 提升因子
        """
        if narrative not in self._narrative_importance:
            self._narrative_importance[narrative] = 1.0

        alpha = self._ewm_alpha
        self._narrative_importance[narrative] = (
            alpha * boost_factor + (1 - alpha) * self._narrative_importance[narrative]
        )
        self._narrative_last_boost[narrative] = time.time()
        self._last_update = time.time()

        log.debug(f"[NarrativeSupplyChainLinker] 叙事 [{narrative}] 重要性提升至 {self._narrative_importance[narrative]:.2f}")

        if self._should_log_summary():
            self._log_narrative_summary()

    def _should_log_summary(self) -> bool:
        return time.time() - self._last_summary_time >= self._summary_interval_seconds

    def _log_narrative_summary(self) -> None:
        self._apply_decay_all()
        hot = self.get_hot_narratives(10)
        lines = ["[NarrativeSupplyChainLinker] 叙事重要性汇总 =========="]
        for narrative, score in hot:
            lines.append(f"  [{narrative}] {score:.2f}")
        lines.append("=" * 50)
        log.info("\n".join(lines))
        self._last_summary_time = time.time()

    def _update_narrative_importance(self, stock_code: str, narratives: List[str], risk_level: RiskLevel):
        """根据风险事件更新叙事重要性"""
        risk_multiplier = {
            RiskLevel.LOW: 1.2,
            RiskLevel.MEDIUM: 1.5,
            RiskLevel.HIGH: 2.0,
            RiskLevel.CRITICAL: 3.0,
        }

        multiplier = risk_multiplier.get(risk_level, 1.0)

        for narrative in narratives:
            alpha = self._ewm_alpha * 0.5
            self._narrative_importance[narrative] = (
                alpha * multiplier + (1 - alpha) * self._narrative_importance[narrative]
            )
            self._narrative_last_boost[narrative] = time.time()

        self._last_update = time.time()

    def _apply_decay(self, narrative: str) -> float:
        """对单个叙事应用自然衰减（EWM模式下自然发生）"""
        if narrative not in self._narrative_importance:
            return 1.0

        hours_elapsed = 0.0
        if narrative in self._narrative_last_boost:
            hours_elapsed = (time.time() - self._narrative_last_boost[narrative]) / 3600.0

        if hours_elapsed <= 0:
            return self._narrative_importance[narrative]

        decay_rate = 0.02
        hours_decay = 1.0 - decay_rate * hours_elapsed
        hours_decay = max(0.5, hours_decay)

        base_value = 1.0
        current_value = self._narrative_importance[narrative]
        decayed_value = base_value + (current_value - base_value) * hours_decay
        decayed_value = max(base_value, decayed_value)

        self._narrative_importance[narrative] = decayed_value
        return decayed_value

    def _apply_decay_all(self) -> None:
        """对所有叙事应用时间衰减"""
        current_time = time.time()
        narratives_to_decay = list(self._narrative_last_boost.keys())

        for narrative in narratives_to_decay:
            self._apply_decay(narrative)

    def get_related_stocks_with_weight(self, narrative: str) -> List[Tuple[str, float]]:
        """
        获取叙事关联的股票及权重（考虑重要性）

        Args:
            narrative: 叙事主题

        Returns:
            [(stock_code, weight), ...]
        """
        self._apply_decay(narrative)

        stocks = self.get_stocks_by_narrative(narrative)
        if not stocks:
            return []

        importance = self._narrative_importance.get(narrative, 1.0)

        weighted_stocks = []
        for stock in stocks:
            node = self._graph.get_stock_node(stock)
            if node:
                risk_report = self._graph.analyze_supply_chain_risk(stock)
                risk_factor = 1.0
                if risk_report:
                    if risk_report.overall_risk_level == "HIGH":
                        risk_factor = 0.8
                    elif risk_report.overall_risk_level == "MEDIUM":
                        risk_factor = 0.9

                weight = importance * risk_factor
                weighted_stocks.append((stock, weight))

        weighted_stocks.sort(key=lambda x: x[1], reverse=True)
        return weighted_stocks

    def get_supply_chain_risk_report(self, stock_code: str) -> Optional[SupplyChainRiskReport]:
        """获取股票的供应链风险报告"""
        return self._graph.analyze_supply_chain_risk(stock_code)

    def get_hot_narratives(self, top_n: int = 5) -> List[Tuple[str, float]]:
        """获取当前最热的叙事主题"""
        self._apply_decay_all()

        sorted_narratives = sorted(
            self._narrative_importance.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_narratives[:top_n]

    def get_supply_chain_for_narrative(self, narrative: str) -> Dict:
        """
        获取叙事主题的完整供应链信息

        Args:
            narrative: 叙事主题

        Returns:
            供应链信息字典
        """
        self._apply_decay(narrative)

        stocks = self.get_stocks_by_narrative(narrative)
        if not stocks:
            return {"narrative": narrative, "stocks": [], "total_risk": "unknown"}

        total_upstream = set()
        total_downstream = set()
        high_risk_stocks = []

        for stock in stocks:
            node = self._graph.get_stock_node(stock)
            if not node:
                continue

            upstream = self._graph.get_upstream_companies(stock)
            downstream = self._graph.get_downstream_companies(stock)

            for up in upstream:
                if up.stock_code:
                    total_upstream.add(up.stock_code)

            for down in downstream:
                if down.stock_code:
                    total_downstream.add(down.stock_code)

            risk_report = self._graph.analyze_supply_chain_risk(stock)
            if risk_report and risk_report.overall_risk_level == "HIGH":
                high_risk_stocks.append(stock)

        return {
            "narrative": narrative,
            "importance": self._narrative_importance.get(narrative, 1.0),
            "core_stocks": stocks,
            "upstream_stocks": list(total_upstream),
            "downstream_stocks": list(total_downstream),
            "high_risk_stocks": high_risk_stocks,
            "total_risk": "HIGH" if high_risk_stocks else "MEDIUM" if total_upstream else "LOW",
        }

    def get_recent_events(self, limit: int = 10) -> List[NarrativeSupplyChainEvent]:
        """获取最近的风险事件"""
        return self._risk_event_history[-limit:]

    def get_supply_chain_summary(self) -> Dict:
        """获取供应链联动摘要"""
        return {
            "total_narratives": len(self._narrative_stock_link),
            "total_stocks_mapped": len(self._stock_narrative_link),
            "recent_events_count": len(self._risk_event_history),
            "hot_narratives": self.get_hot_narratives(5),
            "narrative_importance": dict(self._narrative_importance),
        }


_linker: Optional[NarrativeSupplyChainLinker] = None


def get_supply_chain_linker() -> NarrativeSupplyChainLinker:
    """获取叙事-供应链联动器（单例）"""
    global _linker
    if _linker is None:
        _linker = NarrativeSupplyChainLinker()
    return _linker
