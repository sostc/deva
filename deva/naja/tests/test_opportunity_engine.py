"""
OpportunityEngine 单元测试
"""

import unittest
import time
from deva.naja.evolution.opportunity_engine import (
    OpportunityEngine,
    OpportunityScanner,
    TimingOptimizer,
    OpportunityType,
    OpportunityStage,
    Opportunity,
    TimingSignal,
)


class TestOpportunityScanner(unittest.TestCase):
    """OpportunityScanner 测试"""

    def setUp(self):
        self.scanner = OpportunityScanner()

    def test_scan_momentum(self):
        """测试动量机会扫描"""
        market_data = {
            "sector_changes": {
                "科技": 3.5,
                "新能源": 2.5,
                "消费": 0.5
            }
        }

        opportunities = self.scanner.scan(market_data)
        momentum_opps = [o for o in opportunities if o.opportunity_type == OpportunityType.MOMENTUM]

        self.assertTrue(len(momentum_opps) > 0)
        self.assertEqual(momentum_opps[0].opportunity_type, OpportunityType.MOMENTUM)

    def test_scan_reversal(self):
        """测试反转机会扫描"""
        market_data = {
            "sector_changes": {
                "煤炭": -3.5,
                "钢铁": -2.0,
                "消费": 0.5
            }
        }

        opportunities = self.scanner.scan(market_data)
        reversal_opps = [o for o in opportunities if o.opportunity_type == OpportunityType.REVERSAL]

        self.assertTrue(len(reversal_opps) > 0)
        self.assertEqual(reversal_opps[0].opportunity_type, OpportunityType.REVERSAL)

    def test_scan_sector_rotation(self):
        """测试板块轮动扫描"""
        market_data = {
            "sector_changes": {
                "科技": 1.0,
                "金融": 0.5,
                "消费": 0.0,
                "基建": -1.0,
                "地产": -1.5
            }
        }

        opportunities = self.scanner.scan(market_data)
        rotation_opps = [o for o in opportunities if o.opportunity_type == OpportunityType.SECTOR_ROTATION]

        self.assertTrue(len(rotation_opps) > 0)

    def test_clean_expired(self):
        """测试过期清理"""
        market_data = {"sector_changes": {"科技": 3.0}}
        self.scanner.scan(market_data)

        for opp in self.scanner._opportunities.values():
            opp.expires_at = time.time() - 1

        self.scanner._clean_expired()
        self.assertEqual(len(self.scanner._opportunities), 0)

    def test_get_active_opportunities(self):
        """测试获取活跃机会"""
        market_data = {"sector_changes": {"科技": 3.0, "新能源": 2.0}}
        self.scanner.scan(market_data)

        active = self.scanner.get_active_opportunities()
        self.assertTrue(len(active) > 0)


class TestTimingOptimizer(unittest.TestCase):
    """TimingOptimizer 测试"""

    def setUp(self):
        self.optimizer = TimingOptimizer()

    def test_optimize_entry_ready(self):
        """测试就绪状态入场优化"""
        opportunity = Opportunity(
            opportunity_type=OpportunityType.MOMENTUM,
            symbol="000001",
            confidence=0.8,
            stage=OpportunityStage.READY,
            expected_return=0.05,
            risk_level=0.3,
            entry_timing="立即",
            entry_horizon=300,
            evidence=[],
            created_at=time.time(),
            expires_at=time.time() + 100
        )

        signal = self.optimizer.optimize_entry(opportunity, {})

        self.assertEqual(signal.signal_type, "entry")
        self.assertGreater(signal.urgency, 0.5)

    def test_optimize_entry_confirming(self):
        """测试确认状态入场优化"""
        opportunity = Opportunity(
            opportunity_type=OpportunityType.MOMENTUM,
            symbol="000001",
            confidence=0.6,
            stage=OpportunityStage.CONFIRMING,
            expected_return=0.05,
            risk_level=0.3,
            entry_timing="等待确认",
            entry_horizon=1800,
            evidence=[],
            created_at=time.time(),
            expires_at=time.time() + 1800
        )

        signal = self.optimizer.optimize_entry(opportunity, {})
        self.assertEqual(signal.urgency, 0.5)

    def test_optimize_exit_profit(self):
        """测试盈利出场优化"""
        position = {
            "floating_pnl": 0.08,
            "holding_time": 600
        }

        signal = self.optimizer.optimize_exit(position, {})
        self.assertIn(signal.signal_type, ["exit", "increase"])

    def test_optimize_exit_loss(self):
        """测试亏损出场优化"""
        position = {
            "floating_pnl": -0.05,
            "holding_time": 300
        }

        signal = self.optimizer.optimize_exit(position, {})
        self.assertEqual(signal.signal_type, "exit")
        self.assertGreater(signal.urgency, 0.5)

    def test_record_timing_result(self):
        """测试记录时机结果"""
        timing = TimingSignal(
            signal_type="entry",
            urgency=0.8,
            confidence=0.7,
            reason="测试",
            best_before=time.time() + 300
        )

        self.optimizer.record_timing_result(timing, True)
        self.optimizer.record_timing_result(timing, False)

        stats = self.optimizer.get_timing_stats()
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["success_rate"], 0.5)


class TestOpportunityEngine(unittest.TestCase):
    """OpportunityEngine 综合测试"""

    def setUp(self):
        self.engine = OpportunityEngine()

    def test_discover(self):
        """测试发现机会"""
        market_data = {
            "sector_changes": {
                "科技": 3.5,
                "新能源": 2.0,
                "消费": 0.5
            }
        }

        opportunities = self.engine.discover(market_data)
        self.assertTrue(len(opportunities) > 0)

    def test_get_timing(self):
        """测试获取时机"""
        opportunity = Opportunity(
            opportunity_type=OpportunityType.MOMENTUM,
            symbol="000001",
            confidence=0.8,
            stage=OpportunityStage.READY,
            expected_return=0.05,
            risk_level=0.3,
            entry_timing="立即",
            entry_horizon=300,
            evidence=[],
            created_at=time.time(),
            expires_at=time.time() + 100
        )

        signal = self.engine.get_timing(opportunity, {})
        self.assertIsInstance(signal, TimingSignal)

    def test_get_exit_timing(self):
        """测试获取出场时机"""
        position = {
            "floating_pnl": 0.06,
            "holding_time": 600
        }

        signal = self.engine.get_exit_timing(position, {})
        self.assertIsInstance(signal, TimingSignal)

    def test_get_summary(self):
        """测试获取摘要"""
        market_data = {"sector_changes": {"科技": 3.0}}
        self.engine.discover(market_data)

        summary = self.engine.get_summary()
        self.assertIn("active_opportunities", summary)
        self.assertIn("timing_stats", summary)


if __name__ == "__main__":
    unittest.main()