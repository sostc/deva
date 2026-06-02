"""
兼容性模块 - 重定向到 unified_article_monitor
原模块已合并到 unified_article_monitor.py
"""

# 重定向导入
from deva.naja.tasks.unified_article_monitor import (
    check_and_process,
    listen_and_learn,
    extract_urls,
)

__all__ = ["check_and_process", "listen_and_learn", "extract_urls"]
