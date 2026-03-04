"""任务管理 UI"""

from datetime import datetime

from pywebio.output import put_text, put_markdown, put_table, put_buttons, put_html, toast, popup, close_popup, put_code, use_scope, set_scope
from pywebio.input import input_group, input, textarea, select, actions
from pywebio.session import run_async


DEFAULT_TASK_CODE = '''# 任务执行函数
# 必须定义 execute() 函数
# 支持 async def execute() 异步函数

def execute():
    import time
    print(f"Task executed at {time.strftime('%Y-%m-%d %H:%M:%S')}")
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


async def render_task_admin(ctx: dict):
    """渲染任务管理面板"""
    await ctx["init_naja_ui"]("任务管理")
    set_scope("task_content")
    _render_task_content(ctx)


def _render_task_content(ctx: dict):
    """渲染任务内容（支持局部刷新）"""
    from . import get_task_manager
    from pywebio.output import clear
    
    mgr = get_task_manager()
    
    entries = mgr.list_all()
    stats = mgr.get_stats()
    
    clear("task_content")
    
    ctx["put_html"](_render_task_stats_html(stats), scope="task_content")
    
    if entries:
        table_data = _build_table_data(ctx, entries, mgr)
        ctx["put_table"](table_data, header=["名称", "类型", "状态", "间隔", "成功", "失败", "最后运行", "操作"], scope="task_content")
    else:
        ctx["put_html"]('<div style="padding:40px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无任务，点击下方按钮创建</div>', scope="task_content")
    
    ctx["put_html"]('<div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;">', scope="task_content")
    ctx["put_buttons"]([{"label": "➕ 创建任务", "value": "create"}], 
                       onclick=lambda v, m=mgr, c=ctx: _create_task_dialog(m, c), scope="task_content")
    ctx["put_html"]('</div>', scope="task_content")


def _render_task_stats_html(stats: dict) -> str:
    return f"""
    <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:24px;">
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#667eea,#764ba2);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(102,126,234,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">总任务数</div>
            <div style="font-size:32px;font-weight:700;">{stats['total']}</div>
        </div>
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#11998e,#38ef7d);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(17,153,142,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">成功次数</div>
            <div style="font-size:32px;font-weight:700;">{stats['total_success']}</div>
        </div>
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#ff416c,#ff4b2b);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(255,65,108,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">失败次数</div>
            <div style="font-size:32px;font-weight:700;">{stats['total_failure']}</div>
        </div>
    </div>
    """


def _build_table_data(ctx: dict, entries: list, mgr) -> list:
    table_data = []
    for e in entries:
        status_html = _render_status_badge(e.is_running)
        
        task_type = getattr(e._metadata, "task_type", "interval")
        type_labels = {"interval": "间隔执行", "once": "一次性", "schedule": "定时"}
        type_label = type_labels.get(task_type, task_type)
        type_html = f'<span style="background:#e3f2fd;color:#1565c0;padding:2px 8px;border-radius:4px;font-size:12px;">{type_label}</span>'
        
        interval = f"{getattr(e._metadata, 'interval_seconds', 60):.0f}s"
        
        last_run_ts = getattr(e._state, "last_run_time", 0)
        last_run = _fmt_ts(last_run_ts) if last_run_ts else "-"
        
        action_btns = ctx["put_buttons"]([
            {"label": "详情", "value": f"detail_{e.id}"},
            {"label": "编辑", "value": f"edit_{e.id}"},
            {"label": "停止" if e.is_running else "启动", "value": f"toggle_{e.id}"},
            {"label": "执行一次", "value": f"run_{e.id}"},
            {"label": "删除", "value": f"delete_{e.id}"},
        ], onclick=lambda v, m=mgr, c=ctx: _handle_task_action(v, m, c))
        
        table_data.append([
            ctx["put_html"](f"<strong>{e.name}</strong>"),
            ctx["put_html"](type_html),
            ctx["put_html"](status_html),
            interval,
            ctx["put_html"](f'<span style="color:#28a745;font-weight:500;">{e._state.success_count}</span>'),
            ctx["put_html"](f'<span style="color:#dc3545;font-weight:500;">{e._state.failure_count}</span>'),
            ctx["put_html"](f'<span style="color:#666;font-size:12px;">{last_run}</span>'),
            action_btns,
        ])
    
    return table_data


def _handle_task_action(action: str, mgr, ctx: dict):
    """处理任务操作"""
    parts = action.split("_")
    action_type = parts[0]
    entry_id = "_".join(parts[1:])
    
    if action_type == "detail":
        run_async(_show_task_detail(ctx, mgr, entry_id))
        return
    elif action_type == "edit":
        run_async(_edit_task_dialog(ctx, mgr, entry_id))
        return
    elif action_type == "toggle":
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
    
    with ctx["popup"](f"任务详情: {entry.name}", size="large", closable=True):
        ctx["put_html"](_render_detail_section("📊 基本信息"))
        
        task_type = getattr(entry._metadata, "task_type", "interval")
        type_labels = {"interval": "间隔执行", "once": "一次性", "schedule": "定时"}
        type_label = type_labels.get(task_type, task_type)
        
        ctx["put_table"]([
            ["ID", entry.id],
            ["名称", entry.name],
            ["描述", getattr(entry._metadata, "description", "") or "-"],
            ["状态", "运行中" if entry.is_running else "已停止"],
            ["任务类型", type_label],
            ["间隔", f"{getattr(entry._metadata, 'interval_seconds', 60):.0f} 秒"],
            ["创建时间", _fmt_ts(entry._metadata.created_at)],
        ], header=["字段", "值"])
        
        ctx["put_html"](_render_detail_section("📈 执行统计"))
        
        ctx["put_table"]([
            ["成功次数", entry._state.success_count],
            ["失败次数", entry._state.failure_count],
            ["最后运行", _fmt_ts(entry._state.last_run_time)],
            ["最后结果", (entry._state.last_result or "-")[:100]],
            ["最后错误", entry._state.last_error or "-"],
        ], header=["字段", "值"])
        
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
        form = await ctx["input_group"]("任务配置", [
            ctx["input"]("名称", name="name", value=entry.name),
            ctx["textarea"]("描述", name="description", rows=2, 
                          value=getattr(entry._metadata, "description", "") or ""),
            ctx["select"]("任务类型", name="task_type", options=[
                {"label": "间隔执行", "value": "interval"},
                {"label": "一次性", "value": "once"},
            ], value=getattr(entry._metadata, "task_type", "interval")),
            ctx["input"]("间隔(秒)", name="interval", type="number", 
                        value=getattr(entry._metadata, "interval_seconds", 60)),
            ctx["textarea"]("代码", name="code", 
                          value=entry.func_code or DEFAULT_TASK_CODE, 
                          rows=14, 
                          code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if form and form.get("action") == "cancel":
            ctx["close_popup"]()
            return
        
        if form and form.get("action") == "save":
            if not form.get("name", "").strip():
                ctx["toast"]("名称不能为空", color="error")
                return
            
            result = entry.update_config(
                name=form["name"].strip(),
                description=form.get("description", "").strip(),
                task_type=form.get("task_type"),
                interval_seconds=float(form.get("interval", 60)),
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
        ctx["put_markdown"]("### 创建任务")
        ctx["put_html"]("<p style='color:#666;font-size:13px;'>定时执行 execute() 函数</p>")
        
        form = await ctx["input_group"]("任务配置", [
            ctx["input"]("名称", name="name", placeholder="输入任务名称"),
            ctx["textarea"]("描述", name="description", rows=2, placeholder="任务描述（可选）"),
            ctx["select"]("任务类型", name="task_type", options=[
                {"label": "间隔执行", "value": "interval"},
                {"label": "一次性", "value": "once"},
            ], value="interval"),
            ctx["input"]("间隔(秒)", name="interval", type="number", value=60),
            ctx["textarea"]("代码", name="code", 
                          value=DEFAULT_TASK_CODE, 
                          rows=14, 
                          code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "创建", "value": "create"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if form and form.get("action") == "cancel":
            ctx["close_popup"]()
            return
        
        if form and form.get("action") == "create":
            if not form.get("name", "").strip():
                ctx["toast"]("名称不能为空", color="error")
                return
            
            result = mgr.create(
                name=form["name"].strip(),
                func_code=form.get("code", ""),
                task_type=form.get("task_type", "interval"),
                interval_seconds=float(form.get("interval", 60)),
                description=form.get("description", "").strip(),
            )
            
            if result.get("success"):
                _render_task_content(ctx)
                ctx["toast"]("创建成功", color="success")
                ctx["close_popup"]()
            else:
                ctx["toast"](f"创建失败: {result.get('error')}", color="error")
