"""数据源管理 UI"""

from datetime import datetime

from pywebio.output import put_text, put_markdown, put_table, put_buttons, put_html, toast, popup, close_popup, put_code, use_scope, set_scope
from pywebio.input import input_group, input, textarea, select, actions, radio
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

DEFAULT_FILE_DS_CODE = '''# 文件数据源处理函数
# 参数: line - 文件中的一行内容（或自定义分隔符分割的内容）
# 返回: 处理后的数据，返回 None 则跳过

def fetch_data(line):
    """
    处理文件中的一行数据
    line: 文件中的一行内容
    返回处理后的数据，返回 None 则跳过该行
    """
    # 示例：直接返回行内容
    if line and line.strip():
        return {"content": line.strip()}
    return None
'''

DEFAULT_DIRECTORY_DS_CODE = '''# 目录监控数据源处理函数
# 参数: event - 目录事件对象
# 返回: 处理后的数据，返回 None 则跳过

def fetch_data(event):
    """
    处理目录变化事件
    event: {
        "event": "created" | "modified" | "deleted",
        "path": "文件完整路径",
        "file_info": {"path": ..., "name": ..., "size": ..., "mtime": ...},
        "old_info": {...}  # 仅 modified 事件有
    }
    返回处理后的数据，返回 None 则跳过该事件
    """
    import os
    from datetime import datetime
    
    event_type = event.get("event")
    file_info = event.get("file_info", {})
    
    return {
        "event_type": event_type,
        "file_path": event.get("path"),
        "file_name": file_info.get("name"),
        "file_size": file_info.get("size"),
        "timestamp": datetime.now().isoformat(),
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
    set_scope("ds_content")
    _render_ds_content(ctx)


def _render_ds_content(ctx: dict):
    """渲染数据源内容（支持局部刷新）"""
    from . import get_datasource_manager
    from pywebio.output import clear

    mgr = get_datasource_manager()

    entries = mgr.list_all()
    stats = mgr.get_stats()

    clear("ds_content")

    ctx["put_html"](_render_stats_html(stats), scope="ds_content")

    if entries:
        table_data = _build_table_data(ctx, entries, mgr)
        ctx["put_table"](table_data, header=["名称", "类型", "状态",
                                             "简介", "最近数据", "操作"], scope="ds_content")
    else:
        ctx["put_html"](
            '<div style="padding:40px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无数据源，点击下方按钮创建</div>', scope="ds_content")

    ctx["put_html"](_render_toolbar_html(), scope="ds_content")
    ctx["put_buttons"]([
        {"label": "➕ 创建数据源", "value": "create"},
        {"label": "▶ 全部启动", "value": "start_all"},
        {"label": "⏹ 全部停止", "value": "stop_all"},
    ], onclick=lambda v, m=mgr, c=ctx: _handle_toolbar_action(v, m, c), group=True, scope="ds_content")
    ctx["put_html"]('</div>', scope="ds_content")


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
    interval = getattr(entry._metadata, "interval", 5)

    type_config = {
        "timer": {
            "icon": "⏱️",
            "label": "定时器",
            "title": f"定时器：每 {interval:.0f} 秒执行一次",
            "bg_color": "#e3f2fd",
            "text_color": "#1565c0",
        },
        "stream": {
            "icon": "📡",
            "label": "命名流",
            "title": "命名流：从命名总线订阅数据",
            "bg_color": "#f3e5f5",
            "text_color": "#7b1fa2",
        },
        "http": {
            "icon": "🌐",
            "label": "HTTP服务",
            "title": "HTTP服务：通过HTTP接口获取数据",
            "bg_color": "#e8f5e9",
            "text_color": "#2e7d32",
        },
        "kafka": {
            "icon": "📨",
            "label": "Kafka",
            "title": "Kafka：从Kafka消息队列消费数据",
            "bg_color": "#fce4ec",
            "text_color": "#c2185b",
        },
        "redis": {
            "icon": "🗄️",
            "label": "Redis",
            "title": "Redis：从Redis订阅或拉取数据",
            "bg_color": "#e0f2f1",
            "text_color": "#00695c",
        },
        "tcp": {
            "icon": "🔌",
            "label": "TCP端口",
            "title": "TCP端口：监听TCP端口接收数据",
            "bg_color": "#fff8e1",
            "text_color": "#f57f17",
        },
        "file": {
            "icon": "📄",
            "label": "文件",
            "title": "文件：从文件读取数据",
            "bg_color": "#efebe9",
            "text_color": "#5d4037",
        },
        "directory": {
            "icon": "📂",
            "label": "目录",
            "title": "目录：监控目录中文件变化",
            "bg_color": "#e1f5fe",
            "text_color": "#0277bd",
        },
        "custom": {
            "icon": "⚙️",
            "label": "自定义",
            "title": "自定义：执行自定义代码获取数据",
            "bg_color": "#f5f5f5",
            "text_color": "#616161",
        },
        "replay": {
            "icon": "📼",
            "label": "回放",
            "title": "数据回放：从历史数据表中回放数据",
            "bg_color": "#fff3e0",
            "text_color": "#e65100",
        },
    }

    config = type_config.get(source_type, {
        "icon": "❓",
        "label": source_type,
        "title": source_type,
        "bg_color": "#f5f5f5",
        "text_color": "#616161",
    })

    icon = config["icon"]
    label = config["label"]
    title = config["title"]
    bg_color = config["bg_color"]
    text_color = config["text_color"]

    if source_type == "timer":
        return f'<span title="{title}" style="background:{bg_color};color:{text_color};padding:2px 8px;border-radius:4px;font-size:12px;cursor:help;">{icon} {label} ({interval:.0f}s)</span>'

    return f'<span title="{title}" style="background:{bg_color};color:{text_color};padding:2px 8px;border-radius:4px;font-size:12px;cursor:help;">{icon} {label}</span>'


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


def _handle_toolbar_action(action: str, mgr, ctx: dict):
    """处理工具栏按钮操作"""
    if action == "create":
        _create_ds_dialog(mgr, ctx)
    elif action == "start_all":
        _start_all_ds(mgr, ctx)
    elif action == "stop_all":
        _stop_all_ds(mgr, ctx)


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
            result = mgr.start(entry_id)
            if result.get("success"):
                ctx["toast"]("已启动", color="success")
            else:
                ctx["toast"](f"启动失败: {result.get('error')}", color="error")
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
            ["错误时间", _fmt_ts(entry._state.last_error_ts)],
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
                    ctx["put_code"](json.dumps(latest_data, ensure_ascii=False,
                                               default=str, indent=2), language="json")
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
    interval = getattr(entry._metadata, "interval", 5)
    description = getattr(entry._metadata, "description", "") or ""
    func_code = entry.func_code or DEFAULT_DS_CODE
    result = {"success": False}

    # 根据数据源类型显示对应的编辑表单
    if source_type == "timer":
        form = await ctx["input_group"](f"编辑数据源: {entry.name}", [
            ctx["input"]("名称", name="name", value=entry.name, required=True),
            ctx["textarea"]("描述", name="description", rows=2, value=description),
            ctx["input"]("间隔(秒)", name="interval", type="number", value=interval),
            ctx["textarea"]("代码", name="code", value=func_code, rows=14,
                            code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
                {"label": "取消", "value": "cancel", "color": "danger"},
            ], name="action"),
        ])

        if not form or form.get("action") == "cancel":
            ctx["close_popup"]()
            return

        result = entry.update_config(
            name=form["name"].strip(),
            description=form.get("description", "").strip(),
            interval=float(form.get("interval", 5)),
            func_code=form.get("code"),
        )

    elif source_type == "file":
        form = await ctx["input_group"](f"编辑数据源: {entry.name}", [
            ctx["input"]("名称", name="name", value=entry.name, required=True),
            ctx["textarea"]("描述", name="description", rows=2, value=description),
            ctx["input"]("文件路径", name="file_path", value=config.get("file_path", ""), required=True),
            ctx["input"]("轮询间隔(秒)", name="file_poll_interval", type="number",
                         value=config.get("poll_interval", 0.1)),
            ctx["input"]("分隔符", name="file_delimiter", value=config.get("delimiter", "\\n") or "\\n"),
            ctx["select"]("读取模式", name="file_read_mode", options=[
                {"label": "追踪模式 - 只读取新增内容", "value": "tail"},
                {"label": "全量模式 - 每次读取整个文件", "value": "full"},
            ], value=config.get("read_mode", "tail")),
            ctx["textarea"]("代码", name="code", value=func_code or DEFAULT_FILE_DS_CODE, rows=14,
                            code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
                {"label": "取消", "value": "cancel", "color": "danger"},
            ], name="action"),
        ])

        if not form or form.get("action") == "cancel":
            ctx["close_popup"]()
            return

        result = entry.update_config(
            name=form["name"].strip(),
            description=form.get("description", "").strip(),
            source_type="file",
            config={
                "file_path": form.get("file_path", "").strip(),
                "poll_interval": float(form.get("file_poll_interval", 0.1) or 0.1),
                "delimiter": form.get("file_delimiter", "\\n") or "\\n",
                "read_mode": form.get("file_read_mode", "tail"),
            },
            func_code=form.get("code") or DEFAULT_FILE_DS_CODE,
        )

    elif source_type == "replay":
        replay_tables = _get_replay_tables()
        replay_table_options = [{"label": t["name"], "value": t["name"]} for t in replay_tables]
        if not replay_table_options:
            replay_table_options = [{"label": "无可用回放表", "value": ""}]

        form = await ctx["input_group"](f"编辑数据源: {entry.name}", [
            ctx["input"]("名称", name="name", value=entry.name, required=True),
            ctx["textarea"]("描述", name="description", rows=2, value=description),
            ctx["select"]("回放表名", name="replay_table", options=replay_table_options,
                          value=config.get("table_name", "")),
            ctx["input"]("开始时间", name="replay_start_time",
                         value=config.get("start_time", "") or "",
                         placeholder="YYYY-MM-DD HH:MM:SS，留空从最早开始"),
            ctx["input"]("结束时间", name="replay_end_time",
                         value=config.get("end_time", "") or "",
                         placeholder="YYYY-MM-DD HH:MM:SS，留空到最新结束"),
            ctx["input"]("回放间隔(秒)", name="replay_interval", type="number",
                         value=config.get("interval", 1.0)),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
                {"label": "取消", "value": "cancel", "color": "danger"},
            ], name="action"),
        ])

        if not form or form.get("action") == "cancel":
            ctx["close_popup"]()
            return

        result = entry.update_config(
            name=form["name"].strip(),
            description=form.get("description", "").strip(),
            source_type="replay",
            config={
                "table_name": form.get("replay_table", ""),
                "start_time": form.get("replay_start_time") or None,
                "end_time": form.get("replay_end_time") or None,
                "interval": float(form.get("replay_interval", 1.0) or 1.0),
            },
            func_code="",
        )

    elif source_type == "directory":
        watch_events = config.get("watch_events", ["created", "modified", "deleted"])
        if isinstance(watch_events, str):
            watch_events = [watch_events]

        form = await ctx["input_group"](f"编辑数据源: {entry.name}", [
            ctx["input"]("名称", name="name", value=entry.name, required=True),
            ctx["textarea"]("描述", name="description", rows=2, value=description),
            ctx["input"]("目录路径", name="directory_path", value=config.get("directory_path", ""), required=True,
                         help_text="macOS 用户: 监控 Downloads/Desktop/Documents 等敏感目录需要在系统偏好设置中授予终端「完全磁盘访问权限」"),
            ctx["input"]("轮询间隔(秒)", name="dir_poll_interval", type="number",
                         value=config.get("poll_interval", 1.0)),
            ctx["input"]("文件匹配模式", name="file_pattern", value=config.get("file_pattern", "*.*")),
            ctx["checkbox"]("递归扫描子目录", name="recursive", options=[
                {"label": "递归扫描子目录", "value": "recursive", "selected": config.get("recursive", False)}
            ]),
            ctx["checkbox"]("监控事件", name="watch_events", options=[
                {"label": "文件创建", "value": "created", "selected": "created" in watch_events},
                {"label": "文件修改", "value": "modified", "selected": "modified" in watch_events},
                {"label": "文件删除", "value": "deleted", "selected": "deleted" in watch_events},
            ], value=watch_events),
            ctx["textarea"]("代码", name="code", value=func_code or DEFAULT_DIRECTORY_DS_CODE, rows=14,
                            code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
                {"label": "取消", "value": "cancel", "color": "danger"},
            ], name="action"),
        ])

        if not form or form.get("action") == "cancel":
            ctx["close_popup"]()
            return

        recursive_values = form.get("recursive", [])
        recursive = "recursive" in recursive_values if isinstance(recursive_values, list) else False
        new_watch_events = form.get("watch_events", ["created", "modified", "deleted"])
        if isinstance(new_watch_events, str):
            new_watch_events = [new_watch_events]

        result = entry.update_config(
            name=form["name"].strip(),
            description=form.get("description", "").strip(),
            source_type="directory",
            config={
                "directory_path": form.get("directory_path", "").strip(),
                "poll_interval": float(form.get("dir_poll_interval", 1.0) or 1.0),
                "file_pattern": form.get("file_pattern", "*") or "*",
                "recursive": recursive,
                "watch_events": new_watch_events,
            },
            func_code=form.get("code") or DEFAULT_DIRECTORY_DS_CODE,
        )

    else:
        form = await ctx["input_group"](f"编辑数据源: {entry.name}", [
            ctx["input"]("名称", name="name", value=entry.name, required=True),
            ctx["textarea"]("描述", name="description", rows=2, value=description),
            ctx["input"]("间隔(秒)", name="interval", type="number", value=interval),
            ctx["textarea"]("代码", name="code", value=func_code, rows=14,
                            code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
                {"label": "取消", "value": "cancel", "color": "danger"},
            ], name="action"),
        ])

        if not form or form.get("action") == "cancel":
            ctx["close_popup"]()
            return

        result = entry.update_config(
            name=form["name"].strip(),
            description=form.get("description", "").strip(),
            interval=float(form.get("interval", 5)),
            func_code=form.get("code"),
        )

    if result.get("success"):
        _render_ds_content(ctx)
        ctx["toast"]("保存成功", color="success")
    else:
        ctx["toast"](f"保存失败: {result.get('error')}", color="error")
    
    ctx["close_popup"]()


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
    return ''


def _get_source_type_options() -> list:
    """获取启用的数据源类型选项"""
    from ..config import get_enabled_datasource_types

    all_types = {
        "timer": {"label": "⏱️ 定时器 - 定时执行代码获取数据", "value": "timer"},
        "stream": {"label": "📡 命名流 - 从命名总线订阅数据", "value": "stream"},
        "http": {"label": "🌐 HTTP服务 - 通过HTTP接口获取数据", "value": "http"},
        "kafka": {"label": "📨 Kafka - 从Kafka消息队列消费数据", "value": "kafka"},
        "redis": {"label": "🗄️ Redis - 从Redis订阅或拉取数据", "value": "redis"},
        "tcp": {"label": "🔌 TCP端口 - 监听TCP端口接收数据", "value": "tcp"},
        "file": {"label": "📄 文件 - 监控文件变化读取数据", "value": "file"},
        "directory": {"label": "📂 目录 - 监控目录中文件变化", "value": "directory"},
        "custom": {"label": "⚙️ 自定义代码 - 执行自定义代码获取数据", "value": "custom"},
        "replay": {"label": "📼 数据回放 - 从历史数据表中回放数据", "value": "replay"},
    }

    enabled_types = get_enabled_datasource_types()
    return [all_types[t] for t in enabled_types if t in all_types]


def _create_ds_dialog(mgr, ctx: dict):
    """创建数据源对话框"""
    run_async(_create_ds_dialog_async(mgr, ctx))


async def _create_ds_dialog_async(mgr, ctx: dict):
    """创建数据源对话框（异步）- 两步式流程"""

    # 第一步：选择数据源类型
    source_type_options = _get_source_type_options()

    type_form = await ctx["input_group"]("步骤1: 选择数据源类型", [
        ctx["input"]("名称", name="name", placeholder="输入数据源名称", required=True),
        ctx["textarea"]("描述", name="description", rows=2, placeholder="数据源描述（可选）"),
        radio("数据源类型", name="source_type", options=source_type_options, value="timer"),
        ctx["actions"]("操作", [
            {"label": "下一步", "value": "next"},
            {"label": "取消", "value": "cancel", "color": "danger"},
        ], name="action"),
    ])

    if not type_form or type_form.get("action") == "cancel":
        ctx["close_popup"]()
        return

    source_type = type_form.get("source_type", "timer")
    name = type_form.get("name", "").strip()
    description = type_form.get("description", "").strip()

    if not name:
        ctx["toast"]("名称不能为空", color="error")
        ctx["close_popup"]()
        return

    # 第二步：根据类型填写具体配置
    config_form = await _create_ds_config_form(ctx, source_type)

    if not config_form or config_form.get("action") == "cancel":
        ctx["close_popup"]()
        return

    # 创建数据源
    result = _create_ds_from_form(mgr, name, description, source_type, config_form)

    if result.get("success"):
        _render_ds_content(ctx)
        ctx["toast"]("创建成功", color="success")
    else:
        ctx["toast"](f"创建失败: {result.get('error')}", color="error")
    
    ctx["close_popup"]()


async def _create_ds_config_form(ctx: dict, source_type: str) -> dict:
    """根据数据源类型显示配置表单"""

    if source_type == "timer":
        return await ctx["input_group"]("步骤2: 定时器配置", [
            ctx["input"]("间隔(秒)", name="interval", type="number", value=5, help_text="每隔多少秒执行一次"),
            ctx["textarea"]("代码", name="code", value=DEFAULT_DS_CODE, rows=14,
                            code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "创建", "value": "create"},
                {"label": "返回", "value": "back"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])

    elif source_type == "file":
        return await ctx["input_group"]("步骤2: 文件监控配置", [
            ctx["input"]("文件路径", name="file_path",
                         placeholder="如 /var/log/app.log", required=True),
            ctx["input"]("轮询间隔(秒)", name="file_poll_interval", type="number", value=0.1),
            ctx["input"]("分隔符", name="file_delimiter", value="\\n", help_text="默认为换行符"),
            ctx["select"]("读取模式", name="file_read_mode", options=[
                {"label": "追踪模式 - 只读取新增内容", "value": "tail"},
                {"label": "全量模式 - 每次读取整个文件", "value": "full"},
            ], value="tail"),
            ctx["textarea"]("代码", name="code", value=DEFAULT_FILE_DS_CODE, rows=14,
                            code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "创建", "value": "create"},
                {"label": "返回", "value": "back"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])

    elif source_type == "replay":
        replay_tables = _get_replay_tables()
        replay_table_options = [{"label": t["name"], "value": t["name"]} for t in replay_tables]
        if not replay_table_options:
            replay_table_options = [{"label": "无可用回放表", "value": ""}]

        return await ctx["input_group"]("步骤2: 数据回放配置", [
            ctx["select"]("回放表名", name="replay_table",
                          options=replay_table_options, required=True),
            ctx["input"]("开始时间", name="replay_start_time",
                         placeholder="YYYY-MM-DD HH:MM:SS，留空从最早开始"),
            ctx["input"]("结束时间", name="replay_end_time",
                         placeholder="YYYY-MM-DD HH:MM:SS，留空到最新结束"),
            ctx["input"]("回放间隔(秒)", name="replay_interval", type="number", value=1.0),
            ctx["actions"]("操作", [
                {"label": "创建", "value": "create"},
                {"label": "返回", "value": "back"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])

    elif source_type == "directory":
        return await ctx["input_group"]("步骤2: 目录监控配置", [
            ctx["input"]("目录路径", name="directory_path", placeholder="如 /var/log 或 /tmp/data", required=True,
                        help_text="macOS 用户: 监控 Downloads/Desktop/Documents 等敏感目录需要在系统偏好设置中授予终端「完全磁盘访问权限」"),
            ctx["input"]("轮询间隔(秒)", name="dir_poll_interval", type="number", value=1.0, help_text="每隔多少秒扫描一次目录"),
            ctx["input"]("文件匹配模式", name="file_pattern", value="*.*", placeholder="如 *.log 或 *.txt"),
            ctx["checkbox"]("递归扫描子目录", name="recursive", options=[{"label": "递归扫描子目录", "value": "recursive", "selected": False}]),
            ctx["checkbox"]("监控事件", name="watch_events", options=[
                {"label": "文件创建", "value": "created", "selected": True},
                {"label": "文件修改", "value": "modified", "selected": True},
                {"label": "文件删除", "value": "deleted", "selected": True},
            ], value=["created", "modified", "deleted"]),
            ctx["textarea"]("代码", name="code", value=DEFAULT_DIRECTORY_DS_CODE, rows=14,
                           code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "创建", "value": "create"},
                {"label": "返回", "value": "back"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])

    elif source_type == "custom":
        return await ctx["input_group"]("步骤2: 自定义代码配置", [
            ctx["input"]("间隔(秒)", name="interval", type="number", value=5),
            ctx["textarea"]("代码", name="code", value=DEFAULT_DS_CODE, rows=14,
                            code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "创建", "value": "create"},
                {"label": "返回", "value": "back"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])

    else:
        return await ctx["input_group"]("步骤2: 配置", [
            ctx["input"]("间隔(秒)", name="interval", type="number", value=5),
            ctx["textarea"]("代码", name="code", value=DEFAULT_DS_CODE, rows=14,
                            code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "创建", "value": "create"},
                {"label": "返回", "value": "back"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])


def _create_ds_from_form(mgr, name: str, description: str, source_type: str, form: dict) -> dict:
    """从表单数据创建数据源"""
    config = {}
    func_code = ""
    interval = 5

    if source_type == "replay":
        config = {
            "table_name": form.get("replay_table", ""),
            "start_time": form.get("replay_start_time") or None,
            "end_time": form.get("replay_end_time") or None,
            "interval": float(form.get("replay_interval", 1.0) or 1.0),
        }
    elif source_type == "file":
        config = {
            "file_path": form.get("file_path", "").strip(),
            "poll_interval": float(form.get("file_poll_interval", 0.1) or 0.1),
            "delimiter": form.get("file_delimiter", "\\n") or "\\n",
            "read_mode": form.get("file_read_mode", "tail"),
        }
        func_code = form.get("code", DEFAULT_FILE_DS_CODE)
    elif source_type == "directory":
        recursive_values = form.get("recursive", [])
        recursive = "recursive" in recursive_values if isinstance(
            recursive_values, list) else False
        watch_events = form.get("watch_events", ["created", "modified", "deleted"])
        if isinstance(watch_events, str):
            watch_events = [watch_events]

        config = {
            "directory_path": form.get("directory_path", "").strip(),
            "poll_interval": float(form.get("dir_poll_interval", 1.0) or 1.0),
            "file_pattern": form.get("file_pattern", "*") or "*",
            "recursive": recursive,
            "watch_events": watch_events,
        }
        func_code = form.get("code", DEFAULT_DIRECTORY_DS_CODE)
    else:
        interval = float(form.get("interval", 5))
        func_code = form.get("code", DEFAULT_DS_CODE)

    return mgr.create(
        name=name,
        func_code=func_code,
        interval=interval,
        description=description,
        source_type=source_type,
        config=config,
    )
