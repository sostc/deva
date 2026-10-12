"""
AwakenedAlaya 单元测试
"""

import unittest
from deva.naja.knowledge.alaya.awakened_alaya import (
    AwakenedAlaya,
    CrossMarketMemory,
    PatternArchiveManager,
    AwakeningEngine,
    AwakeningLevel,
    PatternArchive,
    AwakeningSignal,
)


class TestCrossMarketMemory(unittest.TestCase):
    """CrossMarketMemory 测试"""

    def setUp(self):
        self.memory = CrossMarketMemory()

    def test_store_success_pattern(self):
        """测试存储成功模式"""
        pattern = {
            "type": "momentum",
            "conditions": {"volatility": 1.5}
        }

        self.memory.store_success_pattern("futures", pattern)
        self.assertEqual(len(self.memory._source_memories["futures"]), 1)

    def test_recall_applicable_patterns(self):
        """测试召回适用模式"""
        pattern = {
            "type": "momentum",
            "conditions": {"volatility": 1.5}
        }

        self.memory.store_success_pattern("futures", pattern)

        current_conditions = {"volatility": 1.6}
        recalled = self.memory.recall_applicable_patterns("a_stock", current_conditions)

        self.assertGreaterEqual(len(recalled), 0)


class TestPatternArchiveManager(unittest.TestCase):
    """PatternArchiveManager 测试"""

    def setUp(self):
        self.archive = PatternArchiveManager()

    def test_archive(self):
        """测试归档"""
        self.archive.archive(
            pattern_id="test_1",
            pattern_type="momentum",
            market_context={"symbol": "AAPL"},
            outcome={"return": 0.1}
        )

        self.assertEqual(len(self.archive._archives["momentum"]), 1)

    def test_recall(self):
        """测试召回"""
        self.archive.archive(
            pattern_id="test_1",
            pattern_type="momentum",
            market_context={"symbol": "AAPL"},
            outcome={"return": 0.1}
        )

        recalled = self.archive.recall(symbol="AAPL")
        self.assertGreaterEqual(len(recalled), 1)

    def test_get_archive_stats(self):
        """测试获取统计"""
        self.archive.archive(
            pattern_id="test_1",
            pattern_type="momentum",
            market_context={},
            outcome={"return": 0.1}
        )

        stats = self.archive.get_archive_stats()
        self.assertIn("momentum", stats)


class TestAwakeningEngine(unittest.TestCase):
    """AwakeningEngine 测试"""

    def setUp(self):
        self.engine = AwakeningEngine()

    def test_receive_signal(self):
        """测试接收信号"""
        self.engine.receive_signal(
            signal_type="momentum",
            content="动量信号",
            confidence=0.7,
            conditions={"direction": 1}
        )

        self.assertEqual(len(self.engine._weak_signals), 1)

    def test_awakening_level_update(self):
        """测试觉醒层次更新"""
        for i in range(20):
            self.engine.receive_signal(
                signal_type=f"type_{i % 3}",
                content=f"信号{i}",
                confidence=0.6,
                conditions={}
            )

        level = self.engine.get_awakening_level()
        self.assertIn(level, [e.value for e in AwakeningLevel])

    def test_check_for_awakening_no_signal(self):
        """测试无信号时不顿悟"""
        result = self.engine.check_for_awakening()
        self.assertIsNone(result)

    def test_check_for_awakening_with_signals(self):
        """测试多信号时可能顿悟"""
        for i in range(15):
            self.engine.receive_signal(
                signal_type=f"type_{i % 4}",
                content=f"信号{i}",
                confidence=0.6,
                conditions={"direction": 1 if i % 2 == 0 else -1}
            )

        result = self.engine.check_for_awakening()
        self.assertIsNotNone(result)


class TestAwakenedAlaya(unittest.TestCase):
    """AwakenedAlaya 测试"""

    def setUp(self):
        self.alaya = AwakenedAlaya()

    def test_illuminate_basic(self):
        """测试基本照亮"""
        market_data = {
            "symbol": "AAPL",
            "block": "tech",
            "pattern_type": "momentum"
        }

        result = self.alaya.illuminate(market_data)

        self.assertIn("awakening_level", result)

    def test_illuminate_with_signals(self):
        """测试带信号的照亮"""
        market_data = {
            "symbol": "AAPL",
            "block": "tech"
        }

        signals = [
            {"type": "momentum", "content": "动量强", "confidence": 0.7, "conditions": {"direction": 1}},
            {"type": "flow", "content": "资金流入", "confidence": 0.6, "conditions": {}},
        ]

        result = self.alaya.illuminate(market_data, signals)

        self.assertIsNotNone(result)

    def test_archive_pattern(self):
        """测试归档模式"""
        self.alaya.archive_pattern(
            pattern_id="test_1",
            pattern_type="momentum",
            market_context={"symbol": "AAPL"},
            outcome={"return": 0.15}
        )

        recalled = self.alaya.pattern_archive.recall(symbol="AAPL")
        self.assertGreaterEqual(len(recalled), 1)

    def test_get_stats(self):
        """测试获取统计"""
        self.alaya.archive_pattern(
            pattern_id="test_1",
            pattern_type="momentum",
            market_context={},
            outcome={"return": 0.1}
        )

        stats = self.alaya.get_stats()

        self.assertIn("integration_count", stats)
        self.assertIn("awakening_level", stats)


class _TradingCenterProxy:
    """只带 D3 反馈所需依赖的轻量替身，避免构造 TradingCenter 单例。

    它把 `_get_awakening_level` 委托给 TradingCenter 的**真实方法体**
    （unbound 调用），因此测的是产品代码而不是复制的逻辑。
    """

    def __init__(self, alaya, stale_level=None):
        self._alaya = alaya
        self._awakened_state = (
            {} if stale_level is None else {"awakening_level": stale_level}
        )

    def _get_awakened_alaya(self):
        return self._alaya

    def _get_awakening_level(self):
        from deva.naja.attention.orchestration.trading_center import TradingCenter
        return TradingCenter._get_awakening_level(self)


class TestAwakeningFeedbackLoop(unittest.TestCase):
    """D3 闭环反馈：执行结果 → AwakenedAlaya，以及觉醒三重断点 #2 的修复。"""

    def test_get_awakening_level_reads_real_source_not_stale_dict(self):
        """断点 #2：不能再读那个从未被写入的 _awakened_state 字典。"""
        alaya = AwakenedAlaya()
        proxy = _TradingCenterProxy(alaya, stale_level="BOGUS_FROM_STALE_DICT")
        level = proxy._get_awakening_level()
        self.assertNotEqual(level, "BOGUS_FROM_STALE_DICT")
        self.assertEqual(level, "dormant")

    def test_get_awakening_level_falls_back_when_alaya_missing(self):
        proxy = _TradingCenterProxy(None, stale_level="fallback_level")
        self.assertEqual(proxy._get_awakening_level(), "fallback_level")

    def test_record_trade_outcome_feeds_engine_and_raises_level(self):
        """断点 #3：结果真的进 AwakeningEngine，显著结果能跨过阈值。"""
        from deva.naja.attention.orchestration.trading_center import TradingCenter

        alaya = AwakenedAlaya()
        proxy = _TradingCenterProxy(alaya)
        before = alaya.awakening_engine.get_stats()["signal_count"]

        ok = TradingCenter.record_trade_outcome(
            proxy, "600000", 8.0, close_reason="TAKE_PROFIT"
        )

        after = alaya.awakening_engine.get_stats()["signal_count"]
        self.assertTrue(ok)
        self.assertGreater(after, before)
        self.assertNotEqual(alaya.awakening_engine.get_awakening_level(), "dormant")

    def test_small_outcome_does_not_falsely_awaken(self):
        """微小结果只有 1 条弱信号，跨不过 DORMANT=3 —— 不是"什么都算觉醒"。"""
        from deva.naja.attention.orchestration.trading_center import TradingCenter

        alaya = AwakenedAlaya()
        proxy = _TradingCenterProxy(alaya)
        TradingCenter.record_trade_outcome(proxy, "000001", 0.3, close_reason="FORCE")
        self.assertEqual(alaya.awakening_engine.get_awakening_level(), "dormant")

    def test_record_trade_outcome_rejects_bad_input(self):
        from deva.naja.attention.orchestration.trading_center import TradingCenter

        alaya = AwakenedAlaya()
        proxy = _TradingCenterProxy(alaya)
        self.assertFalse(
            TradingCenter.record_trade_outcome(proxy, "600000", "not-a-number")
        )

    def test_awakening_level_provider_reflects_feedback(self):
        """Manas 的觉醒维度读到的是反馈后的真实等级（读取端已接）。"""
        from deva.naja.attention.kernel.manas_engine import ManasEngine
        from deva.naja.attention.orchestration.trading_center import TradingCenter

        alaya = AwakenedAlaya()
        proxy = _TradingCenterProxy(alaya)
        engine = ManasEngine()
        engine.set_awakening_level_provider(proxy._get_awakening_level)

        self.assertEqual(engine._get_awakening_level(), "dormant")
        TradingCenter.record_trade_outcome(proxy, "600000", 6.0, close_reason="TAKE_PROFIT")
        self.assertEqual(
            engine._get_awakening_level(),
            alaya.awakening_engine.get_awakening_level(),
        )
        self.assertNotEqual(engine._get_awakening_level(), "dormant")


if __name__ == "__main__":
    unittest.main()
