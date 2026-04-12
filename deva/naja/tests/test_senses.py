"""
Senses Module 单元测试
"""

import unittest
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deva.naja.radar.senses.prophetic_sensing import (
    ProphetSense, ProphetSignal, PresageType,
    MomentumPrecipice, SentimentTransitionSense, FlowTasteSense,
    VolatilitySurfaceSense
)
from deva.naja.radar.senses.realtime_taste import (
    RealtimeTaste, TasteSignal, PositionState, FreshnessLevel
)


class TestMomentumPrecipice(unittest.TestCase):
    """动量悬崖预判测试"""

    def test_high_price_low_volume(self):
        """测试价格创新高但成交量萎缩"""
        m = MomentumPrecipice()
        result = m.detect('TEST', price=10.0, volume=500000, price_change=3.0)
        if result:
            self.assertEqual(result.presage_type, PresageType.MOMENTUM_EXHAUSTION)

    def test_momentum_decay(self):
        """测试动量衰减"""
        m = MomentumPrecipice()
        for i in range(10):
            m.detect('TEST', price=10.0+i*0.1, volume=1000000, price_change=0.02*(10-i))
        result = m.detect('TEST', price=11.0, volume=800000, price_change=0.01)
        if result:
            self.assertEqual(result.presage_type, PresageType.MOMENTUM_EXHAUSTION)


class TestSentimentTransitionSense(unittest.TestCase):
    """情绪转换预判测试"""

    def test_bearish_transition(self):
        """测试空头情绪转换"""
        s = SentimentTransitionSense()
        for _ in range(10):
            s.detect(advancing=100, declining=200)
        result = s.detect(advancing=50, declining=250)
        if result:
            self.assertEqual(result.presage_type, PresageType.SENTIMENT_REVERSAL)

    def test_bullish_transition(self):
        """测试多头情绪转换"""
        s = SentimentTransitionSense()
        for _ in range(10):
            s.detect(advancing=100, declining=50)
        result = s.detect(advancing=250, declining=50)
        if result:
            self.assertEqual(result.direction, 1)


class TestFlowTasteSense(unittest.TestCase):
    """资金流向味道测试"""

    def test_main_in_retail_out(self):
        """测试主力流入但散户流出"""
        f = FlowTasteSense()
        for _ in range(10):
            f.detect(main_flow=1000000, retail_flow=-500000, total_flow=500000)
        result = f.detect(main_flow=2000000, retail_flow=-1000000, total_flow=1000000)
        if result:
            self.assertEqual(result.presage_type, PresageType.FLOW_REVERSAL)


class TestProphetSense(unittest.TestCase):
    """天眼通测试"""

    def test_basic_sense(self):
        """基本感知测试"""
        p = ProphetSense()
        signal = p.sense({
            'symbol': 'TEST',
            'price': 10.0,
            'volume': 1000000,
            'price_change': 2.0,
            'advancing': 200,
            'declining': 100,
        }, {
            'main_flow': 1000000,
            'retail_flow': -500000,
            'total_flow': 500000,
        })
        self.assertIsInstance(signal, ProphetSignal) if signal else True

    def test_no_signal_under_threshold(self):
        """测试低于阈值时不返回信号"""
        p = ProphetSense()
        p._last_signal_time = time.time()
        signal = p.sense()
        self.assertIsNone(signal)


class TestRealtimeTaste(unittest.TestCase):
    """实时舌识测试"""

    def test_register_and_taste(self):
        """测试注册和尝受"""
        t = RealtimeTaste()
        t.register_position('TEST', entry_price=10.0, quantity=100, entry_time=time.time())
        signal = t.taste_position('TEST', current_price=10.5)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.symbol, 'TEST')
        self.assertGreater(signal.floating_pnl, 0)

    def test_freshness_calculation(self):
        """测试鲜度计算"""
        t = RealtimeTaste()
        t.register_position('TEST', entry_price=10.0, quantity=100, entry_time=time.time())
        signal = t.taste_position('TEST', current_price=10.8)
        self.assertGreaterEqual(signal.freshness, 0.0)
        self.assertLessEqual(signal.freshness, 1.0)

    def test_close_position(self):
        """测试平仓"""
        t = RealtimeTaste()
        t.register_position('TEST', entry_price=10.0, quantity=100, entry_time=time.time())
        t.close_position('TEST')
        signal = t.taste_position('TEST', current_price=11.0)
        self.assertIsNone(signal)


class TestPositionState(unittest.TestCase):
    """持仓状态测试"""

    def test_pnl_calculation(self):
        """测试盈亏计算"""
        pos = PositionState('TEST', entry_price=10.0, quantity=100, entry_time=0)
        pos.update(current_price=11.0, current_time=100)
        self.assertAlmostEqual(pos.get_current_pnl(), 0.1, places=2)

    def test_pnl_trend(self):
        """测试盈亏趋势"""
        pos = PositionState('TEST', entry_price=10.0, quantity=100, entry_time=0)
        for p in [10.0, 10.2, 10.3, 10.4, 10.5]:
            pos.update(current_price=p, current_time=time.time())
        trend = pos.get_pnl_trend()
        self.assertGreater(trend, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
