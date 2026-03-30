"""
DecisionAttention 单元测试
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deva.naja.attention.kernel.decision_attention import DecisionAttention, TemperatureAwareHead


class MockFourDimensions:
    """模拟四维框架"""

    def __init__(self, cash_ratio=0.5, is_ready=True, strategy_count=3, multiplier=1.0):
        self.capital = type('obj', (object,), {'cash_ratio': cash_ratio})()
        self.capability = type('obj', (object,), {
            'is_ready': is_ready,
            'strategy_count': strategy_count,
            'multiplier': multiplier
        })()


class TestDecisionAttention(unittest.TestCase):
    """DecisionAttention 测试"""

    def test_compute_temperature_high_cash(self):
        """测试高仓位时温度应该较低"""
        fd = MockFourDimensions(cash_ratio=0.8)
        da = DecisionAttention(fd)

        T = da.compute_temperature()
        self.assertLess(T, 1.5, "高仓位时温度应该相对较低")

    def test_compute_temperature_low_cash(self):
        """测试低仓位时温度应该高（更保守）"""
        fd = MockFourDimensions(cash_ratio=0.1)
        da = DecisionAttention(fd)

        T = da.compute_temperature()
        self.assertGreater(T, 1.5, "低仓位时温度应该高")

    def test_compute_alpha_high_performance(self):
        """测试策略表现好时 alpha 应该高"""
        da = DecisionAttention(None)

        α = da.compute_alpha(strategy_performance=0.9)
        self.assertGreater(α, 0.9, "高表现时 alpha 应该高")

    def test_compute_alpha_low_performance(self):
        """测试策略表现差时 alpha 应该低"""
        da = DecisionAttention(None)

        α = da.compute_alpha(strategy_performance=0.1)
        self.assertLess(α, 0.8, "低表现时 alpha 应该较小")

    def test_compute_alpha_with_capability(self):
        """测试有能力信息时 alpha 计算"""
        fd = MockFourDimensions(cash_ratio=0.5, is_ready=True, strategy_count=5, multiplier=1.2)
        da = DecisionAttention(fd)

        α = da.compute_alpha(strategy_performance=0.7)

        self.assertIsInstance(α, float)
        self.assertGreater(α, 0.5)
        self.assertLess(α, 1.5)

    def test_modulate_scores(self):
        """测试分数调制"""
        da = DecisionAttention(None)

        raw_scores = [1.0, 2.0, 3.0, 4.0]

        modulated, α, T = da.modulate(raw_scores, strategy_performance=0.7)

        self.assertEqual(len(modulated), len(raw_scores))
        self.assertIsInstance(α, float)
        self.assertIsInstance(T, float)
        self.assertGreater(α, 0)
        self.assertGreater(T, 0)

    def test_modulate_empty_scores(self):
        """测试空分数列表"""
        da = DecisionAttention(None)

        modulated, α, T = da.modulate([], strategy_performance=0.5)

        self.assertEqual(modulated, [])
        self.assertIsInstance(α, float)
        self.assertIsInstance(T, float)

    def test_temperature_range(self):
        """测试温度范围 [0.5, 2.0]"""
        da = DecisionAttention(None)

        for cash in [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0]:
            fd = MockFourDimensions(cash_ratio=cash)
            da.set_four_dimensions(fd)
            T = da.compute_temperature()
            self.assertGreaterEqual(T, 0.5)
            self.assertLessEqual(T, 2.0)

    def test_alpha_range(self):
        """测试 alpha 范围 [0.3, 1.5]"""
        da = DecisionAttention(None)

        for perf in [0.0, 0.2, 0.5, 0.8, 1.0]:
            α = da.compute_alpha(strategy_performance=perf)
            self.assertGreaterEqual(α, 0.3)
            self.assertLessEqual(α, 1.5)

    def test_get_state(self):
        """测试状态获取"""
        da = DecisionAttention(None)
        da.compute_alpha(0.7)
        da.compute_temperature()

        state = da.get_state()

        self.assertIn('alpha', state)
        self.assertIn('temperature', state)
        self.assertIn('strategy_performance', state)


class MockEvent:
    """模拟 AttentionEvent"""

    def __init__(self):
        self.key = {'alpha': 0.8, 'risk': 0.3, 'confidence': 0.6}
        self.value = {'alpha': 0.7, 'risk': 0.4, 'confidence': 0.5}


class TestTemperatureAwareHead(unittest.TestCase):
    """TemperatureAwareHead 测试"""

    def test_compute_without_decision_attention(self):
        """测试不使用决策注意力时"""
        def scorer(Q, K):
            return K.get('alpha', 0) * 0.5

        head = TemperatureAwareHead("test_head", scorer, decision_attention=None)

        Q = {}
        events = [MockEvent(), MockEvent()]

        result = head.compute(Q, events)

        self.assertIn('alpha', result)
        self.assertIn('_alpha', result)
        self.assertEqual(result['_alpha'], 1.0)
        self.assertEqual(result['_temperature'], 1.0)

    def test_compute_with_decision_attention(self):
        """测试使用决策注意力时"""
        def scorer(Q, K):
            return K.get('alpha', 0)

        fd = MockFourDimensions(cash_ratio=0.5, is_ready=True, strategy_count=3, multiplier=1.0)
        da = DecisionAttention(fd)

        head = TemperatureAwareHead("test_head", scorer, decision_attention=da)

        Q = {}
        events = [MockEvent()]

        result = head.compute(Q, events)

        self.assertIn('_alpha', result)
        self.assertIn('_temperature', result)
        self.assertIsInstance(result['_alpha'], float)
        self.assertIsInstance(result['_temperature'], float)

    def test_softmax_temperature_effect(self):
        """测试温度对 softmax 的影响"""
        def scorer(Q, K):
            return K.get('score', 1.0)

        da = DecisionAttention(None)

        head_high_temp = TemperatureAwareHead("high_temp", scorer, da)
        head_low_temp = TemperatureAwareHead("low_temp", scorer, da)

        events = [type('E', (), {'key': {'score': 2.0}, 'value': {'alpha': 1, 'risk': 0, 'confidence': 0}})(),
                  type('E', (), {'key': {'score': 1.0}, 'value': {'alpha': 0, 'risk': 0, 'confidence': 0}})()]

        da._last_temperature = 2.0
        da._last_alpha = 1.0
        result_high = head_high_temp.compute({}, events)

        da._last_temperature = 0.5
        da._last_alpha = 1.0
        result_low = head_low_temp.compute({}, events)

        self.assertIsInstance(result_high['alpha'], float)
        self.assertIsInstance(result_low['alpha'], float)


if __name__ == '__main__':
    unittest.main()
