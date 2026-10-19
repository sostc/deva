"""CognitionUI 主入口

页面版式（2026-10-19 重排）：18 个平铺组件归并为 5 个分节 + 顶部锚点导航，
静态说明与长列表默认折叠。分组依据是"用户此刻想问什么"，不是代码模块归属。

    ① 概览  —— 现在系统看到了什么（中枢指标 / 事件流）
    ② 思考  —— 它得出了什么结论（洞察 / 叙事追踪 / 反思 / 语义 / 跨信号）
    ③ 记忆  —— 它记住了什么（分层记忆 / 衰减参数 / 美林时钟）
    ④ 深度分析 —— 结论背后的展开（供应链 / 传播 / 预测 / 第一性 / 软信息）
    ⑤ 工具  —— 监控与自检（算力消耗 / 反思调度 / 帮助）

❗搬出去的两块（都留了跳转入口，别让它们凭空消失）：
    * 金十实时快讯 → ``/news``（它是未消化的原始新闻流，不是认知产出）
    * 供应链-叙事联动 → ``/supplychain``（它是供应链视图的一半，那页原本
      只有静态图谱）
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
    render_narrative_track,
)
from .components.layout import (
    SECTION_COLORS,
    flush_empty_states,
    jump_card,
    put_page_css,
    render_anchor_nav,
    render_section,
)
from deva.naja.register import SR

log = logging.getLogger(__name__)


def _get_cognition_engine():
    """获取 CognitionEngine（AppContainer 优先，SR fallback 仅开发用）"""
    from deva.naja.application.container import get_app_container
    container = get_app_container()
    if container is not None:
        ce = getattr(container, 'cognition_engine', None)
        if ce is not None:
            return ce
    return SR('cognition_engine')


class CognitionUI:
    """认知系统 UI"""

    def __init__(self):
        self.engine = _get_cognition_engine()

    def _put_html(self, html: str):
        put_html(html)

    def render(self):
        """渲染认知页面完整视图

        注意：页面初始化（set_env / apply_global_styles / create_nav_menu / 主题读取）
        已由 pages.py 通过 init_naja_ui() 统一处理，此处不再重复。
        """
        put_page_css()

        self._put_html('<div class="container">')

        render_anchor_nav([
            ("sec-overview", "① 概览"),
            ("sec-thinking", "② 思考"),
            ("sec-memory", "③ 记忆"),
            ("sec-deep", "④ 深度分析"),
            ("sec-tools", "⑤ 工具"),
        ])

        # ── ① 概览 ──────────────────────────────────────────────
        render_section(
            "sec-overview", "🧠", "概览",
            "此刻系统看到了什么：认知中枢的四项关键指标、事件流吞吐",
            SECTION_COLORS["overview"], first=True,
        )
        render_cognition_summary(self)
        render_event_bus(self)
        # 金十实时快讯已并入 /news（它是未消化的原始流，不是认知产出），
        # 这里只留入口。
        self._put_html(jump_card(
            icon="📌",
            title="金十重要事件",
            desc="实时快讯流已并入新闻页，与「今日新闻消化」同屏",
            href="/news",
        ))

        # ── ② 思考 ──────────────────────────────────────────────
        render_section(
            "sec-thinking", "💡", "思考",
            "它得出了什么：洞察结论、叙事追踪、LLM 深度反思、语义冷启动图谱、跨信号共振",
            SECTION_COLORS["thinking"],
        )
        render_insight(self)
        # 叙事追踪是"系统认定市场在讲什么故事"，属于结论而非下钻分析，
        # 因此放在思考节紧跟洞察；供需价值那套已降级为卡内折叠。
        render_narrative_track(self)
        render_semantic(self)
        render_cross_signal(self)

        # ── ③ 记忆 ──────────────────────────────────────────────
        render_section(
            "sec-memory", "💾", "记忆",
            "它记住了什么：短期/中期分层容量、衰减与强化保护、经济周期位置",
            SECTION_COLORS["memory"],
        )
        render_storage(self)
        render_merrill_clock(self)

        # ── ④ 深度分析 ──────────────────────────────────────────
        render_section(
            "sec-deep", "🔬", "深度分析",
            "结论背后的展开：供应链联动、流动性传播与预测、第一性原理、软信息权重",
            SECTION_COLORS["deep"],
        )
        render_supply_chain(self)
        render_propagation(self)
        render_liquidity_prediction(self)
        render_first_principles(self)
        render_soft_info(self)
        flush_empty_states("等待数据的板块")

        # ── ⑤ 工具 ──────────────────────────────────────────────
        render_section(
            "sec-tools", "🛠️", "工具",
            "监控与自检：TOKEN 消耗趋势、反思调度参数、页面说明",
            SECTION_COLORS["tools"],
        )
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
