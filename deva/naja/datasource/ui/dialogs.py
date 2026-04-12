"""数据源编辑/创建对话框"""

from pywebio.input import radio

from .constants import (
    DEFAULT_DS_CODE, DEFAULT_FILE_DS_CODE, DEFAULT_DIRECTORY_DS_CODE,
    _get_replay_tables, _get_source_type_options,
)
from .schedule import _collect_timer_schedule_config


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

    if source_type == "timer":
        result = await _edit_timer_ds(ctx, entry, description, func_code, interval)
    elif source_type == "file":
        result = await _edit_file_ds(ctx, entry, description, func_code, config)
    elif source_type == "replay":
        result = await _edit_replay_ds(ctx, entry, description, config)
    elif source_type == "directory":
        result = await _edit_directory_ds(ctx, entry, description, func_code, config)
    else:
        result = await _edit_generic_ds(ctx, entry, description, func_code, interval)

    if result and result.get("success"):
        from .table import _render_ds_content
        _render_ds_content(ctx)
        ctx["toast"]("保存成功", color="success")
    elif result:
        ctx["toast"](f'保存失败: {result.get("error")}', color="error")

    ctx["close_popup"]()


async def _edit_timer_ds(ctx, entry, description, func_code, interval):
    """编辑定时器类型数据源"""
    timer_cfg = await _collect_timer_schedule_config(
        ctx,
        defaults={
            "execution_mode": getattr(entry._metadata, "execution_mode", "timer"),
            "scheduler_trigger": getattr(entry._metadata, "scheduler_trigger", "interval"),
            "interval": interval,
            "cron_expr": getattr(entry._metadata, "cron_expr", ""),
            "run_at": getattr(entry._metadata, "run_at", ""),
            "event_source": getattr(entry._metadata, "event_source", "log"),
            "event_condition": getattr(entry._metadata, "event_condition", ""),
            "event_condition_type": getattr(entry._metadata, "event_condition_type", "contains"),
        },
    )
    if not timer_cfg:
        ctx["close_popup"]()
        return {"success": False}

    mode = timer_cfg.get("execution_mode", "timer")
    trig = timer_cfg.get("scheduler_trigger", "interval")

    fields = [
        ctx["input"]("名称", name="name", value=entry.name, required=True),
        ctx["textarea"]("描述", name="description", rows=2, value=description),
    ]
    if mode == "timer":
        fields.append(ctx["input"]("间隔(秒)", name="interval", type="number", value=timer_cfg.get("interval", interval)))
    elif mode == "scheduler":
        if trig == "interval":
            fields.append(ctx["input"]("间隔(秒)", name="interval", type="number", value=timer_cfg.get("interval", interval)))
        elif trig == "date":
            fields.append(ctx["input"]("执行时间", name="run_at", value=timer_cfg.get("run_at", ""), placeholder="例如：2026-03-05 15:30:00"))
        else:
            fields.append(ctx["input"]("Cron 表达式", name="cron_expr", value=timer_cfg.get("cron_expr", ""), placeholder="例如：*/5 * * * *"))
    else:
        fields.extend([
            ctx["select"]("事件源", name="event_source", options=[
                {"label": "log", "value": "log"}, {"label": "bus", "value": "bus"},
            ], value=timer_cfg.get("event_source", "log")),
            ctx["select"]("条件类型", name="event_condition_type", options=[
                {"label": "contains", "value": "contains"}, {"label": "python_expr", "value": "python_expr"},
            ], value=timer_cfg.get("event_condition_type", "contains")),
            ctx["input"]("事件条件", name="event_condition", value=timer_cfg.get("event_condition", "")),
        ])

    fields.extend([
        ctx["textarea"]("代码", name="code", value=func_code, rows=14, code={"mode": "python", "theme": "darcula"}),
        ctx["actions"]("操作", [{"label": "保存", "value": "save"}, {"label": "取消", "value": "cancel", "color": "danger"}], name="action"),
    ])
    form = await ctx["input_group"](f"编辑数据源: {entry.name}", fields)

    if not form or form.get("action") == "cancel":
        return {"success": False}

    interval_val = timer_cfg.get("interval", interval)
    if mode in {"timer", "scheduler"} and trig == "interval":
        interval_val = float(form.get("interval", interval_val) or interval_val)
    if mode == "scheduler" and trig == "date":
        timer_cfg["run_at"] = str(form.get("run_at", timer_cfg.get("run_at", "")) or "").strip()
    if mode == "scheduler" and trig == "cron":
        timer_cfg["cron_expr"] = str(form.get("cron_expr", timer_cfg.get("cron_expr", "")) or "").strip()
        if not timer_cfg["cron_expr"]:
            ctx["toast"]("Cron 表达式不能为空", color="error")
            return {"success": False}
    if mode == "event_trigger":
        timer_cfg["event_source"] = str(form.get("event_source", "log") or "log").strip().lower()
        timer_cfg["event_condition_type"] = str(form.get("event_condition_type", "contains") or "contains").strip().lower()
        timer_cfg["event_condition"] = str(form.get("event_condition", "") or "")
        if timer_cfg["event_condition_type"] == "python_expr" and not timer_cfg["event_condition"].strip():
            ctx["toast"]("python_expr 条件不能为空", color="error")
            return {"success": False}

    return entry.update_config(
        name=form["name"].strip(), description=form.get("description", "").strip(),
        interval=interval_val, execution_mode=timer_cfg.get("execution_mode", "timer"),
        scheduler_trigger=timer_cfg.get("scheduler_trigger", "interval"),
        cron_expr=timer_cfg.get("cron_expr", ""), run_at=timer_cfg.get("run_at", ""),
        event_source=timer_cfg.get("event_source", "log"),
        event_condition=timer_cfg.get("event_condition", ""),
        event_condition_type=timer_cfg.get("event_condition_type", "contains"),
        func_code=form.get("code"),
    )


async def _edit_file_ds(ctx, entry, description, func_code, config):
    """编辑文件类型数据源"""
    form = await ctx["input_group"](f"编辑数据源: {entry.name}", [
        ctx["input"]("名称", name="name", value=entry.name, required=True),
        ctx["textarea"]("描述", name="description", rows=2, value=description),
        ctx["input"]("文件路径", name="file_path", value=config.get("file_path", ""), required=True),
        ctx["input"]("轮询间隔(秒)", name="file_poll_interval", type="number", value=config.get("poll_interval", 0.1)),
        ctx["input"]("分隔符", name="file_delimiter", value=config.get("delimiter", "\\n") or "\\n"),
        ctx["select"]("读取模式", name="file_read_mode", options=[
            {"label": "追踪模式 - 只读取新增内容", "value": "tail"},
            {"label": "全量模式 - 每次读取整个文件", "value": "full"},
        ], value=config.get("read_mode", "tail")),
        ctx["textarea"]("代码", name="code", value=func_code or DEFAULT_FILE_DS_CODE, rows=14, code={"mode": "python", "theme": "darcula"}),
        ctx["actions"]("操作", [{"label": "保存", "value": "save"}, {"label": "取消", "value": "cancel", "color": "danger"}], name="action"),
    ])
    if not form or form.get("action") == "cancel":
        return {"success": False}
    return entry.update_config(
        name=form["name"].strip(), description=form.get("description", "").strip(), source_type="file",
        config={"file_path": form.get("file_path", "").strip(), "poll_interval": float(form.get("file_poll_interval", 0.1) or 0.1),
                "delimiter": form.get("file_delimiter", "\\n") or "\\n", "read_mode": form.get("file_read_mode", "tail")},
        func_code=form.get("code") or DEFAULT_FILE_DS_CODE,
    )


async def _edit_replay_ds(ctx, entry, description, config):
    """编辑回放类型数据源"""
    replay_tables = _get_replay_tables()
    opts = [{"label": t["name"], "value": t["name"]} for t in replay_tables] or [{"label": "无可用回放表", "value": ""}]
    form = await ctx["input_group"](f"编辑数据源: {entry.name}", [
        ctx["input"]("名称", name="name", value=entry.name, required=True),
        ctx["textarea"]("描述", name="description", rows=2, value=description),
        ctx["select"]("回放表名", name="replay_table", options=opts, value=config.get("table_name", "")),
        ctx["input"]("开始时间", name="replay_start_time", value=config.get("start_time", "") or "", placeholder="YYYY-MM-DD HH:MM:SS，留空从最早开始"),
        ctx["input"]("结束时间", name="replay_end_time", value=config.get("end_time", "") or "", placeholder="YYYY-MM-DD HH:MM:SS，留空到最新结束"),
        ctx["input"]("回放间隔(秒)", name="replay_interval", type="number", value=config.get("interval", 1.0)),
        ctx["actions"]("操作", [{"label": "保存", "value": "save"}, {"label": "取消", "value": "cancel", "color": "danger"}], name="action"),
    ])
    if not form or form.get("action") == "cancel":
        return {"success": False}
    return entry.update_config(
        name=form["name"].strip(), description=form.get("description", "").strip(), source_type="replay",
        config={"table_name": form.get("replay_table", ""), "start_time": form.get("replay_start_time") or None,
                "end_time": form.get("replay_end_time") or None, "interval": float(form.get("replay_interval", 1.0) or 1.0)},
        func_code="",
    )


async def _edit_directory_ds(ctx, entry, description, func_code, config):
    """编辑目录监控类型数据源"""
    watch_events = config.get("watch_events", ["created", "modified", "deleted"])
    if isinstance(watch_events, str):
        watch_events = [watch_events]
    form = await ctx["input_group"](f"编辑数据源: {entry.name}", [
        ctx["input"]("名称", name="name", value=entry.name, required=True),
        ctx["textarea"]("描述", name="description", rows=2, value=description),
        ctx["input"]("目录路径", name="directory_path", value=config.get("directory_path", ""), required=True,
                     help_text="macOS: 监控敏感目录需授予终端「完全磁盘访问权限」"),
        ctx["input"]("轮询间隔(秒)", name="dir_poll_interval", type="number", value=config.get("poll_interval", 1.0)),
        ctx["input"]("文件匹配模式", name="file_pattern", value=config.get("file_pattern", "*.*")),
        ctx["checkbox"]("递归扫描子目录", name="recursive", options=[
            {"label": "递归扫描子目录", "value": "recursive", "selected": config.get("recursive", False)}]),
        ctx["checkbox"]("监控事件", name="watch_events", options=[
            {"label": "文件创建", "value": "created", "selected": "created" in watch_events},
            {"label": "文件修改", "value": "modified", "selected": "modified" in watch_events},
            {"label": "文件删除", "value": "deleted", "selected": "deleted" in watch_events},
        ], value=watch_events),
        ctx["textarea"]("代码", name="code", value=func_code or DEFAULT_DIRECTORY_DS_CODE, rows=14, code={"mode": "python", "theme": "darcula"}),
        ctx["actions"]("操作", [{"label": "保存", "value": "save"}, {"label": "取消", "value": "cancel", "color": "danger"}], name="action"),
    ])
    if not form or form.get("action") == "cancel":
        return {"success": False}
    recursive_values = form.get("recursive", [])
    recursive = "recursive" in recursive_values if isinstance(recursive_values, list) else False
    new_watch = form.get("watch_events", ["created", "modified", "deleted"])
    if isinstance(new_watch, str):
        new_watch = [new_watch]
    return entry.update_config(
        name=form["name"].strip(), description=form.get("description", "").strip(), source_type="directory",
        config={"directory_path": form.get("directory_path", "").strip(), "poll_interval": float(form.get("dir_poll_interval", 1.0) or 1.0),
                "file_pattern": form.get("file_pattern", "*") or "*", "recursive": recursive, "watch_events": new_watch},
        func_code=form.get("code") or DEFAULT_DIRECTORY_DS_CODE,
    )


async def _edit_generic_ds(ctx, entry, description, func_code, interval):
    """编辑通用类型数据源"""
    form = await ctx["input_group"](f"编辑数据源: {entry.name}", [
        ctx["input"]("名称", name="name", value=entry.name, required=True),
        ctx["textarea"]("描述", name="description", rows=2, value=description),
        ctx["input"]("间隔(秒)", name="interval", type="number", value=interval),
        ctx["textarea"]("代码", name="code", value=func_code, rows=14, code={"mode": "python", "theme": "darcula"}),
        ctx["actions"]("操作", [{"label": "保存", "value": "save"}, {"label": "取消", "value": "cancel", "color": "danger"}], name="action"),
    ])
    if not form or form.get("action") == "cancel":
        return {"success": False}
    return entry.update_config(
        name=form["name"].strip(), description=form.get("description", "").strip(),
        interval=float(form.get("interval", 5)), func_code=form.get("code"),
    )


# ---------------------------------------------------------------------------
# 创建数据源对话框
# ---------------------------------------------------------------------------

async def _create_ds_dialog_async(mgr, ctx: dict):
    """创建数据源对话框（异步）- 两步式流程"""
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

    config_form = await _create_ds_config_form(ctx, source_type)

    if not config_form or config_form.get("action") == "cancel":
        ctx["close_popup"]()
        return

    result = _create_ds_from_form(mgr, name, description, source_type, config_form)

    if result.get("success"):
        from .table import _render_ds_content
        _render_ds_content(ctx)
        ctx["toast"]("创建成功", color="success")
    else:
        ctx["toast"](f'创建失败: {result.get("error")}', color="error")

    ctx["close_popup"]()


async def _create_ds_config_form(ctx: dict, source_type: str) -> dict:
    """根据数据源类型显示配置表单"""
    if source_type == "timer":
        return await _create_timer_config_form(ctx)
    elif source_type == "file":
        return await _create_file_config_form(ctx)
    elif source_type == "replay":
        return await _create_replay_config_form(ctx)
    elif source_type == "directory":
        return await _create_directory_config_form(ctx)
    else:
        return await _create_generic_config_form(ctx, source_type)


async def _create_timer_config_form(ctx):
    """创建定时器类型配置表单"""
    timer_cfg = await _collect_timer_schedule_config(ctx, defaults={"execution_mode": "timer", "scheduler_trigger": "interval", "interval": 5})
    if not timer_cfg:
        return None
    mode = timer_cfg.get("execution_mode", "timer")
    trig = timer_cfg.get("scheduler_trigger", "interval")
    fields = []
    if mode == "timer":
        fields.append(ctx["input"]("间隔(秒)", name="interval", type="number", value=timer_cfg.get("interval", 5), help_text="每隔多少秒执行一次"))
    elif mode == "scheduler":
        if trig == "interval":
            fields.append(ctx["input"]("间隔(秒)", name="interval", type="number", value=timer_cfg.get("interval", 5)))
        elif trig == "date":
            fields.append(ctx["input"]("执行时间", name="run_at", value=timer_cfg.get("run_at", ""), placeholder="例如：2026-03-05 15:30:00"))
        else:
            fields.append(ctx["input"]("Cron 表达式", name="cron_expr", value=timer_cfg.get("cron_expr", "")))
    else:
        fields.extend([
            ctx["select"]("事件源", name="event_source", options=[{"label": "log", "value": "log"}, {"label": "bus", "value": "bus"}], value=timer_cfg.get("event_source", "log")),
            ctx["select"]("条件类型", name="event_condition_type", options=[{"label": "contains", "value": "contains"}, {"label": "python_expr", "value": "python_expr"}], value=timer_cfg.get("event_condition_type", "contains")),
            ctx["input"]("事件条件", name="event_condition", value=timer_cfg.get("event_condition", "")),
        ])
    fields.extend([
        ctx["textarea"]("代码", name="code", value=DEFAULT_DS_CODE, rows=14, code={"mode": "python", "theme": "darcula"}),
        ctx["actions"]("操作", [{"label": "创建", "value": "create"}, {"label": "返回", "value": "back"}, {"label": "取消", "value": "cancel"}], name="action"),
    ])
    form = await ctx["input_group"]("步骤2: 定时器配置", fields)
    if form:
        form["execution_mode"] = timer_cfg.get("execution_mode", "timer")
        form["scheduler_trigger"] = timer_cfg.get("scheduler_trigger", "interval")
        form["cron_expr"] = str(form.get("cron_expr", timer_cfg.get("cron_expr", "")) or timer_cfg.get("cron_expr", ""))
        form["run_at"] = str(form.get("run_at", timer_cfg.get("run_at", "")) or timer_cfg.get("run_at", ""))
        form["event_source"] = str(form.get("event_source", timer_cfg.get("event_source", "log")) or timer_cfg.get("event_source", "log"))
        form["event_condition"] = str(form.get("event_condition", timer_cfg.get("event_condition", "")) or timer_cfg.get("event_condition", ""))
        form["event_condition_type"] = str(form.get("event_condition_type", timer_cfg.get("event_condition_type", "contains")) or timer_cfg.get("event_condition_type", "contains"))
    return form


async def _create_file_config_form(ctx):
    """创建文件类型配置表单"""
    return await ctx["input_group"]("步骤2: 文件监控配置", [
        ctx["input"]("文件路径", name="file_path", placeholder="如 /var/log/app.log", required=True),
        ctx["input"]("轮询间隔(秒)", name="file_poll_interval", type="number", value=0.1),
        ctx["input"]("分隔符", name="file_delimiter", value="\\n", help_text="默认为换行符"),
        ctx["select"]("读取模式", name="file_read_mode", options=[
            {"label": "追踪模式 - 只读取新增内容", "value": "tail"},
            {"label": "全量模式 - 每次读取整个文件", "value": "full"},
        ], value="tail"),
        ctx["textarea"]("代码", name="code", value=DEFAULT_FILE_DS_CODE, rows=14, code={"mode": "python", "theme": "darcula"}),
        ctx["actions"]("操作", [{"label": "创建", "value": "create"}, {"label": "返回", "value": "back"}, {"label": "取消", "value": "cancel"}], name="action"),
    ])


async def _create_replay_config_form(ctx):
    """创建回放类型配置表单"""
    replay_tables = _get_replay_tables()
    opts = [{"label": t["name"], "value": t["name"]} for t in replay_tables] or [{"label": "无可用回放表", "value": ""}]
    return await ctx["input_group"]("步骤2: 数据回放配置", [
        ctx["select"]("回放表名", name="replay_table", options=opts, required=True),
        ctx["input"]("开始时间", name="replay_start_time", placeholder="YYYY-MM-DD HH:MM:SS，留空从最早开始"),
        ctx["input"]("结束时间", name="replay_end_time", placeholder="YYYY-MM-DD HH:MM:SS，留空到最新结束"),
        ctx["input"]("回放间隔(秒)", name="replay_interval", type="number", value=1.0),
        ctx["actions"]("操作", [{"label": "创建", "value": "create"}, {"label": "返回", "value": "back"}, {"label": "取消", "value": "cancel"}], name="action"),
    ])


async def _create_directory_config_form(ctx):
    """创建目录监控类型配置表单"""
    return await ctx["input_group"]("步骤2: 目录监控配置", [
        ctx["input"]("目录路径", name="directory_path", placeholder="如 /var/log 或 /tmp/data", required=True,
                     help_text="macOS: 监控敏感目录需授予终端「完全磁盘访问权限」"),
        ctx["input"]("轮询间隔(秒)", name="dir_poll_interval", type="number", value=1.0),
        ctx["input"]("文件匹配模式", name="file_pattern", value="*.*", placeholder="如 *.log 或 *.txt"),
        ctx["checkbox"]("递归扫描子目录", name="recursive", options=[{"label": "递归扫描子目录", "value": "recursive", "selected": False}]),
        ctx["checkbox"]("监控事件", name="watch_events", options=[
            {"label": "文件创建", "value": "created", "selected": True},
            {"label": "文件修改", "value": "modified", "selected": True},
            {"label": "文件删除", "value": "deleted", "selected": True},
        ], value=["created", "modified", "deleted"]),
        ctx["textarea"]("代码", name="code", value=DEFAULT_DIRECTORY_DS_CODE, rows=14, code={"mode": "python", "theme": "darcula"}),
        ctx["actions"]("操作", [{"label": "创建", "value": "create"}, {"label": "返回", "value": "back"}, {"label": "取消", "value": "cancel"}], name="action"),
    ])


async def _create_generic_config_form(ctx, source_type):
    """创建通用类型配置表单"""
    title = "步骤2: 自定义代码配置" if source_type == "custom" else "步骤2: 配置"
    return await ctx["input_group"](title, [
        ctx["input"]("间隔(秒)", name="interval", type="number", value=5),
        ctx["textarea"]("代码", name="code", value=DEFAULT_DS_CODE, rows=14, code={"mode": "python", "theme": "darcula"}),
        ctx["actions"]("操作", [{"label": "创建", "value": "create"}, {"label": "返回", "value": "back"}, {"label": "取消", "value": "cancel"}], name="action"),
    ])


def _create_ds_from_form(mgr, name: str, description: str, source_type: str, form: dict) -> dict:
    """从表单数据创建数据源"""
    config = {}
    func_code = ""
    interval = 5
    execution_mode = "timer"
    scheduler_trigger = "interval"
    cron_expr = ""
    run_at = ""
    event_source = "log"
    event_condition = ""
    event_condition_type = "contains"

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
        recursive = "recursive" in recursive_values if isinstance(recursive_values, list) else False
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
        if source_type == "timer":
            execution_mode = str(form.get("execution_mode", "timer") or "timer").strip().lower()
            scheduler_trigger = str(form.get("scheduler_trigger", "interval") or "interval").strip().lower()
            cron_expr = str(form.get("cron_expr", "") or "").strip()
            run_at = str(form.get("run_at", "") or "").strip()
            event_source = str(form.get("event_source", "log") or "log").strip().lower()
            event_condition = str(form.get("event_condition", "") or "")
            event_condition_type = str(form.get("event_condition_type", "contains") or "contains").strip().lower()
            if execution_mode == "event_trigger":
                interval = 0.1
            if execution_mode == "scheduler" and scheduler_trigger != "interval":
                interval = max(0.1, interval)
            if execution_mode == "scheduler" and scheduler_trigger == "cron" and not cron_expr:
                return {"success": False, "error": "Cron 表达式不能为空"}
            if execution_mode == "event_trigger" and event_condition_type == "python_expr" and not event_condition.strip():
                return {"success": False, "error": "python_expr 条件不能为空"}

    return mgr.create(
        name=name, func_code=func_code, interval=interval, description=description,
        source_type=source_type, config=config, execution_mode=execution_mode,
        scheduler_trigger=scheduler_trigger, cron_expr=cron_expr, run_at=run_at,
        event_source=event_source, event_condition=event_condition,
        event_condition_type=event_condition_type,
    )
