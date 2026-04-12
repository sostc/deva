"""供应链 UI - 风险卡片"""

from typing import List, Dict, Tuple
from datetime import datetime

from pywebio.output import (
    put_html, put_row, put_column, put_text, put_button, put_table,
    put_scope, use_scope, clear_scope
)
from pywebio.session import run_js
import math

def render_supply_chain_risk_card(risk_level: str = "LOW", narrative_risk: float = 0.5) -> dict:
    """渲染供应链风险状态卡片"""
    color_map = {
        "HIGH": "#dc2626",
        "MEDIUM": "#ca8a04",
        "LOW": "#22c55e",
        "unknown": "#64748b"
    }

    emoji_map = {
        "HIGH": "🚨",
        "MEDIUM": "⚠️",
        "LOW": "✅",
        "unknown": "❓"
    }

    color = color_map.get(risk_level, "#64748b")
    emoji = emoji_map.get(risk_level, "❓")

    return {
        "emoji": emoji,
        "risk_level": risk_level,
        "narrative_risk": narrative_risk,
        "color": color
    }


