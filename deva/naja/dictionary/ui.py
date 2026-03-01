"""数据字典管理 UI"""

from datetime import datetime

from pywebio.output import put_text, put_markdown, put_table, put_buttons, put_html, toast, popup, close_popup, put_code, use_scope, set_scope
from pywebio.input import input_group, input, textarea, select, actions
from pywebio.session import run_async


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


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_size(size: int) -> str:
    if not size:
        return "-"
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / 1024 / 1024:.1f} MB"


def _schedule_label(entry) -> str:
    schedule_type = getattr(entry._metadata, "schedule_type", "interval")
    if schedule_type == "daily":
        daily_time = getattr(entry._metadata, "daily_time", "03:00")
        return f"每日 {daily_time}"
    interval = getattr(entry._metadata, "interval_seconds", 300)
    return f"每 {interval} 秒"


def _render_status_badge(is_running: bool) -> str:
    if is_running:
        return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#e8f5e9;color:#2e7d32;">● 运行中</span>'
    return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#f5f5f5;color:#757575;">○ 已停止</span>'


def _render_health_badge(last_status: str) -> str:
    if last_status == "success":
        return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#e3f2fd;color:#1565c0;">✓ 健康</span>'
    elif last_status == "error":
        return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#ffebee;color:#c62828;">✗ 异常</span>'
    return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#f5f5f5;color:#757575;">- -</span>'


def _render_detail_section(title: str) -> str:
    return f"""
    <div style="margin:20px 0 12px 0;padding-bottom:8px;border-bottom:2px solid #e0e0e0;">
        <span style="font-size:15px;font-weight:600;color:#333;">{title}</span>
    </div>
    """


async def render_dictionary_admin(ctx: dict):
    """渲染字典管理面板"""
    await ctx["init_naja_ui"]("数据字典管理")
    set_scope("dict_content")
    _render_dict_content(ctx)


def _render_dict_content(ctx: dict):
    """渲染字典内容（支持局部刷新）"""
    from . import get_dictionary_manager
    mgr = get_dictionary_manager()
    
    entries = mgr.list_all()
    stats = mgr.get_stats()
    
    with use_scope("dict_content", clear=True):
        ctx["put_html"](_render_dict_stats_html(stats))
        
        if entries:
            table_data = _build_table_data(ctx, entries, mgr)
            ctx["put_table"](table_data, header=["名称", "类型", "状态", "健康", "大小", "最后更新", "更新频率", "操作"])
        else:
            ctx["put_html"]('<div style="padding:40px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无字典，点击下方按钮创建</div>')
        
        ctx["put_html"]('<div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;">')
        ctx["put_buttons"]([{"label": "➕ 创建字典", "value": "create"}], 
                           onclick=lambda v, m=mgr, c=ctx: _create_dict_dialog(m, c))
        ctx["put_html"]('</div>')


def _render_dict_stats_html(stats: dict) -> str:
    return f"""
    <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:24px;">
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#667eea,#764ba2);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(102,126,234,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">总字典数</div>
            <div style="font-size:32px;font-weight:700;">{stats['total']}</div>
        </div>
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#11998e,#38ef7d);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(17,153,142,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">运行中</div>
            <div style="font-size:32px;font-weight:700;">{stats['running']}</div>
        </div>
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#4facfe,#00f2fe);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(79,172,254,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">健康</div>
            <div style="font-size:32px;font-weight:700;">{stats['success']}</div>
        </div>
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#ff416c,#ff4b2b);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(255,65,108,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">异常</div>
            <div style="font-size:32px;font-weight:700;">{stats['error']}</div>
        </div>
    </div>
    """


def _build_table_data(ctx: dict, entries: list, mgr) -> list:
    table_data = []
    for e in entries:
        status_html = _render_status_badge(e.is_running)
        
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
        
        action_btns = ctx["put_buttons"]([
            {"label": "详情", "value": f"detail_{e.id}"},
            {"label": "编辑", "value": f"edit_{e.id}"},
            {"label": "执行", "value": f"run_{e.id}"},
            {"label": "清空", "value": f"clear_{e.id}"},
            {"label": "停止" if e.is_running else "启动", "value": f"toggle_{e.id}"},
            {"label": "删除", "value": f"delete_{e.id}"},
        ], onclick=lambda v, m=mgr, c=ctx: _handle_dict_action(v, m, c))
        
        table_data.append([
            ctx["put_html"](f"<strong>{e.name}</strong>"),
            ctx["put_html"](type_html),
            ctx["put_html"](status_html),
            ctx["put_html"](health_html),
            _fmt_size(getattr(e._state, "data_size_bytes", 0)),
            _fmt_ts(getattr(e._state, "last_update_ts", 0)),
            _schedule_label(e),
            action_btns,
        ])
    
    return table_data


def _handle_dict_action(action: str, mgr, ctx: dict):
    """处理字典操作"""
    parts = action.split("_")
    action_type = parts[0]
    entry_id = "_".join(parts[1:])
    
    if action_type == "detail":
        run_async(_show_dict_detail(ctx, mgr, entry_id))
        return
    elif action_type == "edit":
        run_async(_edit_dict_dialog(ctx, mgr, entry_id))
        return
    elif action_type == "toggle":
        entry = mgr.get(entry_id)
        if entry and entry.is_running:
            mgr.stop(entry_id)
            ctx["toast"]("已停止", color="warning")
        else:
            mgr.start(entry_id)
            ctx["toast"]("已启动", color="success")
    elif action_type == "run":
        result = mgr.run_once_async(entry_id)
        if result.get("success"):
            ctx["toast"]("已提交异步执行任务", color="success")
        else:
            ctx["toast"](f"执行失败: {result.get('error')}", color="error")
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
        ctx["put_html"](_render_detail_section("📊 基本信息"))
        
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
        
        ctx["put_table"]([
            ["ID", entry.id],
            ["名称", entry.name],
            ["类型", type_label],
            ["描述", getattr(entry._metadata, "description", "") or "-"],
            ["状态", "运行中" if entry.is_running else "已停止"],
            ["调度类型", getattr(entry._metadata, "schedule_type", "interval")],
            ["间隔", f"{getattr(entry._metadata, 'interval_seconds', 300):.0f} 秒"],
            ["每日时间", getattr(entry._metadata, "daily_time", "03:00")],
            ["创建时间", _fmt_ts(entry._metadata.created_at)],
        ], header=["字段", "值"])
        
        ctx["put_html"](_render_detail_section("📈 运行统计"))
        
        last_status = getattr(entry._state, "last_status", "")
        ctx["put_table"]([
            ["最后状态", last_status or "-"],
            ["最后更新", _fmt_ts(getattr(entry._state, "last_update_ts", 0))],
            ["数据大小", _fmt_size(getattr(entry._state, "data_size_bytes", 0))],
            ["运行次数", entry._state.run_count],
            ["错误次数", entry._state.error_count],
            ["最后错误", entry._state.last_error or "-"],
        ], header=["字段", "值"])
        
        ctx["put_html"](_render_detail_section("📦 最新数据"))
        
        payload = entry.get_payload()
        if payload is not None:
            try:
                import pandas as pd
                import json
                if isinstance(payload, pd.DataFrame):
                    ctx["put_html"](payload.head(20).to_html(index=False))
                elif isinstance(payload, (dict, list)):
                    ctx["put_code"](json.dumps(payload, ensure_ascii=False, default=str, indent=2), language="json")
                else:
                    ctx["put_text"](str(payload)[:2000])
            except Exception:
                ctx["put_text"](str(payload)[:2000])
        else:
            ctx["put_html"]('<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无数据</div>')
        
        ctx["put_html"](_render_detail_section("💻 更新代码"))
        
        if entry.func_code:
            ctx["put_code"](entry.func_code, language="python")
        else:
            ctx["put_text"]("暂无代码")


async def _edit_dict_dialog(ctx: dict, mgr, entry_id: str):
    """编辑字典对话框"""
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("字典不存在", color="error")
        return
    
    with ctx["popup"](f"编辑字典: {entry.name}", size="large", closable=True):
        form = await ctx["input_group"]("字典配置", [
            ctx["input"]("名称", name="name", required=True, value=entry.name),
            ctx["textarea"]("描述", name="description", rows=2, 
                          value=getattr(entry._metadata, "description", "") or ""),
            ctx["select"]("字典类型", name="dict_type", options=[
                {"label": "维表", "value": "dimension"},
                {"label": "映射", "value": "mapping"},
                {"label": "股票板块", "value": "stock_basic_block"},
                {"label": "股票基础", "value": "stock_basic"},
                {"label": "行业", "value": "industry"},
                {"label": "自定义", "value": "custom"},
            ], value=getattr(entry._metadata, "dict_type", "dimension")),
            ctx["select"]("调度类型", name="schedule_type", options=[
                {"label": "间隔执行", "value": "interval"},
                {"label": "每日定时", "value": "daily"},
            ], value=getattr(entry._metadata, "schedule_type", "interval")),
            ctx["input"]("间隔(秒)", name="interval", type="number", 
                        value=getattr(entry._metadata, "interval_seconds", 300)),
            ctx["input"]("每日时间", name="daily_time", 
                        value=getattr(entry._metadata, "daily_time", "03:00"),
                        placeholder="HH:MM"),
            ctx["textarea"]("代码", name="code", 
                          value=entry.func_code or DEFAULT_DICT_CODE, 
                          rows=14, 
                          code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if form and form.get("action") == "save":
            result = entry.update_config(
                name=form["name"].strip(),
                description=form.get("description", "").strip(),
                dict_type=form.get("dict_type"),
                schedule_type=form.get("schedule_type"),
                interval_seconds=int(form.get("interval", 300)),
                daily_time=form.get("daily_time", "03:00"),
                func_code=form.get("code"),
            )
            
            if result.get("success"):
                ctx["toast"]("保存成功", color="success")
                ctx["close_popup"]()
                _render_dict_content(ctx)
            else:
                ctx["toast"](f"保存失败: {result.get('error')}", color="error")


def _create_dict_dialog(mgr, ctx: dict):
    """创建字典对话框"""
    run_async(_create_dict_dialog_async(mgr, ctx))


async def _create_dict_dialog_async(mgr, ctx: dict):
    """创建字典对话框（异步）"""
    with ctx["popup"]("创建字典", size="large", closable=True):
        ctx["put_markdown"]("### 创建数据字典")
        ctx["put_html"]("<p style='color:#666;font-size:13px;'>定时执行 fetch_data() 函数更新字典数据</p>")
        
        form = await ctx["input_group"]("字典配置", [
            ctx["input"]("名称", name="name", required=True, placeholder="输入字典名称"),
            ctx["textarea"]("描述", name="description", rows=2, placeholder="字典描述（可选）"),
            ctx["select"]("字典类型", name="dict_type", options=[
                {"label": "维表", "value": "dimension"},
                {"label": "映射", "value": "mapping"},
                {"label": "股票板块", "value": "stock_basic_block"},
                {"label": "股票基础", "value": "stock_basic"},
                {"label": "行业", "value": "industry"},
                {"label": "自定义", "value": "custom"},
            ], value="dimension"),
            ctx["select"]("调度类型", name="schedule_type", options=[
                {"label": "间隔执行", "value": "interval"},
                {"label": "每日定时", "value": "daily"},
            ], value="interval"),
            ctx["input"]("间隔(秒)", name="interval", type="number", value=300),
            ctx["input"]("每日时间", name="daily_time", value="03:00", placeholder="HH:MM"),
            ctx["textarea"]("代码", name="code", 
                          value=DEFAULT_DICT_CODE, 
                          rows=14, 
                          code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "创建", "value": "create"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if form and form.get("action") == "create":
            result = mgr.create(
                name=form["name"].strip(),
                func_code=form.get("code", ""),
                schedule_type=form.get("schedule_type", "interval"),
                interval_seconds=int(form.get("interval", 300)),
                daily_time=form.get("daily_time", "03:00"),
                description=form.get("description", "").strip(),
            )
            
            if result.get("success"):
                ctx["toast"]("创建成功", color="success")
                ctx["close_popup"]()
                _render_dict_content(ctx)
            else:
                ctx["toast"](f"创建失败: {result.get('error')}", color="error")
