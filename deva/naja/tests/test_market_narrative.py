"""
MarketNarrativeSense 单元测试
"""

import unittest
from deva.naja.cognition.market_narrative import (
    MarketNarrativeSense,
    NarrativeTracker,
    NarrativeTransitionSense,
    StoryConflictDetector,
    NarrativeType,
    NarrativeStage,
    MarketNarrative,
    NarrativeTransition,
    StoryConflict,
)


class TestNarrativeTracker(unittest.TestCase):
    """NarrativeTracker 测试"""

    def setUp(self):
        self.tracker = NarrativeTracker()

    def test_track_policy_narrative(self):
        """测试政策叙事追踪"""
        market_data = {}
        news_signals = ["央行降准", "证监会发布新政策", "政策利好"]

        narratives = self.tracker.track(market_data, news_signals)

        policy_narratives = [n for n in narratives if n.narrative_type == NarrativeType.POLICY]
        self.assertTrue(len(policy_narratives) > 0)
        self.assertEqual(policy_narratives[0].stage, NarrativeStage.BUILDING)

    def test_track_earnings_narrative(self):
        """测试业绩叙事追踪"""
        market_data = {
            "price_changes": [5.0, 3.0, 1.0, -1.0, -3.0, -5.0, 4.0, 2.0]
        }

        narratives = self.tracker.track(market_data, None)

        earnings_narratives = [n for n in narratives if n.narrative_type == NarrativeType.EARNINGS]
        self.assertTrue(len(earnings_narratives) > 0)

    def test_track_liquidity_narrative(self):
        """测试流动性叙事追踪"""
        market_data = {}
        flow_data = {
            "net_flow": 2000000000,
            "big_deal_ratio": 0.6
        }

        narratives = self.tracker.track(market_data, None, flow_data)

        liq_narratives = [n for n in narratives if n.narrative_type == NarrativeType.LIQUIDITY]
        self.assertTrue(len(liq_narratives) > 0)

    def test_track_sentiment_narrative(self):
        """测试情绪叙事追踪"""
        market_data = {
            "price_changes": [2.0, 3.0, 1.5, 2.5, 1.0, 3.0, 2.0]
        }

        narratives = self.tracker.track(market_data, None)

        sent_narratives = [n for n in narratives if n.narrative_type == NarrativeType.SENTIMENT]
        self.assertTrue(len(sent_narratives) > 0)
        self.assertIn(sent_narratives[0].stage, [NarrativeStage.BUILDING, NarrativeStage.PEAK])

    def test_get_narrative_summary(self):
        """测试获取叙事摘要"""
        market_data = {"price_changes": [2.0, 3.0, 1.5]}
        self.tracker.track(market_data, ["政策利好", "央行降准"])

        summary = self.tracker.get_narrative_summary()
        self.assertEqual(summary["status"], "active")
        self.assertIn("dominant", summary)


class TestNarrativeTransitionSense(unittest.TestCase):
    """NarrativeTransitionSense 测试"""

    def setUp(self):
        self.sense = NarrativeTransitionSense()

    def test_sense_transition_from_peak(self):
        """测试从高潮期感知转换"""
        narrative = MarketNarrative(
            narrative_type=NarrativeType.LIQUIDITY,
            stage=NarrativeStage.PEAK,
            confidence=0.8,
            evidence=["主力流入10亿"],
            start_time=0,
            strength=0.9,
            related_sectors=[],
            key_stocks=[]
        )

        market_data = {}
        flow_data = {"net_flow": 6000000000, "big_deal_ratio": 0.7}

        transition = self.sense.sense_transition([narrative], market_data, flow_data)

        self.assertIsNotNone(transition)
        self.assertEqual(transition.from_narrative, NarrativeType.LIQUIDITY)
        self.assertEqual(transition.to_narrative, NarrativeType.SENTIMENT)

    def test_no_transition_building(self):
        """测试构建期无转换"""
        narrative = MarketNarrative(
            narrative_type=NarrativeType.POLICY,
            stage=NarrativeStage.BUILDING,
            confidence=0.6,
            evidence=["政策信号"],
            start_time=0,
            strength=0.5,
            related_sectors=[],
            key_stocks=[]
        )

        transition = self.sense.sense_transition([narrative], {}, None)
        self.assertIsNone(transition)


class TestStoryConflictDetector(unittest.TestCase):
    """StoryConflictDetector 测试"""

    def setUp(self):
        self.detector = StoryConflictDetector()

    def test_detect_policy_earnings_conflict(self):
        """测试政策与业绩冲突"""
        narratives = [
            MarketNarrative(
                narrative_type=NarrativeType.POLICY,
                stage=NarrativeStage.PEAK,
                confidence=0.8,
                evidence=["央行放水"],
                start_time=0,
                strength=0.8,
                related_sectors=[],
                key_stocks=[]
            ),
            MarketNarrative(
                narrative_type=NarrativeType.EARNINGS,
                stage=NarrativeStage.PEAK,
                confidence=0.8,
                evidence=["企业业绩下滑"],
                start_time=0,
                strength=0.8,
                related_sectors=[],
                key_stocks=[]
            )
        ]

        conflicts = self.detector.detect_conflict(narratives)

        self.assertTrue(len(conflicts) > 0)
        self.assertEqual(conflicts[0].conflict_type, "contradictory")

    def test_detect_liquidity_sentiment_conflict(self):
        """测试流动性与情绪冲突"""
        narratives = [
            MarketNarrative(
                narrative_type=NarrativeType.LIQUIDITY,
                stage=NarrativeStage.BUILDING,
                confidence=0.7,
                evidence=["主力流入5亿"],
                start_time=0,
                strength=0.7,
                related_sectors=[],
                key_stocks=[]
            ),
            MarketNarrative(
                narrative_type=NarrativeType.SENTIMENT,
                stage=NarrativeStage.PEAK,
                confidence=0.7,
                evidence=["市场情绪悲观", "资金流出"],
                start_time=0,
                strength=0.8,
                related_sectors=[],
                key_stocks=[]
            )
        ]

        conflicts = self.detector.detect_conflict(narratives)
        self.assertTrue(len(conflicts) > 0)


class TestMarketNarrativeSense(unittest.TestCase):
    """MarketNarrativeSense 综合测试"""

    def setUp(self):
        self.sense = MarketNarrativeSense()

    def test_sense_full(self):
        """测试完整感知"""
        market_data = {
            "price_changes": [2.0, 3.0, 1.5],
            "sector_changes": {"科技": 3.0, "金融": 1.0, "消费": -1.0}
        }
        news_signals = ["央行降准", "政策支持"]
        flow_data = {"net_flow": 2000000000, "big_deal_ratio": 0.6}

        result = self.sense.sense(market_data, news_signals, flow_data)

        self.assertIn("narratives", result)
        self.assertIn("transitions", result)
        self.assertIn("conflicts", result)
        self.assertIn("summary", result)
        self.assertTrue(len(result["narratives"]) > 0)

    def test_get_dominant_narrative(self):
        """测试获取主导叙事"""
        market_data = {"price_changes": [3.0, 2.5, 2.0]}
        news_signals = ["重大政策利好"]
        self.sense.sense(market_data, news_signals)

        dominant = self.sense.get_dominant_narrative()
        self.assertIsNotNone(dominant)
        self.assertIn(dominant.narrative_type, [NarrativeType.POLICY, NarrativeType.SENTIMENT])

    def test_build_summary(self):
        """测试摘要构建"""
        market_data = {"price_changes": [2.0, 3.0, 1.5]}
        result = self.sense.sense(market_data, ["政策利好"])

        summary = result["summary"]
        self.assertIsInstance(summary, str)
        self.assertTrue(len(summary) > 0)


if __name__ == "__main__":
    unittest.main()