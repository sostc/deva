"""
ManasEngine 单元测试
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deva.naja.attention.kernel.manas_engine import (
    ManasEngine,
    TimingEngine,
    RegimeEngine,
    ConfidenceEngine,
    RiskEngine,
    MetaManas,
    BiasState,
    ManasOutput,
)


class TestTimingEngine(unittest.TestCase):
    """TimingEngine 测试"""

    def test_basic_computation(self):
        """测试基本计算"""
        engine = TimingEngine()
        score = engine.compute(session_manager=None, scanner=None)
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_timing_range(self):
        """测试时机分数范围"""
        engine = TimingEngine()
        for _ in range(10):
            score = engine.compute()
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)


class TestRegimeEngine(unittest.TestCase):
    """RegimeEngine 测试"""

    def test_basic_computation(self):
        """测试基本计算"""
        engine = RegimeEngine()
        score = engine.compute(scanner=None, macro_signal=0.5)
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, -1.0)
        self.assertLessEqual(score, 1.0)

    def test_regime_range(self):
        """测试环境分数范围"""
        engine = RegimeEngine()
        for macro in [0.0, 0.3, 0.5, 0.7, 1.0]:
            score = engine.compute(macro_signal=macro)
            self.assertGreaterEqual(score, -1.0)
            self.assertLessEqual(score, 1.0)


class TestConfidenceEngine(unittest.TestCase):
    """ConfidenceEngine 测试"""

    def test_basic_computation(self):
        """测试基本计算"""
        engine = ConfidenceEngine()
        score = engine.compute(bandit_tracker=None)
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.5)

    def test_confidence_range(self):
        """测试自信度范围"""
        engine = ConfidenceEngine()
        for _ in range(10):
            score = engine.compute()
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.5)


class TestRiskEngine(unittest.TestCase):
    """RiskEngine 测试"""

    def test_basic_computation(self):
        """测试基本计算"""
        engine = RiskEngine()
        T = engine.compute(portfolio=None, scanner=None)
        self.assertIsInstance(T, float)
        self.assertGreater(T, 0.0)
        self.assertLessEqual(T, 2.0)

    def test_temperature_range(self):
        """测试温度范围"""
        engine = RiskEngine()
        for _ in range(10):
            T = engine.compute()
            self.assertGreater(T, 0.0)
            self.assertLessEqual(T, 2.0)


class TestMetaManas(unittest.TestCase):
    """MetaManas 测试"""

    def test_bias_detection_greed(self):
        """测试贪检测"""
        meta = MetaManas()

        recent_pnl = [0.1, 0.1, 0.1, 0.1, 0.1]
        bias, correction = meta.detect_and_correct(
            manas_score=0.8,
            recent_pnl=recent_pnl,
            decision_aggressiveness=0.8
        )

        self.assertEqual(bias, BiasState.GREED)
        self.assertLess(correction, 1.0)

    def test_bias_detection_fear(self):
        """测试惧检测"""
        meta = MetaManas()

        recent_pnl = [-0.1, -0.1, -0.1, -0.1, -0.1]
        bias, correction = meta.detect_and_correct(
            manas_score=0.3,
            recent_pnl=recent_pnl,
            decision_aggressiveness=0.2
        )

        self.assertEqual(bias, BiasState.FEAR)
        self.assertLess(correction, 1.0)

    def test_bias_neutral(self):
        """测试中性状态"""
        meta = MetaManas()

        recent_pnl = [0.01, -0.01, 0.01, -0.01, 0.0]
        bias, correction = meta.detect_and_correct(
            manas_score=0.5,
            recent_pnl=recent_pnl,
            decision_aggressiveness=0.5
        )

        self.assertEqual(bias, BiasState.NEUTRAL)
        self.assertEqual(correction, 1.0)

    def test_insufficient_data(self):
        """测试数据不足时"""
        meta = MetaManas()

        recent_pnl = [0.1]
        bias, correction = meta.detect_and_correct(
            manas_score=0.5,
            recent_pnl=recent_pnl,
            decision_aggressiveness=0.5
        )

        self.assertEqual(bias, BiasState.NEUTRAL)
        self.assertEqual(correction, 1.0)


class TestManasOutput(unittest.TestCase):
    """ManasOutput 测试"""

    def test_to_dict(self):
        """测试字典转换"""
        output = ManasOutput(
            manas_score=0.7,
            timing_score=0.8,
            regime_score=0.5,
            confidence_score=0.6,
            risk_temperature=1.2,
            should_act=True,
            action_gate_reason="时机成熟 | 顺风 | ✓通过",
            bias_state=BiasState.NEUTRAL,
            bias_correction=1.0,
            alpha=0.9,
            attention_focus=0.7,
        )

        d = output.to_dict()

        self.assertIn('manas_score', d)
        self.assertIn('timing_score', d)
        self.assertIn('regime_score', d)
        self.assertIn('confidence_score', d)
        self.assertIn('risk_temperature', d)
        self.assertIn('should_act', d)
        self.assertIn('bias_state', d)
        self.assertIn('alpha', d)
        self.assertEqual(d['bias_state'], 'neutral')


class TestManasEngine(unittest.TestCase):
    """ManasEngine 测试"""

    def test_basic_computation(self):
        """测试基本计算"""
        manas = ManasEngine()
        output = manas.compute()

        self.assertIsInstance(output, ManasOutput)
        self.assertGreaterEqual(output.manas_score, 0.0)
        self.assertLessEqual(output.manas_score, 1.0)
        self.assertIsInstance(output.should_act, bool)

    def test_manas_score_range(self):
        """测试 manas 分数范围"""
        manas = ManasEngine()
        for _ in range(20):
            output = manas.compute()
            self.assertGreaterEqual(output.manas_score, 0.0)
            self.assertLessEqual(output.manas_score, 1.0)

    def test_gate_mechanism(self):
        """测试行动门"""
        manas = ManasEngine()

        output = manas.compute()

        if output.manas_score > 0.5:
            self.assertTrue(output.should_act)
        else:
            self.assertFalse(output.should_act)

    def test_record_pnl(self):
        """测试记录盈亏"""
        manas = ManasEngine()

        manas.record_pnl(0.05)
        manas.record_pnl(0.03)
        manas.record_pnl(-0.02)

        self.assertEqual(len(manas._recent_pnl), 3)

    def test_reset_bias(self):
        """测试重置偏差"""
        manas = ManasEngine()
        manas.meta_manas.bias_state = BiasState.GREED

        manas.reset_bias()

        self.assertEqual(manas.meta_manas.bias_state, BiasState.NEUTRAL)

    def test_get_state(self):
        """测试获取状态"""
        manas = ManasEngine()
        manas.compute()

        state = manas.get_state()

        self.assertIsInstance(state, dict)
        self.assertIn('manas_score', state)

    def test_alpha_calculation(self):
        """测试 alpha 计算"""
        manas = ManasEngine()
        output = manas.compute()

        self.assertGreaterEqual(output.alpha, 0.3)
        self.assertLessEqual(output.alpha, 1.5)

    def test_bias_correction_range(self):
        """测试偏差修正范围"""
        manas = ManasEngine()

        for i in range(20):
            output = manas.compute()

            self.assertGreaterEqual(output.bias_correction, 0.5)
            self.assertLessEqual(output.bias_correction, 1.0)


class TestManasEngineIntegration(unittest.TestCase):
    """ManasEngine 集成测试"""

    def test_multiple_compute(self):
        """测试多次计算"""
        manas = ManasEngine()

        outputs = []
        for _ in range(10):
            output = manas.compute()
            outputs.append(output)

        self.assertEqual(len(outputs), 10)

        for out in outputs:
            self.assertIsInstance(out.manas_score, float)

    def test_pnl_feedback_loop(self):
        """测试盈亏反馈循环"""
        manas = ManasEngine()

        initial_output = manas.compute()

        for _ in range(5):
            manas.record_pnl(0.05)

        after_greed_output = manas.compute()

        self.assertIsInstance(after_greed_output.manas_score, float)

    def test_timing_consistency(self):
        """测试时机一致性"""
        manas = ManasEngine()

        outputs = []
        for _ in range(5):
            output = manas.compute()
            outputs.append(output)

        timing_scores = [o.timing_score for o in outputs]

        for ts in timing_scores:
            self.assertGreaterEqual(ts, 0.0)
            self.assertLessEqual(ts, 1.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
