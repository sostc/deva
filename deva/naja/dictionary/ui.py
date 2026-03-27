"""数据字典管理 UI"""

from datetime import datetime
from typing import Optional

from pywebio.input import actions, file_upload, input, input_group, select, textarea
from pywebio.session import run_async

from ..tables import parse_uploaded_dataframe
from ..common.ui_style import apply_strategy_like_styles, render_empty_state, render_stats_cards, format_timestamp, render_status_badge, render_detail_section
from ..scheduler.ui import (
    build_cron_expr_wizard,
    choose_scheduler_trigger,
    humanize_cron,
)
from ..scheduler import preview_next_runs


DEFAULT_DICT_CODE = '''# 字典数据获取函数
# 必须定义 fetch_data() 函数
# 返回字典数据 (通常是 pandas DataFrame)

def fetch_data():
    import pandas as pd

    # 示例：返回股票基础信息
    return pd.DataFrame({
        "code": ["000001", "000002"],
        "name": ["平安银行", "万科A"],
        "industry": ["银行", "房地产"]
    })
'''


def _fmt_size(size: int) -> str:
    if not size:
        return "-"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def _refresh_label(entry) -> str:
    source_mode = (getattr(entry._metadata, "source_mode", "task") or "task").strip().lower()
    if source_mode == "upload":
        return "手动上传（按需更新）"

    mode = (getattr(entry._metadata, "execution_mode", "timer") or "timer").strip().lower()
    if mode == "timer":
        return f"自动更新（每 {int(getattr(entry._metadata, 'interval_seconds', 300) or 300)} 秒）"

    if mode == "scheduler":
        trig = (getattr(entry._metadata, "scheduler_trigger", "interval") or "interval").strip().lower()
        if trig == "cron":
            expr = (getattr(entry._metadata, "cron_expr", "") or "").strip()
            return _humanize_cron(expr)
        if trig == "date":
            run_at = (getattr(entry._metadata, "run_at", "") or "").strip()
            return f"自动更新（一次性: {run_at or '-'})"
        return f"自动更新（间隔 {int(getattr(entry._metadata, 'interval_seconds', 300) or 300)} 秒）"

    src = (getattr(entry._metadata, "event_source", "log") or "log").strip().lower()
    cond = (getattr(entry._metadata, "event_condition", "") or "").strip()
    return f"自动更新（事件触发: {src} / {cond or '任意事件'}）"


def _source_mode_label(entry) -> str:
    source_mode = (getattr(entry._metadata, "source_mode", "task") or "task").strip().lower()
    labels = {
        "upload": "仅上传数据",
        "task": "仅鲜活任务",
        "upload_and_task": "上传初始数据 + 鲜活任务",
    }
    return labels.get(source_mode, source_mode)


def _humanize_cron(expr: str) -> str:
    """将 cron 表达式转换为人类可读描述（使用共享函数）"""
    return f"自动更新（{humanize_cron(expr)}）"


def _refresh_detail_text(entry) -> str:
    source_mode = (getattr(entry._metadata, "source_mode", "task") or "task").strip().lower()
    if source_mode == "upload":
        return "手动上传维护，不自动调度"

    mode = (getattr(entry._metadata, "execution_mode", "timer") or "timer").strip().lower()
    if mode == "timer":
        interval = int(getattr(entry._metadata, "interval_seconds", 300) or 300)
        return f"Timer 固定间隔执行，每 {interval} 秒刷新一次"

    if mode == "scheduler":
        trig = (getattr(entry._metadata, "scheduler_trigger", "interval") or "interval").strip().lower()
        if trig == "interval":
            interval = int(getattr(entry._metadata, "interval_seconds", 300) or 300)
            return f"Scheduler / interval，每 {interval} 秒刷新一次"
        if trig == "date":
            run_at = (getattr(entry._metadata, "run_at", "") or "").strip()
            return f"Scheduler / date，将在 {run_at or '-'} 执行一次"
        expr = (getattr(entry._metadata, "cron_expr", "") or "").strip()
        next_runs = _preview_next_runs(expr, count=1)
        next_tip = f"；下次执行：{next_runs[0]}" if next_runs else ""
        return f"Scheduler / cron，{_humanize_cron(expr)}{next_tip}"

    src = (getattr(entry._metadata, "event_source", "log") or "log").strip().lower()
    cond_type = (getattr(entry._metadata, "event_condition_type", "contains") or "contains").strip().lower()
    cond = (getattr(entry._metadata, "event_condition", "") or "").strip()
    return f"EventTrigger，监听 {src}，条件类型 {cond_type}，条件 {cond or '任意事件'}"


def _build_payload_overview(payload):
    import random

    import pandas as pd

    if isinstance(payload, pd.DataFrame):
        row_count = len(payload)
        col_count = len(payload.columns)
        col_preview = ", ".join([str(c) for c in payload.columns[:8]]) or "-"
        summary = f"DataFrame 概要: {row_count} 行 × {col_count} 列；列示例: {col_preview}"
        if row_count == 0:
            return summary, ("empty", None)
        sample_n = min(8, row_count)
        seed = random.randint(1, 10_000_000)
        sample_df = payload.sample(n=sample_n, random_state=seed) if row_count > sample_n else payload
        return summary, ("dataframe", sample_df)

    if isinstance(payload, dict):
        keys = list(payload.keys())
        key_count = len(keys)
        sample_n = min(8, key_count)
        sample_keys = random.sample(keys, sample_n) if key_count > sample_n else keys
        subset = {k: payload.get(k) for k in sample_keys}
        return f"Dict 概要: {key_count} 个键；随机展示 {len(sample_keys)} 个键值", ("json", subset)

    if isinstance(payload, list):
        total = len(payload)
        sample_n = min(8, total)
        if total > sample_n:
            sample_items = random.sample(payload, sample_n)
        else:
            sample_items = payload
        return f"List 概要: 共 {total} 项；随机展示 {len(sample_items)} 项", ("json", sample_items)

    text = str(payload)
    snippet = text[:500] + ("..." if len(text) > 500 else "")
    return f"文本概要: 长度 {len(text)} 字符", ("text", snippet)


def _render_health_badge(last_status: str) -> str:
    if last_status == "success":
        return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#e3f2fd;color:#1565c0;">✓ 健康</span>'
    if last_status == "error":
        return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#ffebee;color:#c62828;">✗ 异常</span>'
    return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#f5f5f5;color:#757575;">- -</span>'


def _dict_type_options():
    return [
        {"label": "维表", "value": "dimension"},
        {"label": "映射", "value": "mapping"},
        {"label": "股票板块", "value": "stock_basic_block"},
        {"label": "股票基础", "value": "stock_basic"},
        {"label": "行业", "value": "industry"},
        {"label": "自定义", "value": "custom"},
    ]


def _source_mode_options():
    return [
        {"label": "仅上传数据（手动维护）", "value": "upload"},
        {"label": "仅鲜活任务（自动拉取）", "value": "task"},
        {"label": "上传初始数据 + 鲜活任务", "value": "upload_and_task"},
    ]


def _parse_hhmm(value: str) -> Optional[tuple]:
    """解析 HH:MM 格式时间（使用共享函数）"""
    from ..scheduler import parse_hhmm
    return parse_hhmm(value)


def _preview_next_runs(cron_expr: str, count: int = 5) -> list:
    """预览 cron 表达式未来执行时间（使用共享函数）"""
    return preview_next_runs(cron_expr, count)


def _task_mode_intro_html(mode: str) -> str:
    if mode == "timer":
        return """
        <div style="margin:8px 0 14px 0;padding:12px;border-radius:8px;background:#eef7ff;color:#245b8f;">
            <div style="font-weight:600;margin-bottom:6px;">Timer（固定间隔执行）</div>
            <div style="font-size:13px;line-height:1.6;">适合轮询更新，例：每 60 秒刷新一次字典。</div>
        </div>
        """
    if mode == "scheduler":
        return """
        <div style="margin:8px 0 14px 0;padding:12px;border-radius:8px;background:#f1f8ef;color:#2f6b2f;">
            <div style="font-weight:600;margin-bottom:6px;">Scheduler（计划调度）</div>
            <div style="font-size:13px;line-height:1.6;">适合按日程执行，支持 interval / cron / date。</div>
        </div>
        """
    return """
    <div style="margin:8px 0 14px 0;padding:12px;border-radius:8px;background:#fff5ec;color:#7a4d1f;">
        <div style="font-weight:600;margin-bottom:6px;">EventTrigger（事件触发）</div>
        <div style="font-size:13px;line-height:1.6;">监听 log/bus 事件，满足条件时刷新字典。</div>
    </div>
    """


async def _choose_fresh_task_mode(ctx: dict, default_mode: str = "timer", title: str = "第 2 步：选择鲜活任务运行分类") -> Optional[str]:
    """选择鲜活任务模式（使用共享 UI 组件）"""
    from ..scheduler.ui import choose_execution_mode
    return await choose_execution_mode(ctx, default_mode=default_mode, title=title)


async def _choose_scheduler_trigger(ctx: dict, default_trigger: str = "interval", title: str = "第 3 步：选择 Scheduler 触发方式") -> Optional[str]:
    """选择调度触发方式（使用共享 UI 组件）"""
    return await choose_scheduler_trigger(ctx, default_trigger=default_trigger, title=title)


async def _build_cron_expr_wizard(ctx: dict, default_expr: str = "") -> Optional[str]:
    """构建 Cron 表达式生成向导（使用共享 UI 组件）"""
    return await build_cron_expr_wizard(ctx, default_expr=default_expr, step_title="步骤4")


async def _collect_fresh_task_config(ctx: dict, entry=None) -> Optional[dict]:
    default_mode = (getattr(entry._metadata, "execution_mode", "timer") if entry else "timer")
    mode = await _choose_fresh_task_mode(ctx, default_mode=default_mode)
    if not mode:
        return None
    ctx["put_html"](_task_mode_intro_html(mode))

    config = {
        "execution_mode": mode,
        "scheduler_trigger": "interval",
        "interval_seconds": int(getattr(entry._metadata, "interval_seconds", 300) if entry else 300),
        "cron_expr": (getattr(entry._metadata, "cron_expr", "") if entry else ""),
        "run_at": (getattr(entry._metadata, "run_at", "") if entry else ""),
        "event_source": (getattr(entry._metadata, "event_source", "log") if entry else "log"),
        "event_condition_type": (getattr(entry._metadata, "event_condition_type", "contains") if entry else "contains"),
        "event_condition": (getattr(entry._metadata, "event_condition", "") if entry else ""),
    }

    if mode == "scheduler":
        trig_default = (getattr(entry._metadata, "scheduler_trigger", "interval") if entry else "interval")
        trig = await _choose_scheduler_trigger(ctx, default_trigger=trig_default)
        if not trig:
            return None
        config["scheduler_trigger"] = trig
        if trig == "cron":
            cron_expr = await _build_cron_expr_wizard(ctx, default_expr=config["cron_expr"])
            if not cron_expr:
                return None
            config["cron_expr"] = cron_expr
    return config


def _extract_uploaded_payload(file_payload: dict):
    if not file_payload:
        return None
    df = parse_uploaded_dataframe(file_payload)
    return df


def _open_file_config_manager(mgr, ctx: dict):
    """打开文件配置管理器"""
    from pywebio.session import run_async
    run_async(_render_file_config_manager(ctx, mgr))


async def _render_file_config_manager(ctx: dict, mgr):
    """渲染文件配置管理界面"""
    from pywebio.output import put_html, put_table, put_buttons, put_markdown, put_code, put_text, popup, close_popup
    from pywebio.input import input_group, actions, input, textarea, select
    from deva.naja.config.file_config import (
        list_configs,
        load_config,
        save_config,
        delete_config,
        get_config_path,
        get_dict_file_config_manager,
        FileConfigMetadata,
    )

    file_mgr = get_dict_file_config_manager()

    with popup("📁 文件配置管理", size="large", closable=True):
        put_markdown("### 字典文件配置管理")
        put_html("<p style='color:#666;font-size:13px;'>配置文件位于 <code>config/dictionaries/</code> 目录，可以提交 git 进行版本控制。</p>")

        existing_configs = list_configs("dictionary")

        if existing_configs:
            table_data = []
            for name in existing_configs:
                config = load_config(name, "dictionary")
                if not config:
                    continue
                meta = config.get('metadata', {})
                func_code = config.get('func_code', '')
                path = get_config_path(name, "dictionary")

                edit_btn = ctx["put_buttons"](
                    [{"label": "编辑", "value": f"edit_{name}", "color": "primary"}],
                    onclick=lambda v, n=name: None
                )
                delete_btn = ctx["put_buttons"](
                    [{"label": "删除", "value": f"delete_{name}", "color": "danger"}],
                    onclick=lambda v, n=name: None
                )
                view_btn = ctx["put_buttons"](
                    [{"label": "查看代码", "value": f"view_{name}", "color": "info"}],
                    onclick=lambda v, n=name: None
                )

                table_data.append([
                    name,
                    f'<span style="color:#666;">{meta.get("description", "")[:40]}...</span>',
                    len(func_code),
                    str(path),
                    edit_btn,
                    delete_btn,
                    view_btn,
                ])

            put_table(table_data, header=["名称", "描述", "代码行数", "文件路径", "编辑", "删除", "查看代码"])
        else:
            put_html('<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无文件配置</div>')

        put_html('<div style="margin-top:16px;">', scope="dict_content")
        put_buttons(
            [{"label": "➕ 创建配置文件", "value": "create", "color": "primary"}],
            onclick=lambda v: None,
            scope="dict_content"
        )
        put_html('</div>', scope="dict_content")


async def _show_file_config_detail(ctx: dict, name: str):
    """显示文件配置的详细信息"""
    from pywebio.output import popup, put_markdown, put_code, put_html, put_table, close_popup
    from deva.naja.config.file_config import load_config, get_config_path

    config = load_config(name, "dictionary")
    if not config:
        ctx["toast"]("配置文件不存在", color="error")
        return

    meta = config.get('metadata', {})
    func_code = config.get('func_code', '')
    path = get_config_path(name, "dictionary")

    with popup(f"配置文件详情: {name}", size="large", closable=True):
        put_markdown(f"### {name}")
        put_html(f"<p style='color:#666;font-size:12px;'>路径: <code>{path}</code></p>")

        put_markdown("#### 元数据")
        put_table([
            ["ID", meta.get('id', '')],
            ["名称", meta.get('name', '')],
            ["描述", meta.get('description', '')],
            ["标签", ', '.join(meta.get('tags', []))],
            ["字典类型", meta.get('dict_type', '')],
            ["执行模式", meta.get('execution_mode', '')],
            ["调度触发", meta.get('scheduler_trigger', '')],
            ["Cron", meta.get('cron_expr', '')],
            ["刷新启用", str(meta.get('refresh_enabled', ''))],
        ], header=["字段", "值"])

        if func_code:
            put_markdown("#### fetch_data 代码")
            put_code(func_code, language="python")


async def render_dictionary_admin(ctx: dict):
    """渲染字典管理面板"""
    ctx["set_scope"]("dict_content")
    _render_dict_content(ctx)


def _render_dict_content(ctx: dict):
    """渲染字典内容（支持局部刷新）"""
    from pywebio.output import clear

    from . import get_dictionary_manager

    mgr = get_dictionary_manager()

    entries = mgr.list_all()
    stats = mgr.get_stats()

    clear("dict_content")
    apply_strategy_like_styles(ctx, scope="dict_content", include_compact_table=True)

    ctx["put_html"](_render_dict_stats_html(stats), scope="dict_content")

    if entries:
        table_data = _build_table_data(ctx, entries, mgr)
        ctx["put_table"](table_data, header=["名称", "类型", "来源", "状态", "健康", "大小", "最后更新", "鲜活方式", "操作"], scope="dict_content")
    else:
        ctx["put_html"](render_empty_state("暂无字典，点击下方按钮创建"), scope="dict_content")

    ctx["put_html"]('<div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;">', scope="dict_content")
    ctx["put_buttons"]([{"label": "➕ 创建字典", "value": "create", "color": "primary"}], onclick=lambda v, m=mgr, c=ctx: _create_dict_dialog(m, c), scope="dict_content")
    ctx["put_buttons"]([{"label": "📁 文件配置管理", "value": "file_config", "color": "info"}], onclick=lambda v, m=mgr, c=ctx: _open_file_config_manager(m, c), scope="dict_content")
    ctx["put_html"]("</div>", scope="dict_content")


def _render_dict_stats_html(stats: dict) -> str:
    return render_stats_cards([
        {"label": "总字典数", "value": stats["total"], "gradient": "linear-gradient(135deg,#667eea,#764ba2)", "shadow": "rgba(102,126,234,0.3)"},
        {"label": "运行中", "value": stats["running"], "gradient": "linear-gradient(135deg,#11998e,#38ef7d)", "shadow": "rgba(17,153,142,0.3)"},
        {"label": "健康", "value": stats["success"], "gradient": "linear-gradient(135deg,#4facfe,#00f2fe)", "shadow": "rgba(79,172,254,0.3)"},
        {"label": "异常", "value": stats["error"], "gradient": "linear-gradient(135deg,#ff416c,#ff4b2b)", "shadow": "rgba(255,65,108,0.3)"},
        {"label": "文件配置", "value": stats.get("file_based", 0), "gradient": "linear-gradient(135deg,#f093fb,#f5576c)", "shadow": "rgba(245,87,108,0.3)"},
    ])


def _build_table_data(ctx: dict, entries: list, mgr) -> list:
    table_data = []
    for e in entries:
        status_html = render_status_badge(e.is_running)

        last_status = getattr(e._state, "last_status", "")
        health_html = _render_health_badge(last_status)

        dict_type = getattr(e._metadata, "dict_type", "dimension")
        type_labels = {
            "dimension": "维表",
            "mapping": "映射",
            "custom": "自定义",
            "stock_basic_block": "股票板块",
            "stock_basic": "股票基础",
            "industry": "行业",
        }
        type_label = type_labels.get(dict_type, dict_type)
        type_html = f'<span style="background:#f3e5f5;color:#7b1fa2;padding:2px 8px;border-radius:4px;font-size:12px;">{type_label}</span>'

        source_label = "📁 文件" if mgr._is_file_based(e) else "💾 NB"
        source_html = f'<span style="background:#e8f5e9;color:#2e7d32;padding:2px 8px;border-radius:4px;font-size:12px;">{source_label}</span>'

        toggle_color = "danger" if e.is_running else "success"

        action_btns = ctx["put_buttons"](
            [
                {"label": "详情", "value": f"detail_{e.id}", "color": "info"},
                {"label": "编辑", "value": f"edit_{e.id}", "color": "primary"},
                {"label": "执行", "value": f"run_{e.id}", "color": "warning"},
                {"label": "清空", "value": f"clear_{e.id}", "color": "default"},
                {"label": "停止" if e.is_running else "启动", "value": f"toggle_{e.id}", "color": toggle_color},
                {"label": "删除", "value": f"delete_{e.id}", "color": "danger"},
            ],
            onclick=lambda v, m=mgr, c=ctx: _handle_dict_action(v, m, c),
        )

        table_data.append(
            [
                ctx["put_html"](f"<strong>{e.name}</strong>"),
                ctx["put_html"](type_html),
                ctx["put_html"](source_html),
                ctx["put_html"](status_html),
                ctx["put_html"](health_html),
                _fmt_size(getattr(e._state, "data_size_bytes", 0)),
                ctx["put_html"](f"<span style='font-size:12px;'>{format_timestamp(getattr(e._state, 'last_update_ts', 0))}</span>"),
                ctx["put_html"](f"<span style='font-size:12px;'>{_refresh_label(e)}</span>"),
                action_btns,
            ]
        )

    return table_data


def _handle_dict_action(action: str, mgr, ctx: dict):
    """处理字典操作"""
    parts = action.split("_")
    action_type = parts[0]
    entry_id = "_".join(parts[1:])

    if action_type == "detail":
        run_async(_show_dict_detail(ctx, mgr, entry_id))
        return
    if action_type == "edit":
        run_async(_edit_dict_dialog(ctx, mgr, entry_id))
        return
    if action_type == "toggle":
        entry = mgr.get(entry_id)
        if entry and entry.is_running:
            mgr.stop(entry_id)
            ctx["toast"]("已停止", color="warning")
        else:
            result = mgr.start(entry_id)
            if result.get("success"):
                ctx["toast"]("已启动", color="success")
            else:
                ctx["toast"](f"启动失败: {result.get('error')}", color="error")
    elif action_type == "run":
        result = mgr.run_once_async(entry_id)
        if result.get("success"):
            ctx["toast"]("执行任务已提交", color="success")
        else:
            ctx["toast"](f"执行失败: {result.get('error')}", color="error")
        return
    elif action_type == "clear":
        entry = mgr.get(entry_id)
        if entry:
            result = entry.clear_payload()
            if result.get("success"):
                ctx["toast"]("已清空数据", color="warning")
            else:
                ctx["toast"](f"清空失败: {result.get('error')}", color="error")
    elif action_type == "delete":
        mgr.delete(entry_id)
        ctx["toast"]("已删除", color="error")

    _render_dict_content(ctx)


async def _show_dict_detail(ctx: dict, mgr, entry_id: str):
    """显示字典详情"""
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("字典不存在", color="error")
        return

    with ctx["popup"](f"字典详情: {entry.name}", size="large", closable=True):
        ctx["put_html"](render_detail_section("📊 基本信息"))

        dict_type = getattr(entry._metadata, "dict_type", "dimension")
        type_labels = {
            "dimension": "维表",
            "mapping": "映射",
            "custom": "自定义",
            "stock_basic_block": "股票板块",
            "stock_basic": "股票基础",
            "industry": "行业",
        }
        type_label = type_labels.get(dict_type, dict_type)

        ctx["put_table"](
            [
                ["ID", entry.id],
                ["名称", entry.name],
                ["类型", type_label],
                ["描述", getattr(entry._metadata, "description", "") or "-"],
                ["状态", "运行中" if entry.is_running else "已停止"],
                ["数据来源", _source_mode_label(entry)],
                ["鲜活配置", _refresh_detail_text(entry)],
                ["创建时间", format_timestamp(entry._metadata.created_at)],
            ],
            header=["字段", "值"],
        )

        ctx["put_html"](render_detail_section("📈 运行统计"))

        last_status = getattr(entry._state, "last_status", "")
        ctx["put_table"](
            [
                ["最后状态", last_status or "-"],
                ["最后更新", format_timestamp(getattr(entry._state, "last_update_ts", 0))],
                ["数据大小", _fmt_size(getattr(entry._state, "data_size_bytes", 0))],
                ["运行次数", entry._state.run_count],
                ["错误次数", entry._state.error_count],
                ["最后错误时间", format_timestamp(getattr(entry._state, "last_error_ts", 0))],
                ["最后错误", entry._state.last_error or "-"],
            ],
            header=["字段", "值"],
        )

        ctx["put_html"](render_detail_section("📦 最新数据"))

        payload = entry.get_payload()
        if payload is not None:
            try:
                import json
                summary_text, content = _build_payload_overview(payload)
                ctx["put_html"](
                    f'<div style="margin-bottom:10px;padding:10px;border-radius:8px;background:#f6f8fa;color:#333;font-size:13px;">{summary_text}</div>'
                )
                content_type, content_data = content
                if content_type == "dataframe" and content_data is not None:
                    ctx["put_html"](content_data.to_html(index=False))
                elif content_type == "json":
                    ctx["put_code"](json.dumps(content_data, ensure_ascii=False, default=str, indent=2), language="json")
                elif content_type == "text":
                    ctx["put_text"](str(content_data))
                else:
                    ctx["put_html"]('<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无可展示样本</div>')
            except Exception:
                ctx["put_text"](str(payload)[:2000])
        else:
            ctx["put_html"]('<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无数据</div>')

        ctx["put_html"](render_detail_section("💻 fetch_data 源码"))

        if entry.func_code:
            ctx["put_code"](entry.func_code, language="python")
        else:
            ctx["put_text"]("当前字典为手动上传模式，无 fetch_data 代码")


async def _choose_source_mode(ctx: dict, default_mode: str = "task", title: str = "第 1 步：选择字典创建方式"):
    form = await ctx["input_group"](
        title,
        [
            ctx["select"]("数据来源方式", name="source_mode", options=_source_mode_options(), value=default_mode),
            ctx["actions"]("操作", [{"label": "下一步", "value": "next"}, {"label": "取消", "value": "cancel"}], name="action"),
        ],
    )
    if not form or form.get("action") == "cancel":
        return None
    return str(form.get("source_mode", default_mode) or default_mode).strip().lower()


def _build_dict_form_fields(mode: str, *, entry=None, task_config: dict = None):
    task_config = task_config or {}
    default_interval = int(task_config.get("interval_seconds", getattr(entry._metadata, "interval_seconds", 300) if entry else 300))
    default_run_at = str(task_config.get("run_at", getattr(entry._metadata, "run_at", "") if entry else ""))
    default_event_source = str(task_config.get("event_source", getattr(entry._metadata, "event_source", "log") if entry else "log"))
    default_event_cond = str(task_config.get("event_condition", getattr(entry._metadata, "event_condition", "") if entry else ""))
    default_event_cond_type = str(task_config.get("event_condition_type", getattr(entry._metadata, "event_condition_type", "contains") if entry else "contains"))

    fields = [
        input("名称", name="name", value=(entry.name if entry else ""), placeholder="例如：股票基础字典"),
        textarea("描述", name="description", rows=2, value=(getattr(entry._metadata, "description", "") if entry else ""), placeholder="说明这个字典的用途（可选）"),
        select("字典类型", name="dict_type", options=_dict_type_options(), value=(getattr(entry._metadata, "dict_type", "dimension") if entry else "dimension")),
    ]

    if mode in {"upload", "upload_and_task"}:
        fields.append(file_upload("上传初始数据（csv/xls/xlsx）", name="upload_file", accept=".csv,.xls,.xlsx", max_size="10M"))

    if mode in {"task", "upload_and_task"}:
        execution_mode = str(task_config.get("execution_mode", "timer") or "timer").strip().lower()
        scheduler_trigger = str(task_config.get("scheduler_trigger", "interval") or "interval").strip().lower()

        if execution_mode == "timer":
            fields.append(input("执行间隔（秒）", name="interval", type="number", value=default_interval))
        elif execution_mode == "scheduler":
            if scheduler_trigger == "interval":
                fields.append(input("执行间隔（秒）", name="interval", type="number", value=default_interval))
            elif scheduler_trigger == "date":
                fields.append(input("执行时间", name="run_at", value=default_run_at, placeholder="例如：2026-03-05 15:30:00"))
            else:
                fields.append(input("Cron 表达式（自动生成，可修改）", name="cron_expr", value=str(task_config.get("cron_expr", "")), placeholder="例如：*/5 * * * *"))
        else:
            fields.extend(
                [
                    select("事件源", name="event_source", options=[{"label": "log", "value": "log"}, {"label": "bus", "value": "bus"}], value=default_event_source),
                    select(
                        "条件类型",
                        name="event_condition_type",
                        options=[
                            {"label": "contains", "value": "contains"},
                            {"label": "python_expr（变量 x）", "value": "python_expr"},
                        ],
                        value=default_event_cond_type,
                    ),
                    input("事件条件", name="event_condition", value=default_event_cond, placeholder="例如：error 或 x.get('type') == 'signal'"),
                ]
            )

        fields.append(textarea("fetch_data 代码", name="code", value=(entry.func_code if entry else DEFAULT_DICT_CODE), rows=14, code={"mode": "python", "theme": "darcula"}))

    return fields


async def _edit_dict_dialog(ctx: dict, mgr, entry_id: str):
    """编辑字典对话框"""
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("字典不存在", color="error")
        return

    with ctx["popup"](f"编辑字典: {entry.name}", size="large", closable=True):
        mode = await _choose_source_mode(ctx, default_mode=(getattr(entry._metadata, "source_mode", "task") or "task"), title="第 1 步：选择字典数据来源（编辑）")
        if not mode:
            ctx["close_popup"]()
            return

        task_config = {}
        if mode in {"task", "upload_and_task"}:
            task_config = await _collect_fresh_task_config(ctx, entry=entry)
            if not task_config:
                ctx["close_popup"]()
                return

        fields = _build_dict_form_fields(mode, entry=entry, task_config=task_config)
        fields.append(actions("操作", [{"label": "保存", "value": "save"}, {"label": "取消", "value": "cancel"}], name="action"))
        form = await input_group("第 6 步：编辑字典配置", fields)

        if form and form.get("action") == "cancel":
            ctx["close_popup"]()
            return

        if form and form.get("action") == "save":
            if not form.get("name", "").strip():
                ctx["toast"]("名称不能为空", color="error")
                return

            upload_payload = None
            if mode in {"upload", "upload_and_task"} and form.get("upload_file"):
                try:
                    upload_payload = _extract_uploaded_payload(form.get("upload_file"))
                except Exception as e:
                    ctx["toast"](f"上传文件解析失败: {e}", color="error")
                    return

            task_params = task_config or {}
            if mode in {"task", "upload_and_task"}:
                task_params["func_code"] = form.get("code", "")
                if task_params.get("execution_mode") == "timer":
                    try:
                        task_params["interval_seconds"] = max(5, int(float(form.get("interval", task_params.get("interval_seconds", 300)) or 300)))
                    except Exception:
                        ctx["toast"]("间隔必须是数字", color="error")
                        return
                elif task_params.get("execution_mode") == "scheduler":
                    trig = task_params.get("scheduler_trigger", "interval")
                    if trig == "interval":
                        try:
                            task_params["interval_seconds"] = max(5, int(float(form.get("interval", task_params.get("interval_seconds", 300)) or 300)))
                        except Exception:
                            ctx["toast"]("间隔必须是数字", color="error")
                            return
                    elif trig == "date":
                        task_params["run_at"] = str(form.get("run_at", task_params.get("run_at", "")) or "").strip()
                    else:
                        task_params["cron_expr"] = str(form.get("cron_expr", task_params.get("cron_expr", "")) or "").strip()
                        if not task_params["cron_expr"]:
                            ctx["toast"]("Cron 表达式不能为空", color="error")
                            return
                else:
                    task_params["event_source"] = str(form.get("event_source", task_params.get("event_source", "log")) or "log").strip().lower()
                    task_params["event_condition_type"] = str(form.get("event_condition_type", task_params.get("event_condition_type", "contains")) or "contains").strip().lower()
                    task_params["event_condition"] = str(form.get("event_condition", task_params.get("event_condition", "")) or "")
                    if task_params["event_condition_type"] == "python_expr" and not task_params["event_condition"].strip():
                        ctx["toast"]("python_expr 条件不能为空", color="error")
                        return

            result = mgr.update(
                entry_id,
                name=form.get("name", "").strip(),
                description=form.get("description", "").strip(),
                dict_type=form.get("dict_type", "dimension"),
                source_mode=mode,
                uploaded_data=upload_payload,
                func_code=task_params.get("func_code") if mode in {"task", "upload_and_task"} else "",
                execution_mode=task_params.get("execution_mode"),
                interval_seconds=task_params.get("interval_seconds"),
                scheduler_trigger=task_params.get("scheduler_trigger"),
                cron_expr=task_params.get("cron_expr"),
                run_at=task_params.get("run_at"),
                event_source=task_params.get("event_source"),
                event_condition=task_params.get("event_condition"),
                event_condition_type=task_params.get("event_condition_type"),
            )

            if result.get("success"):
                _render_dict_content(ctx)
                ctx["toast"]("保存成功", color="success")
                ctx["close_popup"]()
            else:
                ctx["toast"](f"保存失败: {result.get('error')}", color="error")


def _create_dict_dialog(mgr, ctx: dict):
    """创建字典对话框"""
    run_async(_create_dict_dialog_async(mgr, ctx))


async def _create_dict_dialog_async(mgr, ctx: dict):
    """创建字典对话框（异步）"""
    with ctx["popup"]("创建字典", size="large", closable=True):
        ctx["put_markdown"]("### 创建数据字典")
        ctx["put_html"]("<p style='color:#666;font-size:13px;'>可直接上传数据，或创建鲜活任务自动更新数据。</p>")

        mode = await _choose_source_mode(ctx, default_mode="task", title="第 1 步：选择字典数据来源")
        if not mode:
            ctx["close_popup"]()
            return

        task_config = {}
        if mode in {"task", "upload_and_task"}:
            task_config = await _collect_fresh_task_config(ctx, entry=None)
            if not task_config:
                ctx["close_popup"]()
                return

        fields = _build_dict_form_fields(mode, entry=None, task_config=task_config)
        fields.append(actions("操作", [{"label": "创建", "value": "create"}, {"label": "取消", "value": "cancel"}], name="action"))
        form = await input_group("第 6 步：填写字典配置", fields)

        if form and form.get("action") == "cancel":
            ctx["close_popup"]()
            return

        if form and form.get("action") == "create":
            if not form.get("name", "").strip():
                ctx["toast"]("名称不能为空", color="error")
                return

            upload_payload = None
            if mode in {"upload", "upload_and_task"}:
                if not form.get("upload_file"):
                    ctx["toast"]("请上传初始数据文件", color="error")
                    return
                try:
                    upload_payload = _extract_uploaded_payload(form.get("upload_file"))
                except Exception as e:
                    ctx["toast"](f"上传文件解析失败: {e}", color="error")
                    return

            task_params = task_config or {}
            if mode in {"task", "upload_and_task"}:
                if task_params.get("execution_mode") == "timer":
                    try:
                        task_params["interval_seconds"] = max(5, int(float(form.get("interval", task_params.get("interval_seconds", 300)) or 300)))
                    except Exception:
                        ctx["toast"]("间隔必须是数字", color="error")
                        return
                elif task_params.get("execution_mode") == "scheduler":
                    trig = task_params.get("scheduler_trigger", "interval")
                    if trig == "interval":
                        try:
                            task_params["interval_seconds"] = max(5, int(float(form.get("interval", task_params.get("interval_seconds", 300)) or 300)))
                        except Exception:
                            ctx["toast"]("间隔必须是数字", color="error")
                            return
                    elif trig == "date":
                        task_params["run_at"] = str(form.get("run_at", task_params.get("run_at", "")) or "").strip()
                    else:
                        task_params["cron_expr"] = str(form.get("cron_expr", task_params.get("cron_expr", "")) or "").strip()
                        if not task_params["cron_expr"]:
                            ctx["toast"]("Cron 表达式不能为空", color="error")
                            return
                else:
                    task_params["event_source"] = str(form.get("event_source", task_params.get("event_source", "log")) or "log").strip().lower()
                    task_params["event_condition_type"] = str(form.get("event_condition_type", task_params.get("event_condition_type", "contains")) or "contains").strip().lower()
                    task_params["event_condition"] = str(form.get("event_condition", task_params.get("event_condition", "")) or "")
                    if task_params["event_condition_type"] == "python_expr" and not task_params["event_condition"].strip():
                        ctx["toast"]("python_expr 条件不能为空", color="error")
                        return

            result = mgr.create(
                name=form.get("name", "").strip(),
                description=form.get("description", "").strip(),
                dict_type=form.get("dict_type", "dimension"),
                source_mode=mode,
                uploaded_data=upload_payload,
                func_code=(form.get("code", "") if mode in {"task", "upload_and_task"} else ""),
                execution_mode=task_params.get("execution_mode", "timer"),
                interval_seconds=task_params.get("interval_seconds", 300),
                scheduler_trigger=task_params.get("scheduler_trigger", "interval"),
                cron_expr=task_params.get("cron_expr", ""),
                run_at=task_params.get("run_at", ""),
                event_source=task_params.get("event_source", "log"),
                event_condition=task_params.get("event_condition", ""),
                event_condition_type=task_params.get("event_condition_type", "contains"),
            )

            if result.get("success"):
                _render_dict_content(ctx)
                ctx["toast"]("创建成功", color="success")
                ctx["close_popup"]()
            else:
                ctx["toast"](f"创建失败: {result.get('error')}", color="error")
