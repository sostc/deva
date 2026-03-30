"""
PreTasteSense 单元测试
"""

import unittest
from deva.naja.senses.pre_taste import (
    PreTasteSense,
    MomentumTaster,
    LiquidityTaster,
    ValuationTaster,
    RiskTaster,
    CompositeTaster,
    TasteQuality,
    PreTasteResult,
)


class TestMomentumTaster(unittest.TestCase):
    """MomentumTaster 测试"""

    def setUp(self):
        self.taster = MomentumTaster()

    def test_taste_bullish(self):
        """测试上涨动量"""
        data = {
            "price_changes": [1.0, 2.0, 3.0, 4.0, 5.0]
        }
        result = self.taster.taste("000001", data)
        self.assertGreater(result["momentum_score"], 0.5)

    def test_taste_bearish(self):
        """测试下跌动量"""
        data = {
            "price_changes": [-1.0, -2.0, -3.0, -4.0, -5.0]
        }
        result = self.taster.taste("000001", data)
        self.assertLess(result["momentum_score"], 0.5)


class TestLiquidityTaster(unittest.TestCase):
    """LiquidityTaster 测试"""

    def setUp(self):
        self.taster = LiquidityTaster()

    def test_taste_high_liquidity(self):
        """测试高流动性"""
        data = {
            "volume": 10000000,
            "amount": 100000000,
            "price": 10.0,
            "avg_volume": 5000000
        }
        result = self.taster.taste("000001", data)
        self.assertGreater(result["liquidity_score"], 0.5)


class TestValuationTaster(unittest.TestCase):
    """ValuationTaster 测试"""

    def setUp(self):
        self.taster = ValuationTaster()

    def test_taste_cheap(self):
        """测试低估"""
        data = {
            "pe_ratio": 8.0,
            "pb_ratio": 1.0,
            "roe": 0.2,
            "growth": 0.3
        }
        result = self.taster.taste("000001", data)
        self.assertGreater(result["valuation_score"], 0.6)

    def test_taste_expensive(self):
        """测试高估"""
        data = {
            "pe_ratio": 150.0,
            "pb_ratio": 20.0,
            "roe": 0.01,
            "growth": -0.2
        }
        result = self.taster.taste("000001", data)
        self.assertLess(result["valuation_score"], 0.4)


class TestCompositeTaster(unittest.TestCase):
    """CompositeTaster 测试"""

    def setUp(self):
        self.taster = CompositeTaster()

    def test_taste_all(self):
        """测试综合品尝"""
        price_data = {"price_changes": [1.0, 2.0, 3.0, 4.0, 5.0]}
        volume_data = {"volume": 10000000, "amount": 100000000, "price": 10.0, "avg_volume": 5000000}
        valuation_data = {"pe_ratio": 15.0, "pb_ratio": 2.0, "roe": 0.15, "growth": 0.2}
        risk_data = {"volatility": 0.2, "beta": 1.0, "max_drawdown": 0.1}

        result = self.taster.taste_all(
            "000001", price_data, volume_data, valuation_data, risk_data
        )

        self.assertIsInstance(result, PreTasteResult)
        self.assertGreater(result.score, 0)
        self.assertLess(result.score, 1)
        self.assertIsNotNone(result.recommended_action)

    def test_taste_excellent(self):
        """测试绝佳品质"""
        price_data = {"price_changes": [2.0, 3.0, 4.0, 5.0, 6.0]}
        volume_data = {"volume": 20000000, "amount": 200000000, "price": 10.0, "avg_volume": 5000000}
        valuation_data = {"pe_ratio": 8.0, "pb_ratio": 1.0, "roe": 0.25, "growth": 0.4}
        risk_data = {"volatility": 0.15, "beta": 0.8, "max_drawdown": 0.05}

        result = self.taster.taste_all(
            "000001", price_data, volume_data, valuation_data, risk_data
        )

        self.assertEqual(result.quality, TasteQuality.EXCELLENT)


class TestPreTasteSense(unittest.TestCase):
    """PreTasteSense 综合测试"""

    def setUp(self):
        self.sense = PreTasteSense()

    def test_pre_taste(self):
        """测试预尝"""
        market_data = {
            "price_changes": [1.0, 2.0, 3.0, 4.0, 5.0],
            "volume": 10000000,
            "amount": 100000000,
            "price": 10.0,
            "avg_volume": 5000000,
            "pe_ratio": 15.0,
            "pb_ratio": 2.0,
            "roe": 0.15,
            "growth": 0.2,
            "volatility": 0.2,
            "beta": 1.0,
            "max_drawdown": 0.1
        }

        result = self.sense.pre_taste("000001", market_data)

        self.assertIsInstance(result, PreTasteResult)
        self.assertGreater(result.score, 0)
        self.assertLess(result.score, 1)
        self.assertTrue(len(result.flavors) > 0 or len(result.risk_flavors) > 0)

    def test_get_cached_taste(self):
        """测试获取缓存"""
        market_data = {"price_changes": [1.0, 2.0], "volume": 100000, "amount": 1000000, "price": 10.0}
        self.sense.pre_taste("000001", market_data)

        cached = self.sense.get_cached_taste("000001")
        self.assertIsNotNone(cached)

    def test_compare_opportunities(self):
        """测试比较机会"""
        market_data = {
            "000001": {"price_changes": [1.0, 2.0, 3.0, 4.0, 5.0], "volume": 10000000, "amount": 100000000, "price": 10.0},
            "000002": {"price_changes": [-1.0, -2.0, -3.0, -4.0, -5.0], "volume": 5000000, "amount": 50000000, "price": 10.0}
        }

        results = self.sense.compare_opportunities(["000001", "000002"], market_data)

        self.assertEqual(len(results), 2)
        self.assertGreater(list(results.values())[0].score, list(results.values())[1].score)


if __name__ == "__main__":
    unittest.main()