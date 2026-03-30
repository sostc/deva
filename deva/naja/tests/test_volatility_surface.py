"""
VolatilitySurfaceSense 单元测试
"""

import unittest
from deva.naja.senses.volatility_surface import (
    VolatilitySurfaceSense,
    IVSkewAnalyzer,
    TermStructureAnalyzer,
    VolatilityRegimeDetector,
    IVSurfaceAnalyzer,
    VolatilitySignalGenerator,
    VolatilityRegime,
    VolatilitySignal,
    VolatilitySurface,
    VolatilityAlert,
)


class TestIVSkewAnalyzer(unittest.TestCase):
    """IVSkewAnalyzer 测试"""

    def setUp(self):
        self.analyzer = IVSkewAnalyzer()

    def test_calculate_skew_normal(self):
        """测试正常偏度"""
        skew = self.analyzer.calculate_skew(
            otm_put_iv=0.28,
            atm_iv=0.25,
            otm_call_iv=0.23
        )
        self.assertGreater(skew, 0)
        self.assertAlmostEqual(skew, 0.12, places=2)

    def test_calculate_skew_panic(self):
        """测试恐慌市场偏度"""
        skew = self.analyzer.calculate_skew(
            otm_put_iv=0.40,
            atm_iv=0.25,
            otm_call_iv=0.20
        )
        self.assertGreater(skew, 0.5)

    def test_detect_skew_anomaly(self):
        """测试偏度异常检测"""
        for i in range(10):
            self.analyzer.calculate_skew(0.26 + i*0.002, 0.25, 0.23)

        alert = self.analyzer.detect_skew_anomaly(0.6)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.signal, VolatilitySignal.IV_SKEW)


class TestTermStructureAnalyzer(unittest.TestCase):
    """TermStructureAnalyzer 测试"""

    def setUp(self):
        self.analyzer = TermStructureAnalyzer()

    def test_calculate_term_structure_normal(self):
        """测试正常期限结构"""
        term = self.analyzer.calculate_term_structure(
            short_term_iv=0.22,
            mid_term_iv=0.25,
            long_term_iv=0.28
        )
        self.assertLess(term, 1.0)

    def test_detect_term_anomaly(self):
        """测试期限结构异常检测"""
        for i in range(10):
            self.analyzer.calculate_term_structure(0.20 + i*0.002, 0.25, 0.28)

        alert = self.analyzer.detect_term_anomaly(0.4)  # 0.4 vs avg 0.74, diff=0.34>0.3
        self.assertIsNotNone(alert)
        self.assertEqual(alert.signal, VolatilitySignal.TERM_STRUCTURE)


class TestVolatilityRegimeDetector(unittest.TestCase):
    """VolatilityRegimeDetector 测试"""

    def setUp(self):
        self.detector = VolatilityRegimeDetector()

    def test_detect_low_stable(self):
        """测试低位稳定"""
        regime = self.detector.detect_regime(
            current_iv=0.12,
            historical_vol=0.15,
            iv_change=0.05
        )
        self.assertEqual(regime, VolatilityRegime.LOW_STABLE)

    def test_detect_spike(self):
        """测试波动率飙升"""
        regime = self.detector.detect_regime(
            current_iv=0.35,
            historical_vol=0.15,
            iv_change=0.5
        )
        self.assertEqual(regime, VolatilityRegime.SPIKE)

    def test_detect_high_volatile(self):
        """测试高位波动"""
        regime = self.detector.detect_regime(
            current_iv=0.35,
            historical_vol=0.25,
            iv_change=0.2
        )
        self.assertEqual(regime, VolatilityRegime.HIGH_VOLATILE)

    def test_predict_regime_change(self):
        """测试状态转换预测 - 检测已知状态"""
        detector2 = VolatilityRegimeDetector()
        for _ in range(10):
            detector2.detect_regime(0.15, 0.15, 0.05)

        regime = detector2.detect_regime(0.30, 0.15, 0.4)
        self.assertEqual(regime.value, "spike")


class TestIVSurfaceAnalyzer(unittest.TestCase):
    """IVSurfaceAnalyzer 测试"""

    def setUp(self):
        self.analyzer = IVSurfaceAnalyzer()

    def test_analyze_normal(self):
        """测试正常曲面分析"""
        surface = self.analyzer.analyze(
            symbol="000001",
            atm_iv=0.25,
            otm_put_iv=0.28,
            otm_call_iv=0.23,
            short_term_iv=0.22,
            long_term_iv=0.28,
            historical_vol=0.20,
            iv_history=[0.24, 0.25, 0.26, 0.25, 0.27]
        )

        self.assertEqual(surface.symbol, "000001")
        self.assertGreater(surface.current_iv, 0)
        self.assertIsNotNone(surface.regime)


class TestVolatilitySignalGenerator(unittest.TestCase):
    """VolatilitySignalGenerator 测试"""

    def setUp(self):
        self.generator = VolatilitySignalGenerator()

    def test_generate_iv_low_signal(self):
        """测试IV偏低信号"""
        surface = VolatilitySurface(
            symbol="000001",
            current_iv=0.10,
            iv_skew=0.1,
            term_structure=0.8,
            regime=VolatilityRegime.LOW_STABLE,
            regime_confidence=0.8,
            historical_vol=0.25,
            iv_hv_ratio=0.4,
            timestamp=0
        )

        alerts = self.generator.generate_signals(surface)
        self.assertTrue(len(alerts) > 0)
        self.assertEqual(alerts[0].signal, VolatilitySignal.IV_LOW)

    def test_generate_iv_high_signal(self):
        """测试IV偏高信号"""
        surface = VolatilitySurface(
            symbol="000001",
            current_iv=0.40,
            iv_skew=0.3,
            term_structure=0.9,
            regime=VolatilityRegime.HIGH_VOLATILE,
            regime_confidence=0.7,
            historical_vol=0.20,
            iv_hv_ratio=2.0,
            timestamp=0
        )

        alerts = self.generator.generate_signals(surface)
        iv_high_alerts = [a for a in alerts if a.signal == VolatilitySignal.IV_HIGH]
        self.assertTrue(len(iv_high_alerts) > 0)

    def test_generate_spike_warning(self):
        """测试波动率飙升预警"""
        surface = VolatilitySurface(
            symbol="000001",
            current_iv=0.45,
            iv_skew=0.5,
            term_structure=1.2,
            regime=VolatilityRegime.SPIKE,
            regime_confidence=0.9,
            historical_vol=0.20,
            iv_hv_ratio=2.25,
            timestamp=0
        )

        alerts = self.generator.generate_signals(surface)
        spike_alerts = [a for a in alerts if a.signal == VolatilitySignal.SPIKE_WARNING]
        self.assertTrue(len(spike_alerts) > 0)


class TestVolatilitySurfaceSense(unittest.TestCase):
    """VolatilitySurfaceSense 综合测试"""

    def setUp(self):
        self.sense = VolatilitySurfaceSense()

    def test_sense_with_options_data(self):
        """测试有期权数据的情况"""
        market_data = {}
        options_data = {
            "symbol": "000001",
            "atm_iv": 0.15,  # 低IV
            "otm_put_iv": 0.18,
            "otm_call_iv": 0.13,
            "short_term_iv": 0.13,
            "long_term_iv": 0.18,
            "historical_vol": 0.30,
            "iv_history": [0.14, 0.15, 0.16, 0.15, 0.15]
        }

        alert = self.sense.sense(market_data, options_data)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.signal, VolatilitySignal.IV_LOW)

    def test_sense_estimate_from_market(self):
        """测试从市场数据估算"""
        market_data = {
            "symbol": "000001",
            "price": 10.0,
            "price_change": 0.5,
            "volatility": 0.20
        }

        options_data = self.sense._estimate_from_market_data(market_data)

        self.assertEqual(options_data["symbol"], "000001")
        self.assertGreater(options_data["atm_iv"], 0)

    def test_get_current_surface(self):
        """测试获取当前曲面"""
        market_data = {"symbol": "000001", "price": 10.0, "price_change": 0.5}
        self.sense.sense(market_data, None)

        surface = self.sense.get_current_surface()
        self.assertIsNotNone(surface)

    def test_get_regime(self):
        """测试获取波动率状态"""
        market_data = {"symbol": "000001", "price": 10.0, "price_change": 0.5}
        self.sense.sense(market_data, None)

        regime = self.sense.get_regime()
        self.assertIsNotNone(regime)


if __name__ == "__main__":
    unittest.main()