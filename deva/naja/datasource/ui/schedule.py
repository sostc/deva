"""调度配置向导（Timer/Scheduler/Cron 模式选择）"""

from typing import Optional

from .constants import _parse_hhmm, _preview_next_runs


async def _choose_timer_mode(ctx: dict, default_mode: str = "timer", title: str = "步骤2.1: 选择调度方式") -> Optional[str]:
    from deva.naja.config import get_enabled_timer_execution_modes

    enabled_modes = list(get_enabled_timer_execution_modes() or [])
    all_options = [
        {"label": "Timer（固定间隔执行）", "value": "timer"},
        {"label": "Scheduler（计划调度执行）", "value": "scheduler"},
        {"label": "EventTrigger（事件触发执行）", "value": "event_trigger"},
    ]
    mode_options = [o for o in all_options if o["value"] in enabled_modes]
    if not mode_options:
        mode_options = [all_options[0]]
    mode_values = {o["value"] for o in mode_options}
    if default_mode not in mode_values:
        default_mode = mode_options[0]["value"]

    form = await ctx["input_group"](
        title,
        [
            ctx["select"](
                "调度方式",
                name="execution_mode",
                options=mode_options,
                value=default_mode,
            ),
            ctx["actions"]("操作", [{"label": "下一步", "value": "next"}, {"label": "取消", "value": "cancel"}], name="action"),
        ],
    )
    if not form or form.get("action") == "cancel":
        return None
    return str(form.get("execution_mode", default_mode) or default_mode).strip().lower()


async def _choose_scheduler_trigger(ctx: dict, default_trigger: str = "interval", title: str = "步骤2.2: 选择 Scheduler 触发方式") -> Optional[str]:
    form = await ctx["input_group"](
        title,
        [
            ctx["select"](
                "触发方式",
                name="scheduler_trigger",
                options=[
                    {"label": "interval（固定间隔）", "value": "interval"},
                    {"label": "cron（计划表达式）", "value": "cron"},
                    {"label": "date（指定时间一次性）", "value": "date"},
                ],
                value=default_trigger,
            ),
            ctx["actions"]("操作", [{"label": "下一步", "value": "next"}, {"label": "取消", "value": "cancel"}], name="action"),
        ],
    )
    if not form or form.get("action") == "cancel":
        return None
    return str(form.get("scheduler_trigger", default_trigger) or default_trigger).strip().lower()


async def _build_cron_expr_wizard(ctx: dict, default_expr: str = "") -> Optional[str]:
    template_default = "custom" if default_expr else "every_n_minutes"
    while True:
        form = await ctx["input_group"](
            "步骤2.3: Cron 快速生成",
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
                ctx["actions"]("操作", [{"label": "下一步", "value": "next"}, {"label": "取消", "value": "cancel"}], name="action"),
            ],
        )
        if not form or form.get("action") == "cancel":
            return None

        template = str(form.get("template", template_default) or template_default).strip().lower()
        cron_expr = ""
        if template == "every_n_minutes":
            f = await ctx["input_group"]("Cron 模板：每 N 分钟", [
                ctx["input"]("N（1-59）", name="n", type="number", value=5),
                ctx["actions"]("操作", [{"label": "生成", "value": "ok"}, {"label": "返回", "value": "back"}], name="action"),
            ])
            if not f or f.get("action") == "back":
                continue
            try:
                n = int(f.get("n", 5))
                if n < 1 or n > 59:
                    raise ValueError("n")
                cron_expr = f"*/{n} * * * *"
            except Exception:
                ctx["toast"]("N 必须在 1-59", color="error")
                continue
        elif template == "daily":
            f = await ctx["input_group"]("Cron 模板：每天固定时间", [
                ctx["input"]("时间(HH:MM)", name="hhmm", value="09:30"),
                ctx["actions"]("操作", [{"label": "生成", "value": "ok"}, {"label": "返回", "value": "back"}], name="action"),
            ])
            if not f or f.get("action") == "back":
                continue
            t = _parse_hhmm(f.get("hhmm", ""))
            if not t:
                ctx["toast"]("时间格式应为 HH:MM", color="error")
                continue
            hour, minute = t
            cron_expr = f"{minute} {hour} * * *"
        elif template == "weekly":
            f = await ctx["input_group"]("Cron 模板：每周固定时间", [
                ctx["select"]("星期", name="weekday", options=[
                    {"label": "周一", "value": "mon"},
                    {"label": "周二", "value": "tue"},
                    {"label": "周三", "value": "wed"},
                    {"label": "周四", "value": "thu"},
                    {"label": "周五", "value": "fri"},
                    {"label": "周六", "value": "sat"},
                    {"label": "周日", "value": "sun"},
                ], value="mon"),
                ctx["input"]("时间(HH:MM)", name="hhmm", value="09:30"),
                ctx["actions"]("操作", [{"label": "生成", "value": "ok"}, {"label": "返回", "value": "back"}], name="action"),
            ])
            if not f or f.get("action") == "back":
                continue
            t = _parse_hhmm(f.get("hhmm", ""))
            if not t:
                ctx["toast"]("时间格式应为 HH:MM", color="error")
                continue
            hour, minute = t
            cron_expr = f"{minute} {hour} * * {f.get('weekday', 'mon')}"
        elif template == "monthly":
            f = await ctx["input_group"]("Cron 模板：每月固定日期时间", [
                ctx["input"]("日期(1-31)", name="day", type="number", value=1),
                ctx["input"]("时间(HH:MM)", name="hhmm", value="09:30"),
                ctx["actions"]("操作", [{"label": "生成", "value": "ok"}, {"label": "返回", "value": "back"}], name="action"),
            ])
            if not f or f.get("action") == "back":
                continue
            try:
                day = int(f.get("day", 1))
                if day < 1 or day > 31:
                    raise ValueError("day")
            except Exception:
                ctx["toast"]("日期必须在 1-31", color="error")
                continue
            t = _parse_hhmm(f.get("hhmm", ""))
            if not t:
                ctx["toast"]("时间格式应为 HH:MM", color="error")
                continue
            hour, minute = t
            cron_expr = f"{minute} {hour} {day} * *"
        else:
            f = await ctx["input_group"]("Cron 模板：自定义", [
                ctx["input"]("Cron 表达式", name="cron_expr", value=default_expr, placeholder="例如：*/5 * * * *"),
                ctx["actions"]("操作", [{"label": "确认", "value": "ok"}, {"label": "返回", "value": "back"}], name="action"),
            ])
            if not f or f.get("action") == "back":
                continue
            cron_expr = str(f.get("cron_expr", "") or "").strip()
            if not cron_expr:
                ctx["toast"]("Cron 表达式不能为空", color="error")
                continue

        preview = _preview_next_runs(cron_expr, count=5)
        if preview:
            ctx["put_markdown"]("#### 未来 5 次执行预览")
            for i, item in enumerate(preview, start=1):
                ctx["put_text"](f"{i}. {item}")
        return cron_expr


async def _collect_timer_schedule_config(ctx: dict, *, defaults: dict = None) -> Optional[dict]:
    defaults = defaults or {}
    mode = await _choose_timer_mode(ctx, default_mode=str(defaults.get("execution_mode", "timer") or "timer"))
    if not mode:
        return None

    config = {
        "execution_mode": mode,
        "scheduler_trigger": "interval",
        "interval": float(defaults.get("interval", 5) or 5),
        "cron_expr": str(defaults.get("cron_expr", "") or ""),
        "run_at": str(defaults.get("run_at", "") or ""),
        "event_source": str(defaults.get("event_source", "log") or "log"),
        "event_condition": str(defaults.get("event_condition", "") or ""),
        "event_condition_type": str(defaults.get("event_condition_type", "contains") or "contains"),
    }

    if mode == "scheduler":
        trig = await _choose_scheduler_trigger(ctx, default_trigger=str(defaults.get("scheduler_trigger", "interval") or "interval"))
        if not trig:
            return None
        config["scheduler_trigger"] = trig
        if trig == "cron":
            cron_expr = await _build_cron_expr_wizard(ctx, default_expr=config["cron_expr"])
            if not cron_expr:
                return None
            config["cron_expr"] = cron_expr
    return config
