"""
 CognitionUI 主入口

 使用 components/ 中的拆分组件
"""

from typing import Optional, Dict, Any, List
import logging

from pywebio.output import put_html, put_row, put_column, put_scope
from pywebio.session import run_js, set_env

from ..engine import get_cognition_engine
from ..core import AttentionScorer
from ...page_help import render_help_collapse
from ...common.ui_style import format_timestamp
from .components import (
    render_supply_chain,
    render_event_bus,
    render_semantic,
    render_insight,
    render_cognition_summary,
    render_control_panel,
    render_market_replay,
    render_market_replay_empty,
    render_merrill_clock,
    render_propagation,
    render_cross_signal,
    render_storage,
    render_help,
)

log = logging.getLogger(__name__)


def _get_stock_display_info(code: str) -> str:
    """获取股票的显示信息：名称和板块"""
    try:
        from ...dictionary.stock.stock import Stock
        from ...dictionary.tongdaxin_blocks import get_stock_blocks
        name = Stock.get_name(code)
        blocks = get_stock_blocks(code)
        block_str = ",".join(blocks[:2]) if blocks else ""
        return f"{name}({block_str})" if block_str else name
    except Exception:
        return code


def _create_nav_menu():
    """创建导航菜单"""
    from ...common.ui_theme import get_nav_menu_js
    js_code = get_nav_menu_js()
    run_js(js_code)


def _apply_global_styles():
    """应用全局样式"""
    from ...common.ui_theme import get_global_styles
    from pywebio.output import put_html
    put_html(get_global_styles())


def _get_data_sources():
    return [
        {"name": "金十数据", "type": "news", "icon": "📡"},
        {"name": "BlockAttention", "type": "market", "icon": "📊"},
        {"name": "CognitiveSignalBus", "type": "internal", "icon": "🧠"},
    ]


def _get_theme_config():
    return {
        "bg_primary": "rgba(15, 23, 42, 0.95)",
        "bg_secondary": "rgba(30, 41, 59, 0.9)",
        "border": "rgba(148, 163, 184, 0.2)",
        "text_primary": "#f1f5f9",
        "text_secondary": "#94a3b8",
        "accent_blue": "#0ea5e9",
        "accent_purple": "#8b5cf6",
        "accent_green": "#22c55e",
        "accent_orange": "#f59e0b",
    }


def _get_module_status(engine) -> Dict[str, bool]:
    """获取各模块状态"""
    status = {
        "narrative_tracker": False,
        "timing_tracker": False,
        "cross_signal": False,
        "supply_chain": False,
        "insight_pool": False,
        "llm_reflection": False,
        "semantic_cold_start": False,
        "cognitive_bus": False,
    }

    if not engine:
        return status

    try:
        if hasattr(engine, '_narrative_tracker') and engine._narrative_tracker:
            status["narrative_tracker"] = True
    except:
        pass

    try:
        if hasattr(engine, '_cross_signal_analyzer') and engine._cross_signal_analyzer:
            status["cross_signal"] = True
    except:
        pass

    try:
        if hasattr(engine, '_insight_pool') and engine._insight_pool:
            status["insight_pool"] = True
    except:
        pass

    try:
        if hasattr(engine, '_cognitive_bus') and engine._cognitive_bus:
            status["cognitive_bus"] = True
    except:
        pass

    return status


class CognitionUI:
    """认知系统 UI"""

    def __init__(self):
        self.engine = get_cognition_engine()

    def _put_html(self, html: str):
        put_html(html)

    def render(self):
        """渲染认知页面完整视图"""
        set_env(title="Naja - 认知", output_animation=False)
        _apply_global_styles()
        _create_nav_menu()

        self._put_html('<div class="container">')

        render_cognition_summary(self)
        render_supply_chain(self)

        insight_pool = None
        try:
            from ..insight import get_insight_pool
            insight_pool = get_insight_pool()
        except Exception:
            pass

        source_counts = {}
        recent_by_source = {}
        recent_insights = []
        if insight_pool:
            try:
                insights = insight_pool.get_recent_insights(limit=100)
                recent_insights = insights[:20]

                for insight in insights:
                    src = insight.get('source', 'unknown')
                    source_counts[src] = source_counts.get(src, 0) + 1

                    if src not in recent_by_source:
                        recent_by_source[src] = []
                    if len(recent_by_source[src]) < 2:
                        recent_by_source[src].append(insight)
            except Exception:
                pass

        render_event_bus(self, source_counts, recent_by_source, recent_insights)

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

        render_merrill_clock(self)
        render_propagation(self)
        render_cross_signal(self)
        render_semantic(self)
        render_insight(self)
        render_storage(self)
        render_control_panel(self)
        render_help(self)

        self._put_html('</div>')

    def _render_supply_chain_narrative(self):
        render_supply_chain(self)

    def _render_event_bus_flow(self, source_counts=None, recent_by_source=None, recent_insights=None):
        render_event_bus(self, source_counts, recent_by_source, recent_insights)

    def _render_semantic_cold_start(self):
        render_semantic(self)

    def _render_insight_section(self):
        render_insight(self)

    def _render_cognition_summary(self):
        render_cognition_summary(self)

    def _render_control_panel(self):
        render_control_panel(self)

    def _render_market_replay_section(self):
        render_market_replay(self)

    def _render_market_replay_empty(self):
        render_market_replay_empty(self)

    def _trigger_reflection(self):
        """手动触发 LLM 反思"""
        from ..insight import get_llm_reflection_engine

        try:
            engine = get_llm_reflection_engine()
            stats = engine.get_stats()
            reflection_count = stats.get('reflections_count', 0)
            pending_signals = stats.get('pending_signals', 0)

            if pending_signals < 1:
                return

            from pywebio.output import put_toast
            put_toast(f"触发反思: {pending_signals} 条待处理信号", duration=3)

            def do_reflection():
                try:
                    result = engine.trigger_reflection_now()
                    put_toast(f"反思完成! 生成 {len(result.get('reflections', []))} 条洞察", duration=5)
                except Exception as e:
                    from pywebio.output import put_toast
                    put_toast(f"反思失败: {str(e)}", duration=5)

            from threading import Thread
            Thread(target=do_reflection, daemon=True).start()

        except Exception as e:
            from pywebio.output import put_toast
            put_toast(f"反思功能不可用: {str(e)}", duration=3)

    def _render_narrative_lifecycle(self):
        render_narrative_lifecycle(self)

    def _render_narrative_svg(self, nodes: List[Dict], edges: List[Dict]) -> str:
        from ..narrative.ui.svg import render_narrative_svg
        return render_narrative_svg(nodes, edges)

    def _render_merrill_clock_link(self):
        render_merrill_clock(self)

    def _render_propagation_network(self):
        render_propagation(self)

    def _render_cross_signal_section(self):
        render_cross_signal(self)

    def _render_storage(self):
        render_storage(self)

    def _render_help(self):
        render_help(self)

    def _refresh_data(self):
        from ..insight import get_insight_pool, get_llm_reflection_engine
        pool = get_insight_pool()
        llm = get_llm_reflection_engine()

        stats = {
            "insight_count": len(pool.get_recent_insights(limit=1000)) if pool else 0,
            "reflection_count": llm.get_stats().get('reflections_count', 0) if llm else 0,
            "memory_usage": 0,
        }

        from pywebio.output import put_toast
        put_toast(f"数据已刷新! 洞察: {stats['insight_count']}", duration=2)

    def _generate_report(self):
        from pywebio.output import put_toast
        put_toast("报告生成中...", duration=2)

        def generate():
            from ..insight import get_insight_pool
            pool = get_insight_pool()
            if pool:
                report = pool.generate_insight_report()
                from pywebio.output import put_toast
                put_toast(f"报告已生成! 包含 {len(report.get('insights', []))} 条洞察", duration=5)

        from threading import Thread
        Thread(target=generate, daemon=True).start()

    def _trigger_market_replay(self):
        from pywebio.output import put_toast
        put_toast("市场复盘功能开发中...", duration=2)

    def _clear_storage(self):
        from pywebio.output import put_confirm, put_toast

        async def confirm_clear():
            from pywebio import async_io
            confirmed = await async_io.put_confirm("确定要清空短期记忆吗?")
            if confirmed:
                try:
                    from ...narrative import NarrativeTracker
                    tracker = NarrativeTracker()
                    tracker.clear_short_term_memory()
                    put_toast("短期记忆已清空", duration=3)
                except Exception as e:
                    put_toast(f"清空失败: {str(e)}", duration=3)

        from threading import Thread
        Thread(target=lambda: confirm_clear(), daemon=True).start()


def cognition_page():
    """认知页面入口"""
    ui = CognitionUI()
    ui.render()
