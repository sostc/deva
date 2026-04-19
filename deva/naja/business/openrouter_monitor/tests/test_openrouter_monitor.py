"""
OpenRouter 监控测试
"""

import unittest
from unittest.mock import patch, MagicMock
from deva.naja.business.openrouter_monitor.business import (
    OpenRouterMonitor, get_openrouter_monitor,
    get_ai_compute_trend, get_openrouter_trend,
    get_openrouter_full_data, scheduled_openrouter_check
)


class TestOpenRouterMonitor(unittest.TestCase):
    """测试 OpenRouter 监控模块"""

    def setUp(self):
        """设置测试环境"""
        self.monitor = OpenRouterMonitor()

    @patch('deva.NB')
    def test_get_openrouter_trend(self, mock_nb):
        """测试获取 OpenRouter 趋势"""
        # 模拟 NB 返回值
        mock_db = MagicMock()
        mock_db.get.return_value = {
            "direction": "up",
            "strength": 0.5,
            "message": "测试消息"
        }
        mock_nb.return_value = mock_db

        # 调用函数
        result = self.monitor.get_openrouter_trend()

        # 验证结果
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "up")
        self.assertEqual(result["strength"], 0.5)
        self.assertEqual(result["message"], "测试消息")

    @patch('deva.NB')
    def test_get_ai_compute_trend(self, mock_nb):
        """测试获取 AI 算力趋势"""
        # 模拟 NB 返回值
        mock_db = MagicMock()
        mock_db.get.side_effect = [
            {
                "timestamp": "2026-04-16T00:00:00",
                "weekly_history": [
                    {"date": "2026-03-16", "total": 1000},
                    {"date": "2026-04-16", "total": 2000}
                ]
            },
            {
                "direction": "strong_up",
                "strength": 0.8,
                "latest_total": 2000,
                "latest_change": 10.5,
                "acceleration": 5.2,
                "alert_level": "attention",
                "is_anomaly": False,
                "is_incomplete_week": False,
                "data_weeks": 10
            }
        ]
        mock_nb.return_value = mock_db

        # 调用函数
        result = self.monitor.get_ai_compute_trend()

        # 验证结果
        self.assertIsNotNone(result)
        self.assertEqual(result["signal_type"], "ai_compute_trend")
        self.assertEqual(result["trend_direction"], "rising")
        self.assertEqual(result["cumulative_growth"], 1.0)

    def test_get_openrouter_monitor_singleton(self):
        """测试单例模式"""
        instance1 = get_openrouter_monitor()
        instance2 = get_openrouter_monitor()
        self.assertIs(instance1, instance2)

    @patch('deva.naja.business.openrouter_monitor.business.get_openrouter_monitor')
    def test_backward_compatibility_functions(self, mock_get_monitor):
        """测试向后兼容函数"""
        # 模拟监控实例
        mock_monitor = MagicMock()
        mock_get_monitor.return_value = mock_monitor

        # 测试 get_ai_compute_trend
        get_ai_compute_trend()
        mock_monitor.get_ai_compute_trend.assert_called_once()

        # 测试 get_openrouter_trend
        get_openrouter_trend()
        mock_monitor.get_openrouter_trend.assert_called_once()

        # 测试 get_openrouter_full_data
        get_openrouter_full_data()
        mock_monitor.get_openrouter_full_data.assert_called_once()


if __name__ == '__main__':
    unittest.main()
