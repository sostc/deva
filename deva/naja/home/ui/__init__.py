"""Naja 首页 UI 模块"""

from .stats import render_stats_cards
from .fleet import render_fleet_panel
from .architecture import render_attention_kernel_panel, render_system_architecture_panel
from .values import render_values_section
from .quick_links import render_quick_links_panel


def _collect_fleet_stats() -> tuple[dict, dict]:
    """采集「数据源 / 策略」两类的全系统口径。

    ❗不再只读两个 Manager：它们只覆盖各自注册体系内的条目，而热点策略体系
    （十几个在跑）和散落各处的取数器都不在里面。统一走 FleetRegistry，
    注册体系 + 热点体系 + 探针 + 常驻 runner 一视同仁。

    ❗采集失败不许静默：refresh() 内部每个适配器自带 try/except 并落
    ``_source_status``，面板里会显示「采集失败：…」。这里只兜住整体异常，
    返回空口径时卡片会显示成灰色「不可用」而不是假的 0。
    """
    from deva.naja.infra.observability.fleet_registry import (
        KIND_DATASOURCE, KIND_STRATEGY, get_fleet_registry, refresh,
    )
    try:
        reg = get_fleet_registry()
        refresh(reg)
        return (reg.summarize(KIND_DATASOURCE), reg.summarize(KIND_STRATEGY))
    except Exception as e:  # noqa: BLE001 —— 首页不能因为采集挂掉而整页崩
        import logging
        logging.getLogger(__name__).warning(
            "[home] 全系统清单采集失败（%s: %s）", type(e).__name__, e)
        return {}, {}


async def render_home(ctx: dict):
    """渲染首页"""
    from pywebio.output import put_markdown, put_html
    from deva.naja.register import SR

    task_mgr = SR('task_manager')
    dict_mgr = SR('dictionary_manager')

    task_stats = task_mgr.get_stats()
    dict_stats = dict_mgr.get_stats()
    # 数据源 / 策略改从全系统登记册取（见 _collect_fleet_stats 注释）
    ds_stats, strategy_stats = _collect_fleet_stats()

    ctx["put_markdown"]('''### 🚀 Naja 智慧系统''')

    # 统计卡片
    render_stats_cards(ctx, ds_stats, task_stats, strategy_stats, dict_stats)

    # 全量清单（数据源 + 策略逐条明细，可展开）
    render_fleet_panel(ctx)

    # 价值观展示
    values_html = render_values_section()
    ctx["put_html"](values_html)



    # Attention Kernel 热点中枢
    render_attention_kernel_panel(ctx)

    # 系统架构图
    render_system_architecture_panel(ctx)

    # 快速链接
    render_quick_links_panel(ctx)


__all__ = ["render_home"]
