"""任务管理 UI"""

from datetime import datetime
from typing import Optional

from pywebio.session import run_async

from ..common.ui_style import apply_strategy_like_styles, render_empty_state, render_stats_cards
from ..page_help import render_help_collapse
from ..scheduler.ui import (
    build_cron_expr_wizard,
    choose_execution_mode,
    choose_scheduler_trigger,
    get_mode_intro_html,
    get_mode_label,
    get_schedule_desc,
    humanize_cron,
)
from ..scheduler import normalize_execution_mode


DEFAULT_TASK_CODE = '''# 任务执行函数
# 必须定义 execute() 函数
# 支持 async def execute() 异步函数

# EventTrigger 模式下可选接收事件参数: execute(event)
def execute(event=None):
    import time
    print(f"Task executed at {time.strftime('%Y-%m-%d %H:%M:%S')}, event={event}")
    return "done"
'''


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _render_status_badge(is_running: bool) -> str:
    if is_running:
        return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#e8f5e9;color:#2e7d32;">● 运行中</span>'
    return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#f5f5f5;color:#757575;">○ 已停止</span>'


def _render_detail_section(title: str) -> str:
    return f"""
    <div style="margin:20px 0 12px 0;padding-bottom:8px;border-bottom:2px solid #e0e0e0;">
        <span style="font-size:15px;font-weight:600;color:#333;">{title}</span>
    </div>
    """


def _normalize_mode(entry) -> str:
    """标准化执行模式（使用共享函数）"""
    mode = (getattr(entry._metadata, "execution_mode", "") or "").strip().lower()
    task_type = (getattr(entry._metadata, "task_type", "") or "").strip().lower()
    return normalize_execution_mode(mode, task_type)


def _mode_label(mode: str) -> str:
    """获取模式标签（使用共享函数）"""
    return get_mode_label(mode)


def _schedule_desc(entry) -> str:
    """获取调度描述（使用共享函数）"""
    mode = _normalize_mode(entry)
    return get_schedule_desc(
        execution_mode=mode,
        scheduler_trigger=getattr(entry._metadata, "scheduler_trigger", "interval"),
        interval_seconds=getattr(entry._metadata, "interval_seconds", 60.0),
        cron_expr=getattr(entry._metadata, "cron_expr", ""),
        run_at=getattr(entry._metadata, "run_at", ""),
        event_source=getattr(entry._metadata, "event_source", "log"),
        event_condition=getattr(entry._metadata, "event_condition", ""),
        event_condition_type=getattr(entry._metadata, "event_condition_type", "contains"),
    )


def _humanize_cron(expr: str) -> str:
    """将 cron 表达式转换为人类可读描述（使用共享函数）"""
    return humanize_cron(expr)


def _is_dictionary_refresh_task(entry) -> bool:
    name = str(getattr(entry, "name", "") or "").strip().lower()
    desc = str(getattr(entry._metadata, "description", "") or "").strip()
    return name.startswith("dict_refresh_") or ("字典" in desc and "鲜活任务" in desc)


def _is_llm_or_bandit_auto_task(entry) -> bool:
    name = str(getattr(entry, "name", "") or "").strip().lower()
    return name in ("llm_auto_adjust", "bandit_auto_run", "llm_auto_adjust_task")


def _split_entries_by_tab(entries: list):
    normal = []
    dict_tasks = []
    llm_bandit_tasks = []
    for e in entries:
        if _is_dictionary_refresh_task(e):
            dict_tasks.append(e)
        elif _is_llm_or_bandit_auto_task(e):
            llm_bandit_tasks.append(e)
        else:
            normal.append(e)
    return normal, dict_tasks, llm_bandit_tasks


def _resolve_task_type(mode: str, scheduler_trigger: str) -> str:
    if mode == "timer":
        return "interval"
    if mode == "scheduler":
        return "once" if scheduler_trigger == "date" else "schedule"
    return "event_trigger"


def _parse_hhmm(value: str) -> Optional[tuple]:
    """解析 HH:MM 格式时间（使用共享函数）"""
    from ..scheduler import parse_hhmm
    return parse_hhmm(value)


def _preview_next_runs(cron_expr: str, count: int = 5) -> list:
    """预览 cron 表达式未来执行时间（使用共享函数）"""
    from ..scheduler import preview_next_runs
    return preview_next_runs(cron_expr, count)


async def _build_cron_expr_wizard(ctx: dict, default_expr: str = "") -> Optional[str]:
    """构建 Cron 表达式生成向导（使用共享 UI 组件）"""
    return await build_cron_expr_wizard(ctx, default_expr=default_expr, step_title="步骤2")


def _mode_intro_html(mode: str) -> str:
    """获取执行模式的介绍 HTML（使用共享函数）"""
    return get_mode_intro_html(mode)


async def _choose_create_mode(ctx: dict, default_mode: str = "timer", title: str = "第 1 步：选择任务运行分类") -> Optional[str]:
    """选择创建模式（使用共享 UI 组件）"""
    return await choose_execution_mode(ctx, default_mode=default_mode, title=title)


async def _choose_scheduler_trigger(ctx: dict) -> Optional[str]:
    """选择调度触发方式（使用共享 UI 组件）"""
    return await choose_scheduler_trigger(ctx, default_trigger="interval")


async def _choose_scheduler_trigger_with_default(
    ctx: dict, default_trigger: str = "interval", title: str = "第 2 步：选择 Scheduler 触发方式"
) -> Optional[str]:
    """选择调度触发方式（使用共享 UI 组件）"""
    return await choose_scheduler_trigger(ctx, default_trigger=default_trigger, title=title)


def _create_base_fields(ctx: dict, *, default_name: str = "", default_desc: str = "", default_code: str = DEFAULT_TASK_CODE) -> list:
    return [
        ctx["input"]("名称", name="name", placeholder="例如：行情心跳检测", value=default_name),
        ctx["textarea"]("描述", name="description", rows=2, placeholder="这个任务是做什么的（可选）", value=default_desc),
        ctx["textarea"]("代码", name="code", value=default_code, rows=14, code={"mode": "python", "theme": "darcula"}),
    ]


async def _collect_create_form(ctx: dict, mode: str) -> Optional[dict]:
    fields = _create_base_fields(ctx)

    if mode == "timer":
        fields.insert(2, ctx["input"]("执行间隔（秒）", name="interval", type="number", value=60))
    elif mode == "scheduler":
        trigger = await _choose_scheduler_trigger(ctx)
        if not trigger:
            return None
        fields.append(ctx["select"]("Scheduler Trigger", name="scheduler_trigger", options=[
            {"label": "interval", "value": "interval"},
            {"label": "cron", "value": "cron"},
            {"label": "date", "value": "date"},
        ], value=trigger))
        if trigger == "interval":
            fields.insert(2, ctx["input"]("执行间隔（秒）", name="interval", type="number", value=60))
        elif trigger == "cron":
            cron_expr = await _build_cron_expr_wizard(ctx)
            if not cron_expr:
                return None
            fields.insert(2, ctx["input"]("Cron 表达式（自动生成，可修改）", name="cron_expr", value=cron_expr, placeholder="例如：*/5 * * * *"))
        else:
            fields.insert(2, ctx["input"]("执行时间", name="run_at", placeholder="例如：2026-03-05 15:30:00"))
    else:
        fields.insert(2, ctx["select"]("事件源", name="event_source", options=[
            {"label": "log（日志流）", "value": "log"},
            {"label": "bus（事件总线）", "value": "bus"},
        ], value="log"))
        fields.insert(3, ctx["select"]("条件类型", name="event_condition_type", options=[
            {"label": "contains（字符串包含）", "value": "contains"},
            {"label": "python_expr（表达式，变量 x）", "value": "python_expr"},
        ], value="contains"))
        fields.insert(4, ctx["input"]("触发条件", name="event_condition", placeholder="例如：error 或 x.get('type') == 'signal'"))

    fields.append(
        ctx["actions"](
            "操作",
            [
                {"label": "创建任务", "value": "create"},
                {"label": "取消", "value": "cancel"},
            ],
            name="action",
        )
    )
    return await ctx["input_group"]("第 3 步：填写任务表单", fields)


async def _collect_edit_form(ctx: dict, entry, mode: str) -> Optional[dict]:
    fields = _create_base_fields(
        ctx,
        default_name=entry.name,
        default_desc=getattr(entry._metadata, "description", "") or "",
        default_code=entry.func_code or DEFAULT_TASK_CODE,
    )
    scheduler_trigger_default = (getattr(entry._metadata, "scheduler_trigger", "interval") or "interval").strip().lower()

    if mode == "timer":
        fields.insert(2, ctx["input"]("执行间隔（秒）", name="interval", type="number", value=getattr(entry._metadata, "interval_seconds", 60)))
    elif mode == "scheduler":
        trigger = await _choose_scheduler_trigger_with_default(
            ctx, default_trigger=scheduler_trigger_default, title="第 2 步：选择 Scheduler 触发方式（编辑）"
        )
        if not trigger:
            return None
        fields.append(
            ctx["select"](
                "Scheduler Trigger",
                name="scheduler_trigger",
                options=[
                    {"label": "interval", "value": "interval"},
                    {"label": "cron", "value": "cron"},
                    {"label": "date", "value": "date"},
                ],
                value=trigger,
            )
        )
        if trigger == "interval":
            fields.insert(
                2,
                ctx["input"]("执行间隔（秒）", name="interval", type="number", value=getattr(entry._metadata, "interval_seconds", 60)),
            )
        elif trigger == "cron":
            current_expr = (getattr(entry._metadata, "cron_expr", "") or "")
            cron_expr = await _build_cron_expr_wizard(ctx, default_expr=current_expr)
            if not cron_expr:
                return None
            fields.insert(
                2,
                ctx["input"](
                    "Cron 表达式",
                    name="cron_expr",
                    placeholder="例如：*/5 * * * *",
                    value=cron_expr,
                ),
            )
        else:
            fields.insert(
                2,
                ctx["input"](
                    "执行时间",
                    name="run_at",
                    placeholder="例如：2026-03-05 15:30:00",
                    value=(getattr(entry._metadata, "run_at", "") or ""),
                ),
            )
    else:
        fields.insert(
            2,
            ctx["select"](
                "事件源",
                name="event_source",
                options=[
                    {"label": "log（日志流）", "value": "log"},
                    {"label": "bus（事件总线）", "value": "bus"},
                ],
                value=(getattr(entry._metadata, "event_source", "log") or "log"),
            ),
        )
        fields.insert(
            3,
            ctx["select"](
                "条件类型",
                name="event_condition_type",
                options=[
                    {"label": "contains（字符串包含）", "value": "contains"},
                    {"label": "python_expr（表达式，变量 x）", "value": "python_expr"},
                ],
                value=(getattr(entry._metadata, "event_condition_type", "contains") or "contains"),
            ),
        )
        fields.insert(
            4,
            ctx["input"](
                "触发条件",
                name="event_condition",
                placeholder="例如：error 或 x.get('type') == 'signal'",
                value=(getattr(entry._metadata, "event_condition", "") or ""),
            ),
        )

    fields.append(
        ctx["actions"](
            "操作",
            [
                {"label": "保存修改", "value": "save"},
                {"label": "取消", "value": "cancel"},
            ],
            name="action",
        )
    )
    return await ctx["input_group"]("第 3 步：编辑任务表单", fields)


def _parse_task_form(form: dict) -> dict:
    mode = str(form.get("execution_mode", "timer") or "timer").strip().lower()
    scheduler_trigger = str(form.get("scheduler_trigger", "interval") or "interval").strip().lower()

    try:
        interval_seconds = float(form.get("interval", 60) or 60)
    except Exception:
        return {"success": False, "error": "间隔必须是数字"}

    cron_expr = str(form.get("cron_expr", "") or "").strip()
    run_at = str(form.get("run_at", "") or "").strip()
    event_source = str(form.get("event_source", "log") or "log").strip().lower()
    event_condition_type = str(form.get("event_condition_type", "contains") or "contains").strip().lower()
    event_condition = str(form.get("event_condition", "") or "")

    if mode == "scheduler" and scheduler_trigger == "cron" and not cron_expr:
        return {"success": False, "error": "Scheduler + cron 需要填写 cron 表达式"}

    if mode == "scheduler" and scheduler_trigger == "date" and run_at:
        try:
            datetime.fromisoformat(run_at)
        except Exception:
            return {"success": False, "error": "run_at 格式错误，示例: 2026-03-05 15:30:00"}

    if mode == "event_trigger" and event_condition_type == "python_expr" and not event_condition.strip():
        return {"success": False, "error": "EventTrigger + python_expr 需要填写条件表达式"}

    return {
        "success": True,
        "task_type": _resolve_task_type(mode, scheduler_trigger),
        "execution_mode": mode,
        "interval_seconds": max(0.1, interval_seconds),
        "scheduler_trigger": scheduler_trigger,
        "cron_expr": cron_expr,
        "run_at": run_at,
        "event_source": event_source,
        "event_condition_type": event_condition_type,
        "event_condition": event_condition,
    }


async def render_task_admin(ctx: dict):
    """渲染任务管理面板"""
    ctx["set_scope"]("task_content")
    if "_task_tab" not in ctx:
        ctx["_task_tab"] = "normal"
    _render_task_content(ctx)


def _render_task_content(ctx: dict):
    """渲染任务内容（支持局部刷新）"""
    from pywebio.output import clear

    from . import get_task_manager

    mgr = get_task_manager()

    entries = mgr.list_all()
    normal_entries, dict_entries, llm_bandit_entries = _split_entries_by_tab(entries)
    active_tab = str(ctx.get("_task_tab", "normal") or "normal").strip().lower()
    if active_tab not in {"normal", "dictionary", "llm_bandit"}:
        active_tab = "normal"
    
    if active_tab == "normal":
        visible_entries = normal_entries
    elif active_tab == "dictionary":
        visible_entries = dict_entries
    else:
        visible_entries = llm_bandit_entries
    
    stats = _build_task_stats(visible_entries)

    clear("task_content")
    apply_strategy_like_styles(ctx, scope="task_content", include_compact_table=True)

    ctx["put_html"](_render_task_stats_html(stats), scope="task_content")

    ctx["put_html"]('<div style="margin-bottom:12px;display:flex;gap:10px;flex-wrap:wrap;">', scope="task_content")
    ctx["put_buttons"](
        [
            {"label": f"普通任务 ({len(normal_entries)})", "value": "tab_normal"},
            {"label": f"LLM/Bandit ({len(llm_bandit_entries)})", "value": "tab_llm_bandit"},
            {"label": f"数据字典 ({len(dict_entries)})", "value": "tab_dictionary"},
        ],
        onclick=lambda v, c=ctx: _handle_task_tab_switch(v, c),
        scope="task_content",
    )
    ctx["put_html"]("</div>", scope="task_content")

    if visible_entries:
        table_data = _build_table_data(ctx, visible_entries, mgr)
        ctx["put_table"](
            table_data,
            header=["名称", "执行方式", "状态", "成功", "失败", "最后运行", "操作"],
            scope="task_content",
        )
    else:
        ctx["put_html"](render_empty_state("当前标签下暂无任务"), scope="task_content")

    ctx["put_html"]('<div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;">', scope="task_content")
    if active_tab == "normal":
        ctx["put_buttons"](
            [{"label": "➕ 创建任务", "value": "create", "color": "primary"}], onclick=lambda v, m=mgr, c=ctx: _create_task_dialog(m, c), scope="task_content"
        )
    ctx["put_html"]("</div>", scope="task_content")

    render_help_collapse("task")


def _handle_task_tab_switch(action: str, ctx: dict):
    if action == "tab_dictionary":
        ctx["_task_tab"] = "dictionary"
    elif action == "tab_llm_bandit":
        ctx["_task_tab"] = "llm_bandit"
    else:
        ctx["_task_tab"] = "normal"
    _render_task_content(ctx)


def _build_task_stats(entries: list) -> dict:
    total = len(entries)
    total_success = sum(getattr(e._state, "success_count", 0) for e in entries)
    total_failure = sum(getattr(e._state, "failure_count", 0) for e in entries)
    return {"total": total, "total_success": total_success, "total_failure": total_failure}


def _render_task_stats_html(stats: dict) -> str:
    return render_stats_cards([
        {"label": "总任务数", "value": stats["total"], "gradient": "linear-gradient(135deg,#667eea,#764ba2)", "shadow": "rgba(102,126,234,0.3)"},
        {"label": "成功次数", "value": stats["total_success"], "gradient": "linear-gradient(135deg,#11998e,#38ef7d)", "shadow": "rgba(17,153,142,0.3)"},
        {"label": "失败次数", "value": stats["total_failure"], "gradient": "linear-gradient(135deg,#ff416c,#ff4b2b)", "shadow": "rgba(255,65,108,0.3)"},
    ])


def _build_table_data(ctx: dict, entries: list, mgr) -> list:
    table_data = []
    for e in entries:
        status_html = _render_status_badge(e.is_running)

        mode = _normalize_mode(e)
        
        is_llm_bandit = _is_llm_or_bandit_auto_task(e)
        if is_llm_bandit:
            badge_html = '<span style="background:#10b981;color:#fff;padding:2px 6px;border-radius:4px;font-size:10px;margin-right:4px;">🤖</span>'
        else:
            badge_html = ''
        
        execution_mode_html = f'<span style="display:block;">{badge_html}<span style="background:#e3f2fd;color:#1565c0;padding:2px 8px;border-radius:4px;font-size:12px;">{_mode_label(mode)}</span><br><span style="font-size:11px;">{_schedule_desc(e)}</span></span>'

        last_run_ts = getattr(e._state, "last_run_time", 0)
        last_run = _fmt_ts(last_run_ts) if last_run_ts else "-"
        toggle_color = "danger" if e.is_running else "success"

        action_btns = ctx["put_buttons"](
            [
                {"label": "详情", "value": f"detail_{e.id}", "color": "info"},
                {"label": "编辑", "value": f"edit_{e.id}", "color": "primary"},
                {"label": "停止" if e.is_running else "启动", "value": f"toggle_{e.id}", "color": toggle_color},
                {"label": "执行一次", "value": f"run_{e.id}", "color": "warning"},
                {"label": "删除", "value": f"delete_{e.id}", "color": "danger"},
            ],
            onclick=lambda v, m=mgr, c=ctx: _handle_task_action(v, m, c),
        )

        table_data.append(
            [
                ctx["put_html"](
                    f'<div title="{e.name}" style="max-width:460px;white-space:normal;word-break:break-word;line-height:1.4;"><strong>{e.name}</strong></div>'
                ),
                ctx["put_html"](execution_mode_html),
                ctx["put_html"](status_html),
                ctx["put_html"](f'<span style="color:#28a745;font-weight:500;">{e._state.success_count}</span>'),
                ctx["put_html"](f'<span style="color:#dc3545;font-weight:500;">{e._state.failure_count}</span>'),
                ctx["put_html"](f'<span style="color:#666;font-size:12px;">{last_run}</span>'),
                action_btns,
            ]
        )

    return table_data


def _handle_task_action(action: str, mgr, ctx: dict):
    """处理任务操作"""
    parts = action.split("_")
    action_type = parts[0]
    entry_id = "_".join(parts[1:])

    if action_type == "detail":
        run_async(_show_task_detail(ctx, mgr, entry_id))
        return
    if action_type == "edit":
        run_async(_edit_task_dialog(ctx, mgr, entry_id))
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
    elif action_type == "delete":
        mgr.delete(entry_id)
        ctx["toast"]("已删除", color="error")

    _render_task_content(ctx)


async def _show_task_detail(ctx: dict, mgr, entry_id: str):
    """显示任务详情"""
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("任务不存在", color="error")
        return

    mode = _normalize_mode(entry)

    with ctx["popup"](f"任务详情: {entry.name}", size="large", closable=True):
        ctx["put_html"](_render_detail_section("📊 基本信息"))

        ctx["put_table"](
            [
                ["ID", entry.id],
                ["名称", entry.name],
                ["描述", getattr(entry._metadata, "description", "") or "-"],
                ["状态", "运行中" if entry.is_running else "已停止"],
                ["执行方式", _mode_label(mode)],
                ["触发配置", _schedule_desc(entry)],
                ["创建时间", _fmt_ts(entry._metadata.created_at)],
            ],
            header=["字段", "值"],
        )

        ctx["put_html"](_render_detail_section("📈 执行统计"))

        ctx["put_table"](
            [
                ["成功次数", entry._state.success_count],
                ["失败次数", entry._state.failure_count],
                ["最后运行", _fmt_ts(entry._state.last_run_time)],
                ["最后结果", (entry._state.last_result or "-")[:100]],
                ["最后错误", entry._state.last_error or "-"],
            ],
            header=["字段", "值"],
        )

        ctx["put_html"](_render_detail_section("💻 执行代码"))

        if entry.func_code:
            ctx["put_code"](entry.func_code, language="python")
        else:
            ctx["put_text"]("暂无代码")


async def _edit_task_dialog(ctx: dict, mgr, entry_id: str):
    """编辑任务对话框"""
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("任务不存在", color="error")
        return

    with ctx["popup"](f"编辑任务: {entry.name}", size="large", closable=True):
        current_mode = _normalize_mode(entry)
        ctx["put_markdown"]("### 编辑任务向导")
        ctx["put_html"]("<p style='color:#666;font-size:13px;'>先选运行分类，再编辑该分类对应字段。</p>")
        mode = await _choose_create_mode(ctx, default_mode=current_mode, title="第 1 步：选择任务运行分类（编辑）")
        if not mode:
            ctx["close_popup"]()
            return
        ctx["put_html"](_mode_intro_html(mode))
        form = await _collect_edit_form(ctx, entry, mode)
        if not form:
            ctx["close_popup"]()
            return
        form["execution_mode"] = mode

        if form and form.get("action") == "cancel":
            ctx["close_popup"]()
            return

        if form and form.get("action") == "save":
            if not form.get("name", "").strip():
                ctx["toast"]("名称不能为空", color="error")
                return

            parsed = _parse_task_form(form)
            if not parsed.get("success"):
                ctx["toast"](parsed.get("error", "参数错误"), color="error")
                return

            result = entry.update_config(
                name=form["name"].strip(),
                description=form.get("description", "").strip(),
                task_type=parsed["task_type"],
                execution_mode=parsed["execution_mode"],
                interval_seconds=parsed["interval_seconds"],
                scheduler_trigger=parsed["scheduler_trigger"],
                cron_expr=parsed["cron_expr"],
                run_at=parsed["run_at"],
                event_source=parsed["event_source"],
                event_condition_type=parsed["event_condition_type"],
                event_condition=parsed["event_condition"],
                func_code=form.get("code"),
            )

            if result.get("success"):
                _render_task_content(ctx)
                ctx["toast"]("保存成功", color="success")
                ctx["close_popup"]()
            else:
                ctx["toast"](f"保存失败: {result.get('error')}", color="error")


def _create_task_dialog(mgr, ctx: dict):
    """创建任务对话框"""
    run_async(_create_task_dialog_async(mgr, ctx))


async def _create_task_dialog_async(mgr, ctx: dict):
    """创建任务对话框（异步）"""
    with ctx["popup"]("创建任务", size="large", closable=True):
        ctx["put_markdown"]("### 新建任务向导")
        ctx["put_html"]("<p style='color:#666;font-size:13px;'>先选任务运行分类，再填写对应配置。减少无关字段，提高填写效率。</p>")
        mode = await _choose_create_mode(ctx)
        if not mode:
            ctx["close_popup"]()
            return
        ctx["put_html"](_mode_intro_html(mode))
        form = await _collect_create_form(ctx, mode)
        if not form:
            ctx["close_popup"]()
            return
        form["execution_mode"] = mode

        if form and form.get("action") == "cancel":
            ctx["close_popup"]()
            return

        if form and form.get("action") == "create":
            if not form.get("name", "").strip():
                ctx["toast"]("名称不能为空", color="error")
                return

            parsed = _parse_task_form(form)
            if not parsed.get("success"):
                ctx["toast"](parsed.get("error", "参数错误"), color="error")
                return

            result = mgr.create(
                name=form["name"].strip(),
                func_code=form.get("code", ""),
                task_type=parsed["task_type"],
                execution_mode=parsed["execution_mode"],
                interval_seconds=parsed["interval_seconds"],
                scheduler_trigger=parsed["scheduler_trigger"],
                cron_expr=parsed["cron_expr"],
                run_at=parsed["run_at"],
                event_source=parsed["event_source"],
                event_condition_type=parsed["event_condition_type"],
                event_condition=parsed["event_condition"],
                description=form.get("description", "").strip(),
            )

            if result.get("success"):
                _render_task_content(ctx)
                ctx["toast"]("创建成功", color="success")
                ctx["close_popup"]()
            else:
                ctx["toast"](f"创建失败: {result.get('error')}", color="error")
