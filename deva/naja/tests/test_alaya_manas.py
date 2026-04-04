"""
Alaya & Manas 单元测试

测试 ManasEngine 和 AwakenedAlaya 的集成
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deva.naja.alaya.seed_illuminator import (
    SeedIlluminator, IlluminatedPattern, PatternType, PatternTemplate
)
from deva.naja.attention.trading_center import get_trading_center
from deva.naja.manas import HarmonyState


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


class TestManasEngine(unittest.TestCase):
    """ManasEngine 测试"""

    def setUp(self):
        """设置测试"""
        self.tc = get_trading_center()
        self.manas = self.tc.get_attention_os().kernel.get_manas_engine()

    def test_basic_compute(self):
        """测试基本计算"""
        output = self.manas.compute(
            portfolio={},
            scanner=None,
            bandit_tracker=None,
            macro_signal=0.5,
            narratives=[]
        )
        self.assertIsNotNone(output)
        self.assertIsInstance(output.manas_score, float)
        self.assertGreaterEqual(output.manas_score, 0.0)
        self.assertLessEqual(output.manas_score, 1.0)

    def test_harmony_state(self):
        """测试和谐状态"""
        output = self.manas.compute(
            portfolio={},
            scanner=None,
            bandit_tracker=None,
            macro_signal=0.5,
            narratives=[]
        )
        self.assertIsInstance(output.harmony_state, HarmonyState)

    def test_should_act(self):
        """测试是否行动"""
        output = self.manas.compute(
            portfolio={},
            scanner=None,
            bandit_tracker=None,
            macro_signal=0.5,
            narratives=[]
        )
        self.assertIsInstance(output.should_act, bool)

    def test_action_type(self):
        """测试行动类型"""
        output = self.manas.compute(
            portfolio={},
            scanner=None,
            bandit_tracker=None,
            macro_signal=0.5,
            narratives=[]
        )
        self.assertIsNotNone(output.action_type)

    def test_to_dict(self):
        """测试转换为字典"""
        output = self.manas.compute(
            portfolio={},
            scanner=None,
            bandit_tracker=None,
            macro_signal=0.5,
            narratives=[]
        )
        d = output.to_dict()
        self.assertIsInstance(d, dict)
        self.assertIn('manas_score', d)
        self.assertIn('harmony_state', d)


class TestTradingCenterIntegration(unittest.TestCase):
    """TradingCenter 集成测试"""

    def test_trading_center_creation(self):
        """测试 TradingCenter 创建"""
        tc = get_trading_center()
        self.assertIsNotNone(tc)
        self.assertIsNotNone(tc.attention_os)

    def test_make_decision(self):
        """测试做决策"""
        tc = get_trading_center()
        decision = tc.make_decision({'macro_liquidity_signal': 0.5}, None)
        self.assertIsNotNone(decision)
        self.assertIsInstance(decision.should_act, bool)

    def test_get_harmony(self):
        """测试获取和谐状态"""
        tc = get_trading_center()
        harmony = tc.get_harmony()
        self.assertIsInstance(harmony, dict)
        self.assertIn('harmony_strength', harmony)


if __name__ == '__main__':
    unittest.main(verbosity=2)
