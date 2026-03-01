"""增强版任务面板(Task Panel)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime

from deva import log

from .task_unit import TaskType


def _panel_log(level: str, message: str):
    payload = {"level": level.upper(), "source": "deva.admin.task_panel", "message": str(message)}
    try:
        payload >> log
    except Exception:
        print(f"[{level.upper()}][deva.admin.task_panel] {message}")


def _default_task_code() -> str:
    return """async def execute(context=None):
    # 在这里编写任务逻辑
    return "ok"
"""


def _format_time_config(task_type: str, schedule_config: Dict[str, Any]) -> str:
    if task_type == "interval":
        return str(schedule_config.get("interval", 60))
    if task_type == "cron":
        hour = int(schedule_config.get("hour", 2))
        minute = int(schedule_config.get("minute", 0))
        return f"{hour:02d}:{minute:02d}"
    if task_type == "one_time":
        return str(schedule_config.get("run_date", "") or "")
    return "60"


def _parse_schedule_config(task_type: str, time_config: str) -> tuple[Dict[str, Any], Optional[str]]:
    value = (time_config or "").strip()
    if task_type == "interval":
        try:
            interval = int(value)
            if interval <= 0:
                return {}, "间隔任务执行时间必须大于0秒"
            return {"interval": interval}, None
        except Exception:
            return {}, "间隔任务执行时间必须是整数秒"

    if task_type == "cron":
        if ":" in value:
            try:
                hour_str, minute_str = value.split(":", 1)
                hour, minute = int(hour_str), int(minute_str)
            except Exception:
                return {}, "定时任务时间格式应为 HH:MM"
        else:
            try:
                hour, minute = 0, int(value)
            except Exception:
                return {}, "定时任务时间格式应为 HH:MM"
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return {}, "定时任务时间超出范围，小时0-23，分钟0-59"
        return {"hour": hour, "minute": minute}, None

    if task_type == "one_time":
        if not value:
            return {}, "一次性任务需要填写 run_date"
        return {"run_date": value}, None

    return {}, "不支持的任务类型"


async def show_enhanced_create_task_dialog(ctx):
    """增强版创建任务对话框。"""
    try:
        with ctx["popup"]("创建新任务", size="large", closable=True):
            ctx["put_markdown"]("### 创建任务（单页编辑）")
            ctx["put_markdown"]("> 在同一页面完成基础信息和执行代码填写。")

            draft = {
                "name": "",
                "task_type": "interval",
                "description": "",
                "time_config": "60",
                "code": _default_task_code(),
                "confirmations": ["code_reviewed", "code_approved"],
            }

            while True:
                form = await ctx["input_group"]("任务信息与代码", [
                    ctx["input"]("任务名称", name="name", required=True, value=draft["name"], placeholder="输入任务名称"),
                    ctx["select"](
                        "任务类型",
                        name="task_type",
                        options=[
                            {"label": "间隔任务（每隔X秒执行）", "value": "interval"},
                            {"label": "定时任务（每天固定时间执行）", "value": "cron"},
                            {"label": "一次性任务（指定时间执行）", "value": "one_time"},
                        ],
                        value=draft["task_type"],
                    ),
                    ctx["textarea"]("任务描述", name="description", rows=2, value=draft["description"], placeholder="任务描述（可选）"),
                    ctx["input"](
                        "执行时间配置",
                        name="time_config",
                        value=draft["time_config"],
                        help_text="interval: 秒数，例如 60；cron: HH:MM，例如 02:00；one_time: run_date 字符串",
                    ),
                    ctx["textarea"](
                        "任务代码",
                        name="code",
                        rows=16,
                        required=True,
                        value=draft["code"],
                        placeholder="async def execute(context=None):\n    return 'ok'",
                    ),
                    ctx["checkbox"](
                        "确认选项",
                        name="confirmations",
                        options=[
                            {"label": "我已审核代码", "value": "code_reviewed", "selected": "code_reviewed" in draft["confirmations"]},
                            {"label": "我确认创建任务", "value": "code_approved", "selected": "code_approved" in draft["confirmations"]},
                        ],
                    ),
                    ctx["actions"]("操作", [
                        {"label": "✅ 创建任务", "value": "create", "color": "success"},
                        {"label": "❌ 取消", "value": "cancel", "color": "danger"},
                    ], name="action"),
                ])

                if not form or form.get("action") != "create":
                    return

                draft.update(form)
                validation = validate_task_code(draft["code"])
                if not validation["valid"]:
                    ctx["toast"](f"代码验证失败: {'; '.join(validation['errors'])}", color="error")
                    continue

                schedule_config, schedule_error = _parse_schedule_config(draft["task_type"], draft["time_config"])
                if schedule_error:
                    ctx["toast"](schedule_error, color="error")
                    continue

                selected_confirmations = draft.get("confirmations", [])
                if "code_reviewed" not in selected_confirmations or "code_approved" not in selected_confirmations:
                    ctx["toast"]("请勾选必要确认项", color="warning")
                    continue

                await _create_enhanced_task(
                    ctx,
                    {
                        "name": draft["name"],
                        "task_type": draft["task_type"],
                        "description": draft.get("description", ""),
                        "time_config": draft["time_config"],
                        "schedule_config": schedule_config,
                    },
                    draft["code"],
                )
                return
            
    except Exception as e:
        _panel_log("ERROR", f"增强版创建任务对话框错误: {e}")
        ctx["toast"](f"创建任务对话框错误: {e}", color="error")
        ctx["close_popup"]()


async def _manual_task_code_input(ctx) -> str:
    """手动任务代码输入"""
    ctx["put_markdown"]("### 手动代码输入")
    ctx["put_html"]("""
    <div style='background:#fff3e0;padding:12px;border-radius:8px;margin-bottom:15px;'>
        <p style='color:#e65100;font-size:14px;margin:0;'>
            💡 <strong>手动代码输入</strong> - 请直接输入Python代码
        </p>
        <p style='color:#e65100;font-size:12px;margin:5px 0 0 0;'>
            📝 函数签名必须为: async def execute(context=None):
        </p>
    </div>
    """)
    
    code_input = await ctx["input_group"]("代码输入", [
        ctx["textarea"](
            "任务代码",
            name="code",
            placeholder="async def execute(context=None):\n    # 在这里输入您的任务代码\n    # 返回执行结果\n    return result",
            rows=12,
            required=True
        ),
        ctx["actions"]("操作", [
            {"label": "✅ 验证代码", "value": "validate"},
            {"label": "💾 使用代码", "value": "use"},
            {"label": "❌ 取消", "value": "cancel"}
        ], name="action")
    ])
    
    if not code_input or code_input.get("action") == "cancel":
        return ""
    
    code = code_input["code"]
    
    if code_input.get("action") == "validate":
        # 验证代码
        validation = validate_task_code(code)
        if validation["valid"]:
            ctx["put_success"]("✅ 代码验证通过")
            use_code = await ctx["actions"]("是否使用此代码？", [
                {"label": "✅ 使用", "value": "yes"},
                {"label": "❌ 重新编辑", "value": "edit"}
            ])
            if use_code == "edit":
                return await _manual_task_code_input(ctx)
        else:
            ctx["put_error"](f"❌ 代码验证失败: {'; '.join(validation['errors'])}")
            return await _manual_task_code_input(ctx)
    
    return code


async def _task_template_selection(ctx) -> str:
    """任务模板选择"""
    ctx["put_markdown"]("### 任务模板选择")
    ctx["put_html"]("""
    <div style='background:#e8f5e9;padding:12px;border-radius:8px;margin-bottom:15px;'>
        <p style='color:#2e7d32;font-size:14px;margin:0;'>
            📋 <strong>任务模板选择</strong> - 选择预设的代码模板
        </p>
        <p style='color:#2e7d32;font-size:12px;margin:5px 0 0 0;'>
            🚀 选择模板后可以根据需要进行修改
        </p>
    </div>
    """)
    
    # 预定义任务模板
    templates = {
        "database_backup": {
            "name": "数据库备份任务",
            "description": "定期备份数据库到指定位置",
            "code": '''async def execute(context=None):
    """数据库备份任务"""
    import asyncio
    import time
    from datetime import datetime
    from deva import log, write_to_file
    
    # 获取任务信息
    task_name = context.get('task_name', 'unknown') if context else 'unknown'
    start_time = time.time()
    
    try:
        # 任务开始
        f'数据库备份任务 {task_name} 开始执行' >> log
        
        # 模拟数据库备份
        backup_data = f"数据库备份数据 - {datetime.now().isoformat()}"
        backup_file = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
        
        # 写入备份文件
        backup_data >> write_to_file(backup_file)
        
        # 模拟备份过程
        await asyncio.sleep(2)
        
        result = f'数据库备份完成: {backup_file} (耗时: {time.time() - start_time:.2f}s)'
        result >> log
        
        return result
        
    except Exception as e:
        error_msg = f'数据库备份任务失败: {e}'
        error_msg >> log
        raise'''
        },
        "system_monitoring": {
            "name": "系统监控任务",
            "description": "监控系统状态和性能指标",
            "code": '''async def execute(context=None):
    """系统监控任务"""
    import asyncio
    import time
    from datetime import datetime
    from deva import log
    
    # 获取任务信息
    task_name = context.get('task_name', 'unknown') if context else 'unknown'
    start_time = time.time()
    
    try:
        # 任务开始
        f'系统监控任务 {task_name} 开始执行' >> log
        
        # 模拟系统监控
        import random
        
        # 模拟CPU使用率
        cpu_usage = random.uniform(10, 90)
        
        # 模拟内存使用率
        memory_usage = random.uniform(30, 80)
        
        # 模拟磁盘使用率
        disk_usage = random.uniform(40, 95)
        
        # 模拟网络状态
        network_status = random.choice(["正常", "警告", "异常"])
        
        # 生成监控报告
        report = f"""系统监控报告 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}):
CPU使用率: {cpu_usage:.1f}%
内存使用率: {memory_usage:.1f}%
磁盘使用率: {disk_usage:.1f}%
网络状态: {network_status}"""
        
        report >> log
        
        result = f'系统监控完成 (耗时: {time.time() - start_time:.2f}s)'
        result >> log
        
        return result
        
    except Exception as e:
        error_msg = f'系统监控任务失败: {e}'
        error_msg >> log
        raise'''
        },
        "data_cleanup": {
            "name": "数据清理任务",
            "description": "定期清理过期数据文件",
            "code": '''async def execute(context=None):
    """数据清理任务"""
    import asyncio
    import time
    import os
    import glob
    from datetime import datetime, timedelta
    from deva import log
    
    # 获取任务信息
    task_name = context.get('task_name', 'unknown') if context else 'unknown'
    start_time = time.time()
    
    try:
        # 任务开始
        f'数据清理任务 {task_name} 开始执行' >> log
        
        # 模拟数据清理
        # 清理7天前的临时文件
        cutoff_date = datetime.now() - timedelta(days=7)
        
        # 模拟临时文件列表
        temp_files = [
            f"temp_file_{i}.tmp" for i in range(10)
        ]
        
        deleted_count = 0
        
        for file_path in temp_files:
            try:
                # 模拟文件删除
                f'删除文件: {file_path}' >> log
                deleted_count += 1
            except Exception as e:
                f'删除文件失败: {file_path} - {e}' >> log
        
        result = f'数据清理完成，删除 {deleted_count} 个文件 (耗时: {time.time() - start_time:.2f}s)'
        result >> log
        
        return result
        
    except Exception as e:
        error_msg = f'数据清理任务失败: {e}'
        error_msg >> log
        raise'''
        },
        "report_generation": {
            "name": "报告生成任务",
            "description": "定期生成业务报告",
            "code": '''async def execute(context=None):
    """报告生成任务"""
    import asyncio
    import time
    from datetime import datetime
    from deva import log, write_to_file
    
    # 获取任务信息
    task_name = context.get('task_name', 'unknown') if context else 'unknown'
    start_time = time.time()
    
    try:
        # 任务开始
        f'报告生成任务 {task_name} 开始执行' >> log
        
        # 模拟报告生成
        import random
        
        # 生成模拟业务数据
        report_data = {
            "report_date": datetime.now().strftime("%Y-%m-%d"),
            "total_sales": random.uniform(10000, 100000),
            "total_orders": random.randint(100, 1000),
            "avg_order_value": random.uniform(50, 200),
            "new_customers": random.randint(10, 100),
            "satisfaction_score": random.uniform(3.0, 5.0)
        }
        
        # 生成报告内容
        report_content = f"""# 业务日报 - {report_data['report_date']}

## 销售数据
- 总销售额: ${report_data['total_sales']:,.2f}
- 订单总数: {report_data['total_orders']:,}
- 平均订单价值: ${report_data['avg_order_value']:.2f}

## 客户数据
- 新增客户: {report_data['new_customers']:,}
- 客户满意度: {report_data['satisfaction_score']:.1f}/5.0

## 总结
今日业务表现良好，各项指标均在预期范围内。
"""
        
        # 保存报告到文件
        report_file = f"daily_report_{report_data['report_date']}.md"
        report_content >> write_to_file(report_file)
        
        result = f'报告生成完成: {report_file} (耗时: {time.time() - start_time:.2f}s)'
        result >> log
        
        return result
        
    except Exception as e:
        error_msg = f'报告生成任务失败: {e}'
        error_msg >> log
        raise'''
        }
    }
    
    # 显示模板选择
    template_options = []
    for key, template in templates.items():
        template_options.append({
            "label": f"{template['name']} - {template['description']}",
            "value": key
        })
    
    selected_template = await ctx["select"](
        "选择任务模板",
        options=template_options,
        help_text="选择预设的任务代码模板"
    )
    
    if not selected_template:
        return ""
    
    # 显示模板代码
    template_info = templates[selected_template]
    
    ctx["put_markdown"](f"#### 模板: {template_info['name']}")
    ctx["put_text"](f"描述: {template_info['description']}")
    
    with ctx["put_collapse"]("📋 模板代码预览", open=True):
        ctx["put_code"](template_info['code'], language="python")
    
    # 确认使用
    confirm_use = await ctx["actions"]("是否使用此模板？", [
        {"label": "✅ 使用模板", "value": "use"},
        {"label": "✏️ 编辑模板", "value": "edit"},
        {"label": "❌ 重新选择", "value": "reselect"}
    ])
    
    if confirm_use == "edit":
        # 允许用户编辑模板
        edited_code = await ctx["textarea"](
            "编辑代码",
            value=template_info['code'],
            rows=15,
            help_text="您可以在此修改模板代码"
        )
        return edited_code if edited_code else template_info['code']
    elif confirm_use == "use":
        return template_info['code']
    elif confirm_use == "reselect":
        return await _task_template_selection(ctx)
    else:
        return ""


async def _task_file_import(ctx) -> str:
    """从文件导入任务代码"""
    ctx["put_markdown"]("### 从文件导入代码")
    ctx["put_html"]("""
    <div style='background:#f3e5f5;padding:12px;border-radius:8px;margin-bottom:15px;'>
        <p style='color:#6a1b9a;font-size:14px;margin:0;'>
            📁 <strong>文件导入</strong> - 上传Python代码文件
        </p>
        <p style='color:#6a1b9a;font-size:12px;margin:5px 0 0 0;'>
            📋 文件内容必须包含 async def execute(context=None) 函数
        </p>
    </div>
    """)
    
    # 文件上传
    uploaded_file = await ctx["file_upload"](
        "选择Python文件",
        accept=".py",
        help_text="上传包含 execute 函数的Python文件"
    )
    
    if not uploaded_file:
        ctx["toast"]("未选择文件", color="warning")
        return ""
    
    try:
        # 读取文件内容
        file_content = uploaded_file['content'].decode('utf-8')
        
        # 验证代码
        validation = validate_task_code(file_content)
        
        if validation["valid"]:
            ctx["put_success"]("✅ 文件验证通过")
            
            # 显示代码预览
            with ctx["put_collapse"]("📋 文件内容预览", open=False):
                ctx["put_code"](file_content, language="python")
            
            # 确认使用
            confirm = await ctx["actions"]("是否使用此文件？", [
                {"label": "✅ 使用文件", "value": "use"},
                {"label": "❌ 取消", "value": "cancel"}
            ])
            
            if confirm == "use":
                return file_content
            else:
                return ""
        else:
            ctx["put_error"](f"❌ 文件验证失败: {'; '.join(validation['errors'])}")
            return ""
            
    except Exception as e:
        ctx["put_error"](f"❌ 文件处理错误: {str(e)}")
        return ""


async def _create_enhanced_task(ctx, basic_form: Dict[str, Any], generated_code: str):
    """创建增强版任务"""
    try:
        from .task_manager import get_task_manager
        from .task_unit import TaskUnit, TaskMetadata, TaskState, TaskExecution
        
        task_manager = get_task_manager()
        
        # 转换任务类型
        task_type_map = {
            "interval": TaskType.INTERVAL,
            "cron": TaskType.CRON,
            "one_time": TaskType.ONE_TIME
        }
        
        task_type = task_type_map.get(basic_form.get("task_type", "interval"), TaskType.INTERVAL)
        
        schedule_config = basic_form.get("schedule_config")
        if not isinstance(schedule_config, dict):
            schedule_config, schedule_error = _parse_schedule_config(
                basic_form.get("task_type", "interval"),
                basic_form.get("time_config", "60"),
            )
            if schedule_error:
                ctx["toast"](f"创建任务失败: {schedule_error}", color="error")
                return
        
        # 创建任务元数据
        metadata = TaskMetadata(
            id=f"task_{basic_form['name']}_{int(datetime.now().timestamp())}",
            name=basic_form["name"],
            description=basic_form.get("description", ""),
            task_type=task_type,
            schedule_config=schedule_config,
            retry_config={"max_retries": 3, "retry_interval": 300},
            func_code=generated_code
        )
        
        # 创建任务状态
        state = TaskState(
            status="stopped",
            last_run_time=0,
            next_run_time=0,
            run_count=0,
            error_count=0
        )
        
        # 创建执行信息
        execution = TaskExecution(
            job_code=generated_code,
            execution_history=[]
        )
        
        # 创建任务单元
        task_unit = TaskUnit(
            metadata=metadata,
            state=state,
            execution=execution
        )
        
        # 注册任务
        register_result = task_manager.register(task_unit)
        
        if register_result.get("success"):
            ctx["toast"](f"任务创建成功: {task_unit.id}", color="success")
            
            # 可选：自动启动任务
            start_result = task_manager.start(task_unit.id)
            if start_result.get("success"):
                ctx["toast"]("任务已自动启动", color="info")
            else:
                ctx["toast"](f"任务启动失败: {start_result.get('error', '')}", color="warning")
                
            ctx["run_js"]("location.reload()")
        else:
            ctx["toast"](f"任务创建失败: {register_result.get('error', '')}", color="error")
            
    except Exception as e:
        _panel_log("ERROR", f"创建增强版任务错误: {e}")
        ctx["toast"](f"创建任务错误: {e}", color="error")


async def show_enhanced_edit_task_dialog(ctx, task_name: str):
    """增强版编辑任务对话框。"""
    try:
        from .task_manager import get_task_manager
        
        task_manager = get_task_manager()
        
        # 查找任务
        task_unit = None
        for task in task_manager.list_all():
            if task.name == task_name:
                task_unit = task
                break
        
        if not task_unit:
            ctx["toast"]("任务不存在", color="error")
            return
        
        with ctx["popup"](f"编辑任务: {task_unit.name}", size="large", closable=True):
            ctx["put_markdown"](f"### 编辑任务: {task_unit.name}")
            ctx["put_markdown"]("> 在同一页面完成内容编辑和代码输入。")

            current_code = (task_unit.metadata.func_code or "").strip() or (task_unit.execution.job_code or "").strip() or _default_task_code()
            current_type = task_unit.metadata.task_type.value
            draft = {
                "name": task_unit.name,
                "task_type": current_type,
                "description": task_unit.metadata.description or "",
                "time_config": _format_time_config(current_type, task_unit.metadata.schedule_config or {}),
                "code": current_code,
                "confirmations": ["code_reviewed", "save_approved"],
            }

            while True:
                form = await ctx["input_group"]("任务信息与代码", [
                    ctx["input"]("任务名称", name="name", required=True, value=draft["name"]),
                    ctx["select"](
                        "任务类型",
                        name="task_type",
                        options=[
                            {"label": "间隔任务（每隔X秒执行）", "value": "interval"},
                            {"label": "定时任务（每天固定时间执行）", "value": "cron"},
                            {"label": "一次性任务（指定时间执行）", "value": "one_time"},
                        ],
                        value=draft["task_type"],
                    ),
                    ctx["textarea"]("任务描述", name="description", rows=2, value=draft["description"], placeholder="任务描述（可选）"),
                    ctx["input"](
                        "执行时间配置",
                        name="time_config",
                        value=draft["time_config"],
                        help_text="interval: 秒数，例如 60；cron: HH:MM，例如 02:00；one_time: run_date 字符串",
                    ),
                    ctx["textarea"]("任务代码", name="code", rows=16, required=True, value=draft["code"]),
                    ctx["checkbox"](
                        "确认选项",
                        name="confirmations",
                        options=[
                            {"label": "我已审核代码修改", "value": "code_reviewed", "selected": "code_reviewed" in draft["confirmations"]},
                            {"label": "我确认保存修改", "value": "save_approved", "selected": "save_approved" in draft["confirmations"]},
                        ],
                    ),
                    ctx["actions"]("操作", [
                        {"label": "✅ 保存修改", "value": "save", "color": "success"},
                        {"label": "❌ 取消", "value": "cancel", "color": "danger"},
                    ], name="action"),
                ])

                if not form or form.get("action") != "save":
                    return

                draft.update(form)
                selected_confirmations = draft.get("confirmations", [])
                if "code_reviewed" not in selected_confirmations or "save_approved" not in selected_confirmations:
                    ctx["toast"]("请勾选必要确认项", color="warning")
                    continue

                validation = validate_task_code(draft["code"])
                if not validation["valid"]:
                    ctx["toast"](f"代码验证失败: {'; '.join(validation['errors'])}", color="error")
                    continue

                schedule_config, schedule_error = _parse_schedule_config(draft["task_type"], draft["time_config"])
                if schedule_error:
                    ctx["toast"](schedule_error, color="error")
                    continue

                task_type_map = {
                    "interval": TaskType.INTERVAL,
                    "cron": TaskType.CRON,
                    "one_time": TaskType.ONE_TIME,
                }
                task_type = task_type_map.get(draft["task_type"], TaskType.INTERVAL)

                task_unit.metadata.name = draft["name"]
                task_unit.metadata.description = draft.get("description", "")
                task_unit.metadata.task_type = task_type
                task_unit.metadata.schedule_config = schedule_config

                if draft["code"] != current_code:
                    task_unit.metadata.func_code = draft["code"]
                    task_unit.execution.job_code = draft["code"]
                    compile_result = task_unit.compile_code(draft["code"], "execute")
                    if not compile_result.get("success"):
                        ctx["toast"](f"代码编译失败: {compile_result.get('error', '')}", color="error")
                        continue
                    task_unit.execution.compiled_func = compile_result["func"]
                    task_unit._func = compile_result["func"]

                task_unit.save()

                if task_unit.is_running:
                    stop_result = task_manager.stop(task_unit.id)
                    if not stop_result.get("success"):
                        ctx["toast"](f"重载任务停止失败: {stop_result.get('error', '')}", color="warning")
                    start_result = task_manager.start(task_unit.id)
                    if not start_result.get("success"):
                        ctx["toast"](f"重载任务启动失败: {start_result.get('error', '')}", color="warning")

                ctx["toast"]("任务修改保存成功", color="success")
                ctx["run_js"]("location.reload()")
                return
            
    except Exception as e:
        _panel_log("ERROR", f"增强版编辑任务对话框错误: {e}")
        ctx["toast"](f"编辑任务对话框错误: {e}", color="error")
        ctx["close_popup"]()


async def _manual_task_code_edit(ctx, current_code: str) -> str:
    """手动编辑任务代码"""
    ctx["put_markdown"]("### 手动编辑代码")
    ctx["put_html"]("""
    <div style='background:#fff3e0;padding:12px;border-radius:8px;margin-bottom:15px;'>
        <p style='color:#e65100;font-size:14px;margin:0;'>
            💡 <strong>手动编辑代码</strong> - 请直接修改Python代码
        </p>
        <p style='color:#e65100;font-size:12px;margin:5px 0 0 0;'>
            📝 函数签名必须为: async def execute(context=None):
        </p>
    </div>
    """)
    
    code_input = await ctx["input_group"]("代码编辑", [
        ctx["textarea"](
            "任务代码",
            name="code",
            placeholder="async def execute(context=None):\n    # 在这里输入您的任务代码\n    # 返回执行结果\n    return result",
            rows=15,
            required=True,
            value=current_code
        ),
        ctx["actions"]("操作", [
            {"label": "✅ 验证代码", "value": "validate"},
            {"label": "💾 保存代码", "value": "save"},
            {"label": "❌ 取消", "value": "cancel"}
        ], name="action")
    ])
    
    if not code_input or code_input.get("action") == "cancel":
        return current_code
    
    code = code_input["code"]
    
    if code_input.get("action") == "validate":
        # 验证代码
        validation = validate_task_code(code)
        if validation["valid"]:
            ctx["put_success"]("✅ 代码验证通过")
            use_code = await ctx["actions"]("是否使用此代码？", [
                {"label": "✅ 使用", "value": "yes"},
                {"label": "❌ 重新编辑", "value": "edit"}
            ])
            if use_code == "edit":
                return await _manual_task_code_edit(ctx, current_code)
        else:
            ctx["put_error"](f"❌ 代码验证失败: {'; '.join(validation['errors'])}")
            return await _manual_task_code_edit(ctx, current_code)
    
    return code


def validate_task_code(code: str) -> Dict[str, Any]:
    """验证任务代码"""
    try:
        import ast
        
        # 语法检查
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {
                "valid": False,
                "errors": [f"语法错误: {e}"]
            }
        
        # 检查函数定义
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                functions.append(node.name)
            elif isinstance(node, ast.FunctionDef):
                functions.append(node.name)
        
        if "execute" not in functions:
            return {
                "valid": False,
                "errors": ["未找到'execute'函数定义，任务必须包含execute函数"]
            }
        
        # 安全性检查
        dangerous_keywords = ['eval', 'exec', '__import__', 'open', 'file']
        warnings = []
        for keyword in dangerous_keywords:
            if keyword in code:
                warnings.append(f"检测到潜在危险关键字: {keyword}")
        
        return {
            "valid": True,
            "errors": [],
            "warnings": warnings,
            "functions": functions
        }
        
    except Exception as e:
        return {
            "valid": False,
            "errors": [f"验证过程出错: {e}"]
        }
