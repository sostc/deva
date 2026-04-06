"""
美林时钟用户界面模块

提供Web界面和Markdown报告生成功能。
"""

from .web_ui import render_merrill_clock_page
from .markdown_reporter import get_merrill_clock_markdown

__all__ = [
    "render_merrill_clock_page",
    "get_merrill_clock_markdown",
]