"""
PositionSizer 单元测试
"""

import unittest
from deva.naja.risk.position_sizer import (
    PositionSizer,
    KellySizer,
    VolatilitySizer,
    ConfidenceSizer,
    RiskParitySizer,
    SizingMethod,
    PositionSize,
)


class TestKellySizer(unittest.TestCase):
    """KellySizer 测试"""

    def setUp(self):
        self.sizer = KellySizer()

    def test_calculate_positive_expectation(self):
        """测试正期望"""
        result = self.sizer.calculate(
            win_rate=0.6,
            avg_win=1000,
            avg_loss=500,
            total_capital=100000
        )

        self.assertGreater(result.size_ratio, 0)
        self.assertEqual(result.method, SizingMethod.KELLY)

    def test_calculate_negative_expectation(self):
        """测试负期望"""
        result = self.sizer.calculate(
            win_rate=0.3,
            avg_win=500,
            avg_loss=1000,
            total_capital=100000
        )

        self.assertEqual(result.size_ratio, 0)

    def test_calculate_max_ratio_limit(self):
        """测试上限限制"""
        result = self.sizer.calculate(
            win_rate=0.9,
            avg_win=10000,
            avg_loss=100,
            total_capital=100000
        )

        self.assertLessEqual(result.size_ratio, 0.25)


class TestVolatilitySizer(unittest.TestCase):
    """VolatilitySizer 测试"""

    def setUp(self):
        self.sizer = VolatilitySizer()

    def test_calculate_normal(self):
        """测试正常波动率"""
        result = self.sizer.calculate(
            symbol="000001",
            current_volatility=0.3,
            price=10.0,
            total_capital=100000
        )

        self.assertGreater(result.size_ratio, 0)
        self.assertEqual(result.symbol, "000001")

    def test_calculate_low_volatility(self):
        """测试低波动率"""
        result = self.sizer.calculate(
            symbol="000001",
            current_volatility=0.1,
            price=10.0,
            total_capital=100000
        )

        self.assertGreater(result.size_ratio, 0.3)


class TestConfidenceSizer(unittest.TestCase):
    """ConfidenceSizer 测试"""

    def setUp(self):
        self.sizer = ConfidenceSizer()

    def test_calculate_high_confidence(self):
        """测试高置信度"""
        result = self.sizer.calculate(
            symbol="000001",
            signal_confidence=0.9,
            price=10.0,
            total_capital=100000
        )

        self.assertGreater(result.size_ratio, 0.05)

    def test_calculate_low_confidence(self):
        """测试低置信度"""
        result = self.sizer.calculate(
            symbol="000001",
            signal_confidence=0.3,
            price=10.0,
            total_capital=100000
        )

        self.assertLess(result.size_ratio, 0.05)


class TestRiskParitySizer(unittest.TestCase):
    """RiskParitySizer 测试"""

    def setUp(self):
        self.sizer = RiskParitySizer()

    def test_calculate_for_portfolio(self):
        """测试组合仓位"""
        positions = {
            "000001": {"quantity": 1000, "price": 10.0},
            "000002": {"quantity": 500, "price": 20.0},
        }
        volatilities = {
            "000001": 0.3,
            "000002": 0.2,
        }

        result = self.sizer.calculate_for_portfolio(positions, volatilities, 100000)

        self.assertEqual(len(result), 2)
        for r in result:
            self.assertGreater(r.size_ratio, 0)


class TestPositionSizer(unittest.TestCase):
    """PositionSizer 综合测试"""

    def setUp(self):
        self.sizer = PositionSizer()

    def test_calculate_size_kelly(self):
        """测试Kelly方法"""
        result = self.sizer.calculate_size(
            symbol="000001",
            price=10.0,
            total_capital=100000,
            method=SizingMethod.KELLY,
            win_rate=0.6,
            avg_win=1000,
            avg_loss=500
        )

        self.assertEqual(result.method, SizingMethod.KELLY)

    def test_calculate_size_volatility(self):
        """测试波动率方法"""
        result = self.sizer.calculate_size(
            symbol="000001",
            price=10.0,
            total_capital=100000,
            method=SizingMethod.VOLATILITY,
            current_volatility=0.3
        )

        self.assertEqual(result.method, SizingMethod.VOLATILITY)

    def test_calculate_optimal_size(self):
        """测试最优仓位"""
        result = self.sizer.calculate_optimal_size(
            symbol="000001",
            price=10.0,
            total_capital=100000,
            signal_confidence=0.7,
            win_rate=0.6,
            volatility=0.3
        )

        self.assertGreater(result.size_ratio, 0)
        self.assertLessEqual(result.size_ratio, 0.3)


if __name__ == "__main__":
    unittest.main()