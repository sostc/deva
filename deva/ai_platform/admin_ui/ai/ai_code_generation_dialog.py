"""AI代码生成对话框集成(AI Code Generation Dialog Integration)

为策略、数据源和任务模块提供统一的AI代码生成对话框组件，
集成到现有的创建和编辑流程中。

================================================================================
功能特性
================================================================================

1. **统一对话框**: 为所有模块提供一致的AI代码生成界面
2. **智能集成**: 无缝集成到现有的创建编辑流程
3. **用户友好**: 直观的界面设计和操作流程
4. **实时验证**: 边编辑边验证代码质量
5. **一键部署**: 审核通过后直接部署到对应管理器
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime

from deva import log

from .interactive_ai_code_generator import InteractiveCodeGenerator, CodeReviewResult
from .ai_code_generation_ui import AICodeGenerationUI, get_ai_code_generation_ui
from ..tasks.task_unit import TaskType


class AICodeGenerationDialog:
    """AI代码生成对话框
    
    为策略、数据源和任务模块提供统一的AI代码生成界面
    """
    
    def __init__(self, unit_type: str, ctx: Dict[str, Any]):
        """
        Args:
            unit_type: 单元类型 ("strategy", "datasource", "task")
            ctx: 上下文对象，包含PyWebIO组件
        """
        self.unit_type = unit_type
        self.ctx = ctx
        self.ai_generator = InteractiveCodeGenerator(unit_type)
        self.ai_ui = get_ai_code_generation_ui()
    
    # ==========================================================================
    # 策略模块AI代码生成对话框
    # ==========================================================================
    
    async def show_strategy_ai_dialog(
        self,
        existing_code: str = "",
        strategy_name: str = "",
        bound_datasource: str = "",
        on_code_generated: Callable[[str], None] = None
    ) -> Optional[str]:
        """显示策略AI代码生成对话框
        
        Args:
            existing_code: 现有代码（编辑模式）
            strategy_name: 策略名称
            bound_datasource: 绑定的数据源名称
            on_code_generated: 代码生成后的回调函数
            
        Returns:
            生成的代码，如果用户取消则返回None
        """
        try:
            from pywebio import output as pw_output
            from pywebio import input as pw_input
            
            # 清空当前页面内容
            self.ctx["put_html"]("<div id='ai-dialog-container'></div>")
            
            # 显示对话框标题
            dialog_title = "🤖 AI策略代码生成器" if not existing_code else "🤖 AI策略代码编辑器"
            self.ctx["put_markdown"](f"### {dialog_title}")
            
            # 显示策略信息
            if strategy_name:
                self.ctx["put_info"](f"策略名称: {strategy_name}")
            if bound_datasource:
                self.ctx["put_info"](f"绑定数据源: {bound_datasource}")
            
            # 步骤1: 收集需求信息
            requirement_info = await self._collect_strategy_requirements(
                existing_code, strategy_name, bound_datasource
            )
            
            if not requirement_info:
                self.ctx["toast"]("用户取消了需求收集", color="warning")
                return None
            
            # 步骤2: 生成并审核代码
            self.ctx["put_markdown"]("### 步骤2: AI代码生成与审核")
            
            # 构建上下文
            context = {
                "strategy_name": strategy_name,
                "bound_datasource": bound_datasource,
                "input_data_example": requirement_info.get("input_data_example", ""),
                "output_format": requirement_info.get("output_format", ""),
                "generation_options": requirement_info.get("generation_options", [])
            }
            
            # 生成并审核代码
            review_result = await self.ai_generator.generate_and_review(
                requirement=requirement_info["requirement"],
                context=context,
                show_comparison=True,
                enable_realtime_validation=True,
                include_comments="include_comments" in requirement_info["generation_options"],
                include_error_handling="include_error_handling" in requirement_info["generation_options"],
                include_optimization="include_optimization" in requirement_info["generation_options"]
            )
            
            if not review_result.approved:
                self.ctx["toast"]("用户取消了代码生成", color="warning")
                return None
            
            # 步骤3: 代码验证和测试
            self.ctx["put_markdown"]("### 步骤3: 代码验证与测试")
            
            test_result = await self._test_generated_code(
                review_result.code, "strategy", context
            )
            
            if test_result.get("error") and not test_result.get("can_continue", False):
                retry = await self.ctx["actions"](
                    "代码测试失败，是否重新生成？",
                    [
                        {"label": "重新生成", "value": "retry"},
                        {"label": "使用当前代码", "value": "continue"},
                        {"label": "取消", "value": "cancel"}
                    ]
                )
                
                if retry == "retry":
                    return await self.show_strategy_ai_dialog(
                        existing_code, strategy_name, bound_datasource, on_code_generated
                    )
                elif retry == "cancel":
                    return None
            
            # 步骤4: 最终确认
            self.ctx["put_markdown"]("### 步骤4: 最终确认")
            
            final_confirmation = await self._show_final_confirmation(
                review_result, test_result, "strategy"
            )
            
            if not final_confirmation["confirmed"]:
                self.ctx["toast"]("用户取消了最终确认", color="warning")
                return None
            
            # 步骤5: 执行回调函数
            if on_code_generated:
                try:
                    on_code_generated(review_result.code)
                    self.ctx["toast"]("代码已成功生成并应用", color="success")
                except Exception as e:
                    self.ctx["toast"](f"代码应用失败: {e}", color="error")
                    return None
            
            return review_result.code
            
        except Exception as e:
            log.error(f"策略AI代码生成对话框错误: {e}")
            self.ctx["toast"](f"AI代码生成失败: {e}", color="error")
            return None
    
    async def _collect_strategy_requirements(
        self,
        existing_code: str = "",
        strategy_name: str = "",
        bound_datasource: str = ""
    ) -> Optional[Dict[str, Any]]:
        """收集策略需求信息"""
        try:
            # 显示需求收集表单
            requirement_form = await self.ctx["input_group"]("策略需求配置", [
                self.ctx["textarea"](
                    "策略需求描述",
                    name="requirement",
                    placeholder="请输入您的策略需求，例如：基于5日和20日均线交叉生成交易信号，当短期均线上穿长期均线时买入，下穿时卖出",
                    rows=3,
                    required=True,
                    value=f"为策略'{strategy_name}'生成处理函数" if strategy_name else ""
                ),
                self.ctx["textarea"](
                    "输入数据说明",
                    name="input_data_example",
                    placeholder="描述输入数据结构，例如：包含开盘价、收盘价、最高价、最低价、成交量的股票历史数据",
                    rows=2,
                    value=f"来自数据源'{bound_datasource}'的数据" if bound_datasource else ""
                ),
                self.ctx["textarea"](
                    "期望输出格式",
                    name="output_format",
                    placeholder="描述期望的输出格式，例如：返回包含买卖信号和时间戳的DataFrame，信号列包含1(买入)、-1(卖出)、0(持有)",
                    rows=2
                ),
                self.ctx["checkbox"](
                    "生成选项",
                    name="generation_options",
                    options=[
                        {"label": "包含详细注释", "value": "include_comments", "selected": True},
                        {"label": "包含错误处理", "value": "include_error_handling", "selected": True},
                        {"label": "包含性能优化", "value": "include_optimization", "selected": False}
                    ]
                ),
                self.ctx["textarea"](
                    "特殊要求 (可选)",
                    name="special_requirements",
                    placeholder="任何特殊要求或约束条件",
                    rows=2
                )
            ])
            
            return requirement_form
            
        except Exception as e:
            log.error(f"收集策略需求错误: {e}")
            return None
    
    # ==========================================================================
    # 数据源模块AI代码生成对话框
    # ==========================================================================
    
    async def show_datasource_ai_dialog(
        self,
        existing_code: str = "",
        datasource_name: str = "",
        datasource_type: str = "custom",
        on_code_generated: Callable[[str], None] = None
    ) -> Optional[str]:
        """显示数据源AI代码生成对话框
        
        Args:
            existing_code: 现有代码（编辑模式）
            datasource_name: 数据源名称
            datasource_type: 数据源类型
            on_code_generated: 代码生成后的回调函数
            
        Returns:
            生成的代码，如果用户取消则返回None
        """
        try:
            from pywebio import output as pw_output
            from pywebio import input as pw_input
            
            # 显示对话框标题
            dialog_title = "🤖 AI数据源代码生成器" if not existing_code else "🤖 AI数据源代码编辑器"
            self.ctx["put_markdown"](f"### {dialog_title}")
            
            # 显示数据源信息
            if datasource_name:
                self.ctx["put_info"](f"数据源名称: {datasource_name}")
            if datasource_type:
                self.ctx["put_info"](f"数据源类型: {datasource_type}")
            
            # 步骤1: 收集需求信息
            requirement_info = await self._collect_datasource_requirements(
                existing_code, datasource_name, datasource_type
            )
            
            if not requirement_info:
                self.ctx["toast"]("用户取消了需求收集", color="warning")
                return None
            
            # 步骤2: 生成并审核代码
            self.ctx["put_markdown"]("### 步骤2: AI代码生成与审核")
            
            # 构建上下文
            context = {
                "datasource_name": datasource_name,
                "datasource_type": datasource_type,
                "update_frequency": requirement_info.get("update_frequency", ""),
                "data_format": requirement_info.get("data_format", ""),
                "api_info": requirement_info.get("api_info", ""),
                "generation_options": requirement_info.get("generation_options", [])
            }
            
            # 生成并审核代码
            review_result = await self.ai_generator.generate_and_review(
                requirement=requirement_info["requirement"],
                context=context,
                show_comparison=True,
                enable_realtime_validation=True
            )
            
            if not review_result.approved:
                self.ctx["toast"]("用户取消了代码生成", color="warning")
                return None
            
            # 步骤3: 代码验证和测试
            self.ctx["put_markdown"]("### 步骤3: 代码验证与测试")
            
            test_result = await self._test_generated_code(
                review_result.code, "datasource", context
            )
            
            if test_result.get("error") and not test_result.get("can_continue", False):
                retry = await self.ctx["actions"](
                    "代码测试失败，是否重新生成？",
                    [
                        {"label": "重新生成", "value": "retry"},
                        {"label": "使用当前代码", "value": "continue"},
                        {"label": "取消", "value": "cancel"}
                    ]
                )
                
                if retry == "retry":
                    return await self.show_datasource_ai_dialog(
                        existing_code, datasource_name, datasource_type, on_code_generated
                    )
                elif retry == "cancel":
                    return None
            
            # 步骤4: 最终确认
            self.ctx["put_markdown"]("### 步骤4: 最终确认")
            
            final_confirmation = await self._show_final_confirmation(
                review_result, test_result, "datasource"
            )
            
            if not final_confirmation["confirmed"]:
                self.ctx["toast"]("用户取消了最终确认", color="warning")
                return None
            
            # 步骤5: 执行回调函数
            if on_code_generated:
                try:
                    on_code_generated(review_result.code)
                    self.ctx["toast"]("代码已成功生成并应用", color="success")
                except Exception as e:
                    self.ctx["toast"](f"代码应用失败: {e}", color="error")
                    return None
            
            return review_result.code
            
        except Exception as e:
            log.error(f"数据源AI代码生成对话框错误: {e}")
            self.ctx["toast"](f"AI代码生成失败: {e}", color="error")
            return None
    
    async def _collect_datasource_requirements(
        self,
        existing_code: str = "",
        datasource_name: str = "",
        datasource_type: str = "custom"
    ) -> Optional[Dict[str, Any]]:
        """收集数据源需求信息"""
        try:
            # 数据源类型选项
            datasource_type_options = [
                {"label": "API接口", "value": "api"},
                {"label": "数据库", "value": "database"},
                {"label": "文件", "value": "file"},
                {"label": "网页抓取", "value": "web_scraping"},
                {"label": "自定义", "value": "custom"}
            ]
            
            # 显示需求收集表单
            requirement_form = await self.ctx["input_group"]("数据源需求配置", [
                self.ctx["select"](
                    "数据源类型",
                    name="datasource_type",
                    options=datasource_type_options,
                    value=datasource_type,
                    help_text="选择数据源类型，AI将根据类型生成相应的代码"
                ),
                self.ctx["textarea"](
                    "数据源需求描述",
                    name="requirement",
                    placeholder="描述您需要获取的数据，例如：从天气API获取实时天气数据，包含温度、湿度、风速等信息",
                    rows=3,
                    required=True,
                    value=f"为数据源'{datasource_name}'生成数据获取函数" if datasource_name else ""
                ),
                self.ctx["textarea"](
                    "数据更新频率",
                    name="update_frequency",
                    placeholder="例如：每5分钟更新一次，或每天更新一次",
                    rows=1,
                    help_text="描述数据获取的频率要求"
                ),
                self.ctx["textarea"](
                    "数据格式要求",
                    name="data_format",
                    placeholder="描述期望的数据格式，例如：返回包含温度、湿度、风速的DataFrame",
                    rows=2
                ),
                self.ctx["textarea"](
                    "API信息 (如果适用)",
                    name="api_info",
                    placeholder="API地址、认证方式、请求参数等信息",
                    rows=2,
                    help_text="如果是API数据源，请提供相关信息"
                ),
                self.ctx["checkbox"](
                    "生成选项",
                    name="generation_options",
                    options=[
                        {"label": "包含错误处理", "value": "include_error_handling", "selected": True},
                        {"label": "包含重试机制", "value": "include_retry", "selected": True},
                        {"label": "包含数据验证", "value": "include_validation", "selected": True}
                    ]
                )
            ])
            
            return requirement_form
            
        except Exception as e:
            log.error(f"收集数据源需求错误: {e}")
            return None
    
    # ==========================================================================
    # 任务模块AI代码生成对话框
    # ==========================================================================
    
    async def show_task_ai_dialog(
        self,
        existing_code: str = "",
        task_name: str = "",
        task_type: str = "interval",
        on_code_generated: Callable[[str], None] = None
    ) -> Optional[str]:
        """显示任务AI代码生成对话框
        
        Args:
            existing_code: 现有代码（编辑模式）
            task_name: 任务名称
            task_type: 任务类型
            on_code_generated: 代码生成后的回调函数
            
        Returns:
            生成的代码，如果用户取消则返回None
        """
        try:
            from pywebio import output as pw_output
            from pywebio import input as pw_input
            
            # 显示对话框标题
            dialog_title = "🤖 AI任务代码生成器" if not existing_code else "🤖 AI任务代码编辑器"
            self.ctx["put_markdown"](f"### {dialog_title}")
            
            # 显示任务信息
            if task_name:
                self.ctx["put_info"](f"任务名称: {task_name}")
            if task_type:
                self.ctx["put_info"](f"任务类型: {task_type}")
            
            # 步骤1: 收集需求信息
            requirement_info = await self._collect_task_requirements(
                existing_code, task_name, task_type
            )
            
            if not requirement_info:
                self.ctx["toast"]("用户取消了需求收集", color="warning")
                return None
            
            # 步骤2: 生成并审核代码
            self.ctx["put_markdown"]("### 步骤2: AI代码生成与审核")
            
            # 构建上下文
            context = {
                "task_name": task_name,
                "task_type": task_type,
                "schedule_config": requirement_info.get("schedule_config", ""),
                "retry_config": requirement_info.get("retry_config", ""),
                "task_options": requirement_info.get("task_options", [])
            }
            
            # 转换任务类型
            task_type_map = {
                "interval": TaskType.INTERVAL,
                "cron": TaskType.CRON,
                "one_time": TaskType.ONE_TIME
            }
            
            # 生成并审核代码
            review_result = await self.ai_generator.generate_and_review(
                requirement=requirement_info["requirement"],
                context=context,
                show_comparison=True,
                enable_realtime_validation=True,
                task_type=task_type_map.get(task_type, TaskType.INTERVAL),
                include_monitoring=True,
                include_retry="enable_retry" in requirement_info["task_options"]
            )
            
            if not review_result.approved:
                self.ctx["toast"]("用户取消了代码生成", color="warning")
                return None
            
            # 步骤3: 代码验证和测试
            self.ctx["put_markdown"]("### 步骤3: 代码验证与测试")
            
            test_result = await self._test_generated_code(
                review_result.code, "task", context
            )
            
            if test_result.get("error") and not test_result.get("can_continue", False):
                retry = await self.ctx["actions"](
                    "代码测试失败，是否重新生成？",
                    [
                        {"label": "重新生成", "value": "retry"},
                        {"label": "使用当前代码", "value": "continue"},
                        {"label": "取消", "value": "cancel"}
                    ]
                )
                
                if retry == "retry":
                    return await self.show_task_ai_dialog(
                        existing_code, task_name, task_type, on_code_generated
                    )
                elif retry == "cancel":
                    return None
            
            # 步骤4: 最终确认
            self.ctx["put_markdown"]("### 步骤4: 最终确认")
            
            final_confirmation = await self._show_final_confirmation(
                review_result, test_result, "task"
            )
            
            if not final_confirmation["confirmed"]:
                self.ctx["toast"]("用户取消了最终确认", color="warning")
                return None
            
            # 步骤5: 执行回调函数
            if on_code_generated:
                try:
                    on_code_generated(review_result.code)
                    self.ctx["toast"]("代码已成功生成并应用", color="success")
                except Exception as e:
                    self.ctx["toast"](f"代码应用失败: {e}", color="error")
                    return None
            
            return review_result.code
            
        except Exception as e:
            log.error(f"任务AI代码生成对话框错误: {e}")
            self.ctx["toast"](f"AI代码生成失败: {e}", color="error")
            return None
    
    async def _collect_task_requirements(
        self,
        existing_code: str = "",
        task_name: str = "",
        task_type: str = "interval"
    ) -> Optional[Dict[str, Any]]:
        """收集任务需求信息"""
        try:
            # 任务类型选项
            task_type_options = [
                {"label": "间隔任务（每隔X秒执行）", "value": "interval"},
                {"label": "定时任务（每天固定时间执行）", "value": "cron"},
                {"label": "一次性任务（指定时间执行）", "value": "one_time"}
            ]
            
            # 显示需求收集表单
            requirement_form = await self.ctx["input_group"]("任务需求配置", [
                self.ctx["select"](
                    "任务类型",
                    name="task_type",
                    options=task_type_options,
                    value=task_type,
                    help_text="选择任务类型，AI将生成相应的调度代码"
                ),
                self.ctx["textarea"](
                    "任务需求描述",
                    name="requirement",
                    placeholder="描述您的任务需求，例如：每天凌晨2点备份数据库，包含数据导出和文件压缩",
                    rows=3,
                    required=True,
                    value=f"为任务'{task_name}'生成执行函数" if task_name else ""
                ),
                self.ctx["textarea"](
                    "执行时间配置",
                    name="schedule_config",
                    placeholder="根据任务类型填写：间隔秒数(如3600) 或 时间HH:MM(如02:00)",
                    rows=1,
                    help_text="设置任务的执行时间或间隔"
                ),
                self.ctx["textarea"](
                    "失败重试配置",
                    name="retry_config",
                    placeholder="失败后重试次数和间隔，例如：重试3次，间隔5分钟",
                    rows=1,
                    help_text="设置任务失败后的重试策略"
                ),
                self.ctx["checkbox"](
                    "任务选项",
                    name="task_options",
                    options=[
                        {"label": "失败后重试", "value": "enable_retry", "selected": True},
                        {"label": "发送执行通知", "value": "send_notification", "selected": False},
                        {"label": "记录详细日志", "value": "detailed_logging", "selected": True}
                    ]
                )
            ])
            
            return requirement_form
            
        except Exception as e:
            log.error(f"收集任务需求错误: {e}")
            return None
    
    # ==========================================================================
    # 通用辅助方法
    # ==========================================================================
    
    async def _test_generated_code(
        self,
        code: str,
        unit_type: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """测试生成的代码"""
        try:
            test_result = {
                "success": True,
                "error": None,
                "warnings": [],
                "can_continue": True,
                "test_duration": 0
            }
            
            import time
            start_time = time.time()
            
            # 使用AI UI的测试功能
            test_result = await self.ai_ui.test_generated_code(code, unit_type, context)
            
            test_result["test_duration"] = time.time() - start_time
            
            # 显示测试结果
            if test_result.get("syntax_check"):
                self.ctx["put_success"]("✅ 语法检查通过")
            else:
                self.ctx["put_error"]("❌ 语法检查失败")
            
            if test_result.get("execution_test"):
                self.ctx["put_success"](f"✅ 代码执行测试通过 (耗时: {test_result.get('execution_time', 0):.3f}s)")
            else:
                self.ctx["put_warning"]("⚠️ 代码执行测试未通过")
            
            # 显示警告信息
            warnings = test_result.get("warnings", [])
            if warnings:
                self.ctx["put_warning"](f"⚠️  发现 {len(warnings)} 个警告:")
                for warning in warnings:
                    self.ctx["put_text"](f"   • {warning}")
            
            return test_result
            
        except Exception as e:
            log.error(f"测试生成代码错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "can_continue": True,
                "test_duration": 0
            }
    
    async def _show_final_confirmation(
        self,
        review_result: CodeReviewResult,
        test_result: Dict[str, Any],
        unit_type: str
    ) -> Dict[str, Any]:
        """显示最终确认界面"""
        try:
            # 显示代码摘要
            self.ctx["put_markdown"]("#### 代码生成摘要")
            
            summary_data = [
                ["审核状态", "✅ 已通过"],
                ["用户修改", "是" if review_result.user_modified else "否"],
                ["代码长度", f"{len(review_result.code)} 字符"],
                ["审核意见", review_result.review_comments or "无"],
                ["测试状态", "通过" if test_result.get("execution_test") else "有警告"],
                ["测试耗时", f"{test_result.get('test_duration', 0):.3f}s"]
            ]
            
            self.ctx["put_table"](summary_data, header=["项目", "值"])
            
            # 显示代码预览
            with self.ctx["put_collapse"]("📋 最终代码预览", open=False):
                self.ctx["put_code"](review_result.code, language="python")
            
            # 显示最终确认选项
            confirmation = await self.ctx["input_group"]("最终确认", [
                self.ctx["checkbox"](
                    "确认选项",
                    name="confirmation_options",
                    options=[
                        {"label": "我已检查代码逻辑", "value": "checked_logic", "selected": True},
                        {"label": "我了解代码的执行环境", "value": "understand_env", "selected": True},
                        {"label": "我同意使用此代码", "value": "agree_to_use", "selected": True}
                    ]
                ),
                self.ctx["textarea"](
                    "备注 (可选)",
                    name="notes",
                    placeholder="添加关于此代码的任何备注信息",
                    rows=2
                ),
                self.ctx["actions"](
                    "确认操作",
                    [
                        {"label": "✅ 确认并应用代码", "value": "confirm", "color": "success"},
                        {"label": "❌ 取消", "value": "cancel", "color": "danger"}
                    ],
                    name="final_action"
                )
            ])
            
            if not confirmation or confirmation.get("final_action") != "confirm":
                return {"confirmed": False, "notes": ""}
            
            # 检查确认选项
            required_options = ["checked_logic", "agree_to_use"]
            selected_options = confirmation.get("confirmation_options", [])
            
            for option in required_options:
                if option not in selected_options:
                    self.ctx["toast"]("请确认所有必要选项", color="warning")
                    return await self._show_final_confirmation(review_result, test_result, unit_type)
            
            return {
                "confirmed": True,
                "notes": confirmation.get("notes", ""),
                "confirmation_options": selected_options
            }
            
        except Exception as e:
            log.error(f"显示最终确认界面错误: {e}")
            return {"confirmed": False, "notes": ""}
    
    # ==========================================================================
    # 工具方法
    # ==========================================================================
    
    def show_ai_help(self):
        """显示AI代码生成帮助信息"""
        help_content = f"""
        ### 🤖 AI代码生成器使用指南
        
        **{self.unit_type.title()}代码生成器**可以帮助您快速创建高质量的代码。
        
        #### 使用步骤：
        1. **描述需求** - 详细描述您的代码需求
        2. **设置选项** - 选择生成选项和特殊要求
        3. **AI生成** - AI根据需求生成代码
        4. **用户审核** - 审核和编辑生成的代码
        5. **代码测试** - 验证代码的正确性
        6. **最终确认** - 确认使用生成的代码
        
        #### 最佳实践：
        - 提供清晰、具体的需求描述
        - 说明输入数据的结构和格式
        - 描述期望的输出结果
        - 指定特殊要求或约束条件
        
        #### 安全提示：
        - AI生成的代码需要人工审核
        - 在生产环境使用前请充分测试
        - 注意代码中的潜在安全风险
        """
        
        self.ctx["put_markdown"](help_content)
    
    def get_dialog_stats(self) -> Dict[str, Any]:
        """获取对话框统计信息"""
        return {
            "unit_type": self.unit_type,
            "ai_generator_type": type(self.ai_generator).__name__,
            "has_ui_context": bool(self.ctx),
            "supported_features": [
                "requirement_collection",
                "ai_code_generation",
                "user_review_editing",
                "realtime_validation",
                "code_testing",
                "final_confirmation"
            ]
        }