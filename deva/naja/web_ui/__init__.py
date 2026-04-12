"""Naja 管理面板 - 基于 PyWebIO 和 Tornado 的 Web 应用程序

拆分结构：
  theme.py    — 主题管理
  modes.py    — 启动模式初始化 (实验室/新闻雷达/调参/认知调试)
  styles.py   — 全局样式
  ui_base.py  — 导航菜单、UI 初始化、上下文
  pages.py    — 所有页面路由函数
  routes.py   — 路由注册 (create_handlers)
  server.py   — 服务器启动 (run_server)
"""

from .theme import get_request_theme, set_request_theme
from .server import run_server
from .routes import create_handlers

__all__ = [
    "get_request_theme",
    "set_request_theme",
    "run_server",
    "create_handlers",
]
