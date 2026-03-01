"""任务管理UI."""

from __future__ import annotations

from .enhanced_task_panel import (
    show_enhanced_create_task_dialog,
    show_enhanced_edit_task_dialog,
)
from .task_manager import get_task_manager
from .task_unit import TaskType


async def render_enhanced_task_admin(ctx):
    """渲染任务管理界面。"""
    ctx["put_markdown"]("## ⏰ 任务管理")
    ctx["put_markdown"]("> 支持任务创建、编辑、启动/停止、详情查看和批量操作。")
    ctx["use_scope"]("task_list_scope", clear=True)
    await render_task_list(ctx)
    ctx["put_row"]([
        ctx["put_button"](
            "➕ 创建任务",
            onclick=lambda: ctx["run_async"](show_enhanced_create_task_dialog(ctx)),
            color="primary",
            outline=True,
        ),
        ctx["put_button"](
            "📋 批量管理",
            onclick=lambda: ctx["run_async"](show_batch_management(ctx)),
            color="info",
            outline=True,
        ),
        ctx["put_button"](
            "🔄 刷新列表",
            onclick=lambda: ctx["run_async"](refresh_task_list(ctx)),
            color="secondary",
            outline=True,
        ),
    ])
    await render_task_statistics(ctx)


async def render_task_statistics(ctx):
    """渲染任务统计信息。"""
    task_manager = get_task_manager()
    stats = task_manager.get_overall_stats()
    basic = stats["basic_stats"]
    execution_stats = stats.get("execution_stats", {})
    success_rate = execution_stats.get("success_rate", 0) * 100
    ctx["put_markdown"](f"""
### 📊 任务统计

| 指标 | 数值 |
|------|------|
| 总任务数 | {basic["total"]} |
| 运行中 | {basic["running_count"]} |
| 已停止 | {basic["stopped_count"]} |
| 错误状态 | {basic["error_count"]} |
| 总执行次数 | {execution_stats.get("total_executions", 0)} |
| 成功率 | {success_rate:.1f}% |
""")


async def render_task_list(ctx):
    """渲染任务列表。"""
    task_manager = get_task_manager()
    tasks = task_manager.list_all()
    if not tasks:
        ctx["put_markdown"]("> 📝 暂无任务，点击上方“创建任务”开始。")
        return

    table_data = []
    for task in tasks:
        task_stats = task_manager.get_task_stats(task.id) or {}
        exec_stats = task_stats.get("execution_stats", {})
        success_rate = exec_stats.get("success_rate", 0) * 100
        action_options = [
            {"label": "⏸️ 停止" if task.is_running else "▶️ 启动", "value": f"toggle_{task.id}"},
            {"label": "📄 源码", "value": f"code_{task.id}"},
            {"label": "✏️ 编辑(含代码)", "value": f"edit_{task.id}"},
            {"label": "📊 详情", "value": f"details_{task.id}"},
            {"label": "🗑️ 删除", "value": f"delete_{task.id}"},
        ]
        actions = ctx["put_buttons"](
            action_options,
            onclick=lambda v, _ctx=ctx: _ctx["run_async"](handle_task_action(_ctx, v)),
        )
        table_data.append([
            f"{_get_task_type_icon(task.metadata.task_type)} {task.name}",
            _get_status_text(task.state.status),
            task.metadata.task_type.value,
            task.get_schedule_description(),
            str(task.state.run_count),
            f"{success_rate:.1f}%",
            actions,
        ])

    with ctx["use_scope"]("task_list_scope", clear=True):
        ctx["put_markdown"]("### 📋 任务列表")
        ctx["put_table"](
            table_data,
            header=["任务名称", "状态", "类型", "调度配置", "执行次数", "成功率", "操作"],
        )


def _get_status_text(status):
    status_texts = {
        "running": "🟢 运行中",
        "stopped": "⚫ 已停止",
        "error": "🔴 错误",
        "paused": "🟡 暂停",
        "completed": "🔵 已完成",
    }
    return status_texts.get(status, f"❓ {status}")


def _get_task_type_icon(task_type):
    icons = {
        TaskType.INTERVAL: "⏱️",
        TaskType.CRON: "⏰",
        TaskType.ONE_TIME: "🔔",
    }
    return icons.get(task_type, "📋")


async def handle_task_action(ctx, action):
    """处理任务操作。"""
    action_type, task_id = action.split("_", 1)
    task_manager = get_task_manager()
    task = task_manager.get(task_id)
    if not task:
        ctx["toast"]("任务不存在", color="error")
        return

    if action_type == "toggle":
        result = task_manager.stop(task_id) if task.is_running else task_manager.start(task_id)
        if result.get("success"):
            ctx["toast"]("操作成功", color="success")
        else:
            ctx["toast"](f"操作失败: {result.get('error', '')}", color="error")
    elif action_type == "code":
        await show_task_code(ctx, task)
    elif action_type == "edit":
        await show_enhanced_edit_task_dialog(ctx, task.name)
    elif action_type == "details":
        await show_task_details(ctx, task)
    elif action_type == "delete":
        confirm = await ctx["actions"](
            f"确认删除任务 '{task.name}'?",
            [{"label": "确认", "value": "confirm"}, {"label": "取消", "value": "cancel"}],
        )
        if confirm == "confirm":
            result = task_manager.unregister(task_id)
            if result.get("success"):
                ctx["toast"]("任务已删除", color="success")
            else:
                ctx["toast"](f"删除失败: {result.get('error', '')}", color="error")

    await refresh_task_list(ctx)


async def show_task_details(ctx, task):
    """显示任务详情"""
    
    put_markdown = ctx["put_markdown"]
    put_collapse = ctx["put_collapse"]
    put_code = ctx["put_code"]
    put_text = ctx["put_text"]
    
    task_manager = get_task_manager()
    task_stats = task_manager.get_task_stats(task.id)
    
    with ctx["popup"](f"任务详情: {task.name}", size="large"):
        put_markdown(f"### 📊 {task.name} 详细信息")
        
        # 基本信息
        put_text("")
        put_markdown(f"""
**基本信息**

- **任务ID:** `{task.id}`
- **任务类型:** `{task.metadata.task_type.value}`
- **调度配置:** `{task.get_schedule_description()}`
- **当前状态:** `{task.state.status}`
- **执行次数:** `{task.state.run_count}`
- **错误次数:** `{task.state.error_count}`
""")
        put_text("")
        
        # 执行统计
        if task_stats and task_stats.get("execution_stats"):
            exec_stats = task_stats["execution_stats"]
            put_text("")
            put_markdown(f"""
**执行统计**

- **总执行次数:** `{exec_stats.get('total_executions', 0)}`
- **成功次数:** `{exec_stats.get('successful_executions', 0)}`
- **失败次数:** `{exec_stats.get('failed_executions', 0)}`
- **成功率:** `{exec_stats.get('success_rate', 0) * 100:.1f}%`
- **平均耗时:** `{exec_stats.get('avg_duration', 0):.2f}秒`
- **总耗时:** `{exec_stats.get('total_duration', 0):.2f}秒`
""")
            put_text("")
        
        # 代码预览
        code = (task.metadata.func_code or "").strip() or (task.execution.job_code or "").strip()
        if code:
            with put_collapse("📋 任务代码预览", open=False):
                put_code(code, language="python")
        else:
            put_markdown("**任务代码:** `暂无`")
        
        # 执行历史
        if task.execution.execution_history:
            with put_collapse("📈 最近执行历史", open=False):
                recent_history = task.execution.get_recent_history(5)
                for i, entry in enumerate(recent_history, 1):
                    status_emoji = "✅" if entry["status"] == "success" else "❌"
                    put_text("")
                    put_markdown(f"""
**执行 #{i}** {status_emoji}

- **时间:** `{entry["start_time"]}`
- **耗时:** `{entry["duration"]}秒`
- **状态:** `{entry["status"]}`
""")
                    if entry.get("output"):
                        put_markdown(f"- **输出:** `{entry["output"]}`")
                    if entry.get("error"):
                        put_markdown(f"- **错误:** `{entry["error"]}`")
                    put_text("")


async def show_task_code(ctx, task):
    """显示任务源码。"""
    code = (task.metadata.func_code or "").strip() or (task.execution.job_code or "").strip()
    with ctx["popup"](f"任务源码: {task.name}", size="large", closable=True):
        if code:
            ctx["put_code"](code, language="python")
        else:
            ctx["put_text"]("暂无任务代码")


async def show_batch_management(ctx):
    """显示批量管理界面。"""
    with ctx["popup"]("批量任务管理", size="large"):
        ctx["put_markdown"]("### ⚙️ 批量任务管理")
        ctx["put_row"]([
            ctx["put_button"]("▶️ 启动所有任务", onclick=lambda: ctx["run_async"](batch_start_all(ctx)), color="success"),
            ctx["put_button"]("⏸️ 停止所有任务", onclick=lambda: ctx["run_async"](batch_stop_all(ctx)), color="warning"),
            ctx["put_button"]("🔄 重启所有任务", onclick=lambda: ctx["run_async"](batch_restart_all(ctx)), color="info"),
        ])
        ctx["put_markdown"]("#### 按类型批量操作")
        ctx["put_row"]([
            ctx["put_button"]("⏱️ 启动间隔任务", onclick=lambda: ctx["run_async"](batch_start_by_type(ctx, TaskType.INTERVAL)), color="success", outline=True),
            ctx["put_button"]("⏰ 启动定时任务", onclick=lambda: ctx["run_async"](batch_start_by_type(ctx, TaskType.CRON)), color="success", outline=True),
            ctx["put_button"]("🔔 启动一次性任务", onclick=lambda: ctx["run_async"](batch_start_by_type(ctx, TaskType.ONE_TIME)), color="success", outline=True),
        ])


async def batch_start_all(ctx):
    """批量启动所有任务。"""
    task_manager = get_task_manager()
    results = task_manager.start_all_tasks()
    ctx["toast"](
        f"批量启动完成: 成功={results['success']}, 失败={results['failed']}, 跳过={results['skipped']}",
        color="info" if results["failed"] == 0 else "warning",
    )
    await refresh_task_list(ctx)


async def batch_stop_all(ctx):
    """批量停止所有任务。"""
    task_manager = get_task_manager()
    results = task_manager.stop_all_tasks()
    ctx["toast"](
        f"批量停止完成: 成功={results['success']}, 失败={results['failed']}, 跳过={results['skipped']}",
        color="info" if results["failed"] == 0 else "warning",
    )
    await refresh_task_list(ctx)


async def batch_restart_all(ctx):
    """批量重启所有任务。"""
    task_manager = get_task_manager()
    stop_results = task_manager.stop_all_tasks()
    start_results = task_manager.start_all_tasks()
    ctx["toast"](f"批量重启完成: 停止={stop_results['success']}, 启动={start_results['success']}", color="info")
    await refresh_task_list(ctx)


async def batch_start_by_type(ctx, task_type):
    """按类型批量启动任务。"""
    task_manager = get_task_manager()
    results = task_manager.start_all_tasks(task_type)
    type_names = {
        TaskType.INTERVAL: "间隔任务",
        TaskType.CRON: "定时任务",
        TaskType.ONE_TIME: "一次性任务",
    }
    ctx["toast"](
        f"{type_names.get(task_type, '任务')}批量启动完成: 成功={results['success']}, 失败={results['failed']}, 跳过={results['skipped']}",
        color="info" if results["failed"] == 0 else "warning",
    )
    await refresh_task_list(ctx)


async def refresh_task_list(ctx):
    """刷新任务列表。"""
    with ctx["use_scope"]("task_list_scope", clear=True):
        await render_task_list(ctx)


__all__ = ["render_enhanced_task_admin"]
