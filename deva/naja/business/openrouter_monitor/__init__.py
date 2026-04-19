"""
OpenRouter 监控业务模块

功能：
1. 每周一获取 OpenRouter TOKEN 消耗数据
2. 分析趋势（上涨/下跌/加速/减速/异常）
3. 数据存储到 NB 表，供其他模块查询
4. 异常时发送雷达事件
5. 提供 AI 算力趋势信号供认知系统使用
"""

from .business import OpenRouterMonitor

__all__ = ['OpenRouterMonitor']
