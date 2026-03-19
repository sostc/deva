"""注意力调度系统模块

提供注意力系统的 Web UI 和管理功能
"""

from .ui import render_attention_admin, set_auto_refresh

__all__ = ['render_attention_admin', 'set_auto_refresh']
