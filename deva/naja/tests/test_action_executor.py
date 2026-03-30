"""
ActionExecutor 单元测试
"""

import unittest
import time
from deva.naja.evolution.action_executor import (
    ActionExecutor,
    WisdomSynthesizer,
    ActionGenerator,
    ExecutionCoordinator,
    ActionType,
    ActionPriority,
    TradingAction,
    WisdomInput,
)


class TestWisdomSynthesizer(unittest.TestCase):
    """WisdomSynthesizer 测试"""

    def setUp(self):
        self.synth = WisdomSynthesizer()

    def test_synthesize_empty(self):
        """测试空输入"""
        wisdom = WisdomInput()
        result = self.synth.synthesize(wisdom, {})
        self.assertEqual(result["signal_count"], 0)
        self.assertIsNone(result["dominant_signal"])

    def test_synthesize_with_signals(self):
        """测试有信号的输入"""
        wisdom = WisdomInput(
            prophet_signal={"type": "momentum_precipice", "intensity": 0.8},
            adaptive_decision={"harmony_state": "harmony", "intensity": 0.7}
        )
        result = self.synth.synthesize(wisdom, {})

        self.assertGreater(result["signal_count"], 0)
        self.assertIsNotNone(result["dominant_signal"])


class TestActionGenerator(unittest.TestCase):
    """ActionGenerator 测试"""

    def setUp(self):
        self.generator = ActionGenerator()

    def test_generate_from_opportunity(self):
        """测试从机会生成行动"""
        synthesis = {"signals": [], "overall_confidence": 0.7, "dominant_signal": "主动机会"}

        wisdom = WisdomInput(
            prophet_signal={"type": "momentum_precipice", "intensity": 0.8},
            illuminated_patterns=[],
            opportunities=[
                type('obj', (object,), {
                    "opportunity_type": type('obj', (object,), {"value": "momentum"})(),
                    "symbol": "000001",
                    "confidence": 0.8,
                    "stage": type('obj', (object,), {"value": "ready"})(),
                    "expected_return": 0.05,
                    "entry_horizon": 300
                })()
            ]
        )

        actions = self.generator.generate(synthesis, wisdom, {})
        self.assertTrue(len(actions) > 0)
        self.assertEqual(actions[0].action_type, ActionType.BUY)

    def test_prioritize_actions(self):
        """测试优先级排序"""
        actions = [
            TradingAction(ActionType.HOLD, "000001", 100, ActionPriority.NORMAL, 0.5, "test", [], time.time(), time.time() + 300),
            TradingAction(ActionType.BUY, "000002", 100, ActionPriority.HIGH, 0.7, "test", [], time.time(), time.time() + 300),
            TradingAction(ActionType.SELL, "000001", 100, ActionPriority.URGENT, 0.9, "test", [], time.time(), time.time() + 300),
        ]

        prioritized = self.generator._prioritize_actions(actions)

        self.assertEqual(prioritized[0].action_type, ActionType.SELL)
        self.assertEqual(prioritized[0].priority, ActionPriority.URGENT)


class TestExecutionCoordinator(unittest.TestCase):
    """ExecutionCoordinator 测试"""

    def setUp(self):
        self.coord = ExecutionCoordinator()

    def test_coordinate_no_conflict(self):
        """测试无冲突"""
        actions = [
            TradingAction(ActionType.BUY, "000001", 100, ActionPriority.HIGH, 0.8, "test", [], time.time(), time.time() + 300),
            TradingAction(ActionType.BUY, "000002", 100, ActionPriority.HIGH, 0.7, "test", [], time.time(), time.time() + 300),
        ]

        coordinated = self.coord.coordinate(actions)
        self.assertEqual(len(coordinated), 2)

    def test_coordinate_with_conflict(self):
        """测试有冲突"""
        actions = [
            TradingAction(ActionType.BUY, "000001", 100, ActionPriority.HIGH, 0.8, "test", [], time.time(), time.time() + 300),
            TradingAction(ActionType.SELL, "000001", 100, ActionPriority.HIGH, 0.7, "test", [], time.time(), time.time() + 300),
        ]

        coordinated = self.coord.coordinate(actions)
        self.assertEqual(len(coordinated), 1)

    def test_mark_executed(self):
        """测试标记已执行"""
        action = TradingAction(ActionType.BUY, "000001", 100, ActionPriority.HIGH, 0.8, "test", [], time.time(), time.time() + 300)
        self.coord.mark_executed(action)

        self.assertEqual(len(self.coord._executed_actions), 1)
        self.assertEqual(len(self.coord._pending_actions), 0)


class TestActionExecutor(unittest.TestCase):
    """ActionExecutor 综合测试"""

    def setUp(self):
        self.executor = ActionExecutor()

    def test_execute_full(self):
        """测试完整执行"""
        from deva.naja.manas.adaptive_manas import WuWeiDecision, HarmonyState

        wisdom = WisdomInput(
            prophet_signal={"type": "momentum_precipice", "intensity": 0.8},
            adaptive_decision=WuWeiDecision(
                should_act=True,
                harmony_state=HarmonyState.RESONANCE,
                harmony_strength=0.7,
                tian_shi_score=0.8,
                di_shi_score=0.6,
                ren_shi_score=0.7,
                confidence=0.75,
                reason="测试",
                action_type="buy"
            )
        )

        market_state = {"trend": "up"}
        positions = {}

        actions = self.executor.execute(wisdom, market_state, positions)
        self.assertIsInstance(actions, list)

    def test_execute_summary(self):
        """测试执行摘要"""
        summary = self.executor.get_execution_summary()
        self.assertIn("pending", summary)
        self.assertIn("executed_today", summary)


if __name__ == "__main__":
    unittest.main()