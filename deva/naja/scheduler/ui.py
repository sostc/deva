"""调度 UI 共享模块 - 统一的调度相关 UI 组件

提供数据源、任务、字典等模块共享的调度配置 UI 组件。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from pywebio.session import run_async

from .common import (
    humanize_cron,
    parse_hhmm,
    preview_next_runs,
)


async def build_cron_expr_wizard(
    ctx: dict,
    default_expr: str = "",
    step_title: str = "Cron 表达式生成"
) -> Optional[str]:
    """构建 Cron 表达式生成向导
    
    Args:
        ctx: UI 上下文
        default_expr: 默认的 cron 表达式
        step_title: 步骤标题前缀
        
    Returns:
        生成的 cron 表达式，如果用户取消则返回 None
    """
    template_default = "custom" if default_expr else "every_n_minutes"
    
    while True:
        template_form = await ctx["input_group"](
            f"{step_title} - 选择模板",
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
                f"{step_title} - 每 N 分钟",
                [
                    ctx["input"]("间隔分钟数", name="n", type="number", value=5),
                    ctx["actions"](
                        "操作",
                        [
                            {"label": "生成", "value": "ok"},
                            {"label": "返回模板", "value": "back"},
                            {"label": "取消", "value": "cancel"},
                        ],
                        name="action",
                    ),
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
                f"{step_title} - 每天固定时间",
                [
                    ctx["input"]("时间（HH:MM）", name="hhmm", value="09:30", placeholder="例如：09:30"),
                    ctx["actions"](
                        "操作",
                        [
                            {"label": "生成", "value": "ok"},
                            {"label": "返回模板", "value": "back"},
                            {"label": "取消", "value": "cancel"},
                        ],
                        name="action",
                    ),
                ],
            )
            if not f or f.get("action") == "cancel":
                return None
            if f.get("action") == "back":
                continue
            t = parse_hhmm(f.get("hhmm", ""))
            if not t:
                ctx["toast"]("时间格式无效，应为 HH:MM", color="error")
                continue
            hour, minute = t
            cron_expr = f"{minute} {hour} * * *"
            
        elif template == "weekly":
            f = await ctx["input_group"](
                f"{step_title} - 每周固定时间",
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
                    ctx["actions"](
                        "操作",
                        [
                            {"label": "生成", "value": "ok"},
                            {"label": "返回模板", "value": "back"},
                            {"label": "取消", "value": "cancel"},
                        ],
                        name="action",
                    ),
                ],
            )
            if not f or f.get("action") == "cancel":
                return None
            if f.get("action") == "back":
                continue
            t = parse_hhmm(f.get("hhmm", ""))
            if not t:
                ctx["toast"]("时间格式无效，应为 HH:MM", color="error")
                continue
            hour, minute = t
            cron_expr = f"{minute} {hour} * * {f.get('weekday', 'mon')}"
            
        elif template == "monthly":
            f = await ctx["input_group"](
                f"{step_title} - 每月固定日期时间",
                [
                    ctx["input"]("日期（1-31）", name="day", type="number", value=1),
                    ctx["input"]("时间（HH:MM）", name="hhmm", value="09:30", placeholder="例如：09:30"),
                    ctx["actions"](
                        "操作",
                        [
                            {"label": "生成", "value": "ok"},
                            {"label": "返回模板", "value": "back"},
                            {"label": "取消", "value": "cancel"},
                        ],
                        name="action",
                    ),
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
            t = parse_hhmm(f.get("hhmm", ""))
            if not t:
                ctx["toast"]("时间格式无效，应为 HH:MM", color="error")
                continue
            hour, minute = t
            cron_expr = f"{minute} {hour} {day} * *"
            
        else:  # custom
            f = await ctx["input_group"](
                f"{step_title} - 自定义 Cron",
                [
                    ctx["input"](
                        "Cron 表达式",
                        name="cron_expr",
                        value=default_expr or "",
                        placeholder="例如：*/5 * * * *"
                    ),
                    ctx["actions"](
                        "操作",
                        [
                            {"label": "确认", "value": "ok"},
                            {"label": "返回模板", "value": "back"},
                            {"label": "取消", "value": "cancel"},
                        ],
                        name="action",
                    ),
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
        
        # 预览未来执行时间
        preview = preview_next_runs(cron_expr, count=5)
        if preview:
            ctx["put_markdown"]("#### 未来 5 次执行预览")
            for i, ts in enumerate(preview, start=1):
                ctx["put_text"](f"{i}. {ts}")
        
        # 确认
        confirm = await ctx["input_group"](
            f"{step_title} - 确认",
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


async def choose_execution_mode(
    ctx: dict,
    default_mode: str = "timer",
    title: str = "选择执行模式"
) -> Optional[str]:
    """选择执行模式
    
    Args:
        ctx: UI 上下文
        default_mode: 默认模式
        title: 对话框标题
        
    Returns:
        选择的执行模式 (timer/scheduler/event_trigger)，如果用户取消则返回 None
    """
    mode_form = await ctx["input_group"](
        title,
        [
            ctx["select"](
                "执行模式",
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
    return str(mode_form.get("execution_mode", default_mode) or default_mode).strip().lower()


async def choose_scheduler_trigger(
    ctx: dict,
    default_trigger: str = "interval",
    title: str = "选择 Scheduler 触发方式"
) -> Optional[str]:
    """选择 Scheduler 触发方式
    
    Args:
        ctx: UI 上下文
        default_trigger: 默认触发方式
        title: 对话框标题
        
    Returns:
        选择的触发方式 (interval/cron/date)，如果用户取消则返回 None
    """
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


def get_mode_intro_html(mode: str) -> str:
    """获取执行模式的介绍 HTML
    
    Args:
        mode: 执行模式
        
    Returns:
        HTML 字符串
    """
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


def get_mode_label(mode: str) -> str:
    """获取执行模式的显示标签
    
    Args:
        mode: 执行模式
        
    Returns:
        显示标签
    """
    labels = {
        "timer": "Timer",
        "scheduler": "Scheduler",
        "event_trigger": "EventTrigger",
    }
    return labels.get(mode, mode)


def get_schedule_desc(
    execution_mode: str,
    scheduler_trigger: str = "interval",
    interval_seconds: float = 60.0,
    cron_expr: str = "",
    run_at: str = "",
    event_source: str = "log",
    event_condition: str = "",
    event_condition_type: str = "contains"
) -> str:
    """获取调度描述的文本
    
    Args:
        execution_mode: 执行模式
        scheduler_trigger: 调度触发方式
        interval_seconds: 间隔秒数
        cron_expr: cron 表达式
        run_at: 执行时间
        event_source: 事件源
        event_condition: 事件条件
        event_condition_type: 事件条件类型
        
    Returns:
        调度描述文本
    """
    if execution_mode == "timer":
        return f"每 {float(interval_seconds or 60):.1f} 秒执行一次"
    
    if execution_mode == "scheduler":
        trigger = str(scheduler_trigger or "interval").strip().lower()
        if trigger == "cron":
            expr = str(cron_expr or "").strip()
            return humanize_cron(expr)
        if trigger == "date":
            return f"一次性: {run_at or '-'}"
        return f"按固定间隔执行（{float(interval_seconds or 60):.1f} 秒）"
    
    source = str(event_source or "log").strip().lower()
    cond = str(event_condition or "").strip()
    return f"事件触发（来源: {source}，条件: {cond or '任意事件'}）"


async def collect_scheduler_config(
    ctx: dict,
    default_config: Optional[Dict[str, Any]] = None,
    step_prefix: str = ""
) -> Optional[Dict[str, Any]]:
    """收集调度配置的完整向导
    
    Args:
        ctx: UI 上下文
        default_config: 默认配置
        step_prefix: 步骤标题前缀
        
    Returns:
        调度配置字典，如果用户取消则返回 None
    """
    default_config = default_config or {}
    
    # 步骤1: 选择执行模式
    mode = await choose_execution_mode(
        ctx,
        default_mode=default_config.get("execution_mode", "timer"),
        title=f"{step_prefix}步骤1: 选择执行模式" if step_prefix else "选择执行模式"
    )
    if not mode:
        return None
    
    ctx["put_html"](get_mode_intro_html(mode))
    
    config = {
        "execution_mode": mode,
        "scheduler_trigger": "interval",
        "interval_seconds": float(default_config.get("interval_seconds", 60.0)),
        "cron_expr": default_config.get("cron_expr", ""),
        "run_at": default_config.get("run_at", ""),
        "event_source": default_config.get("event_source", "log"),
        "event_condition": default_config.get("event_condition", ""),
        "event_condition_type": default_config.get("event_condition_type", "contains"),
    }
    
    # 根据模式收集具体配置
    if mode == "scheduler":
        trigger = await choose_scheduler_trigger(
            ctx,
            default_trigger=default_config.get("scheduler_trigger", "interval"),
            title=f"{step_prefix}步骤2: 选择触发方式" if step_prefix else "选择触发方式"
        )
        if not trigger:
            return None
        
        config["scheduler_trigger"] = trigger
        
        if trigger == "cron":
            cron_expr = await build_cron_expr_wizard(
                ctx,
                default_expr=config["cron_expr"],
                step_title=f"{step_prefix}步骤3" if step_prefix else "Cron 表达式"
            )
            if not cron_expr:
                return None
            config["cron_expr"] = cron_expr
        elif trigger == "date":
            date_form = await ctx["input_group"](
                f"{step_prefix}步骤3: 设置执行时间" if step_prefix else "设置执行时间",
                [
                    ctx["input"](
                        "执行时间",
                        name="run_at",
                        value=config["run_at"],
                        placeholder="例如：2026-03-05 15:30:00"
                    ),
                    ctx["actions"](
                        "操作",
                        [
                            {"label": "确认", "value": "ok"},
                            {"label": "取消", "value": "cancel"},
                        ],
                        name="action",
                    ),
                ],
            )
            if not date_form or date_form.get("action") == "cancel":
                return None
            config["run_at"] = str(date_form.get("run_at", "") or "").strip()
        else:  # interval
            interval_form = await ctx["input_group"](
                f"{step_prefix}步骤3: 设置间隔" if step_prefix else "设置间隔",
                [
                    ctx["input"](
                        "执行间隔（秒）",
                        name="interval",
                        type="number",
                        value=config["interval_seconds"]
                    ),
                    ctx["actions"](
                        "操作",
                        [
                            {"label": "确认", "value": "ok"},
                            {"label": "取消", "value": "cancel"},
                        ],
                        name="action",
                    ),
                ],
            )
            if not interval_form or interval_form.get("action") == "cancel":
                return None
            try:
                config["interval_seconds"] = max(0.1, float(interval_form.get("interval", 60)))
            except Exception:
                ctx["toast"]("间隔必须是数字", color="error")
                return None
    
    elif mode == "timer":
        interval_form = await ctx["input_group"](
            f"{step_prefix}步骤2: 设置间隔" if step_prefix else "设置间隔",
            [
                ctx["input"](
                    "执行间隔（秒）",
                    name="interval",
                    type="number",
                    value=config["interval_seconds"]
                ),
                ctx["actions"](
                    "操作",
                    [
                        {"label": "确认", "value": "ok"},
                        {"label": "取消", "value": "cancel"},
                    ],
                    name="action",
                ),
            ],
        )
        if not interval_form or interval_form.get("action") == "cancel":
            return None
        try:
            config["interval_seconds"] = max(0.1, float(interval_form.get("interval", 60)))
        except Exception:
            ctx["toast"]("间隔必须是数字", color="error")
            return None
    
    else:  # event_trigger
        event_form = await ctx["input_group"](
            f"{step_prefix}步骤2: 设置事件触发" if step_prefix else "设置事件触发",
            [
                ctx["select"](
                    "事件源",
                    name="event_source",
                    options=[
                        {"label": "log（日志流）", "value": "log"},
                        {"label": "bus（事件总线）", "value": "bus"},
                    ],
                    value=config["event_source"],
                ),
                ctx["select"](
                    "条件类型",
                    name="event_condition_type",
                    options=[
                        {"label": "contains（字符串包含）", "value": "contains"},
                        {"label": "python_expr（表达式，变量 x）", "value": "python_expr"},
                    ],
                    value=config["event_condition_type"],
                ),
                ctx["input"](
                    "触发条件",
                    name="event_condition",
                    value=config["event_condition"],
                    placeholder="例如：error 或 x.get('type') == 'signal'"
                ),
                ctx["actions"](
                    "操作",
                    [
                        {"label": "确认", "value": "ok"},
                        {"label": "取消", "value": "cancel"},
                    ],
                    name="action",
                ),
            ],
        )
        if not event_form or event_form.get("action") == "cancel":
            return None
        
        config["event_source"] = str(event_form.get("event_source", "log") or "log").strip().lower()
        config["event_condition_type"] = str(event_form.get("event_condition_type", "contains") or "contains").strip().lower()
        config["event_condition"] = str(event_form.get("event_condition", "") or "")
        
        if config["event_condition_type"] == "python_expr" and not config["event_condition"].strip():
            ctx["toast"]("python_expr 条件不能为空", color="error")
            return None
    
    return config
