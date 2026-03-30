"""
Alaya & Manas 单元测试
"""

import unittest
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deva.naja.alaya.seed_illuminator import (
    SeedIlluminator, IlluminatedPattern, PatternType, PatternTemplate
)
from deva.naja.manas.adaptive_manas import (
    AdaptiveManas, WuWeiDecision, HarmonyState,
    TianShiResponse, RegimeHarmony, RenShiResponse
)


class TestSeedIlluminator(unittest.TestCase):
    """光明藏测试"""

    def test_recall_momentum(self):
        """测试动量模式召回"""
        s = SeedIlluminator()
        patterns = s.recall({
            'price_change': 0.05,
            'volume_ratio': 2.0,
            'symbols': ['TEST']
        })
        self.assertIsInstance(patterns, list)

    def test_recall_reversal(self):
        """测试反转模式召回"""
        s = SeedIlluminator()
        patterns = s.recall({
            'price_change': -0.08,
            'volume_ratio': 2.5,
            'breadth_ratio': 0.3,
            'symbols': ['TEST']
        })
        self.assertIsInstance(patterns, list)

    def test_register_market_state(self):
        """测试注册市场状态"""
        s = SeedIlluminator()
        s.register_market_state({'price': 10.0, 'volume': 1000})
        self.assertGreater(len(s._market_state_history), 0)

    def test_record_outcome(self):
        """测试记录结果"""
        s = SeedIlluminator()
        s.record_outcome(PatternType.MOMENTUM, success=True, holding_period=3600)
        stats = s._pattern_match_stats.get(PatternType.MOMENTUM.value)
        self.assertIsNotNone(stats)
        self.assertEqual(stats['matches'], 1)
        self.assertEqual(stats['successes'], 1)


class TestAdaptiveManas(unittest.TestCase):
    """顺应型末那识测试"""

    def test_resonance_decision(self):
        """测试共振决策"""
        m = AdaptiveManas()
        decision = m.compute_顺应({
            'is_market_open': True,
            'volatility': 1.0,
            'trend_strength': 0.8,
            'time_of_day': 10.0,
            'regime': 'trend',
            'regime_stability': 0.8,
            'market_breadth': 0.5
        }, confidence=0.8)
        self.assertIsInstance(decision, WuWeiDecision)
        self.assertIn(decision.harmony_state, HarmonyState)

    def test_resistance_decision(self):
        """测试不利条件下不应行动"""
        m = AdaptiveManas()
        decision = m.compute_顺应({
            'is_market_open': False,
            'volatility': 3.0,
            'trend_strength': 0.1,
            'time_of_day': 3.0,
            'regime': 'unknown',
            'regime_stability': 0.2,
            'market_breadth': 0.0
        }, confidence=0.3)
        self.assertIsInstance(decision, WuWeiDecision)
        self.assertFalse(decision.should_act)

    def test_traditional_compute(self):
        """测试传统计算方式"""
        m = AdaptiveManas()
        decision = m.compute_traditional(manas_score=0.7)
        self.assertIsInstance(decision, WuWeiDecision)


class TestTianShiResponse(unittest.TestCase):
    """天时响应测试"""

    def test_evaluate(self):
        """测试评估"""
        t = TianShiResponse()
        score = t.evaluate({
            'is_market_open': True,
            'volatility': 1.0,
            'trend_strength': 0.5,
            'time_of_day': 10.0
        })
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


class TestRegimeHarmony(unittest.TestCase):
    """环境和谐测试"""

    def test_evaluate(self):
        """测试评估"""
        r = RegimeHarmony()
        harmony, state = r.evaluate('trend', 0.7, 0.3)
        self.assertGreaterEqual(harmony, 0.0)
        self.assertLessEqual(harmony, 1.0)
        self.assertIn(state, HarmonyState)


class TestRenShiResponse(unittest.TestCase):
    """人时响应测试"""

    def test_evaluate(self):
        """测试评估"""
        r = RenShiResponse()
        score = r.evaluate(confidence=0.7, risk_appetite=0.5, recent_success_rate=0.6)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
