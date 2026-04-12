"""
EpiphanyEngine 单元测试
"""

import unittest
import time
from deva.naja.knowledge.alaya.epiphany_engine import (
    EpiphanyEngine,
    CrossMarketTransfer,
    PatternEpiphany,
    FullRecall,
    MarketType,
    CrossMarketPattern,
    Epiphany,
)


class TestCrossMarketTransfer(unittest.TestCase):
    """CrossMarketTransfer 测试"""

    def setUp(self):
        self.transfer = CrossMarketTransfer()

    def test_register_pattern(self):
        """测试注册跨市场模式"""
        pattern = {
            "type": "momentum",
            "description": "动量效应",
            "conditions": ["trend>0.5"]
        }

        self.transfer.register_pattern(MarketType.US_STOCK, pattern, True)
        self.transfer.update_confidence()

        patterns = self.transfer.find_applicable_patterns(MarketType.A_SHARE, {"trend_strength": 0.6})
        self.assertTrue(len(patterns) > 0)

    def test_find_applicable_patterns(self):
        """测试查找适用模式"""
        pattern = {
            "type": "reversal",
            "description": "反转效应",
            "conditions": ["volatility>1.5"]
        }

        self.transfer.register_pattern(MarketType.HK_STOCK, pattern, True)

        patterns = self.transfer.find_applicable_patterns(
            MarketType.A_SHARE,
            {"volatility": 2.0, "trend_strength": 0.3}
        )

        self.assertTrue(len(patterns) > 0)

    def test_get_summary(self):
        """测试获取摘要"""
        pattern = {"type": "momentum", "description": "", "conditions": []}
        self.transfer.register_pattern(MarketType.US_STOCK, pattern, True)

        summary = self.transfer.get_cross_market_summary()
        self.assertIn("total_patterns", summary)


class TestPatternEpiphany(unittest.TestCase):
    """PatternEpiphany 测试"""

    def setUp(self):
        self.epiphany = PatternEpiphany()

    def test_receive_signal(self):
        """测试接收信号"""
        self.epiphany.receive_signal({
            "type": "momentum",
            "direction": "up",
            "description": "动量上升"
        })

        self.assertEqual(len(self.epiphany._weak_signals), 1)

    def test_check_for_epiphany_timing(self):
        """测试时机顿悟"""
        signals = [
            {"type": "momentum", "direction": "up", "value": 0.8},
            {"type": "flow", "direction": "out", "value": -0.6},
            {"type": "momentum", "direction": "down", "value": -0.3},
        ]

        for s in signals:
            self.epiphany.receive_signal(s)

        epiphany = self.epiphany.check_for_epiphany()
        self.assertIsNotNone(epiphany)
        self.assertEqual(epiphany.epiphany_type, "timing_insight")

    def test_check_for_epiphany_sentiment(self):
        """测试情绪顿悟"""
        signals = [
            {"type": "sentiment", "value": 0.8},
            {"type": "sentiment", "value": 0.7},
            {"type": "sentiment", "value": 0.75},
        ]

        for s in signals:
            self.epiphany.receive_signal(s)

        epiphany = self.epiphany.check_for_epiphany()
        self.assertIsNotNone(epiphany)
        self.assertEqual(epiphany.epiphany_type, "pattern_discovery")

    def test_check_no_epiphany(self):
        """测试无顿悟"""
        self.epiphany.receive_signal({"type": "other", "value": 0.5})
        self.epiphany.receive_signal({"type": "other", "value": 0.3})

        epiphany = self.epiphany.check_for_epiphany()
        self.assertIsNone(epiphany)


class TestFullRecall(unittest.TestCase):
    """FullRecall 测试"""

    def setUp(self):
        self.recall = FullRecall()

    def test_archive_pattern(self):
        """测试归档模式"""
        pattern = {
            "type": "momentum",
            "change": 3.0,
            "volume_ratio": 1.5
        }
        outcome = {"success_rate": 0.7, "holding_period": 5}

        self.recall.archive_pattern("momentum", pattern, outcome)

        stats = self.recall.get_archive_stats()
        self.assertEqual(stats["momentum"], 1)

    def test_recall_patterns(self):
        """测试召回模式"""
        pattern = {
            "type": "momentum",
            "change": 3.0,
            "volume_ratio": 1.5
        }
        outcome = {"success_rate": 0.8, "holding_period": 5}

        self.recall.archive_pattern("momentum", pattern, outcome)

        recalled = self.recall.recall("momentum", {"change": 3.0})
        self.assertTrue(len(recalled) > 0)


class TestEpiphanyEngine(unittest.TestCase):
    """EpiphanyEngine 综合测试"""

    def setUp(self):
        self.engine = EpiphanyEngine()

    def test_receive_signal(self):
        """测试接收信号"""
        self.engine.receive_signal({
            "type": "momentum",
            "description": "动量信号"
        })

        self.assertEqual(len(self.engine.pattern_epiphany._weak_signals), 1)

    def test_check_epiphany(self):
        """测试检查顿悟"""
        signals = [
            {"type": "momentum", "direction": "up", "value": 0.8},
            {"type": "flow", "direction": "out", "value": -0.6},
            {"type": "momentum", "direction": "down", "value": -0.3},
        ]

        for s in signals:
            self.engine.receive_signal(s)

        epiphany = self.engine.check_epiphany()
        self.assertIsNotNone(epiphany)

    def test_archive_and_recall(self):
        """测试归档和召回"""
        pattern = {"type": "reversal", "change": -3.0}
        outcome = {"success_rate": 0.75}

        self.engine.archive_outcome("reversal", pattern, outcome)

        recalled = self.engine.recall_patterns("reversal", {"change": -3.0})
        self.assertTrue(len(recalled) > 0)

    def test_find_cross_market_opportunities(self):
        """测试查找跨市场机会"""
        self.engine.cross_market.register_pattern(
            MarketType.US_STOCK,
            {"type": "momentum", "description": "美股动量", "conditions": []},
            True
        )

        opportunities = self.engine.find_cross_market_opportunities(
            MarketType.A_SHARE,
            {"volatility": 1.5}
        )

        self.assertIsInstance(opportunities, list)

    def test_get_engine_summary(self):
        """测试获取引擎摘要"""
        summary = self.engine.get_engine_summary()
        self.assertIn("cross_market_summary", summary)
        self.assertIn("archive_stats", summary)


if __name__ == "__main__":
    unittest.main()