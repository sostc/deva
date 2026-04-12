"""运行时状态管理 UI"""

from pywebio.output import put_text, put_markdown, put_table, put_buttons, put_html, toast, popup, close_popup
from pywebio.input import input_group, select

from deva.naja.infra.ui.ui_style import apply_strategy_like_styles, render_stats_cards


def render_runtime_state_page(ctx: dict):
    """渲染运行时状态管理面板"""
    from deva.naja.state.runtime import get_runtime_state_manager, register_all_adapters
    from pywebio.output import clear

    clear("runtime_state_content")

    mgr = get_runtime_state_manager()
    states = mgr.list_all()

    if not states:
        register_all_adapters()
        states = mgr.list_all()

    apply_strategy_like_styles(ctx=ctx, scope="runtime_state_content", include_compact_table=True)

    ctx["put_html"](
        "<style>.pywebio-table .pywebio-btn-group{flex-wrap:nowrap!important;gap:6px!important;}</style>",
        scope="runtime_state_content",
    )

    ctx["put_html"](
        """
        <div style="padding: 10px 0;">
            <h3 style="margin: 0 0 15px 0;">运行时状态持久化管理</h3>
            <p style="color: #666; margin: 0;">
                管理所有组件的运行时状态持久化，包括数据源、策略、注意力系统等。
            </p>
        </div>
        """,
        scope="runtime_state_content",
    )

    if not states:
        ctx["put_html"](
            """
            <div style="padding: 40px; text-align: center; color: #999;">
                <p>暂无注册的运行时状态</p>
                <p style="font-size: 12px;">组件需要在初始化时注册到 RuntimeStateManager</p>
            </div>
            """,
            scope="runtime_state_content",
        )
    else:
        _render_state_table(ctx, mgr, states)

    ctx["put_html"](_get_toolbar_html(), scope="runtime_state_content")
    ctx["put_buttons"](
        [
            {"label": "🔄 刷新状态", "value": "refresh", "color": "secondary"},
            {"label": "💾 全部保存", "value": "save_all", "color": "primary"},
            {"label": "📥 全部加载", "value": "load_all", "color": "info"},
            {"label": "🔍 预演模式", "value": "dry_run", "color": "warning"},
        ],
        onclick=lambda v, m=mgr, c=ctx: _handle_action(v, m, c),
        scope="runtime_state_content",
    )


def _render_state_table(ctx, mgr, states):
    """渲染状态表格"""
    from pywebio.output import put_row

    table_data = []

    for s in states:
        status_text = _get_status_text(s.status.value)

        priority_label = f"P{s.priority:02d}"

        error_short = s.last_error[:30] if s.last_error else "-"

        table_data.append([
            s.persistence_id,
            s.table_name,
            priority_label,
            status_text,
            s.last_save_time[:19] if s.last_save_time else "从未",
            s.last_load_time[:19] if s.last_load_time else "从未",
            error_short,
        ])

    ctx["put_table"](
        table_data,
        header=["组件", "表名", "优先级", "状态", "最后保存", "最后加载", "错误"],
        scope="runtime_state_content",
    )


def _get_status_text(status: str) -> str:
    """获取状态显示文本"""
    status_config = {
        "saved": "✅ 已保存",
        "loaded": "✅ 已加载",
        "modified": "⚠️ 已修改",
        "error": "❌ 错误",
        "unknown": "❓ 未知",
        "not_registered": "🔓 未注册",
    }

    return status_config.get(status, "❓ " + status)


def _get_toolbar_html() -> str:
    """获取工具栏 HTML"""
    return """
    <div style="margin-top: 20px; padding: 15px; background: #f5f5f5; border-radius: 8px;">
        <h4 style="margin: 0 0 10px 0;">说明</h4>
        <ul style="margin: 0; padding-left: 20px; color: #666; font-size: 13px;">
            <li><strong>优先级</strong>：数字越小越先加载/保存</li>
            <li><strong>状态</strong>：显示上次操作的结果</li>
            <li><strong>保存</strong>：将当前内存状态写入数据库</li>
            <li><strong>加载</strong>：从数据库恢复状态到内存</li>
            <li><strong>预演模式</strong>：显示将要执行的操作但不实际执行</li>
        </ul>
    </div>
    """


def _handle_action(action: str, mgr, ctx: dict):
    """处理按钮操作"""
    try:
        if action == "refresh":
            render_runtime_state_page(ctx)

        elif action == "save_all":
            result = mgr.save_all()
            _show_result(ctx, "保存结果", result)
            render_runtime_state_page(ctx)

        elif action == "load_all":
            result = mgr.load_all()
            _show_result(ctx, "加载结果", result)
            render_runtime_state_page(ctx)

        elif action == "dry_run":
            save_result = mgr.save_all(dry_run=True)
            load_result = mgr.load_all(dry_run=True)
            _show_result(ctx, "预演结果 - 保存", save_result)
            _show_result(ctx, "预演结果 - 加载", load_result)

    except Exception as e:
        toast(f"操作失败: {e}", color="danger")


def _show_result(ctx, title: str, result: dict):
    """显示操作结果"""
    success_count = result.get("success", 0)
    failed_count = result.get("failed", 0)
    total_count = result.get("total", 0)

    summary = f"总计: {total_count} | 成功: {success_count} | 失败: {failed_count}"

    details = result.get("details", [])
    table_data = [
        [d["id"], d.get("name", ""), d.get("status", ""), d.get("error", "")]
        for d in details
    ]

    popup(
        title,
        [
            put_markdown(f"**{summary}**"),
            put_table(table_data, header=["ID", "名称", "状态", "错误"]),
            [put_buttons(["关闭"], onclick=lambda: close_popup())],
        ],
    )