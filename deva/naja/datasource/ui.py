"""数据源管理 UI"""

from datetime import datetime

from pywebio.output import put_text, put_markdown, put_table, put_buttons, put_html, toast, popup, close_popup, put_code, use_scope, set_scope
from pywebio.input import input_group, input, textarea, select, actions
from pywebio.session import run_async


DEFAULT_DS_CODE = '''# 数据获取函数
# 必须定义 fetch_data() 函数，返回获取的数据
# 返回 None 表示本次无数据

def fetch_data():
    import time
    return {
        "timestamp": time.time(),
        "value": 42,
        "message": "Hello from data source"
    }
'''


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_ts_short(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S")


async def render_datasource_admin(ctx: dict):
    """渲染数据源管理面板"""
    await ctx["init_naja_ui"]("数据源管理")
    set_scope("ds_content")
    _render_ds_content(ctx)


def _render_ds_content(ctx: dict):
    """渲染数据源内容（支持局部刷新）"""
    from . import get_datasource_manager
    mgr = get_datasource_manager()
    
    entries = mgr.list_all()
    stats = mgr.get_stats()
    
    with use_scope("ds_content", clear=True):
        ctx["put_html"](_render_stats_html(stats))
        
        if entries:
            table_data = _build_table_data(ctx, entries, mgr)
            ctx["put_table"](table_data, header=["名称", "类型", "状态", "简介", "最近数据", "操作"])
        else:
            ctx["put_html"]('<div style="padding:40px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无数据源，点击下方按钮创建</div>')
        
        ctx["put_html"](_render_toolbar_html())
        ctx["put_buttons"]([{"label": "➕ 创建数据源", "value": "create"}], 
                           onclick=lambda v, m=mgr, c=ctx: _create_ds_dialog(m, c))
        ctx["put_buttons"]([{"label": "▶ 全部启动", "value": "start_all"}], 
                           onclick=lambda v, m=mgr, c=ctx: _start_all_ds(m, c))
        ctx["put_buttons"]([{"label": "⏹ 全部停止", "value": "stop_all"}], 
                           onclick=lambda v, m=mgr, c=ctx: _stop_all_ds(m, c))
        ctx["put_html"]('</div>')


def _render_stats_html(stats: dict) -> str:
    return f"""
    <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:24px;">
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#667eea,#764ba2);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(102,126,234,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">总数据源</div>
            <div style="font-size:32px;font-weight:700;">{stats['total']}</div>
        </div>
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#11998e,#38ef7d);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(17,153,142,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">运行中</div>
            <div style="font-size:32px;font-weight:700;">{stats['running']}</div>
        </div>
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#636363,#a2abba);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(99,99,99,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">已停止</div>
            <div style="font-size:32px;font-weight:700;">{stats['stopped']}</div>
        </div>
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#ff416c,#ff4b2b);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(255,65,108,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">错误数</div>
            <div style="font-size:32px;font-weight:700;">{stats['error']}</div>
        </div>
    </div>
    """


def _render_toolbar_html() -> str:
    return '<div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;">'


def _build_table_data(ctx: dict, entries: list, mgr) -> list:
    table_data = []
    for e in entries:
        status_html = _render_status_badge(e.is_running)
        type_label = _get_type_label(e)
        desc_short = _get_description_short(e)
        recent_data_info = _get_recent_data_info(e)
        
        action_btns = ctx["put_buttons"]([
            {"label": "详情", "value": f"detail_{e.id}"},
            {"label": "编辑", "value": f"edit_{e.id}"},
            {"label": "停止" if e.is_running else "启动", "value": f"toggle_{e.id}"},
            {"label": "删除", "value": f"delete_{e.id}"},
        ], onclick=lambda v, m=mgr, c=ctx: _handle_ds_action(v, m, c))
        
        table_data.append([
            ctx["put_html"](f"<strong>{e.name}</strong>"),
            ctx["put_html"](type_label),
            ctx["put_html"](status_html),
            ctx["put_html"](f'<span style="color:#666;font-size:12px;" title="{getattr(e._metadata, "description", "") or ""}">{desc_short}</span>'),
            ctx["put_html"](f'<span style="color:#666;font-size:12px;">{recent_data_info}</span>'),
            action_btns,
        ])
    return table_data


def _render_status_badge(is_running: bool) -> str:
    if is_running:
        return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#e8f5e9;color:#2e7d32;">● 运行中</span>'
    return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#f5f5f5;color:#757575;">○ 已停止</span>'


def _get_type_label(entry) -> str:
    source_type = getattr(entry._metadata, "source_type", "custom")
    labels = {
        "timer": "定时器",
        "stream": "命名流",
        "http": "HTTP服务",
        "kafka": "Kafka",
        "redis": "Redis",
        "tcp": "TCP端口",
        "file": "文件",
        "custom": "自定义",
        "replay": "数据回放",
    }
    label = labels.get(source_type, source_type)
    interval = getattr(entry._metadata, "interval", 5)
    
    type_colors = {
        "timer": "#e3f2fd",
        "stream": "#f3e5f5",
        "http": "#e8f5e9",
        "replay": "#fff3e0",
        "kafka": "#fce4ec",
        "redis": "#e0f2f1",
        "custom": "#f5f5f5",
    }
    bg_color = type_colors.get(source_type, "#f5f5f5")
    text_color = "#1565c0" if source_type == "timer" else "#7b1fa2"
    
    if source_type == "timer":
        return f'<span style="background:{bg_color};color:{text_color};padding:2px 8px;border-radius:4px;font-size:12px;">{label} ({interval:.0f}s)</span>'
    return f'<span style="background:{bg_color};color:{text_color};padding:2px 8px;border-radius:4px;font-size:12px;">{label}</span>'


def _get_description_short(entry) -> str:
    description = getattr(entry._metadata, "description", "") or ""
    return description[:30] + "..." if len(description) > 30 else description or "-"


def _get_recent_data_info(entry) -> str:
    last_data_ts = entry._state.last_data_ts
    total_emitted = entry._state.total_emitted
    if last_data_ts > 0:
        return f"{_fmt_ts_short(last_data_ts)} ({total_emitted}条)"
    return f"无数据 ({total_emitted}条)"


def _start_all_ds(mgr, ctx: dict):
    result = mgr.start_all()
    ctx["toast"](f"启动完成: 成功{result['success']}, 失败{result['failed']}, 跳过{result['skipped']}", color="info")
    _render_ds_content(ctx)


def _stop_all_ds(mgr, ctx: dict):
    result = mgr.stop_all()
    ctx["toast"](f"停止完成: 成功{result['success']}, 失败{result['failed']}, 跳过{result['skipped']}", color="info")
    _render_ds_content(ctx)


def _handle_ds_action(action: str, mgr, ctx: dict):
    """处理数据源操作"""
    parts = action.split("_")
    action_type = parts[0]
    entry_id = "_".join(parts[1:])
    
    if action_type == "detail":
        run_async(_show_ds_detail(ctx, mgr, entry_id))
        return
    elif action_type == "edit":
        run_async(_edit_ds_dialog(ctx, mgr, entry_id))
        return
    elif action_type == "toggle":
        entry = mgr.get(entry_id)
        if entry and entry.is_running:
            mgr.stop(entry_id)
            ctx["toast"]("已停止", color="warning")
        else:
            mgr.start(entry_id)
            ctx["toast"]("已启动", color="success")
    elif action_type == "delete":
        mgr.delete(entry_id)
        ctx["toast"]("已删除", color="error")
    
    _render_ds_content(ctx)


async def _show_ds_detail(ctx: dict, mgr, entry_id: str):
    """显示数据源详情"""
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("数据源不存在", color="error")
        return
    
    with ctx["popup"](f"数据源详情: {entry.name}", size="large", closable=True):
        ctx["put_html"](_render_detail_section("📊 基本信息"))
        
        source_type = getattr(entry._metadata, "source_type", "custom")
        type_labels = {
            "timer": "定时器",
            "stream": "命名流",
            "http": "HTTP服务",
            "kafka": "Kafka",
            "redis": "Redis",
            "tcp": "TCP端口",
            "file": "文件",
            "custom": "自定义",
            "replay": "数据回放",
        }
        type_label = type_labels.get(source_type, source_type)
        
        ctx["put_table"]([
            ["ID", entry.id],
            ["名称", entry.name],
            ["类型", type_label],
            ["描述", getattr(entry._metadata, "description", "") or "-"],
            ["状态", "运行中" if entry.is_running else "已停止"],
            ["间隔", f"{getattr(entry._metadata, 'interval', 5):.1f} 秒"],
            ["创建时间", _fmt_ts(entry._metadata.created_at)],
            ["更新时间", _fmt_ts(entry._metadata.updated_at)],
        ], header=["字段", "值"])
        
        ctx["put_html"](_render_detail_section("📈 运行统计"))
        
        ctx["put_table"]([
            ["发射次数", entry._state.total_emitted],
            ["错误次数", entry._state.error_count],
            ["最后错误", entry._state.last_error or "-"],
            ["最后活动", _fmt_ts(entry._state.last_data_ts)],
            ["启动时间", _fmt_ts(entry._state.start_time)],
        ], header=["字段", "值"])
        
        ctx["put_html"](_render_detail_section("📦 最新数据"))
        
        latest_data = entry.get_latest_data()
        if latest_data is not None:
            try:
                import pandas as pd
                import json
                if isinstance(latest_data, pd.DataFrame):
                    ctx["put_html"](latest_data.head(10).to_html(index=False))
                elif isinstance(latest_data, (dict, list)):
                    ctx["put_code"](json.dumps(latest_data, ensure_ascii=False, default=str, indent=2), language="json")
                else:
                    ctx["put_text"](str(latest_data)[:2000])
            except Exception:
                ctx["put_text"](str(latest_data)[:2000])
        else:
            ctx["put_text"]("暂无数据")
        
        ctx["put_html"](_render_detail_section("💻 执行代码"))
        
        if entry.func_code:
            ctx["put_code"](entry.func_code, language="python")
        else:
            ctx["put_text"]("暂无代码")
        
        dependent_strategies = _get_dependent_strategies(entry_id)
        ctx["put_html"](_render_detail_section("🔗 依赖策略"))
        
        if dependent_strategies:
            strategy_table = []
            for s in dependent_strategies:
                status_html = _render_status_badge(s.get("is_running"))
                strategy_table.append([s.get("name", "-"), ctx["put_html"](status_html)])
            ctx["put_table"](strategy_table, header=["策略名称", "状态"])
        else:
            ctx["put_text"]("暂无依赖策略")


def _render_detail_section(title: str) -> str:
    return f"""
    <div style="margin:20px 0 12px 0;padding-bottom:8px;border-bottom:2px solid #e0e0e0;">
        <span style="font-size:15px;font-weight:600;color:#333;">{title}</span>
    </div>
    """


def _get_dependent_strategies(ds_id: str) -> list:
    """获取依赖该数据源的策略列表"""
    try:
        from ..strategy import get_strategy_manager
        mgr = get_strategy_manager()
        strategies = []
        for s in mgr.list_all():
            bound_ds = getattr(s._metadata, "bound_datasource_id", "")
            if bound_ds == ds_id:
                strategies.append({
                    "id": s.id,
                    "name": s.name,
                    "is_running": s.is_running,
                })
        return strategies
    except Exception:
        return []


async def _edit_ds_dialog(ctx: dict, mgr, entry_id: str):
    """编辑数据源对话框"""
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("数据源不存在", color="error")
        return
    
    source_type = getattr(entry._metadata, "source_type", "custom") or "custom"
    config = getattr(entry._metadata, "config", {}) or {}
    
    replay_tables = _get_replay_tables()
    replay_table_options = [{"label": t["name"], "value": t["name"]} for t in replay_tables]
    if not replay_table_options:
        replay_table_options = [{"label": "无可用回放表", "value": ""}]
    
    with ctx["popup"](f"编辑数据源: {entry.name}", size="large", closable=True):
        ctx["put_html"](_get_ds_type_js())
        
        form = await ctx["input_group"]("数据源配置", [
            ctx["input"]("名称", name="name", required=True, value=entry.name),
            ctx["textarea"]("描述", name="description", rows=2, 
                          value=getattr(entry._metadata, "description", "") or ""),
            ctx["select"]("数据源类型", name="source_type", options=[
                {"label": "自定义代码", "value": "custom"},
                {"label": "数据回放", "value": "replay"},
            ], value=source_type),
            ctx["input"]("间隔(秒)", name="interval", type="number", 
                        value=getattr(entry._metadata, "interval", 5)),
            ctx["select"]("回放表名", name="replay_table", options=replay_table_options, 
                        value=config.get("table_name", "")),
            ctx["input"]("开始时间", name="replay_start_time", 
                        value=config.get("start_time", "") or "",
                        placeholder="格式: YYYY-MM-DD HH:MM:SS，留空从最早开始"),
            ctx["input"]("结束时间", name="replay_end_time", 
                        value=config.get("end_time", "") or "",
                        placeholder="格式: YYYY-MM-DD HH:MM:SS，留空到最新结束"),
            ctx["input"]("回放间隔(秒)", name="replay_interval", type="number", 
                        value=config.get("interval", 1.0)),
            ctx["textarea"]("代码", name="code", 
                          value=entry.func_code or DEFAULT_DS_CODE, 
                          rows=14, 
                          code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if form and form.get("action") == "save":
            new_source_type = form.get("source_type", "custom")
            new_config = {}
            
            if new_source_type == "replay":
                new_config = {
                    "table_name": form.get("replay_table", ""),
                    "start_time": form.get("replay_start_time") or None,
                    "end_time": form.get("replay_end_time") or None,
                    "interval": float(form.get("replay_interval", 1.0) or 1.0),
                }
            
            result = entry.update_config(
                name=form["name"].strip(),
                description=form.get("description", "").strip(),
                source_type=new_source_type,
                config=new_config,
                interval=float(form.get("interval", 5)),
                func_code=form.get("code"),
            )
            
            if result.get("success"):
                ctx["toast"]("保存成功", color="success")
                ctx["close_popup"]()
                _render_ds_content(ctx)
            else:
                ctx["toast"](f"保存失败: {result.get('error')}", color="error")


def _get_replay_tables():
    """获取可用的回放表列表"""
    try:
        from deva import NB
        tables = NB.list_tables()
        replay_tables = []
        for table in tables:
            if table.startswith("ds_") or table.startswith("data_") or "_stream" in table or "_output" in table:
                try:
                    db = NB(table)
                    count = len(list(db.keys()))
                    if count > 0:
                        replay_tables.append({"name": table, "count": count})
                except Exception:
                    pass
        return replay_tables
    except Exception:
        return []


def _get_ds_type_js() -> str:
    return '''
    <script>
    setTimeout(function() {
        const sourceTypeSelect = document.querySelector('select[name="source_type"]');
        if (sourceTypeSelect) {
            function toggleFields() {
                const selectedType = sourceTypeSelect.value;
                const replayTableSelect = document.querySelector('select[name="replay_table"]').closest('.form-group');
                const replayStartTimeInput = document.querySelector('input[name="replay_start_time"]').closest('.form-group');
                const replayEndTimeInput = document.querySelector('input[name="replay_end_time"]').closest('.form-group');
                const replayIntervalInput = document.querySelector('input[name="replay_interval"]').closest('.form-group');
                const intervalInput = document.querySelector('input[name="interval"]').closest('.form-group');
                const codeTextarea = document.querySelector('textarea[name="code"]').closest('.form-group');
                
                if (selectedType === 'replay') {
                    if (replayTableSelect) replayTableSelect.style.display = 'block';
                    if (replayStartTimeInput) replayStartTimeInput.style.display = 'block';
                    if (replayEndTimeInput) replayEndTimeInput.style.display = 'block';
                    if (replayIntervalInput) replayIntervalInput.style.display = 'block';
                    if (intervalInput) intervalInput.style.display = 'none';
                    if (codeTextarea) codeTextarea.style.display = 'none';
                } else {
                    if (replayTableSelect) replayTableSelect.style.display = 'none';
                    if (replayStartTimeInput) replayStartTimeInput.style.display = 'none';
                    if (replayEndTimeInput) replayEndTimeInput.style.display = 'none';
                    if (replayIntervalInput) replayIntervalInput.style.display = 'none';
                    if (intervalInput) intervalInput.style.display = 'block';
                    if (codeTextarea) codeTextarea.style.display = 'block';
                }
            }
            sourceTypeSelect.addEventListener('change', toggleFields);
            toggleFields();
        }
    }, 100);
    </script>
    '''


def _create_ds_dialog(mgr, ctx: dict):
    """创建数据源对话框"""
    run_async(_create_ds_dialog_async(mgr, ctx))


async def _create_ds_dialog_async(mgr, ctx: dict):
    """创建数据源对话框（异步）"""
    replay_tables = _get_replay_tables()
    replay_table_options = [{"label": t["name"], "value": t["name"]} for t in replay_tables]
    if not replay_table_options:
        replay_table_options = [{"label": "无可用回放表", "value": ""}]
    
    with ctx["popup"]("创建数据源", size="large", closable=True):
        ctx["put_markdown"]("### 创建数据源")
        ctx["put_html"]("<p style='color:#666;font-size:13px;'>定时执行 fetch_data() 函数获取数据，或回放历史数据</p>")
        ctx["put_html"](_get_ds_type_js())
        
        form = await ctx["input_group"]("数据源配置", [
            ctx["input"]("名称", name="name", required=True, placeholder="输入数据源名称"),
            ctx["textarea"]("描述", name="description", rows=2, placeholder="数据源描述（可选）"),
            ctx["select"]("数据源类型", name="source_type", options=[
                {"label": "自定义代码", "value": "custom"},
                {"label": "数据回放", "value": "replay"},
            ], value="custom"),
            ctx["input"]("间隔(秒)", name="interval", type="number", value=5),
            ctx["select"]("回放表名", name="replay_table", options=replay_table_options, value=""),
            ctx["input"]("开始时间", name="replay_start_time", placeholder="格式: YYYY-MM-DD HH:MM:SS，留空从最早开始"),
            ctx["input"]("结束时间", name="replay_end_time", placeholder="格式: YYYY-MM-DD HH:MM:SS，留空到最新结束"),
            ctx["input"]("回放间隔(秒)", name="replay_interval", type="number", value=1.0),
            ctx["textarea"]("代码", name="code", 
                          value=DEFAULT_DS_CODE, 
                          rows=14, 
                          code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "创建", "value": "create"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if form and form.get("action") == "create":
            source_type = form.get("source_type", "custom")
            config = {}
            
            if source_type == "replay":
                config = {
                    "table_name": form.get("replay_table", ""),
                    "start_time": form.get("replay_start_time") or None,
                    "end_time": form.get("replay_end_time") or None,
                    "interval": float(form.get("replay_interval", 1.0) or 1.0),
                }
            
            result = mgr.create(
                name=form["name"].strip(),
                func_code=form.get("code", "") if source_type == "custom" else "",
                interval=float(form.get("interval", 5)),
                description=form.get("description", "").strip(),
                source_type=source_type,
                config=config,
            )
            
            if result.get("success"):
                ctx["toast"]("创建成功", color="success")
                ctx["close_popup"]()
                _render_ds_content(ctx)
            else:
                ctx["toast"](f"创建失败: {result.get('error')}", color="error")
