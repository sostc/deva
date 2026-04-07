"""
ResonanceAnalyzer - 三焦点共振分析器

三焦点模型：
1. 市场焦点：行情热点（舆情 + 资金流向）
2. 舆情焦点：外部世界变化（新闻 + 市场变动）
3. 内部焦点：我们自身变化（交易 + 痛点 + 知识）

共振分析检测这三个方向的注意力是否一致

设计原则：
- 关键词对齐：提取三个方向的关键词，看是否有重叠
- 方向判断：判断三者方向是否一致
- 信号强度：计算共振程度（0-1）
"""

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

RESONANCE_TABLE = "naja_resonance_state"


class ResonanceAnalyzer:
    """
    共振分析器

    分析三个焦点之间的共振关系：
    - 市场焦点 vs 舆情焦点
    - 市场焦点 vs 内部焦点
    - 舆情焦点 vs 内部焦点
    """

    def __init__(self):
        self._market_keywords: List[str] = []
        self._news_keywords: List[str] = []
        self._internal_keywords: List[str] = []

    def analyze(
        self,
        market_focus: Dict[str, Any],
        news_focus: Dict[str, Any],
        internal_changes: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        执行共振分析

        Args:
            market_focus: 市场焦点数据
            news_focus: 舆情焦点数据
            internal_changes: 内部变化数据

        Returns:
            共振分析结果
        """
        self._extract_keywords(market_focus, news_focus, internal_changes)

        resonances = self._calculate_resonances()
        overall_score = self._calculate_overall_score(resonances)
        conclusion = self._generate_conclusion(resonances, overall_score)

        return {
            "status": "ok",
            "market_keywords": self._market_keywords,
            "news_keywords": self._news_keywords,
            "internal_keywords": self._internal_keywords,
            "resonances": resonances,
            "overall_score": overall_score,
            "conclusion": conclusion,
        }

    def _extract_keywords(
        self,
        market_focus: Dict[str, Any],
        news_focus: Dict[str, Any],
        internal_changes: Dict[str, Any],
    ):
        """提取三个方向的关键词"""
        self._market_keywords = []
        self._news_keywords = []
        self._internal_keywords = []

        if market_focus.get("status") == "ok":
            narratives = market_focus.get("narratives", {})
            self._market_keywords = list(narratives.keys())[:5]

        if news_focus.get("status") == "ok":
            macro_news = news_focus.get("macro_news", [])
            industry_news = news_focus.get("industry_news", [])

            for news in macro_news[:3]:
                title = news.get("title", "")
                self._news_keywords.append(self._extract_key_terms(title))

            for news in industry_news[:3]:
                title = news.get("title", "")
                self._news_keywords.append(self._extract_key_terms(title))

            self._news_keywords = [k for k in self._news_keywords if k][:5]

        if internal_changes.get("status") == "ok":
            trade_changes = internal_changes.get("trade_changes", [])
            for trade in trade_changes[:3]:
                symbol = trade.get("symbol", "")
                if symbol:
                    self._internal_keywords.append(symbol)

            pain_points = internal_changes.get("pain_point_changes", [])
            for pp in pain_points[:2]:
                self._internal_keywords.append(pp.get("id", ""))

            knowledge_changes = internal_changes.get("knowledge_changes", [])
            for kc in knowledge_changes[:2]:
                items = kc.get("items", [])
                for item in items[:2]:
                    cause = item.get("knowledge", item.get("cause", ""))
                    if cause:
                        self._internal_keywords.append(cause[:20])

    def _extract_key_terms(self, text: str) -> str:
        """从文本中提取关键词"""
        import re

        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        words = text.split()

        stop_words = {"的", "了", "是", "在", "和", "与", "或", "等", "对", "为", "被", "有", "这", "那", "将", "把", "从", "向", "到"}
        meaningful_words = [w for w in words if len(w) > 1 and w not in stop_words]

        return " ".join(meaningful_words[:3]) if meaningful_words else text[:20]

    def _calculate_resonances(self) -> Dict[str, Any]:
        """计算三个方向两两之间的共振"""
        resonances = {}

        resonances["market_news"] = self._check_resonance(
            self._market_keywords,
            self._news_keywords,
            "市场焦点",
            "舆情焦点",
        )

        resonances["market_internal"] = self._check_resonance(
            self._market_keywords,
            self._internal_keywords,
            "市场焦点",
            "内部焦点",
        )

        resonances["news_internal"] = self._check_resonance(
            self._news_keywords,
            self._internal_keywords,
            "舆情焦点",
            "内部焦点",
        )

        return resonances

    def _check_resonance(
        self,
        keywords1: List[str],
        keywords2: List[str],
        name1: str,
        name2: str,
    ) -> Dict[str, Any]:
        """检查两个方向的共振"""
        if not keywords1 or not keywords2:
            return {
                "resonance": False,
                "score": 0.0,
                "name1": name1,
                "name2": name2,
                "common": [],
                "description": "数据不足，无法判断",
            }

        common = self._find_common_keywords(keywords1, keywords2)
        score = min(1.0, len(common) / 2)

        resonance = score >= 0.3

        description = ""
        if resonance:
            description = f"{name1} ✓ 共振 {name2}"
            if common:
                description += f"（共同关注：{', '.join(common[:3])}）"
        else:
            description = f"{name1} 与 {name2} 未共振"

        return {
            "resonance": resonance,
            "score": score,
            "name1": name1,
            "name2": name2,
            "common": common,
            "description": description,
        }

    def _find_common_keywords(self, keywords1: List[str], keywords2: List[str]) -> List[str]:
        """找出两组关键词的共同词"""
        common = []

        kw1_normalized = [self._normalize(k) for k in keywords1]
        kw2_normalized = [self._normalize(k) for k in keywords2]

        for k1, k1_n in zip(keywords1, kw1_normalized):
            for k2, k2_n in zip(keywords2, kw2_normalized):
                if k1_n and k2_n and (k1_n in k2_n or k2_n in k1_n):
                    common.append(k1 if len(k1) < len(k2) else k2)
                    break

        return list(set(common))

    def _normalize(self, text: str) -> str:
        """标准化关键词"""
        import re
        text = text.lower()
        text = re.sub(r'[^\w\u4e00-\u9fff]', '', text)
        return text

    def _calculate_overall_score(self, resonances: Dict[str, Any]) -> float:
        """计算整体共振得分"""
        scores = []

        for key, res in resonances.items():
            if res.get("resonance"):
                scores.append(res.get("score", 0))

        if not scores:
            return 0.0

        return round(sum(scores) / len(scores), 2)

    def _generate_conclusion(self, resonances: Dict[str, Any], overall_score: float) -> str:
        """生成共振结论"""
        resonance_count = sum(1 for r in resonances.values() if r.get("resonance"))

        if resonance_count == 3:
            return "三重共振 → 大机会/大风险，积极操作"
        elif resonance_count == 2:
            return "双重共振 → 机会存在，顺势而为"
        elif resonance_count == 1:
            return "单点共振 → 谨慎观望"
        else:
            return "无共振 → 保持中性，等待信号"


def get_resonance_analyzer() -> ResonanceAnalyzer:
    """获取共振分析器单例"""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = ResonanceAnalyzer()
    return _analyzer_instance


_analyzer_instance = None