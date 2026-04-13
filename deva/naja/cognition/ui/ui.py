"""
 CognitionUI 主入口

 使用 components/ 中的拆分组件
"""

import logging

from pywebio.output import put_html

from .components import (
    render_supply_chain,
    render_event_bus,
    render_semantic,
    render_insight,
    render_cognition_summary,
    render_control_panel,
    render_merrill_clock,
    render_propagation,
    render_cross_signal,
    render_storage,
    render_help,
    render_first_principles,
    render_soft_info,
    render_liquidity_prediction,
    render_token_monitor,
    render_narrative_value,
)
from deva.naja.register import SR

log = logging.getLogger(__name__)


class CognitionUI:
    """认知系统 UI"""

    def __init__(self):
        self.engine = SR('cognition_engine')

    def _put_html(self, html: str):
        put_html(html)

    def render(self):
        """渲染认知页面完整视图

        注意：页面初始化（set_env / apply_global_styles / create_nav_menu / 主题读取）
        已由 pages.py 通过 init_naja_ui() 统一处理，此处不再重复。
        """

        self._put_html('<div class="container">')

        render_cognition_summary(self)
        render_supply_chain(self)
        render_event_bus(self)

        self._put_html("""
        <div style="
            background: linear-gradient(135deg, rgba(99,102,241,0.1), rgba(139,92,246,0.1));
            border: 1px solid rgba(139,92,246,0.2);
            border-radius: 12px;
            padding: 16px;
            margin: 16px 0;
        ">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 18px;">📖</span>
                    <span style="font-size: 14px; font-weight: 600; color: #a78bfa;">叙事追踪</span>
                </div>
                <a href="/narrative" style="
                    background: linear-gradient(135deg, #6366f1, #8b5cf6);
                    color: white;
                    padding: 6px 14px;
                    border-radius: 6px;
                    font-size: 12px;
                    text-decoration: none;
                ">查看详情 →</a>
            </div>
            <div style="font-size: 12px; color: #94a3b8;">
                外部新闻叙事追踪 · 时机感知 · 供应链联动
            </div>
        </div>
        """)

        render_narrative_value(self)
        render_merrill_clock(self)
        render_propagation(self)
        render_liquidity_prediction(self)
        render_cross_signal(self)
        render_first_principles(self)
        render_semantic(self)
        render_insight(self)
        render_soft_info(self)
        render_storage(self)
        render_token_monitor(self)
        render_control_panel(self)
        render_help(self)

        self._put_html('</div>')

    # --- narrative lifecycle 需要这个方法（被 lifecycle.py L139 调用）---
    def _render_narrative_svg(self, nodes, edges):
        from ..narrative.ui.svg import render_narrative_svg
        return render_narrative_svg(nodes, edges)


def cognition_page():
    """认知页面入口"""
    ui = CognitionUI()
    ui.render()
