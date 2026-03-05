"""任务管理 UI"""

from datetime import datetime
from typing import Optional

from pywebio.session import run_async


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
    mode = (getattr(entry._metadata, "execution_mode", "") or "").strip().lower()
    task_type = (getattr(entry._metadata, "task_type", "") or "").strip().lower()

    if mode in {"timer", "scheduler", "event_trigger"}:
        return mode
    if task_type == "interval":
        return "timer"
    if task_type in {"once", "schedule", "cron"}:
        return "scheduler"
    if task_type in {"event", "eventtrigger", "event_trigger"}:
        return "event_trigger"
    return "timer"


def _mode_label(mode: str) -> str:
    labels = {
        "timer": "Timer",
        "scheduler": "Scheduler",
        "event_trigger": "EventTrigger",
    }
    return labels.get(mode, mode)


def _schedule_desc(entry) -> str:
    mode = _normalize_mode(entry)

    if mode == "timer":
        return f"每 {float(getattr(entry._metadata, 'interval_seconds', 60) or 60):.1f} 秒执行一次"

    if mode == "scheduler":
        trigger = (getattr(entry._metadata, "scheduler_trigger", "interval") or "interval").strip().lower()
        if trigger == "cron":
            expr = (getattr(entry._metadata, "cron_expr", "") or "").strip()
            return _humanize_cron(expr)
        if trigger == "date":
            run_at = (getattr(entry._metadata, "run_at", "") or "").strip()
            return f"一次性: {run_at or '-'}"
        return f"按固定间隔执行（{float(getattr(entry._metadata, 'interval_seconds', 60) or 60):.1f} 秒）"

    source = (getattr(entry._metadata, "event_source", "log") or "log").strip().lower()
    cond_type = (getattr(entry._metadata, "event_condition_type", "contains") or "contains").strip().lower()
    condition = (getattr(entry._metadata, "event_condition", "") or "").strip()
    return f"事件触发（来源: {source}，条件: {condition or '任意事件'}）"


def _humanize_cron(expr: str) -> str:
    cron = str(expr or "").strip()
    if not cron:
        return "按计划执行"

    parts = cron.split()
    if len(parts) != 5:
        return f"按计划执行（规则: {cron}）"

    minute, hour, day, month, weekday = parts
    if minute.startswith("*/") and hour == "*" and day == "*" and month == "*" and weekday == "*":
        n = minute[2:]
        if n.isdigit():
            return f"每 {n} 分钟执行一次"

    if hour == "*" and day == "*" and month == "*" and weekday == "*" and minute.isdigit():
        return f"每小时第 {int(minute):02d} 分执行"

    if minute.isdigit() and hour.isdigit() and day == "*" and month == "*" and weekday == "*":
        return f"每天 {int(hour):02d}:{int(minute):02d} 执行"

    weekday_map = {"mon": "周一", "tue": "周二", "wed": "周三", "thu": "周四", "fri": "周五", "sat": "周六", "sun": "周日"}
    if minute.isdigit() and hour.isdigit() and day == "*" and month == "*" and weekday.lower() in weekday_map:
        return f"每{weekday_map[weekday.lower()]} {int(hour):02d}:{int(minute):02d} 执行"

    if minute.isdigit() and hour.isdigit() and day.isdigit() and month == "*" and weekday == "*":
        return f"每月 {int(day)} 日 {int(hour):02d}:{int(minute):02d} 执行"

    return f"按计划执行（规则: {cron}）"


def _is_dictionary_refresh_task(entry) -> bool:
    name = str(getattr(entry, "name", "") or "").strip().lower()
    desc = str(getattr(entry._metadata, "description", "") or "").strip()
    return name.startswith("dict_refresh_") or ("字典" in desc and "鲜活任务" in desc)


def _split_entries_by_tab(entries: list):
    normal = []
    dict_tasks = []
    for e in entries:
        if _is_dictionary_refresh_task(e):
            dict_tasks.append(e)
        else:
            normal.append(e)
    return normal, dict_tasks


def _resolve_task_type(mode: str, scheduler_trigger: str) -> str:
    if mode == "timer":
        return "interval"
    if mode == "scheduler":
        return "once" if scheduler_trigger == "date" else "schedule"
    return "event_trigger"


def _parse_hhmm(value: str) -> Optional[tuple]:
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = raw.replace("：", ":")
    parts = raw.split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except Exception:
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour, minute


def _preview_next_runs(cron_expr: str, count: int = 5) -> list:
    try:
        from apscheduler.triggers.cron import CronTrigger
        import pytz
    except Exception:
        return []

    try:
        trigger = CronTrigger.from_crontab(str(cron_expr or "").strip(), timezone=pytz.timezone("Asia/Shanghai"))
        out = []
        now = datetime.now(pytz.timezone("Asia/Shanghai"))
        prev = None
        current = now
        for _ in range(max(1, count)):
            nxt = trigger.get_next_fire_time(prev, current)
            if not nxt:
                break
            out.append(nxt.strftime("%Y-%m-%d %H:%M:%S"))
            prev = nxt
            current = nxt
        return out
    except Exception:
        return []


async def _build_cron_expr_wizard(ctx: dict, default_expr: str = "") -> Optional[str]:
    template_default = "custom" if default_expr else "every_n_minutes"
    while True:
        template_form = await ctx["input_group"](
            "第 2.1 步：选择 Cron 模板",
            [
                ctx["select"](
                    "模板",
                    name="template",
                    options=[
                        {"label": "每 N 分钟", "value": "every_n_minutes"},
                        {"label": "每天固定时间", "value": "daily"},
                        {"label": "每周固定时间", "value": "weekly"},
                        {"label": "每月固定日期时间", "value": "monthly"},
                        {"label": "自定义 Cron（高级）", "value": "custom"},
                    ],
                    value=template_default,
                ),
                ctx["actions"](
                    "操作",
                    [
                        {"label": "下一步", "value": "next"},
                        {"label": "取消", "value": "cancel"},
                    ],
                    name="action",
                ),
            ],
        )
        if not template_form or template_form.get("action") == "cancel":
            return None

        template = str(template_form.get("template", template_default) or template_default).strip().lower()
        cron_expr = ""
        if template == "every_n_minutes":
            f = await ctx["input_group"](
                "第 2.2 步：每 N 分钟",
                [
                    ctx["input"]("间隔分钟数", name="n", type="number", value=5),
                    ctx["actions"]("操作", [{"label": "生成", "value": "ok"}, {"label": "返回模板", "value": "back"}, {"label": "取消", "value": "cancel"}], name="action"),
                ],
            )
            if not f or f.get("action") == "cancel":
                return None
            if f.get("action") == "back":
                continue
            try:
                n = int(f.get("n", 5))
                if n < 1 or n > 59:
                    raise ValueError("N 必须在 1-59")
                cron_expr = f"*/{n} * * * *"
            except Exception:
                ctx["toast"]("分钟数无效，应为 1-59", color="error")
                continue
        elif template == "daily":
            f = await ctx["input_group"](
                "第 2.2 步：每天固定时间",
                [
                    ctx["input"]("时间（HH:MM）", name="hhmm", value="09:30", placeholder="例如：09:30"),
                    ctx["actions"]("操作", [{"label": "生成", "value": "ok"}, {"label": "返回模板", "value": "back"}, {"label": "取消", "value": "cancel"}], name="action"),
                ],
            )
            if not f or f.get("action") == "cancel":
                return None
            if f.get("action") == "back":
                continue
            t = _parse_hhmm(f.get("hhmm", ""))
            if not t:
                ctx["toast"]("时间格式无效，应为 HH:MM", color="error")
                continue
            hour, minute = t
            cron_expr = f"{minute} {hour} * * *"
        elif template == "weekly":
            f = await ctx["input_group"](
                "第 2.2 步：每周固定时间",
                [
                    ctx["select"](
                        "星期几",
                        name="weekday",
                        options=[
                            {"label": "周一", "value": "mon"},
                            {"label": "周二", "value": "tue"},
                            {"label": "周三", "value": "wed"},
                            {"label": "周四", "value": "thu"},
                            {"label": "周五", "value": "fri"},
                            {"label": "周六", "value": "sat"},
                            {"label": "周日", "value": "sun"},
                        ],
                        value="mon",
                    ),
                    ctx["input"]("时间（HH:MM）", name="hhmm", value="09:30", placeholder="例如：09:30"),
                    ctx["actions"]("操作", [{"label": "生成", "value": "ok"}, {"label": "返回模板", "value": "back"}, {"label": "取消", "value": "cancel"}], name="action"),
                ],
            )
            if not f or f.get("action") == "cancel":
                return None
            if f.get("action") == "back":
                continue
            t = _parse_hhmm(f.get("hhmm", ""))
            if not t:
                ctx["toast"]("时间格式无效，应为 HH:MM", color="error")
                continue
            hour, minute = t
            cron_expr = f"{minute} {hour} * * {f.get('weekday', 'mon')}"
        elif template == "monthly":
            f = await ctx["input_group"](
                "第 2.2 步：每月固定日期时间",
                [
                    ctx["input"]("日期（1-31）", name="day", type="number", value=1),
                    ctx["input"]("时间（HH:MM）", name="hhmm", value="09:30", placeholder="例如：09:30"),
                    ctx["actions"]("操作", [{"label": "生成", "value": "ok"}, {"label": "返回模板", "value": "back"}, {"label": "取消", "value": "cancel"}], name="action"),
                ],
            )
            if not f or f.get("action") == "cancel":
                return None
            if f.get("action") == "back":
                continue
            try:
                day = int(f.get("day", 1))
                if day < 1 or day > 31:
                    raise ValueError("day")
            except Exception:
                ctx["toast"]("日期无效，应为 1-31", color="error")
                continue
            t = _parse_hhmm(f.get("hhmm", ""))
            if not t:
                ctx["toast"]("时间格式无效，应为 HH:MM", color="error")
                continue
            hour, minute = t
            cron_expr = f"{minute} {hour} {day} * *"
        else:
            f = await ctx["input_group"](
                "第 2.2 步：自定义 Cron",
                [
                    ctx["input"]("Cron 表达式", name="cron_expr", value=default_expr or "", placeholder="例如：*/5 * * * *"),
                    ctx["actions"]("操作", [{"label": "确认", "value": "ok"}, {"label": "返回模板", "value": "back"}, {"label": "取消", "value": "cancel"}], name="action"),
                ],
            )
            if not f or f.get("action") == "cancel":
                return None
            if f.get("action") == "back":
                continue
            cron_expr = str(f.get("cron_expr", "") or "").strip()
            if not cron_expr:
                ctx["toast"]("Cron 表达式不能为空", color="error")
                continue

        preview = _preview_next_runs(cron_expr, count=5)
        if preview:
            ctx["put_markdown"]("#### 未来 5 次执行预览")
            for i, ts in enumerate(preview, start=1):
                ctx["put_text"](f"{i}. {ts}")

        confirm = await ctx["input_group"](
            "第 2.3 步：确认 Cron",
            [
                ctx["input"]("生成的 Cron", name="cron_expr", value=cron_expr),
                ctx["actions"](
                    "操作",
                    [
                        {"label": "使用这个 Cron", "value": "use"},
                        {"label": "重新生成", "value": "regen"},
                        {"label": "取消", "value": "cancel"},
                    ],
                    name="action",
                ),
            ],
        )
        if not confirm or confirm.get("action") == "cancel":
            return None
        if confirm.get("action") == "regen":
            default_expr = str(confirm.get("cron_expr", cron_expr) or cron_expr).strip()
            template_default = "custom"
            continue

        final_expr = str(confirm.get("cron_expr", cron_expr) or cron_expr).strip()
        if not final_expr:
            ctx["toast"]("Cron 表达式不能为空", color="error")
            continue
        return final_expr


def _mode_intro_html(mode: str) -> str:
    if mode == "timer":
        return """
        <div style="margin:8px 0 14px 0;padding:12px;border-radius:8px;background:#eef7ff;color:#245b8f;">
            <div style="font-weight:600;margin-bottom:6px;">Timer（固定间隔执行）</div>
            <div style="font-size:13px;line-height:1.6;">
                适合心跳任务、轮询任务。<br/>
                例如：每 60 秒拉取一次状态、每 5 秒检查一次指标。
            </div>
        </div>
        """
    if mode == "scheduler":
        return """
        <div style="margin:8px 0 14px 0;padding:12px;border-radius:8px;background:#f1f8ef;color:#2f6b2f;">
            <div style="font-weight:600;margin-bottom:6px;">Scheduler（计划调度执行）</div>
            <div style="font-size:13px;line-height:1.6;">
                适合按日程执行。支持 interval / cron / date(一次性)。<br/>
                例如：每天 09:30 执行、每 5 分钟执行、在指定时间执行一次。
            </div>
        </div>
        """
    return """
    <div style="margin:8px 0 14px 0;padding:12px;border-radius:8px;background:#fff5ec;color:#7a4d1f;">
        <div style="font-weight:600;margin-bottom:6px;">EventTrigger（事件触发执行）</div>
        <div style="font-size:13px;line-height:1.6;">
            适合被动触发任务。监听 log 或 bus 流，在匹配条件时执行。<br/>
            例如：日志包含 error 时触发、bus 收到 open 事件时触发。
        </div>
    </div>
    """


async def _choose_create_mode(ctx: dict, default_mode: str = "timer", title: str = "第 1 步：选择任务运行分类") -> Optional[str]:
    mode_form = await ctx["input_group"](
        title,
        [
            ctx["select"](
                "任务运行分类",
                name="execution_mode",
                options=[
                    {"label": "Timer（固定间隔执行）", "value": "timer"},
                    {"label": "Scheduler（计划调度执行）", "value": "scheduler"},
                    {"label": "EventTrigger（事件触发执行）", "value": "event_trigger"},
                ],
                value=default_mode,
            ),
            ctx["actions"](
                "操作",
                [
                    {"label": "下一步", "value": "next"},
                    {"label": "取消", "value": "cancel"},
                ],
                name="action",
            ),
        ],
    )
    if not mode_form or mode_form.get("action") == "cancel":
        return None
    return str(mode_form.get("execution_mode", "timer") or "timer").strip().lower()


async def _choose_scheduler_trigger(ctx: dict) -> Optional[str]:
    trigger_form = await ctx["input_group"](
        "第 2 步：选择 Scheduler 触发方式",
        [
            ctx["select"](
                "触发方式",
                name="scheduler_trigger",
                options=[
                    {"label": "interval（按固定间隔）", "value": "interval"},
                    {"label": "cron（按 cron 表达式）", "value": "cron"},
                    {"label": "date（指定时间执行一次）", "value": "date"},
                ],
                value="interval",
            ),
            ctx["actions"](
                "操作",
                [
                    {"label": "下一步", "value": "next"},
                    {"label": "取消", "value": "cancel"},
                ],
                name="action",
            ),
        ],
    )
    if not trigger_form or trigger_form.get("action") == "cancel":
        return None
    return str(trigger_form.get("scheduler_trigger", "interval") or "interval").strip().lower()


async def _choose_scheduler_trigger_with_default(
    ctx: dict, default_trigger: str = "interval", title: str = "第 2 步：选择 Scheduler 触发方式"
) -> Optional[str]:
    trigger_form = await ctx["input_group"](
        title,
        [
            ctx["select"](
                "触发方式",
                name="scheduler_trigger",
                options=[
                    {"label": "interval（按固定间隔）", "value": "interval"},
                    {"label": "cron（按 cron 表达式）", "value": "cron"},
                    {"label": "date（指定时间执行一次）", "value": "date"},
                ],
                value=default_trigger,
            ),
            ctx["actions"](
                "操作",
                [
                    {"label": "下一步", "value": "next"},
                    {"label": "取消", "value": "cancel"},
                ],
                name="action",
            ),
        ],
    )
    if not trigger_form or trigger_form.get("action") == "cancel":
        return None
    return str(trigger_form.get("scheduler_trigger", default_trigger) or default_trigger).strip().lower()


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
    normal_entries, dict_entries = _split_entries_by_tab(entries)
    active_tab = str(ctx.get("_task_tab", "normal") or "normal").strip().lower()
    if active_tab not in {"normal", "dictionary"}:
        active_tab = "normal"
    visible_entries = normal_entries if active_tab == "normal" else dict_entries
    stats = _build_task_stats(visible_entries)

    clear("task_content")

    ctx["put_html"](_render_task_stats_html(stats), scope="task_content")

    ctx["put_html"]('<div style="margin-bottom:12px;display:flex;gap:10px;flex-wrap:wrap;">', scope="task_content")
    ctx["put_buttons"](
        [
            {"label": f"任务列表 ({len(normal_entries)})", "value": "tab_normal"},
            {"label": f"数据字典任务 ({len(dict_entries)})", "value": "tab_dictionary"},
        ],
        onclick=lambda v, c=ctx: _handle_task_tab_switch(v, c),
        scope="task_content",
    )
    ctx["put_html"]("</div>", scope="task_content")

    if visible_entries:
        table_data = _build_table_data(ctx, visible_entries, mgr)
        ctx["put_table"](
            table_data,
            header=["名称", "执行方式", "状态", "触发配置", "成功", "失败", "最后运行", "操作"],
            scope="task_content",
        )
    else:
        ctx["put_html"](
            '<div style="padding:40px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">当前标签下暂无任务</div>',
            scope="task_content",
        )

    ctx["put_html"]('<div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;">', scope="task_content")
    if active_tab == "normal":
        ctx["put_buttons"](
            [{"label": "➕ 创建任务", "value": "create"}], onclick=lambda v, m=mgr, c=ctx: _create_task_dialog(m, c), scope="task_content"
        )
    ctx["put_html"]("</div>", scope="task_content")


def _handle_task_tab_switch(action: str, ctx: dict):
    if action == "tab_dictionary":
        ctx["_task_tab"] = "dictionary"
    else:
        ctx["_task_tab"] = "normal"
    _render_task_content(ctx)


def _build_task_stats(entries: list) -> dict:
    total = len(entries)
    total_success = sum(getattr(e._state, "success_count", 0) for e in entries)
    total_failure = sum(getattr(e._state, "failure_count", 0) for e in entries)
    return {"total": total, "total_success": total_success, "total_failure": total_failure}


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

        mode = _normalize_mode(e)
        type_html = f'<span style="background:#e3f2fd;color:#1565c0;padding:2px 8px;border-radius:4px;font-size:12px;">{_mode_label(mode)}</span>'

        last_run_ts = getattr(e._state, "last_run_time", 0)
        last_run = _fmt_ts(last_run_ts) if last_run_ts else "-"

        action_btns = ctx["put_buttons"](
            [
                {"label": "详情", "value": f"detail_{e.id}"},
                {"label": "编辑", "value": f"edit_{e.id}"},
                {"label": "停止" if e.is_running else "启动", "value": f"toggle_{e.id}"},
                {"label": "执行一次", "value": f"run_{e.id}"},
                {"label": "删除", "value": f"delete_{e.id}"},
            ],
            onclick=lambda v, m=mgr, c=ctx: _handle_task_action(v, m, c),
        )

        table_data.append(
            [
                ctx["put_html"](
                    f'<div title="{e.name}" style="max-width:260px;white-space:normal;word-break:break-word;line-height:1.4;"><strong>{e.name}</strong></div>'
                ),
                ctx["put_html"](type_html),
                ctx["put_html"](status_html),
                _schedule_desc(e),
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
