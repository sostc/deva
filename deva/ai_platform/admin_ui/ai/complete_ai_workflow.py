"""AI代码生成集成示例(Complete AI Code Generation Integration Example)

展示如何在策略、数据源和任务模块中完整集成交互式AI代码生成功能。
"""

from __future__ import annotations

import asyncio
from typing import Dict, Any, Optional

from deva import log

from .ai_code_generation_ui import AICodeGenerationUI, get_ai_code_generation_ui
from .task_unit import TaskType
from .task_manager import get_task_manager
from .strategy_manager import get_strategy_manager
from .datasource import get_ds_manager


class CompleteAIGenerationWorkflow:
    """完整的AI代码生成工作流
    
    提供从需求输入到代码部署的完整流程
    """
    
    def __init__(self):
        self.ai_ui = get_ai_code_generation_ui()
        self.workflow_steps = {
            "input": "需求收集",
            "generation": "AI代码生成", 
            "review": "用户审核编辑",
            "validation": "代码验证测试",
            "deployment": "代码部署保存",
            "monitoring": "执行监控"
        }
    
    # ==========================================================================
    # 完整工作流 - 策略模块
    # ==========================================================================
    
    async def run_strategy_workflow(self, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """运行策略模块AI代码生成完整工作流"""
        try:
            from pywebio import output as pw_output
            from pywebio import input as pw_input
            
            # 步骤1: 显示工作流介绍
            pw_output.clear()
            pw_output.put_markdown("# 🚀 AI策略代码生成工作流")
            
            with pw_output.put_collapse("📋 工作流步骤", open=True):
                for step_key, step_name in self.workflow_steps.items():
                    pw_output.put_text(f"{step_key}. {step_name}")
            
            # 步骤2: 收集需求
            pw_output.put_markdown("## 步骤1: 需求收集")
            
            requirement_input = await self._collect_strategy_requirements(ctx)
            if not requirement_input:
                pw_output.put_warning("用户取消了需求收集")
                return None
            
            # 步骤3: AI代码生成和审核
            pw_output.put_markdown("## 步骤2: AI代码生成")
            
            code_result = await self.ai_ui.show_strategy_code_generation(ctx)
            if not code_result:
                pw_output.put_warning("用户取消了代码生成")
                return None
            
            # 步骤4: 代码验证和测试
            pw_output.put_markdown("## 步骤3: 代码验证测试")
            
            test_result = await self.ai_ui.test_generated_code(
                code=code_result["code"],
                unit_type="strategy",
                ctx=ctx
            )
            
            if test_result.get("error"):
                pw_output.put_error(f"代码测试失败: {test_result['error']}")
                # 提供重新生成的选项
                retry = await pw_input.actions("是否重新生成代码？", [
                    {"label": "重新生成", "value": "retry"},
                    {"label": "取消", "value": "cancel"}
                ])
                
                if retry == "retry":
                    return await self.run_strategy_workflow(ctx)
                else:
                    return None
            
            # 步骤5: 代码部署保存
            pw_output.put_markdown("## 步骤4: 代码部署保存")
            
            save_result = await self.ai_ui.save_code_to_unit(
                code=code_result["code"],
                unit_type="strategy",
                ctx=ctx
            )
            
            if not save_result["success"]:
                pw_output.put_error(f"代码保存失败: {save_result['error']}")
                return None
            
            # 步骤6: 执行监控设置
            pw_output.put_markdown("## 步骤5: 执行监控")
            
            await self._setup_strategy_monitoring(save_result, ctx)
            
            # 显示最终结果
            pw_output.put_success("🎉 策略代码生成工作流完成！")
            
            final_result = {
                "unit_type": "strategy",
                "unit_id": save_result["unit_id"],
                "unit_name": save_result["unit_name"],
                "code": code_result["code"],
                "test_result": test_result,
                "user_modified": code_result.get("user_modified", False),
                "review_comments": code_result.get("review_comments", "")
            }
            
            # 显示结果摘要
            self._display_workflow_summary(final_result)
            
            return final_result
            
        except Exception as e:
            log.error(f"策略工作流错误: {e}")
            pw_output.put_error(f"工作流执行错误: {str(e)}")
            return None
    
    # ==========================================================================
    # 完整工作流 - 数据源模块
    # ==========================================================================
    
    async def run_datasource_workflow(self, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """运行数据源模块AI代码生成完整工作流"""
        try:
            from pywebio import output as pw_output
            from pywebio import input as pw_input
            
            # 步骤1: 显示工作流介绍
            pw_output.clear()
            pw_output.put_markdown("# 🚀 AI数据源代码生成工作流")
            
            with pw_output.put_collapse("📋 工作流步骤", open=True):
                for step_key, step_name in self.workflow_steps.items():
                    pw_output.put_text(f"{step_key}. {step_name}")
            
            # 步骤2: 收集需求
            pw_output.put_markdown("## 步骤1: 数据源需求收集")
            
            requirement_input = await self._collect_datasource_requirements(ctx)
            if not requirement_input:
                pw_output.put_warning("用户取消了需求收集")
                return None
            
            # 步骤3: AI代码生成和审核
            pw_output.put_markdown("## 步骤2: AI代码生成")
            
            code_result = await self.ai_ui.show_datasource_code_generation(ctx)
            if not code_result:
                pw_output.put_warning("用户取消了代码生成")
                return None
            
            # 步骤4: 代码验证和测试
            pw_output.put_markdown("## 步骤3: 代码验证测试")
            
            test_result = await self.ai_ui.test_generated_code(
                code=code_result["code"],
                unit_type="datasource",
                ctx=ctx
            )
            
            if test_result.get("error"):
                pw_output.put_error(f"代码测试失败: {test_result['error']}")
                retry = await pw_input.actions("是否重新生成代码？", [
                    {"label": "重新生成", "value": "retry"},
                    {"label": "取消", "value": "cancel"}
                ])
                
                if retry == "retry":
                    return await self.run_datasource_workflow(ctx)
                else:
                    return None
            
            # 步骤5: 代码部署保存
            pw_output.put_markdown("## 步骤4: 代码部署保存")
            
            save_result = await self.ai_ui.save_code_to_unit(
                code=code_result["code"],
                unit_type="datasource",
                ctx=ctx
            )
            
            if not save_result["success"]:
                pw_output.put_error(f"代码保存失败: {save_result['error']}")
                return None
            
            # 步骤6: 连接测试
            pw_output.put_markdown("## 步骤5: 数据源连接测试")
            
            await self._test_datasource_connection(save_result, ctx)
            
            # 显示最终结果
            pw_output.put_success("🎉 数据源代码生成工作流完成！")
            
            final_result = {
                "unit_type": "datasource",
                "unit_id": save_result["unit_id"],
                "unit_name": save_result["unit_name"],
                "code": code_result["code"],
                "test_result": test_result,
                "user_modified": code_result.get("user_modified", False),
                "review_comments": code_result.get("review_comments", "")
            }
            
            self._display_workflow_summary(final_result)
            
            return final_result
            
        except Exception as e:
            log.error(f"数据源工作流错误: {e}")
            pw_output.put_error(f"工作流执行错误: {str(e)}")
            return None
    
    # ==========================================================================
    # 完整工作流 - 任务模块
    # ==========================================================================
    
    async def run_task_workflow(self, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """运行任务模块AI代码生成完整工作流"""
        try:
            from pywebio import output as pw_output
            from pywebio import input as pw_input
            
            # 步骤1: 显示工作流介绍
            pw_output.clear()
            pw_output.put_markdown("# 🚀 AI任务代码生成工作流")
            
            with pw_output.put_collapse("📋 工作流步骤", open=True):
                for step_key, step_name in self.workflow_steps.items():
                    pw_output.put_text(f"{step_key}. {step_name}")
            
            # 步骤2: 收集需求
            pw_output.put_markdown("## 步骤1: 任务需求收集")
            
            requirement_input = await self._collect_task_requirements(ctx)
            if not requirement_input:
                pw_output.put_warning("用户取消了需求收集")
                return None
            
            # 步骤3: AI代码生成和审核
            pw_output.put_markdown("## 步骤2: AI代码生成")
            
            code_result = await self.ai_ui.show_task_code_generation(ctx)
            if not code_result:
                pw_output.put_warning("用户取消了代码生成")
                return None
            
            # 步骤4: 代码验证和测试
            pw_output.put_markdown("## 步骤3: 代码验证测试")
            
            test_result = await self.ai_ui.test_generated_code(
                code=code_result["code"],
                unit_type="task",
                ctx=ctx
            )
            
            if test_result.get("error"):
                pw_output.put_error(f"代码测试失败: {test_result['error']}")
                retry = await pw_input.actions("是否重新生成代码？", [
                    {"label": "重新生成", "value": "retry"},
                    {"label": "取消", "value": "cancel"}
                ])
                
                if retry == "retry":
                    return await self.run_task_workflow(ctx)
                else:
                    return None
            
            # 步骤5: 代码部署保存
            pw_output.put_markdown("## 步骤4: 代码部署保存")
            
            save_result = await self.ai_ui.save_code_to_unit(
                code=code_result["code"],
                unit_type="task",
                ctx=ctx
            )
            
            if not save_result["success"]:
                pw_output.put_error(f"代码保存失败: {save_result['error']}")
                return None
            
            # 步骤6: 调度配置
            pw_output.put_markdown("## 步骤5: 调度配置")
            
            await self._setup_task_scheduling(save_result, ctx)
            
            # 显示最终结果
            pw_output.put_success("🎉 任务代码生成工作流完成！")
            
            final_result = {
                "unit_type": "task",
                "unit_id": save_result["unit_id"],
                "unit_name": save_result["unit_name"],
                "code": code_result["code"],
                "test_result": test_result,
                "user_modified": code_result.get("user_modified", False),
                "review_comments": code_result.get("review_comments", "")
            }
            
            self._display_workflow_summary(final_result)
            
            return final_result
            
        except Exception as e:
            log.error(f"任务工作流错误: {e}")
            pw_output.put_error(f"工作流执行错误: {str(e)}")
            return None
    
    # ==========================================================================
    # 需求收集辅助方法
    # ==========================================================================
    
    async def _collect_strategy_requirements(self, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """收集策略需求"""
        from pywebio import input as pw_input
        
        return await pw_input.input_group("策略需求配置", [
            pw_input.textarea(
                "策略需求描述",
                name="requirement",
                placeholder="请输入您的策略需求，例如：基于5日和20日均线交叉生成交易信号",
                rows=3,
                required=True
            ),
            pw_input.textarea(
                "输入数据说明",
                name="input_data",
                placeholder="描述输入数据，例如：包含开盘价、收盘价、最高价、最低价的股票数据",
                rows=2
            ),
            pw_input.textarea(
                "期望输出格式",
                name="output_format",
                placeholder="描述期望的输出格式，例如：包含买卖信号和时间戳的DataFrame",
                rows=2
            ),
            pw_input.checkbox(
                "生成选项",
                name="generation_options",
                options=[
                    {"label": "包含详细注释", "value": "comments", "selected": True},
                    {"label": "包含错误处理", "value": "error_handling", "selected": True},
                    {"label": "包含性能优化", "value": "optimization", "selected": False}
                ]
            )
        ])
    
    async def _collect_datasource_requirements(self, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """收集数据源需求"""
        from pywebio import input as pw_input
        
        return await pw_input.input_group("数据源需求配置", [
            pw_input.select(
                "数据源类型",
                name="datasource_type",
                options=[
                    {"label": "API接口", "value": "api"},
                    {"label": "数据库", "value": "database"},
                    {"label": "文件", "value": "file"},
                    {"label": "网页抓取", "value": "web_scraping"},
                    {"label": "自定义", "value": "custom"}
                ],
                value="api"
            ),
            pw_input.textarea(
                "数据源需求描述",
                name="requirement",
                placeholder="描述您需要获取的数据，例如：从天气API获取实时天气数据",
                rows=3,
                required=True
            ),
            pw_input.textarea(
                "数据更新频率",
                name="update_frequency",
                placeholder="例如：每5分钟更新一次，或每天更新一次",
                rows=1
            ),
            pw_input.textarea(
                "数据格式要求",
                name="data_format",
                placeholder="描述期望的数据格式，例如：返回包含温度、湿度、风速的DataFrame",
                rows=2
            )
        ])
    
    async def _collect_task_requirements(self, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """收集任务需求"""
        from pywebio import input as pw_input
        
        return await pw_input.input_group("任务需求配置", [
            pw_input.select(
                "任务类型",
                name="task_type",
                options=[
                    {"label": "间隔任务（每隔X秒执行）", "value": "interval"},
                    {"label": "定时任务（每天固定时间执行）", "value": "cron"},
                    {"label": "一次性任务（指定时间执行）", "value": "one_time"}
                ],
                value="interval"
            ),
            pw_input.textarea(
                "任务需求描述",
                name="requirement",
                placeholder="描述您的任务需求，例如：每天凌晨备份数据库",
                rows=3,
                required=True
            ),
            pw_input.textarea(
                "执行时间配置",
                name="schedule_config",
                placeholder="根据任务类型填写：间隔秒数(如60) 或 时间HH:MM(如02:00)",
                rows=1
            ),
            pw_input.textarea(
                "失败重试配置",
                name="retry_config",
                placeholder="失败后重试次数和间隔，例如：重试3次，间隔5分钟",
                rows=1
            )
        ])
    
    # ==========================================================================
    # 后续配置辅助方法
    # ==========================================================================
    
    async def _setup_strategy_monitoring(self, save_result: Dict[str, Any], ctx: Dict[str, Any]):
        """设置策略监控"""
        from pywebio import output as pw_output
        from pywebio import input as pw_input
        
        pw_output.put_info(f"正在为策略 '{save_result['unit_name']}' 设置监控...")
        
        # 获取策略管理器
        manager = get_strategy_manager()
        strategy = manager.get(save_result["unit_id"])
        
        if strategy:
            # 启动策略
            start_result = manager.start(save_result["unit_id"])
            if start_result["success"]:
                pw_output.put_success(f"✅ 策略已启动: {save_result['unit_name']}")
            else:
                pw_output.put_warning(f"⚠️  策略启动失败: {start_result.get('error', '未知错误')}")
        else:
            pw_output.put_error(f"❌ 策略未找到: {save_result['unit_id']}")
    
    async def _test_datasource_connection(self, save_result: Dict[str, Any], ctx: Dict[str, Any]):
        """测试数据源连接"""
        from pywebio import output as pw_output
        
        pw_output.put_info(f"正在测试数据源 '{save_result['unit_name']}' 连接...")
        
        # 获取数据源管理器
        manager = get_ds_manager()
        datasource = manager.get(save_result["unit_id"])
        
        if datasource:
            # 启动数据源
            start_result = manager.start(save_result["unit_id"])
            if start_result["success"]:
                pw_output.put_success(f"✅ 数据源已启动: {save_result['unit_name']}")
                
                # 等待数据获取
                await asyncio.sleep(3)
                
                # 检查数据获取情况
                if hasattr(datasource, 'state') and datasource.state:
                    pw_output.put_text(f"最后数据时间: {datasource.state.last_data_ts}")
                else:
                    pw_output.put_warning("⚠️  无法获取数据源状态")
            else:
                pw_output.put_warning(f"⚠️  数据源启动失败: {start_result.get('error', '未知错误')}")
        else:
            pw_output.put_error(f"❌ 数据源未找到: {save_result['unit_id']}")
    
    async def _setup_task_scheduling(self, save_result: Dict[str, Any], ctx: Dict[str, Any]):
        """设置任务调度"""
        from pywebio import output as pw_output
        
        pw_output.put_info(f"正在为任务 '{save_result['unit_name']}' 设置调度...")
        
        # 获取任务管理器
        manager = get_task_manager()
        task = manager.get(save_result["unit_id"])
        
        if task:
            # 启动任务
            start_result = manager.start(save_result["unit_id"])
            if start_result["success"]:
                pw_output.put_success(f"✅ 任务已启动并调度: {save_result['unit_name']}")
            else:
                pw_output.put_warning(f"⚠️  任务启动失败: {start_result.get('error', '未知错误')}")
        else:
            pw_output.put_error(f"❌ 任务未找到: {save_result['unit_id']}")
    
    # ==========================================================================
    # 结果显示辅助方法
    # ==========================================================================
    
    def _display_workflow_summary(self, result: Dict[str, Any]):
        """显示工作流摘要"""
        from pywebio import output as pw_output
        
        pw_output.put_markdown("### 📊 工作流完成摘要")
        
        summary_data = [
            ["单元类型", result["unit_type"].title()],
            ["单元名称", result["unit_name"]],
            ["单元ID", result["unit_id"]],
            ["用户修改", "是" if result.get("user_modified", False) else "否"],
            ["审核意见", result.get("review_comments", "无")],
            ["代码长度", f"{len(result['code'])} 字符"],
            ["测试状态", "通过" if not result["test_result"].get("error") else "失败"]
        ]
        
        pw_output.put_table(summary_data, header=["项目", "值"])
        
        # 显示代码预览
        with pw_output.put_collapse("📋 代码预览", open=False):
            pw_output.put_code(result["code"], language="python")
        
        # 后续操作建议
        pw_output.put_markdown("### 🔧 后续操作建议")
        pw_output.put_text("1. 监控单元运行状态")
        pw_output.put_text("2. 查看执行日志和统计")
        pw_output.put_text("3. 根据运行情况调整参数")
        pw_output.put_text("4. 设置告警和通知")


# ==========================================================================
# 使用示例和测试
# ==========================================================================

async def demo_complete_ai_workflow():
    """演示完整的AI代码生成工作流"""
    try:
        from pywebio import output as pw_output
        from pywebio import input as pw_input
        from pywebio import start_server
        
        # 创建工作流实例
        workflow = CompleteAIGenerationWorkflow()
        
        # 创建模拟上下文
        ctx = {
            "current_time": "2024-01-01 12:00:00",
            "global_ns": {},
            "log": log
        }
        
        # 显示主界面
        pw_output.clear()
        pw_output.put_markdown("# 🤖 AI代码生成工作流演示")
        pw_output.put_text("选择要演示的模块工作流:")
        
        # 选择工作流类型
        workflow_type = await pw_input.select(
            "选择工作流类型",
            options=[
                {"label": "策略代码生成工作流", "value": "strategy"},
                {"label": "数据源代码生成工作流", "value": "datasource"},
                {"label": "任务代码生成工作流", "value": "task"}
            ]
        )
        
        if workflow_type == "strategy":
            result = await workflow.run_strategy_workflow(ctx)
        elif workflow_type == "datasource":
            result = await workflow.run_datasource_workflow(ctx)
        elif workflow_type == "task":
            result = await workflow.run_task_workflow(ctx)
        else:
            pw_output.put_warning("未选择工作流类型")
            return
        
        if result:
            pw_output.put_success(f"🎉 {workflow_type.title()}工作流演示完成！")
            pw_output.put_text(f"生成的单元: {result['unit_name']} ({result['unit_id']})")
        else:
            pw_output.put_warning("工作流演示被取消或失败")
            
    except ImportError:
        print("PyWebIO未安装，无法运行完整演示")
        print("请安装: pip install pywebio")
    except Exception as e:
        print(f"演示错误: {e}")


# 简单的命令行演示
async def demo_simple_workflow():
    """简单的命令行演示"""
    print("=== AI代码生成工作流演示 ===")
    
    # 创建工作流实例
    workflow = CompleteAIGenerationWorkflow()
    
    # 创建模拟上下文
    ctx = {
        "current_time": "2024-01-01 12:00:00",
        "global_ns": {},
        "log": log
    }
    
    # 演示策略工作流
    print("\n1. 策略代码生成工作流")
    print("需求: 创建一个基于移动平均的策略")
    
    # 模拟需求输入
    mock_requirement = {
        "requirement": "创建一个基于5日和20日均线交叉的交易策略",
        "input_data": "股票历史价格数据，包含开盘价、收盘价、最高价、最低价",
        "output_format": "包含买卖信号和时间戳的DataFrame",
        "generation_options": ["comments", "error_handling"]
    }
    
    print(f"需求: {mock_requirement['requirement']}")
    print("正在生成代码...")
    
    # 这里应该调用完整的工作流，但简化演示
    print("✅ 策略代码生成完成")
    
    # 演示数据源工作流
    print("\n2. 数据源代码生成工作流")
    print("需求: 创建一个天气数据获取器")
    
    mock_datasource_requirement = {
        "datasource_type": "api",
        "requirement": "从天气API获取实时天气数据",
        "update_frequency": "每5分钟更新一次",
        "data_format": "包含温度、湿度、风速的DataFrame"
    }
    
    print(f"需求: {mock_datasource_requirement['requirement']}")
    print("正在生成代码...")
    print("✅ 数据源代码生成完成")
    
    # 演示任务工作流
    print("\n3. 任务代码生成工作流")
    print("需求: 创建一个数据库备份任务")
    
    mock_task_requirement = {
        "task_type": "cron",
        "requirement": "每天凌晨2点备份数据库",
        "schedule_config": "02:00",
        "retry_config": "重试3次，间隔5分钟"
    }
    
    print(f"需求: {mock_task_requirement['requirement']}")
    print("正在生成代码...")
    print("✅ 任务代码生成完成")
    
    print("\n=== 演示完成 ===")
    print("完整的工作流包含：")
    print("1. 需求收集和分析")
    print("2. AI代码生成")
    print("3. 用户审核编辑")
    print("4. 代码验证测试")
    print("5. 代码部署保存")
    print("6. 执行监控设置")


if __name__ == "__main__":
    # 运行简单演示
    import asyncio
    asyncio.run(demo_simple_workflow())