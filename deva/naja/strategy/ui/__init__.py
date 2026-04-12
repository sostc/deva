"""策略管理 UI

拆分自原 strategy/ui.py (2895行)，按功能职责分为以下子模块：
- diagrams: 策略图表常量与原理渲染
- table: 策略列表表格与分类切换
- stats: 统计面板渲染
- detail: 策略/结果详情展示
- board: 策略看板与自动刷新
- actions: 工具栏操作与批量操作
- dialogs: 创建/编辑/实验模式对话框
"""

from pywebio.output import set_scope, clear
from pywebio.session import run_async

from deva.naja.register import SR
from deva.naja.infra.ui.ui_style import apply_strategy_like_styles, render_empty_state
from deva.naja.infra.ui.page_help import render_help_collapse

# 子模块导入
from .stats import _render_strategy_stats_html, _render_result_stats_html
from . import table as _table_mod  # 全局状态 _current_category/_view_mode 住在 table 模块
from .table import (
    _render_category_tabs, _build_table_data, _get_all_categories,
    _resolve_datasource_name, _render_type_badge, _categorize_strategy_by_handler,
)
from .actions import _handle_toolbar_action, _export_all_strategies_to_file
from .dialogs import _create_strategy_dialog
from .board import _show_strategy_board
from .detail import _render_recent_results

# 公开 API
__all__ = ["render_strategy_admin"]


async def render_strategy_admin(ctx: dict):
    """渲染策略管理面板"""
    set_scope("strategy_content")
    _render_strategy_content(ctx)


def _render_strategy_help(ctx: dict):
    """渲染策略系统帮助说明"""
    render_help_collapse("strategy")


def _render_strategy_content(ctx: dict):
    """渲染策略管理内容（支持局部刷新）"""
    import time as time_module
    _perf_start = time_module.time()

    from deva.naja.strategy import get_strategy_manager
    from deva.naja.strategy.result_store import get_result_store

    _t0 = time_module.time()
    mgr = get_strategy_manager()
    _t1 = time_module.time()

    store = get_result_store()
    _t2 = time_module.time()

    _t3 = time_module.time()
    entries = mgr.list_all()
    _t4 = time_module.time()

    stats = mgr.get_stats()
    _t5 = time_module.time()

    result_stats = store.get_stats()
    _t6 = time_module.time()

    running_count = sum(1 for e in entries if e.is_running)
    error_count = sum(1 for e in entries if e._state.error_count > 0)

    clear("strategy_content")
    _t7 = time_module.time()

    apply_strategy_like_styles(ctx, scope="strategy_content", include_compact_table=True, include_category_tabs=True)
    _t8 = time_module.time()

    ctx["put_html"](_render_strategy_stats_html(
        stats, running_count, error_count), scope="strategy_content")

    exp_info = mgr.get_experiment_info()
    if exp_info.get("active"):
        categories_text = "、".join(exp_info.get("categories", []))
        ds_name = exp_info.get("datasource_name") or _resolve_datasource_name(exp_info.get("datasource_id", ""))
        target_count = int(exp_info.get("target_count", 0))
        ctx["put_html"](f"""
        <div style="margin-bottom:14px;padding:12px 14px;border-radius:10px;
                    background:linear-gradient(135deg,#fff3cd,#ffe8a1);
                    border:1px solid #f5d37a;color:#7a5a00;font-size:13px;">
            <strong>🧪 实验模式已开启</strong><br>
            类别：{categories_text or "-"} ｜ 数据源：{ds_name} ｜ 策略数：{target_count}
        </div>
        """, scope="strategy_content")

    # 渲染类别 Tab
    categories = _get_all_categories(entries)
    _render_category_tabs(ctx, categories, entries, mgr)
    _t9 = time_module.time()

    # 根据当前类别筛选策略（状态住在 table 模块）
    current_cat = _table_mod._current_category
    current_vm = _table_mod._view_mode
    if current_cat == "全部":
        filtered_entries = entries
    else:
        if current_vm == "handler":
            filtered_entries = [e for e in entries if _categorize_strategy_by_handler(e) == current_cat]
        else:
            filtered_entries = [e for e in entries if getattr(e._metadata, "category", "默认") == current_cat]

    if filtered_entries:
        _t10 = time_module.time()
        table_data = _build_table_data(ctx, filtered_entries, mgr)
        _t11 = time_module.time()

        ctx["put_table"](table_data, header=["名称", "来源", "类型", "状态", "数据源", "简介",
                                             "最近数据", "操作"], scope="strategy_content")

        ctx["put_html"](
            '<div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;">', scope="strategy_content")
        toolbar_buttons = [
            {"label": "➕ 创建策略", "value": "create", "color": "primary"},
            {"label": "▶️ 全部启动", "value": "start_all", "color": "success"},
            {"label": "⏹️ 全部停止", "value": "stop_all", "color": "danger"},
            {"label": "🔄 重载配置", "value": "reload_all", "color": "info"},
            {"label": "🔄 刷新结果", "value": "refresh_results", "color": "info"},
            {"label": "📜 执行历史", "value": "show_history", "color": "default"},
        ]
        if exp_info.get("active"):
            toolbar_buttons.append({"label": "🧪 关闭实验模式", "value": "close_experiment", "color": "danger"})
        else:
            toolbar_buttons.append({"label": "🧪 开启实验模式", "value": "open_experiment", "color": "warning"})

        ctx["put_buttons"](toolbar_buttons, onclick=lambda v, m=mgr, c=ctx: _handle_toolbar_action(v, m, c), group=True, scope="strategy_content")
        ctx["put_html"]('</div>', scope="strategy_content")

        # 渲染策略关系图
        from deva.naja.strategy.relationship import build_relationship_html
        ctx["put_html"](build_relationship_html(), scope="strategy_content")

    else:
        ctx["put_html"](render_empty_state("暂无策略，点击下方按钮创建"), scope="strategy_content")
        ctx["put_buttons"]([{"label": "➕ 创建策略", "value": "create", "color": "primary"}],
                           onclick=lambda v, m=mgr, c=ctx: _create_strategy_dialog(m, c), scope="strategy_content")

    ctx["put_buttons"]([{"label": "📁 导出全部到文件", "value": "export_all", "color": "info"}],
                       onclick=lambda v, m=mgr, c=ctx: _export_all_strategies_to_file(m, c), scope="strategy_content")

    ctx["put_html"](
        "<hr style='margin:24px 0;border:none;border-top:1px solid #e0e0e0;'>", scope="strategy_content")

    ctx["put_html"](_render_result_stats_html(result_stats), scope="strategy_content")

    _render_strategy_help(ctx)

    _t12 = time_module.time()
    total_time_ms = (_t12-_perf_start)*1000

    # 记录 Web 请求性能
    try:
        from deva.naja.infra.observability.performance_monitor import record_web_request
        record_web_request(
            request_path="/naja/strategy",
            execution_time_ms=total_time_ms,
            success=True,
        )
    except Exception:
        pass
