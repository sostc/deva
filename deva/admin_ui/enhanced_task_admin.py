"""增强版任务管理UI - 集成AI代码生成功能"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

from deva import log

# 导入增强版任务面板
from .strategy.enhanced_task_panel import (
    show_enhanced_create_task_dialog, 
    show_enhanced_edit_task_dialog
)
from .strategy.task_manager import get_task_manager
from .strategy.task_unit import TaskUnit, TaskType


async def render_enhanced_task_admin(ctx):
    """渲染增强版任务管理界面"""
    
    put_markdown = ctx["put_markdown"]
    put_button = ctx["put_button"]
    put_row = ctx["put_row"]
    use_scope = ctx["use_scope"]
    toast = ctx["toast"]
    put_text = ctx["put_text"]
    
    # 页面标题和介绍
    put_markdown("## 🤖 增强版任务管理 (AI驱动)")
    
    # 使用put_text和put_markdown创建美观的介绍
    put_text("")
    put_markdown("> 🚀 **AI智能任务创建** - 使用AI自动生成任务代码，支持自然语言描述需求，提供完整的代码审核和编辑流程")
    put_text("")
    
    # 操作按钮区域
    put_row([
        put_button("🤖 AI创建任务", onclick=lambda: show_enhanced_create_task_dialog(ctx), color="success", outline=True),
        put_button("📋 批量管理", onclick=lambda: show_batch_management(ctx), color="info", outline=True),
        put_button("🔄 刷新列表", onclick=lambda: refresh_task_list(ctx), color="secondary", outline=True)
    ])
    
    # 统计信息卡片
    await render_task_statistics(ctx)
    
    # 任务列表区域 - 使用use_scope创建命名区域
    use_scope("task_list_scope", clear=True)
    await render_task_list(ctx)


async def render_task_statistics(ctx):
    """渲染任务统计信息"""
    
    put_row = ctx["put_row"]
    put_text = ctx["put_text"]
    put_markdown = ctx["put_markdown"]
    
    task_manager = get_task_manager()
    stats = task_manager.get_overall_stats()
    
    total_tasks = stats["basic_stats"]["total"]
    running_tasks = stats["basic_stats"]["running_count"]
    stopped_tasks = stats["basic_stats"]["stopped_count"]
    error_tasks = stats["basic_stats"]["error_count"]
    
    execution_stats = stats.get("execution_stats", {})
    total_executions = execution_stats.get("total_executions", 0)
    success_rate = execution_stats.get("success_rate", 0) * 100
    
    # 使用put_markdown创建统计信息
    put_markdown(f"""
### 📊 任务统计概览

| 指标 | 数值 | 状态 |
|------|------|------|
| 总任务数 | {total_tasks} | 📋 |
| 运行中 | {running_tasks} | 🟢 |
| 已停止 | {stopped_tasks} | ⚫ |
| 错误状态 | {error_tasks} | 🔴 |
| 成功率 | {success_rate:.1f}% | 📈 |
""")
    
    put_text("")  # 添加间距


async def render_task_list(ctx):
    """渲染任务列表"""
    
    put_markdown = ctx["put_markdown"]
    put_table = ctx["put_table"]
    put_button = ctx["put_button"]
    put_text = ctx["put_text"]
    
    task_manager = get_task_manager()
    tasks = task_manager.list_all()
    
    if not tasks:
        put_text("")
        put_markdown("> 📝 **暂无任务** - 点击上方\"🤖 AI创建任务\"按钮创建您的第一个任务")
        put_text("")
        return
    
    put_markdown("### 📋 任务列表")
    
    # 构建表格数据
    table_data = []
    for task in tasks:
        # 获取任务统计
        task_stats = task_manager.get_task_stats(task.id)
        
        # 状态指示器
        status_text = get_status_text(task.state.status)
        
        # 任务类型图标
        type_icon = get_task_type_icon(task.metadata.task_type)
        
        # 操作按钮（简化版本，使用文本描述）
        actions = []
        if task.is_running:
            actions.append("⏸️ 停止")
        else:
            actions.append("▶️ 启动")
        
        actions.extend(["✏️ 编辑", "📊 详情", "🗑️ 删除"])
        
        # 成功率
        exec_stats = task_stats.get("execution_stats", {}) if task_stats else {}
        success_rate = exec_stats.get("success_rate", 0) * 100 if exec_stats.get("success_rate") else 0
        
        table_data.append([
            f"{type_icon} {task.name}",
            status_text,
            task.metadata.task_type.value,
            task.get_schedule_description(),
            f"{task.state.run_count}次",
            f"{success_rate:.1f}%",
            " | ".join(actions)
        ])
    
    # 渲染表格
    put_table(
        table_data,
        header=["任务名称", "状态", "类型", "调度配置", "执行次数", "成功率", "操作"]
    )
    
    put_text("")
    put_markdown("> 💡 **操作提示**: 点击\"✏️ 编辑\"可以修改任务代码，点击\"📊 详情\"查看完整信息")
    put_text("")


def get_status_text(status):
    """获取状态文本"""
    status_texts = {
        "running": "🟢 运行中",
        "stopped": "⚫ 已停止",
        "error": "🔴 错误",
        "paused": "🟡 暂停",
        "completed": "🔵 已完成"
    }
    
    return status_texts.get(status, f"❓ {status}")


def get_task_type_icon(task_type):
    """获取任务类型图标"""
    icons = {
        TaskType.INTERVAL: "⏱️",
        TaskType.CRON: "⏰", 
        TaskType.ONE_TIME: "🔔"
    }
    return icons.get(task_type, "📋")


async def handle_task_action(ctx, action, task_id):
    """处理任务操作"""
    
    toast = ctx["toast"]
    task_manager = get_task_manager()
    
    action_parts = action.split("_", 1)
    if len(action_parts) != 2:
        return
    
    action_type, task_id = action_parts
    
    # 查找任务
    task = task_manager.get(task_id)
    if not task:
        toast("任务不存在", color="error")
        return
    
    try:
        if action_type == "start":
            result = task_manager.start(task_id)
            if result.get("success"):
                toast(f"任务已启动: {task.name}", color="success")
            else:
                toast(f"启动失败: {result.get('error', '')}", color="error")
                
        elif action_type == "stop":
            result = task_manager.stop(task_id)
            if result.get("success"):
                toast(f"任务已停止: {task.name}", color="success")
            else:
                toast(f"停止失败: {result.get('error', '')}", color="error")
                
        elif action_type == "edit":
            await show_enhanced_edit_task_dialog(ctx, task.name)
            
        elif action_type == "details":
            await show_task_details(ctx, task)
            
        elif action_type == "delete":
            confirm = await ctx["actions"](
                f"确认删除任务 '{task.name}'?",
                [
                    {"label": "✅ 确认删除", "value": "confirm", "color": "danger"},
                    {"label": "❌ 取消", "value": "cancel", "color": "secondary"}
                ]
            )
            
            if confirm == "confirm":
                result = task_manager.unregister(task_id)
                if result.get("success"):
                    toast(f"任务已删除: {task.name}", color="success")
                    await refresh_task_list(ctx)
                else:
                    toast(f"删除失败: {result.get('error', '')}", color="error")
    
    except Exception as e:
        toast(f"操作失败: {str(e)}", color="error")


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
        if task.metadata.func_code:
            with put_collapse("📋 任务代码预览", open=False):
                put_code(task.metadata.func_code, language="python")
        
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


async def show_batch_management(ctx):
    """显示批量管理界面"""
    
    put_markdown = ctx["put_markdown"]
    put_row = ctx["put_row"]
    put_button = ctx["put_button"]
    toast = ctx["toast"]
    
    with ctx["popup"]("批量任务管理", size="large"):
        put_markdown("### ⚙️ 批量任务管理")
        
        put_row([
            put_button("▶️ 启动所有任务", onclick=lambda: batch_start_all(ctx), color="success"),
            put_button("⏸️ 停止所有任务", onclick=lambda: batch_stop_all(ctx), color="warning"),
            put_button("🔄 重启所有任务", onclick=lambda: batch_restart_all(ctx), color="info"),
        ])
        
        put_markdown("#### 按类型批量操作")
        
        put_row([
            put_button("⏱️ 启动间隔任务", onclick=lambda: batch_start_by_type(ctx, TaskType.INTERVAL), color="success", outline=True),
            put_button("⏰ 启动定时任务", onclick=lambda: batch_start_by_type(ctx, TaskType.CRON), color="success", outline=True),
            put_button("🔔 启动一次性任务", onclick=lambda: batch_start_by_type(ctx, TaskType.ONE_TIME), color="success", outline=True),
        ])


async def batch_start_all(ctx):
    """批量启动所有任务"""
    task_manager = get_task_manager()
    results = task_manager.start_all_tasks()
    
    toast(f"批量启动完成: 成功={results['success']}, 失败={results['failed']}, 跳过={results['skipped']}", 
          color="info" if results['failed'] == 0 else "warning")
    await refresh_task_list(ctx)


async def batch_stop_all(ctx):
    """批量停止所有任务"""
    task_manager = get_task_manager()
    results = task_manager.stop_all_tasks()
    
    toast(f"批量停止完成: 成功={results['success']}, 失败={results['failed']}, 跳过={results['skipped']}", 
          color="info" if results['failed'] == 0 else "warning")
    await refresh_task_list(ctx)


async def batch_restart_all(ctx):
    """批量重启所有任务"""
    task_manager = get_task_manager()
    
    # 先停止所有任务
    stop_results = task_manager.stop_all_tasks()
    
    # 再启动所有任务
    start_results = task_manager.start_all_tasks()
    
    toast(f"批量重启完成: 停止={stop_results['success']}, 启动={start_results['success']}", 
          color="info")
    await refresh_task_list(ctx)


async def batch_start_by_type(ctx, task_type):
    """按类型批量启动任务"""
    task_manager = get_task_manager()
    results = task_manager.start_all_tasks(task_type)
    
    type_names = {
        TaskType.INTERVAL: "间隔任务",
        TaskType.CRON: "定时任务", 
        TaskType.ONE_TIME: "一次性任务"
    }
    
    toast(f"{type_names.get(task_type, '任务')}批量启动完成: 成功={results['success']}, 失败={results['failed']}, 跳过={results['skipped']}", 
          color="info" if results['failed'] == 0 else "warning")
    await refresh_task_list(ctx)


async def refresh_task_list(ctx):
    """刷新任务列表"""
    with ctx["use_scope"]("task_list_scope", clear=True):
        await render_task_list(ctx)


# 导出函数供外部使用
__all__ = ['render_enhanced_task_admin']