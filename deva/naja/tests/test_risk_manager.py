"""
RiskManager 单元测试
"""

import unittest
from deva.naja.risk.risk_manager import (
    RiskManager,
    PositionRiskMonitor,
    MarketRiskDetector,
    RiskControlRules,
    RiskLevel,
    RiskType,
    RiskAlert,
)


class TestPositionRiskMonitor(unittest.TestCase):
    """PositionRiskMonitor 测试"""

    def setUp(self):
        self.monitor = PositionRiskMonitor()

    def test_monitor_normal(self):
        """测试正常持仓"""
        positions = {
            "000001": {"quantity": 500, "cost": 10.0, "current_price": 11.0},
            "000002": {"quantity": 300, "cost": 20.0, "current_price": 21.0},
            "000003": {"quantity": 400, "cost": 15.0, "current_price": 16.0},
            "000004": {"quantity": 200, "cost": 25.0, "current_price": 26.0},
            "000005": {"quantity": 300, "cost": 8.0, "current_price": 8.5},
        }
        alerts = self.monitor.monitor(positions, 50000)
        overweight_alerts = [a for a in alerts if a.risk_type == RiskType.SINGLE_POSITION]
        self.assertEqual(len(overweight_alerts), 0)

    def test_monitor_overweight(self):
        """测试超重仓位"""
        positions = {
            "000001": {"quantity": 5000, "cost": 10.0, "current_price": 15.0}
        }
        alerts = self.monitor.monitor(positions, 50000)
        self.assertGreater(len(alerts), 0)
        self.assertEqual(alerts[0].risk_type, RiskType.SINGLE_POSITION)

    def test_monitor_total_exposure(self):
        """测试总仓位"""
        positions = {
            "000001": {"quantity": 2000, "cost": 10.0, "current_price": 12.0},
            "000002": {"quantity": 2000, "cost": 10.0, "current_price": 12.0},
        }
        alerts = self.monitor.monitor(positions, 50000)
        total_alerts = [a for a in alerts if a.risk_type == RiskType.TOTAL_POSITION]
        self.assertGreater(len(total_alerts), 0)

    def test_monitor_concentration(self):
        """测试集中度"""
        positions = {
            "000001": {"quantity": 1000, "cost": 10.0, "current_price": 11.0}
        }
        alerts = self.monitor.monitor(positions, 50000)
        conc_alerts = [a for a in alerts if a.risk_type == RiskType.CONCENTRATION]
        self.assertGreater(len(conc_alerts), 0)


class TestMarketRiskDetector(unittest.TestCase):
    """MarketRiskDetector 测试"""

    def setUp(self):
        self.detector = MarketRiskDetector()

    def test_detect_high_volatility(self):
        """测试高波动率检测"""
        market_data = {"market_volatility": 2.8}
        market_state = {}

        alerts = self.detector.detect(market_data, market_state)
        vol_alerts = [a for a in alerts if a.risk_type == RiskType.VOLATILITY]
        self.assertGreater(len(vol_alerts), 0)

    def test_detect_extreme_breadth(self):
        """测试极端广度检测"""
        market_data = {}
        market_state = {"market_breadth": 0.7}

        alerts = self.detector.detect(market_data, market_state)
        self.assertGreater(len(alerts), 0)


class TestRiskControlRules(unittest.TestCase):
    """RiskControlRules 测试"""

    def setUp(self):
        self.rules = RiskControlRules()

    def test_check_rules_loss(self):
        """测试亏损规则"""
        positions = {}
        market_data = {"total_assets": 100000}
        daily_pnl = -0.06

        alerts = self.rules.check_rules(positions, market_data, daily_pnl)
        self.assertGreater(len(alerts), 0)


class TestRiskManager(unittest.TestCase):
    """RiskManager 综合测试"""

    def setUp(self):
        self.manager = RiskManager()

    def test_assess_risk_normal(self):
        """测试正常风险评估"""
        positions = {
            "000001": {"quantity": 500, "cost": 10.0, "current_price": 11.0},
            "000002": {"quantity": 300, "cost": 20.0, "current_price": 21.0},
            "000003": {"quantity": 400, "cost": 15.0, "current_price": 16.0},
            "000004": {"quantity": 200, "cost": 25.0, "current_price": 26.0},
            "000005": {"quantity": 300, "cost": 8.0, "current_price": 8.5},
        }
        market_data = {"market_volatility": 1.0, "liquidity_score": 0.8}
        market_state = {"trend_strength": 0.3, "market_breadth": 0.1}

        metrics = self.manager.assess_risk(positions, market_data, market_state, 50000)

        self.assertIsInstance(metrics.risk_level, RiskLevel)
        self.assertLessEqual(metrics.overall_risk_score, 0.5)

    def test_assess_risk_high(self):
        """测试高风险评估"""
        positions = {
            "000001": {"quantity": 10000, "cost": 10.0, "current_price": 15.0}
        }
        market_data = {"market_volatility": 3.0, "liquidity_score": 0.5}
        market_state = {"trend_strength": 0.9, "market_breadth": 0.8}

        metrics = self.manager.assess_risk(positions, market_data, market_state, 50000)

        self.assertGreater(metrics.overall_risk_score, 0.5)

    def test_get_alert_summary(self):
        """测试警报摘要"""
        positions = {"000001": {"quantity": 10000, "cost": 10.0, "current_price": 15.0}}
        market_data = {"market_volatility": 3.0}
        market_state = {}

        self.manager.assess_risk(positions, market_data, market_state, 50000)

        summary = self.manager.get_alert_summary()
        self.assertGreater(summary["total"], 0)


if __name__ == "__main__":
    unittest.main()