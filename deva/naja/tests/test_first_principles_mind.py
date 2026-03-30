"""
FirstPrinciplesMind 单元测试
"""

import unittest
from deva.naja.cognition.first_principles_mind import (
    FirstPrinciplesMind,
    FirstPrinciplesAnalyzer,
    CausalityTracker,
    ContradictionDetector,
    ThoughtLevel,
    FirstPrinciplesInsight,
    CausalityChain,
    Contradiction,
)


class TestCausalityTracker(unittest.TestCase):
    """CausalityTracker 测试"""

    def setUp(self):
        self.tracker = CausalityTracker()

    def test_add_knowledge(self):
        """测试添加因果知识"""
        self.tracker.add_knowledge("降息", "股市上涨", 0.8)
        effects = self.tracker.predict_effects("降息")
        self.assertIn("股市上涨", effects)

    def test_find_root_cause(self):
        """测试寻找根本原因"""
        self.tracker.add_knowledge("降息", "流动性增加", 0.9)
        self.tracker.add_knowledge("流动性增加", "股市上涨", 0.8)

        root = self.tracker.find_root_cause("股市上涨")
        self.assertIsNotNone(root)
        self.assertIn("降息", root)

    def test_predict_effects(self):
        """测试预测效果"""
        self.tracker.add_knowledge("加息", "流动性减少", 0.8)
        self.tracker.add_knowledge("流动性减少", "股市下跌", 0.75)

        effects = self.tracker.predict_effects("加息")
        self.assertIn("流动性减少", effects)
        self.assertIn("股市下跌", effects)


class TestContradictionDetector(unittest.TestCase):
    """ContradictionDetector 测试"""

    def setUp(self):
        self.detector = ContradictionDetector()

    def test_add_narrative(self):
        """测试添加叙事"""
        self.detector.add_narrative("市场", "股市将上涨")
        self.assertEqual(len(self.detector._narratives), 1)

    def test_check_contradiction(self):
        """测试检查矛盾"""
        self.detector.add_narrative("市场A", "股市将大涨")
        self.detector.add_narrative("市场B", "股市将大跌")

        contradiction = self.detector.check_contradiction("市场A", "市场B")
        self.assertIsNotNone(contradiction)
        self.assertGreater(contradiction.severity, 0.5)

    def test_no_contradiction(self):
        """测试无矛盾"""
        self.detector.add_narrative("市场A", "股市稳定")
        self.detector.add_narrative("市场B", "成交量放大")

        contradiction = self.detector.check_contradiction("市场A", "市场B")
        self.assertIsNone(contradiction)


class TestFirstPrinciplesAnalyzer(unittest.TestCase):
    """FirstPrinciplesAnalyzer 测试"""

    def setUp(self):
        self.analyzer = FirstPrinciplesAnalyzer()

    def test_analyze_price_up_with_volume_up(self):
        """测试分析价涨量涨"""
        market_data = {
            "price_change": 4.0,
            "volume_change": 60.0,
            "volatility": 1.2
        }

        insights = self.analyzer.analyze(market_data)
        self.assertIsInstance(insights, list)

    def test_analyze_high_volatility(self):
        """测试分析高波动"""
        market_data = {
            "price_change": 0.5,
            "volume_change": 10.0,
            "volatility": 2.5
        }

        insights = self.analyzer.analyze(market_data)
        risk_insights = [i for i in insights if i.insight_type == "risk"]
        self.assertGreater(len(risk_insights), 0)

    def test_analyze_narratives(self):
        """测试分析叙事"""
        market_data = {"price_change": 0.5, "volume_change": 10.0, "volatility": 1.0}
        narratives = ["政策利好出现", "流动性充裕", "市场情绪乐观"]

        insights = self.analyzer.analyze(market_data, narratives=narratives)
        self.assertIsInstance(insights, list)

    def test_analyze_contradiction(self):
        """测试分析矛盾"""
        market_data = {
            "price_change": 3.0,
            "volume_change": -30.0,
            "volatility": 1.5
        }

        insights = self.analyzer.analyze(market_data)
        contradiction_insights = [i for i in insights if i.insight_type == "contradiction"]
        self.assertGreater(len(contradiction_insights), 0)

    def test_analyze_signals(self):
        """测试分析信号"""
        market_data = {"price_change": 0.5, "volume_change": 10.0, "volatility": 1.0}
        signals = [
            {"action": "buy", "symbol": "AAPL"},
            {"action": "buy", "symbol": "GOOGL"},
            {"action": "buy", "symbol": "MSFT"},
            {"action": "sell", "symbol": "TSLA"},
        ]

        insights = self.analyzer.analyze(market_data, signals=signals)
        self.assertIsInstance(insights, list)


class TestFirstPrinciplesMind(unittest.TestCase):
    """FirstPrinciplesMind 测试"""

    def setUp(self):
        self.mind = FirstPrinciplesMind()

    def test_think_basic(self):
        """测试基本思考"""
        market_data = {
            "price_change": 3.0,
            "volume_change": 50.0,
            "volatility": 1.5
        }

        result = self.mind.think(market_data)

        self.assertIn("insights", result)
        self.assertIn("depth", result)
        self.assertIn("summary", result)
        self.assertIsInstance(result["insights"], list)

    def test_think_with_narratives(self):
        """测试带叙事的思考"""
        market_data = {
            "price_change": 1.0,
            "volume_change": 20.0,
            "volatility": 1.0
        }
        narratives = ["市场情绪乐观", "资金面充裕"]

        result = self.mind.think(market_data, narratives=narratives)
        self.assertIsInstance(result["insights"], list)

    def test_think_with_signals(self):
        """测试带信号的思考"""
        market_data = {
            "price_change": 0.5,
            "volume_change": 10.0,
            "volatility": 1.0
        }
        signals = [
            {"action": "buy", "symbol": "AAPL"},
            {"action": "buy", "symbol": "GOOGL"},
        ]

        result = self.mind.think(market_data, signals=signals)
        self.assertIsInstance(result["insights"], list)

    def test_get_depth(self):
        """测试获取思考深度"""
        market_data = {
            "price_change": 3.0,
            "volume_change": -30.0,
            "volatility": 2.0
        }

        self.mind.think(market_data)
        depth = self.mind.get_depth()

        self.assertIn(depth, [e.value for e in ThoughtLevel])

    def test_get_insights_summary(self):
        """测试获取洞察摘要"""
        market_data = {
            "price_change": 2.0,
            "volume_change": 40.0,
            "volatility": 1.5
        }

        self.mind.think(market_data)
        summary = self.mind.first_principles_analyzer.get_insights_summary()

        self.assertIn("total_insights", summary)
        self.assertIn("by_type", summary)
        self.assertIn("causality", summary)


if __name__ == "__main__":
    unittest.main()
