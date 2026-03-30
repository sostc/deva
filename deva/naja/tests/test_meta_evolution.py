"""
MetaEvolution 单元测试
"""

import unittest
import time
from deva.naja.evolution import (
    MetaEvolution,
    SelfObserver,
    EvolutionPhase,
    PerformanceTrend,
    get_meta_evolution,
    initialize_meta_evolution,
)


class TestSelfObserver(unittest.TestCase):
    """SelfObserver 测试"""

    def setUp(self):
        self.observer = SelfObserver()

    def test_record_decision(self):
        """测试记录决策"""
        self.observer.record_decision(
            decision_type="buy",
            context={"symbol": "000001", "price": 10.0},
            decision="buy",
            outcome=0.05
        )

        summary = self.observer.get_summary()
        self.assertEqual(summary["total_decisions"], 1)

    def test_record_outcome(self):
        """测试记录结果"""
        self.observer.record_decision(
            decision_type="sell",
            context={"symbol": "000001"},
            decision="sell"
        )
        self.observer.record_outcome("sell", success=True, latency_ms=50.0)

        summary = self.observer.get_summary()
        self.assertEqual(summary["successful"], 1)
        self.assertEqual(summary["modules"]["sell"]["avg_latency_ms"], 50.0)

    def test_trend_calculation(self):
        """测试趋势计算"""
        for i in range(10):
            self.observer.record_decision(
                decision_type="trend_test",
                context={},
                decision="hold"
            )
            self.observer.record_outcome("trend_test", success=(i % 2 == 0), latency_ms=10.0)

        summary = self.observer.get_summary()
        module = summary["modules"]["trend_test"]
        self.assertIn(module["trend"], [e.value for e in PerformanceTrend])


class TestMetaEvolution(unittest.TestCase):
    """MetaEvolution 测试"""

    def setUp(self):
        self.evo = MetaEvolution()

    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.evo.observer)
        self.assertEqual(self.evo.get_phase(), EvolutionPhase.OBSERVING)

    def test_record_decision(self):
        """测试记录决策"""
        self.evo.record_decision(
            decision_type="test_decision",
            context={"test": True},
            decision="action"
        )
        self.assertEqual(len(self.evo.observer._decision_records), 1)

    def test_record_outcome(self):
        """测试记录结果"""
        self.evo.record_decision(
            decision_type="outcome_test",
            context={},
            decision="action"
        )
        self.evo.record_outcome("outcome_test", success=True, latency_ms=100.0)

        summary = self.evo.observer.get_summary()
        self.assertEqual(summary["successful"], 1)

    def test_think(self):
        """测试思考"""
        for _ in range(15):
            self.evo.record_decision("think_test", {}, "action")
            self.evo.record_outcome("think_test", success=True)

        insights = self.evo.think()
        self.assertIsInstance(insights, list)

    def test_phase_transitions(self):
        """测试阶段转换"""
        self.assertEqual(self.evo.get_phase(), EvolutionPhase.OBSERVING)

        for i in range(20):
            self.evo.record_decision(f"phase_{i}", {}, "action")
            self.evo.record_outcome(f"phase_{i}", success=(i % 3 == 0))

        self.evo.think()

    def test_singleton(self):
        """测试单例"""
        evo1 = get_meta_evolution()
        evo2 = get_meta_evolution()
        self.assertIs(evo1, evo2)

    def test_enabled_flag(self):
        """测试启用标志"""
        self.evo.set_enabled(False)
        self.evo.record_decision("disabled", {}, "action")
        self.assertEqual(len(self.evo.observer._decision_records), 0)

        self.evo.set_enabled(True)
        self.evo.record_decision("enabled", {}, "action")
        self.assertEqual(len(self.evo.observer._decision_records), 1)

    def test_get_status(self):
        """测试获取状态"""
        self.evo.record_decision("status_test", {}, "action")
        self.evo.record_outcome("status_test", success=True)

        status = self.evo.get_status()
        self.assertIn("phase", status)
        self.assertIn("observer_summary", status)
        self.assertTrue(status["enabled"])

    def test_module_insights(self):
        """测试模块洞察"""
        for i in range(15):
            self.evo.record_decision("insight_test", {}, "action")
            self.evo.record_outcome("insight_test", success=(i % 2 == 0))

        insights = self.evo.observer.get_module_insights()
        self.assertIsInstance(insights, list)


class TestEvolutionPhase(unittest.TestCase):
    """EvolutionPhase 枚举测试"""

    def test_phase_values(self):
        """测试阶段值"""
        self.assertEqual(EvolutionPhase.OBSERVING.value, "observing")
        self.assertEqual(EvolutionPhase.HYPOTHESIZING.value, "hypothesizing")
        self.assertEqual(EvolutionPhase.TESTING.value, "testing")
        self.assertEqual(EvolutionPhase.STABILIZING.value, "stabilizing")
        self.assertEqual(EvolutionPhase.EVOLVED.value, "evolved")

    def test_phase_order(self):
        """测试阶段顺序"""
        phases = list(EvolutionPhase)
        self.assertEqual(len(phases), 5)


if __name__ == "__main__":
    unittest.main()