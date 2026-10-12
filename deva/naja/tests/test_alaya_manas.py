"""
Alaya & Manas 单元测试

测试 ManasEngine 和 AwakenedAlaya 的集成
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deva.naja.knowledge.alaya.seed_illuminator import (
    SeedIlluminator, IlluminatedPattern, PatternType, PatternTemplate
)
from deva.naja.attention.orchestration.trading_center import get_trading_center
from deva.naja.attention.kernel.manas_engine import HarmonyState


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

    def test_get_harmony(self):
        """测试获取和谐状态"""
        tc = get_trading_center()
        harmony = tc.get_harmony()
        self.assertIsInstance(harmony, dict)
        self.assertIn('harmony_strength', harmony)


class TestAttentionSchedulingGuard(unittest.TestCase):
    """钉死 `market_scheduler` 重命名遗留，防止静默失效复发。

    背景（2026-10-12 清理）：`AttentionOS` 上**从未存在** `market_scheduler`
    属性（真实属性是 `strategy_decision_maker`），但全仓曾有 6 处调用点引用它，
    且全部被 ``try/except`` 吞成静默 no-op —— ``process_datasource_data``
    永远失败、market_observer 的 Lab 模式推送、snapshot 的 symbol weights、
    home/ui/stats 的 registered_strategies 全部静默死掉。

    这里把三件事钉住：正确属性存在 / 坏名字没被悄悄加回来 /
    ``schedule_market()`` 真的产出权重（而不是又一条静默空路径）。
    """

    def test_strategy_decision_maker_is_the_real_attribute(self):
        from deva.naja.attention.os.attention_os import AttentionOS

        maker = getattr(AttentionOS(), "strategy_decision_maker", None)
        self.assertIsNotNone(maker, "AttentionOS 应暴露 strategy_decision_maker")
        self.assertTrue(hasattr(maker, "schedule"))
        self.assertTrue(hasattr(maker, "_symbol_weights"))
        self.assertTrue(hasattr(maker, "_block_weights"))

    def test_market_scheduler_alias_does_not_exist(self):
        """坏名字不该被悄悄加回来——加回来等于掩盖调用点拼错。"""
        from deva.naja.attention.os.attention_os import AttentionOS

        self.assertFalse(hasattr(AttentionOS(), "market_scheduler"))

    def test_schedule_market_really_returns_weights(self):
        """公开包装必须真的产出权重，而不是又一条静默空路径。"""
        from deva.naja.attention.os.attention_os import AttentionOS

        result = AttentionOS().schedule_market(
            {
                "symbol_weights": {"600000": 0.5, "000001": 0.3},
                "block_hotspot": {"AI": 1.0},
            }
        )
        self.assertIsInstance(result, dict)
        self.assertIn("symbol_weights", result)
        self.assertIn("frequency_level", result)
        self.assertIn("600000", result["symbol_weights"])

    def test_process_datasource_data_is_no_longer_silently_dead(self):
        """走通兼容入口，确认不再是 AttributeError 被吞掉的死路径。"""
        tc = get_trading_center()
        tc.process_datasource_data("replay", {"symbol_weights": {"600000": 0.5}})
        maker = tc.get_attention_os().strategy_decision_maker
        self.assertIn("600000", maker._symbol_weights)

    def test_no_source_references_market_scheduler(self):
        """全仓源码（deva/naja 包）不该再出现 `market_scheduler` 字样。"""
        import pathlib

        pkg_root = pathlib.Path(__file__).resolve().parents[1]  # deva/naja
        self_path = pathlib.Path(__file__).resolve()
        offenders = []
        for path in pkg_root.rglob("*.py"):
            if "__pycache__" in path.parts or path.resolve() == self_path:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "market_scheduler" in text:
                offenders.append(str(path.relative_to(pkg_root)))
        self.assertEqual(offenders, [], f"仍在引用 market_scheduler: {offenders}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
