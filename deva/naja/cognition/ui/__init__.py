"""
认知系统 UI 模块

目录结构：
├── __init__.py      # 统一导出
├── main.py          # cognition_page 入口
├── glossary.py      # 名词解释
└── ui.py           # CognitionUI 类
"""

from .main import cognition_page
from .glossary import cognition_glossary_page
from .ui import CognitionUI

__all__ = [
    "CognitionUI",
    "cognition_page",
    "cognition_glossary_page",
]
