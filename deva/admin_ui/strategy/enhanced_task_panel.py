"""增强版任务面板(AI Enhanced Task Panel)

为任务面板集成AI代码生成功能，提供用户审核编辑界面。
"""

from __future__ import annotations

import json
import traceback
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime

from deva import log

from .ai_code_generation_dialog import AICodeGenerationDialog
from .interactive_ai_code_generator import InteractiveCodeGenerator, CodeReviewResult
from .ai_code_generation_ui import AICodeGenerationUI, get_ai_code_generation_ui
from .task_unit import TaskType


async def show_enhanced_create_task_dialog(ctx):
    """增强版创建任务对话框 - 集成AI代码生成功能"""
    try:
        from pywebio import output as pw_output
        from pywebio import input as pw_input
        
        with ctx["popup"]("创建新任务 (AI增强版)", size="large", closable=True):
            ctx["put_markdown"]("### 任务配置 (AI增强版)")
            ctx["put_html"]("""
            <div style='background:#e3f2fd;padding:12px;border-radius:8px;margin-bottom:15px;'>
                <p style='color:#1565c0;font-size:14px;margin:0;'>
                    💡 <strong>AI代码生成</strong>：点击「AI生成」按钮，由AI根据需求描述自动生成任务代码
                </p>
                <p style='color:#1565c0;font-size:12px;margin:5px 0 0 0;'>
                    📝 <strong>代码审核</strong>：生成的代码需要您的审核和编辑确认
                </p>
            </div>
            """)
            
            # 基础信息收集
            basic_form = await ctx["input_group"]("基础信息", [
                ctx["input"]("任务名称", name="name", required=True, placeholder="输入任务名称"),
                ctx["select"](
                    "任务类型",
                    name="task_type",
                    options=[
                        {"label": "间隔任务（每隔X秒执行）", "value": "interval"},
                        {"label": "定时任务（每天固定时间执行）", "value": "cron"},
                        {"label": "一次性任务（指定时间执行）", "value": "one_time"}
                    ],
                    value="interval"
                ),
                ctx["textarea"]("任务描述", name="description", placeholder="任务描述（可选）", rows=2),
                ctx["input"]("执行时间配置", name="time_config", placeholder="间隔秒数(如60) 或 时间HH:MM(如02:00)", help_text="根据任务类型设置执行时间或间隔")
            ])
            
            if not basic_form:
                ctx["close_popup"]()
                return
            
            # 代码生成选项
            ctx["put_markdown"]("### 代码生成选项")
            code_generation_method = await ctx["radio"](
                "选择代码生成方式",
                options=[
                    {"label": "🤖 AI智能生成 - 描述需求，AI自动生成代码", "value": "ai_generate"},
                    {"label": "✏️ 手动编写 - 直接输入Python代码", "value": "manual_write"},
                    {"label": "📋 从模板选择 - 选择预设代码模板", "value": "template_select"},
                    {"label": "📁 从文件导入 - 上传Python代码文件", "value": "file_import"}
                ],
                value="ai_generate"
            )
            
            generated_code = ""
            
            if code_generation_method == "ai_generate":
                generated_code = await _enhanced_task_ai_generation(ctx, basic_form)
                
            elif code_generation_method == "manual_write":
                generated_code = await _manual_task_code_input(ctx)
                
            elif code_generation_method == "template_select":
                generated_code = await _task_template_selection(ctx)
                
            elif code_generation_method == "file_import":
                generated_code = await _task_file_import(ctx)
            
            if not generated_code:
                ctx["toast"]("代码生成被取消", color="warning")
                return
            
            # 最终确认
            ctx["put_markdown"]("### 最终确认")
            ctx["put_info"](f"任务名称: {basic_form['name']}")
            ctx["put_info"](f"任务类型: {basic_form['task_type']}")
            ctx["put_info"](f"代码长度: {len(generated_code)} 字符")
            
            with ctx["put_collapse"]("预览代码", open=False):
                ctx["put_code"](generated_code, language="python")
            
            final_confirm = await ctx["input_group"]("确认创建", [
                ctx["checkbox"](
                    "确认选项",
                    name="confirmations",
                    options=[
                        {"label": "我已审核生成的代码", "value": "code_reviewed", "selected": True},
                        {"label": "我理解代码的执行逻辑", "value": "logic_understood", "selected": True},
                        {"label": "我确认使用此代码", "value": "code_approved", "selected": True}
                    ]
                ),
                ctx["actions"]("操作", [
                    {"label": "✅ 创建任务", "value": "create", "color": "success"},
                    {"label": "❌ 取消", "value": "cancel", "color": "danger"}
                ], name="action")
            ])
            
            if not final_confirm or final_confirm.get("action") != "create":
                return
            
            # 检查确认选项
            required_confirmations = ["code_reviewed", "code_approved"]
            selected_confirmations = final_confirm.get("confirmations", [])
            
            for req in required_confirmations:
                if req not in selected_confirmations:
                    ctx["toast"]("请确认所有必要选项", color="warning")
                    return
            
            # 创建任务
            await _create_enhanced_task(ctx, basic_form, generated_code)
            
    except Exception as e:
        log.error(f"增强版创建任务对话框错误: {e}")
        ctx["toast"](f"创建任务对话框错误: {e}", color="error")
        ctx["close_popup"]()


async def _enhanced_task_ai_generation(ctx, basic_form: Dict[str, Any]) -> str:
    """增强版AI任务代码生成流程"""
    try:
        # 创建AI代码生成对话框
        ai_dialog = AICodeGenerationDialog("task", ctx)
        
        # 显示AI代码生成向导
        ctx["put_markdown"]("#### 🤖 AI任务代码生成向导")
        ctx["put_html"]("""
        <div style='background:#e8f5e9;padding:12px;border-radius:8px;margin-bottom:15px;'>
            <p style='color:#2e7d32;font-size:14px;margin:0;'>
                💡 <strong>AI任务代码生成向导</strong>将引导您完成代码生成过程
            </p>
            <p style='color:#2e7d32;font-size:12px;margin:5px 0 0 0;'>
                📝 请详细描述您的任务需求，AI将生成相应的Python异步代码
            </p>
        </div>
        """)
        
        # 步骤1: 收集需求信息
        ctx["put_markdown"]("##### 步骤1: 任务需求收集")
        
        requirement_form = await _collect_enhanced_task_requirements(ctx, basic_form)
        
        if not requirement_form:
            return ""
        
        # 步骤2: AI代码生成
        ctx["put_markdown"]("##### 步骤2: AI代码生成")
        ctx["put_info"]("正在生成代码，请稍候...")
        
        # 构建生成上下文
        generation_context = {
            "task_name": basic_form.get("name", "未命名任务"),
            "task_type": basic_form.get("task_type", "interval"),
            "time_config": basic_form.get("time_config", "60"),
            "schedule_config": requirement_form.get("schedule_config", ""),
            "retry_config": requirement_form.get("retry_config", ""),
            "task_options": requirement_form.get("task_options", []),
            "enable_retry": "enable_retry" in requirement_form.get("task_options", []),
            "send_notification": "send_notification" in requirement_form.get("task_options", []),
            "detailed_logging": "detailed_logging" in requirement_form.get("task_options", [])
        }
        
        # 转换任务类型
        task_type_map = {
            "interval": TaskType.INTERVAL,
            "cron": TaskType.CRON,
            "one_time": TaskType.ONE_TIME
        }
        
        # 使用交互式代码生成器
        generator = InteractiveCodeGenerator("task")
        
        review_result = await generator.generate_and_review(
            requirement=requirement_form["requirement"],
            context=generation_context,
            show_comparison=True,
            enable_realtime_validation=True,
            task_type=task_type_map.get(basic_form.get("task_type", "interval"), TaskType.INTERVAL),
            include_monitoring=True,
            include_retry=generation_context["enable_retry"]
        )
        
        if not review_result.approved:
            ctx["toast"]("代码生成被取消", color="warning")
            return ""
        
        # 步骤3: 代码审核与编辑
        ctx["put_markdown"]("##### 步骤3: 代码审核与编辑")
        
        # 显示生成结果
        ctx["put_success"](f"✅ 代码生成完成 (长度: {len(review_result.code)} 字符)")
        if review_result.user_modified:
            ctx["put_info"]("📝 用户对代码进行了修改")
        
        # 显示代码预览
        with ctx["put_collapse"]("📋 生成代码预览", open=False):
            ctx["put_code"](review_result.code, language="python")
        
        # 显示代码说明
        if review_result.validation_result:
            with ctx["put_collapse"]("📖 代码说明和验证结果", open=False):
                if review_result.validation_result.get("success"):
                    ctx["put_success"]("✅ 代码验证通过")
                else:
                    ctx["put_error"](f"❌ 代码验证失败: {review_result.validation_result.get('error', '')}")
                
                warnings = review_result.validation_result.get("warnings", [])
                if warnings:
                    ctx["put_warning"](f"⚠️  发现 {len(warnings)} 个警告:")
                    for warning in warnings:
                        ctx["put_text"](f"   • {warning}")
        
        # 最终确认
        final_confirm = await ctx["input_group"]("代码确认", [
            ctx["checkbox"](
                "确认选项",
                name="code_confirmations",
                options=[
                    {"label": "我已审核生成的代码", "value": "reviewed", "selected": True},
                    {"label": "我理解代码的执行逻辑", "value": "understood", "selected": True},
                    {"label": "我确认使用此代码", "value": "approved", "selected": True}
                ]
            ),
            ctx["actions"]("操作", [
                {"label": "✅ 使用此代码", "value": "use_code", "color": "success"},
                {"label": "🔄 重新生成", "value": "regenerate", "color": "warning"},
                {"label": "❌ 取消", "value": "cancel", "color": "danger"}
            ], name="action")
        ])
        
        if not final_confirm or final_confirm.get("action") == "cancel":
            return ""
        
        if final_confirm.get("action") == "regenerate":
            return await _enhanced_task_ai_generation(ctx, basic_form)
        
        # 检查确认选项
        required_confirmations = ["reviewed", "approved"]
        selected_confirmations = final_confirm.get("code_confirmations", [])
        
        for req in required_confirmations:
            if req not in selected_confirmations:
                ctx["toast"]("请确认所有必要选项", color="warning")
                return await _enhanced_task_ai_generation(ctx, basic_form)
        
        return review_result.code
        
    except Exception as e:
        log.error(f"增强版AI任务代码生成错误: {e}")
        ctx["toast"](f"AI代码生成错误: {e}", color="error")
        return ""


async def _collect_enhanced_task_requirements(ctx, basic_form: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """收集增强版任务需求信息"""
    try:
        # 根据任务类型显示不同的配置选项
        task_type = basic_form.get("task_type", "interval")
        time_config = basic_form.get("time_config", "60")
        
        # 构建默认配置
        default_schedule_config = ""
        default_retry_config = ""
        
        if task_type == "interval":
            default_schedule_config = f"每{time_config}秒执行一次"
            default_retry_config = "失败后重试3次，间隔5分钟"
        elif task_type == "cron":
            default_schedule_config = f"每天{time_config}执行"
            default_retry_config = "失败后重试3次，间隔10分钟"
        elif task_type == "one_time":
            default_schedule_config = f"在{time_config}执行一次"
            default_retry_config = "失败后不重试"
        
        # 显示需求收集表单
        requirement_form = await ctx["input_group"]("任务需求配置", [
            ctx["textarea"](
                "任务需求描述",
                name="requirement",
                placeholder="请详细描述您的任务需求，例如：\n- 每天凌晨2点备份数据库\n- 包含数据导出和文件压缩\n- 完成后发送通知邮件",
                rows=4,
                required=True,
                value=f"为任务'{basic_form.get('name', '')}'生成执行函数" if basic_form.get('name') else ""
            ),
            ctx["textarea"](
                "执行时间配置",
                name="schedule_config",
                placeholder="根据任务类型填写：\n- 间隔任务：间隔秒数(如3600)\n- 定时任务：时间HH:MM(如02:00)\n- 一次性任务：具体日期时间",
                rows=2,
                help_text="设置任务的执行时间或间隔",
                value=default_schedule_config
            ),
            ctx["textarea"](
                "失败重试配置",
                name="retry_config",
                placeholder="失败后重试次数和间隔，例如：\n- 重试3次，间隔5分钟\n- 重试5次，间隔10分钟\n- 不重试",
                rows=2,
                help_text="设置任务失败后的重试策略",
                value=default_retry_config
            ),
            ctx["checkbox"](
                "任务选项",
                name="task_options",
                options=[
                    {"label": "失败后重试", "value": "enable_retry", "selected": True},
                    {"label": "发送执行通知", "value": "send_notification", "selected": False},
                    {"label": "记录详细日志", "value": "detailed_logging", "selected": True},
                    {"label": "记录执行历史", "value": "record_history", "selected": True}
                ]
            ),
            ctx["textarea"](
                "特殊要求或约束",
                name="constraints",
                placeholder="任何特殊要求或约束条件，例如：\n- 需要考虑网络超时\n- 处理大文件时需要分块\n- 避免重复执行",
                rows=2
            )
        ])
        
        return requirement_form
        
    except Exception as e:
        log.error(f"收集增强版任务需求错误: {e}")
        return None


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
        
        # 解析时间配置
        schedule_config = {}
        time_config = basic_form.get("time_config", "60")
        
        if basic_form.get("task_type") == "interval":
            schedule_config["interval"] = int(time_config)
        elif basic_form.get("task_type") == "cron":
            # 解析时间格式 HH:MM
            if ":" in time_config:
                hour, minute = time_config.split(":")
                schedule_config["hour"] = int(hour)
                schedule_config["minute"] = int(minute)
            else:
                schedule_config["hour"] = 0
                schedule_config["minute"] = int(time_config)
        elif basic_form.get("task_type") == "one_time":
            # 一次性任务的时间配置
            schedule_config["run_date"] = time_config
        
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
        log.error(f"创建增强版任务错误: {e}")
        ctx["toast"](f"创建任务错误: {e}", color="error")


async def show_enhanced_edit_task_dialog(ctx, task_name: str):
    """增强版编辑任务对话框 - 集成AI代码生成功能"""
    try:
        from pywebio import output as pw_output
        from pywebio import input as pw_input
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
        
        with ctx["popup"](f"编辑任务: {task_unit.name} (AI增强版)", size="large", closable=True):
            ctx["put_markdown"](f"### 编辑任务: {task_unit.name}")
            ctx["put_html"]("""
            <div style='background:#e3f2fd;padding:12px;border-radius:8px;margin-bottom:15px;'>
                <p style='color:#1565c0;font-size:14px;margin:0;'>
                    💡 <strong>AI代码生成</strong>：点击「AI生成」按钮，由AI根据需求描述自动生成任务代码
                </p>
                <p style='color:#1565c0;font-size:12px;margin:5px 0 0 0;'>
                    📝 <strong>代码审核</strong>：生成的代码需要您的审核和编辑确认
                </p>
            </div>
            """)
            
            # 基础信息编辑
            basic_form = await ctx["input_group"]("基础信息", [
                ctx["input"]("任务名称", name="name", required=True, value=task_unit.name),
                ctx["select"](
                    "任务类型",
                    name="task_type",
                    options=[
                        {"label": "间隔任务（每隔X秒执行）", "value": "interval"},
                        {"label": "定时任务（每天固定时间执行）", "value": "cron"},
                        {"label": "一次性任务（指定时间执行）", "value": "one_time"}
                    ],
                    value=task_unit.metadata.task_type.value
                ),
                ctx["textarea"]("任务描述", name="description", placeholder="任务描述（可选）", 
                               rows=2, value=task_unit.metadata.description or ""),
                ctx["input"]("执行时间配置", name="time_config", 
                           value=str(task_unit.metadata.schedule_config.get("interval", 60)) if task_unit.metadata.task_type == TaskType.INTERVAL else "02:00",
                           help_text="根据任务类型设置执行时间或间隔")
            ])
            
            if not basic_form:
                ctx["close_popup"]()
                return
            
            # 代码编辑选项
            ctx["put_markdown"]("### 代码编辑选项")
            
            # 显示当前代码
            current_code = task_unit.metadata.func_code or ""
            if current_code:
                with ctx["put_collapse"]("📋 当前代码", open=False):
                    ctx["put_code"](current_code, language="python")
            
            code_edit_method = await ctx["radio"](
                "选择代码编辑方式",
                options=[
                    {"label": "🤖 AI智能生成 - 描述需求，AI自动生成代码", "value": "ai_generate"},
                    {"label": "✏️ 手动编辑 - 直接修改Python代码", "value": "manual_edit"},
                    {"label": "📋 从模板选择 - 选择预设代码模板", "value": "template_select"},
                    {"label": "📁 从文件导入 - 上传Python代码文件", "value": "file_import"},
                    {"label": "💾 保持现有代码 - 不修改代码", "value": "keep_existing"}
                ],
                value="keep_existing"
            )
            
            new_code = current_code
            
            if code_edit_method == "ai_generate":
                new_code = await _enhanced_task_ai_generation(ctx, basic_form)
            elif code_edit_method == "manual_edit":
                new_code = await _manual_task_code_edit(ctx, current_code)
            elif code_edit_method == "template_select":
                new_code = await _task_template_selection(ctx)
            elif code_edit_method == "file_import":
                new_code = await _task_file_import(ctx)
            
            if code_edit_method != "keep_existing" and not new_code:
                ctx["toast"]("代码编辑被取消", color="warning")
                return
            
            # 最终确认
            ctx["put_markdown"]("### 最终确认")
            ctx["put_info"](f"任务名称: {basic_form['name']}")
            ctx["put_info"](f"任务类型: {basic_form['task_type']}")
            
            if new_code != current_code:
                ctx["put_info"](f"代码长度: {len(new_code)} 字符")
                with ctx["put_collapse"]("预览新代码", open=False):
                    ctx["put_code"](new_code, language="python")
            else:
                ctx["put_info"]("代码未修改")
            
            final_confirm = await ctx["input_group"]("确认编辑", [
                ctx["checkbox"](
                    "确认选项",
                    name="confirmations",
                    options=[
                        {"label": "我已审核代码修改", "value": "code_reviewed", "selected": True},
                        {"label": "我理解代码的执行逻辑", "value": "logic_understood", "selected": True},
                        {"label": "我确认保存修改", "value": "save_approved", "selected": True}
                    ]
                ),
                ctx["actions"]("操作", [
                    {"label": "✅ 保存修改", "value": "save", "color": "success"},
                    {"label": "❌ 取消", "value": "cancel", "color": "danger"}
                ], name="action")
            ])
            
            if not final_confirm or final_confirm.get("action") != "save":
                return
            
            # 检查确认选项
            required_confirmations = ["code_reviewed", "save_approved"]
            selected_confirmations = final_confirm.get("confirmations", [])
            
            for req in required_confirmations:
                if req not in selected_confirmations:
                    ctx["toast"]("请确认所有必要选项", color="warning")
                    return
            
            # 更新任务
            # 转换任务类型
            task_type_map = {
                "interval": TaskType.INTERVAL,
                "cron": TaskType.CRON,
                "one_time": TaskType.ONE_TIME
            }
            
            task_type = task_type_map.get(basic_form.get("task_type", "interval"), TaskType.INTERVAL)
            
            # 解析时间配置
            schedule_config = {}
            time_config = basic_form.get("time_config", "60")
            
            if basic_form.get("task_type") == "interval":
                schedule_config["interval"] = int(time_config)
            elif basic_form.get("task_type") == "cron":
                if ":" in time_config:
                    hour, minute = time_config.split(":")
                    schedule_config["hour"] = int(hour)
                    schedule_config["minute"] = int(minute)
                else:
                    schedule_config["hour"] = 0
                    schedule_config["minute"] = int(time_config)
            elif basic_form.get("task_type") == "one_time":
                schedule_config["run_date"] = time_config
            
            # 更新元数据
            task_unit.metadata.name = basic_form["name"]
            task_unit.metadata.description = basic_form.get("description", "")
            task_unit.metadata.task_type = task_type
            task_unit.metadata.schedule_config = schedule_config
            
            if new_code != current_code:
                task_unit.metadata.func_code = new_code
            
            # 保存修改
            task_unit.save()
            
            ctx["toast"]("任务修改保存成功", color="success")
            ctx["run_js"]("location.reload()")
            
    except Exception as e:
        log.error(f"增强版编辑任务对话框错误: {e}")
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