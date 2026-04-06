"""
美林时钟测试模块

集成测试和功能验证。
"""

from .test_integration import test_merrill_clock_integration as test_merrill_clock

__all__ = [
    "test_merrill_clock",
]