"""Naja 首页 UI 模块"""

from .stats import render_stats_cards
from .architecture import render_attention_kernel_panel, render_system_architecture_panel
from .values import render_values_section
from .quick_links import render_quick_links_panel


async def render_home(ctx: dict):
    """渲染首页"""
    from pywebio.output import put_markdown, put_html
    from deva.naja.register import SR
    from deva.naja.datasource import get_datasource_manager
    from deva.naja.strategy import get_strategy_manager

    ds_mgr = get_datasource_manager()
    task_mgr = SR('task_manager')
    strategy_mgr = get_strategy_manager()
    dict_mgr = SR('dictionary_manager')

    ds_stats = ds_mgr.get_stats()
    task_stats = task_mgr.get_stats()
    strategy_stats = strategy_mgr.get_stats()
    dict_stats = dict_mgr.get_stats()

    ctx["put_markdown"]('''### 🚀 Naja 智慧系统''')

    # 统计卡片
    render_stats_cards(ctx, ds_stats, task_stats, strategy_stats, dict_stats)

    # 价值观展示
    values_html = render_values_section()
    ctx["put_html"](values_html)

    # 系统健康监控面板
    try:
        from deva.naja.infra.observability.system_monitor_ui import render_monitor_panel
        ctx["put_html"](render_monitor_panel())
    except Exception:
        pass

    # Attention Kernel 热点中枢
    render_attention_kernel_panel(ctx)

    # 系统架构图
    render_system_architecture_panel(ctx)

    # 快速链接
    render_quick_links_panel(ctx)


__all__ = ["render_home"]
