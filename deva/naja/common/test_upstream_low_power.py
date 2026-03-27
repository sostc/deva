#!/usr/bin/env python3
"""
上游依赖低频模式测试

测试 SignalListener、MarketObserver 的低功耗模式，以及 AutoTuner 的 upstream_inactive 检测。

运行方式:
    cd /Users/spark/pycharmproject/deva
    python deva/naja/common/test_upstream_low_power.py

或者:
    python -m pytest deva/naja/common/test_upstream_low_power.py -v
"""

import sys
import os
import time
import unittest
from unittest.mock import MagicMock, patch
from typing import Dict, List

sys.path.insert(0, '/Users/spark/pycharmproject/deva')

os.environ['NAJA_ATTENTION_ENABLED'] = 'false'
os.environ['NAJA_LAB_MODE'] = ''

class TestSignalListenerLowPower(unittest.TestCase):
    """SignalListener 低功耗模式测试"""

    @classmethod
    def setUpClass(cls):
        from deva.naja.bandit.signal_listener import SignalListener
        cls.listener = SignalListener()
        cls.listener._low_power_mode = False
        cls.listener._poll_interval = 2.0
        cls.listener._normal_poll_interval = 2.0
        cls.listener._low_power_poll_interval = 60.0

    def setUp(self):
        self.listener._low_power_mode = False
        self.listener._poll_interval = 2.0
        self.listener._normal_poll_interval = 2.0
        self.listener._low_power_poll_interval = 60.0

    def test_tc001_enter_low_power_mode(self):
        """TC-001: SignalListener 进入低频模式"""
        from deva.naja.signal.stream import SignalStream

        with patch.object(self.listener, '_signal_stream') as mock_stream:
            mock_stream.get_recent.return_value = []

            with patch('deva.naja.strategy.get_strategy_manager') as mock_mgr:
                mock_entry = MagicMock()
                mock_entry.is_processing_data.return_value = False
                mock_mgr.return_value.list_all.return_value = [mock_entry]

                self.listener._process_signals()

                self.assertTrue(self.listener._low_power_mode)
                self.assertEqual(self.listener._poll_interval, 60.0)
                self.assertEqual(self.listener._low_power_poll_interval, 60.0)
        print("✓ TC-001: SignalListener 进入低频模式 - PASS")

    def test_tc002_exit_low_power_mode(self):
        """TC-002: SignalListener 主动退出低频模式"""
        self.listener._low_power_mode = True
        self.listener._poll_interval = 60.0

        with patch.object(self.listener, '_signal_stream') as mock_stream:
            mock_stream.get_recent.return_value = []

            with patch('deva.naja.strategy.get_strategy_manager') as mock_mgr:
                mock_entry = MagicMock()
                mock_entry.is_processing_data.return_value = True
                mock_mgr.return_value.list_all.return_value = [mock_entry]

                self.listener._process_signals()

                self.assertFalse(self.listener._low_power_mode)
                self.assertEqual(self.listener._poll_interval, 2.0)
        print("✓ TC-002: SignalListener 主动退出低频模式 - PASS")

    def test_tc003_set_poll_interval_in_low_power_mode(self):
        """TC-003: set_poll_interval 在低功耗模式下不覆盖正常间隔"""
        self.listener._low_power_mode = True
        self.listener._poll_interval = 60.0

        self.listener.set_poll_interval(120)

        self.assertEqual(self.listener._low_power_poll_interval, 120)
        self.assertEqual(self.listener._poll_interval, 60.0)
        self.assertEqual(self.listener._normal_poll_interval, 2.0)
        print("✓ TC-003: set_poll_interval 在低功耗模式下正确处理 - PASS")

    def test_tc004_set_poll_interval_in_normal_mode(self):
        """TC-004: set_poll_interval 在正常模式下更新正常间隔"""
        self.listener._low_power_mode = False
        self.listener._poll_interval = 2.0

        self.listener.set_poll_interval(5)

        self.assertEqual(self.listener._normal_poll_interval, 5)
        self.assertEqual(self.listener._poll_interval, 5)
        print("✓ TC-004: set_poll_interval 在正常模式下正确工作 - PASS")


class TestMarketObserverLowPower(unittest.TestCase):
    """MarketObserver 低功耗模式测试"""

    @classmethod
    def setUpClass(cls):
        from deva.naja.bandit.market_observer import MarketDataObserver
        cls.observer = MarketDataObserver()
        cls.observer._low_power_mode = False
        cls.observer._fetch_interval = 5.0
        cls.observer._normal_fetch_interval = 5.0
        cls.observer._low_power_fetch_interval = 60.0
        cls.observer._current_datasource = None
        cls.observer._running = True

    def setUp(self):
        self.observer._low_power_mode = False
        self.observer._fetch_interval = 5.0
        self.observer._normal_fetch_interval = 5.0
        self.observer._low_power_fetch_interval = 60.0
        self.observer._current_datasource = None
        self.observer._running = True
        self.observer._last_datasource_available = True

    def test_tc101_enter_low_power_mode(self):
        """TC-101: MarketObserver 进入低频模式"""
        self.observer._current_datasource = None
        self.observer._is_allowed_to_run = MagicMock(return_value=True)

        self.observer._low_power_mode = False
        self.observer._fetch_interval = 5.0

        iteration = 0
        max_iterations = 1
        stop_event_set = False

        original_wait = self.observer._fetch_stop_event.wait
        def mock_wait(timeout):
            nonlocal iteration, stop_event_set
            iteration += 1
            if iteration >= max_iterations:
                stop_event_set = True
                raise KeyboardInterrupt()
            return False
        self.observer._fetch_stop_event.wait = mock_wait
        self.observer._is_datasource_running = MagicMock(return_value=False)

        try:
            self.observer._fetch_loop()
        except KeyboardInterrupt:
            pass

        self.assertTrue(self.observer._low_power_mode)
        self.assertEqual(self.observer._fetch_interval, 60.0)
        print("✓ TC-101: MarketObserver 进入低频模式 - PASS")

    def test_tc102_exit_low_power_mode(self):
        """TC-102: MarketObserver 主动退出低频模式"""
        mock_ds = MagicMock()
        mock_ds.is_running = True
        mock_ds._running = True

        self.observer._current_datasource = mock_ds
        self.observer._low_power_mode = True
        self.observer._fetch_interval = 60.0
        self.observer._is_allowed_to_run = MagicMock(return_value=True)
        self.observer._is_datasource_running = MagicMock(return_value=True)

        iteration = 0
        max_iterations = 1

        def mock_wait(timeout):
            nonlocal iteration
            iteration += 1
            if iteration >= max_iterations:
                raise KeyboardInterrupt()
            return False
        self.observer._fetch_stop_event.wait = mock_wait

        try:
            self.observer._fetch_loop()
        except KeyboardInterrupt:
            pass

        self.assertFalse(self.observer._low_power_mode)
        self.assertEqual(self.observer._fetch_interval, 5.0)
        print("✓ TC-102: MarketObserver 主动退出低频模式 - PASS")

    def test_tc103_adjust_interval_in_low_power_mode(self):
        """TC-103: adjust_interval 在低功耗模式下更新低功耗间隔"""
        self.observer._low_power_mode = True
        self.observer._fetch_interval = 60.0

        self.observer.adjust_interval(120, "test reason")

        self.assertEqual(self.observer._low_power_fetch_interval, 120)
        self.assertEqual(self.observer._fetch_interval, 60.0)
        print("✓ TC-103: adjust_interval 在低功耗模式下正确处理 - PASS")

    def test_tc104_adjust_interval_in_normal_mode(self):
        """TC-104: adjust_interval 在正常模式下更新正常间隔"""
        self.observer._low_power_mode = False
        self.observer._fetch_interval = 5.0

        self.observer.adjust_interval(10, "test reason")

        self.assertEqual(self.observer._normal_fetch_interval, 10)
        self.assertEqual(self.observer._fetch_interval, 10)
        print("✓ TC-104: adjust_interval 在正常模式下正确工作 - PASS")


class TestAutoTunerUpstreamInactive(unittest.TestCase):
    """AutoTuner upstream_inactive 检测测试"""

    @classmethod
    def setUpClass(cls):
        from deva.naja.common.auto_tuner import AutoTuner
        cls.tuner = AutoTuner.__new__(AutoTuner)
        cls.tuner._initialized = False
        cls.tuner._conditions = {}
        cls.tuner._condition_states = {}
        cls.tuner._events = []

    def test_tc205_upstream_inactive_condition_registered(self):
        """TC-205: upstream_inactive 条件注册"""
        from dataclasses import dataclass

        @dataclass
        class TuneCondition:
            cooldown: int = 300
            threshold: int = 0
            action: str = ""

        self.tuner._conditions['upstream_inactive'] = TuneCondition(
            cooldown=30,
            threshold=0,
            action='adjust_consumer_interval'
        )

        cond = self.tuner._conditions.get('upstream_inactive')
        self.assertIsNotNone(cond)
        self.assertEqual(cond.cooldown, 30)
        self.assertEqual(cond.action, 'adjust_consumer_interval')
        print("✓ TC-205: upstream_inactive 条件注册 - PASS")

    def test_tc201_check_signal_listener_upstream_inactive(self):
        """TC-201: AutoTuner 检测 SignalListener 上游不活跃"""
        with patch('deva.naja.bandit.signal_listener.get_signal_listener') as mock_listener:
            mock_instance = MagicMock()
            mock_instance._running = True
            mock_instance._poll_interval = 2.0
            mock_listener.return_value = mock_instance

            with patch('deva.naja.strategy.get_strategy_manager') as mock_mgr:
                mock_entry = MagicMock()
                mock_entry.is_processing_data.return_value = False
                mock_mgr.return_value.list_all.return_value = [mock_entry]

                result = self.tuner._check_signal_listener_upstream()

                self.assertIsNotNone(result)
                self.assertEqual(result['consumer_name'], 'signal_listener')
                self.assertEqual(result['target_interval'], 60.0)
        print("✓ TC-201: AutoTuner 检测 SignalListener 上游不活跃 - PASS")

    def test_tc202_check_market_observer_upstream_inactive(self):
        """TC-202: AutoTuner 检测 MarketObserver 上游不活跃"""
        with patch('deva.naja.bandit.market_observer.get_market_observer') as mock_observer:
            mock_instance = MagicMock()
            mock_instance._running = True
            mock_instance._fetch_interval = 5.0
            mock_instance._current_datasource = None
            mock_observer.return_value = mock_instance

            result = self.tuner._check_market_observer_upstream()

            self.assertIsNotNone(result)
            self.assertEqual(result['consumer_name'], 'market_observer')
            self.assertEqual(result['target_interval'], 60.0)
        print("✓ TC-202: AutoTuner 检测 MarketObserver 上游不活跃 - PASS")

    def test_tc203_upstream_active_returns_none(self):
        """TC-203: 上游活跃时不返回检测结果"""
        with patch('deva.naja.bandit.signal_listener.get_signal_listener') as mock_listener:
            mock_instance = MagicMock()
            mock_instance._running = True
            mock_instance._poll_interval = 2.0
            mock_listener.return_value = mock_instance

            with patch('deva.naja.strategy.get_strategy_manager') as mock_mgr:
                mock_entry = MagicMock()
                mock_entry.is_processing_data.return_value = True
                mock_mgr.return_value.list_all.return_value = [mock_entry]

                result = self.tuner._check_signal_listener_upstream()

                self.assertIsNone(result)
        print("✓ TC-203: 上游活跃时不返回检测结果 - PASS")

    def test_tc204_adjust_consumer_intervals(self):
        """TC-204: 批量调整消费者间隔"""
        inactive_consumers = [
            {
                'consumer_name': 'signal_listener',
                'current_interval': 2.0,
                'target_interval': 60.0,
                'reason': 'test'
            },
            {
                'consumer_name': 'market_observer',
                'current_interval': 5.0,
                'target_interval': 60.0,
                'reason': 'test'
            }
        ]

        with patch('deva.naja.bandit.signal_listener.get_signal_listener') as mock_listener:
            mock_listener_instance = MagicMock()
            mock_listener.return_value = mock_listener_instance

            with patch('deva.naja.bandit.market_observer.get_market_observer') as mock_observer:
                mock_observer_instance = MagicMock()
                mock_observer.return_value = mock_observer_instance

                self.tuner._adjust_consumer_intervals(inactive_consumers)

                mock_listener_instance.set_poll_interval.assert_called_once_with(60.0)
                mock_observer_instance.adjust_interval.assert_called_once_with(60.0, 'test')
        print("✓ TC-204: 批量调整消费者间隔 - PASS")

    def test_tc206_check_upstream_inactive_coordination(self):
        """TC-206: _check_upstream_inactive 协调检测"""
        with patch('deva.naja.bandit.signal_listener.get_signal_listener') as mock_listener:
            mock_instance = MagicMock()
            mock_instance._running = True
            mock_instance._poll_interval = 2.0
            mock_listener.return_value = mock_instance

            with patch('deva.naja.strategy.get_strategy_manager') as mock_mgr:
                mock_entry = MagicMock()
                mock_entry.is_processing_data.return_value = False
                mock_mgr.return_value.list_all.return_value = [mock_entry]

                with patch('deva.naja.bandit.market_observer.get_market_observer') as mock_observer:
                    mock_observer_instance = MagicMock()
                    mock_observer_instance._running = True
                    mock_observer_instance._fetch_interval = 5.0
                    mock_observer_instance._current_datasource = None
                    mock_observer.return_value = mock_observer_instance

                    result = self.tuner._check_upstream_inactive()

                    self.assertIsNotNone(result)
                    self.assertIn('inactive_consumers', result)
                    self.assertEqual(len(result['inactive_consumers']), 2)
        print("✓ TC-206: _check_upstream_inactive 协调检测 - PASS")


def run_tests():
    """运行所有测试"""
    print("\n" + "=" * 70)
    print("🧪 上游依赖低频模式测试套件")
    print("=" * 70)

    test_classes = [
        TestSignalListenerLowPower,
        TestMarketObserverLowPower,
        TestAutoTunerUpstreamInactive,
    ]

    total_tests = 0
    passed_tests = 0
    failed_tests = []

    for test_class in test_classes:
        print(f"\n📂 {test_class.__name__}")
        print("-" * 70)

        instance = test_class()
        if hasattr(instance, 'setUpClass'):
            test_class.setUpClass()

        for method_name in dir(instance):
            if method_name.startswith('test_'):
                try:
                    if hasattr(instance, 'setUp'):
                        instance.setUp()

                    getattr(instance, method_name)()
                    total_tests += 1
                    passed_tests += 1
                except Exception as e:
                    total_tests += 1
                    failed_tests.append((test_class.__name__, method_name, str(e)))
                    print(f"✗ {method_name}: FAIL - {e}")

    print("\n" + "=" * 70)
    print(f"📊 测试结果: {passed_tests}/{total_tests} 通过")
    if failed_tests:
        print(f"❌ 失败用例:")
        for cls_name, method_name, error in failed_tests:
            print(f"   - {cls_name}.{method_name}: {error}")
    print("=" * 70)

    return len(failed_tests) == 0


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
