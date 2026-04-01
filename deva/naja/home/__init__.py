"""
Naja首页模块

包含：
- 首页主界面
- 灵魂管理页面
"""

from .ui import render_home
from .soul_admin import soul_admin_page

__all__ = ["render_home", "soul_admin_page"]
