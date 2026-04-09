"""
CognitionUI 主入口

重新组织认知页面 UI
"""

from typing import Optional, Dict, Any, List
import logging

from pywebio.output import put_html, put_row, put_column, put_scope
from pywebio.session import set_env

from ...common.ui_theme import get_nav_menu_js

log = logging.getLogger(__name__)


def cognition_page():
    """认知页面入口 - 直接使用原有 ui.py 的逻辑"""
    set_env(title="Naja - 认知系统", output_animation=False)

    from pywebio.session import run_js
    run_js(get_nav_menu_js())

    from .ui import CognitionUI
    ui = CognitionUI()
    ui.render()
