"""AI代码生成UI集成示例(AI Code Generation UI Integration Example)

展示如何在策略、数据源和任务模块中集成交互式AI代码生成功能。
"""

from __future__ import annotations

import asyncio
from typing import Dict, Any, Optional

from deva import log

from .interactive_ai_code_generator import InteractiveCodeGenerator, PyWebIOCodeReviewAdapter, CodeReviewResult
from .task_unit import TaskType
from .task_manager import get_task_manager
from .strategy_manager import get_manager as get_strategy_manager
from .datasource import get_ds_manager


class AICodeGenerationUI:
    """AI代码生成UI集成类
    
    为策略、数据源和任务模块提供统一的AI代码生成界面
    """
    
    def __init__(self):
        self.generators = {
            "strategy": InteractiveCodeGenerator("strategy"),
            "datasource": InteractiveCodeGenerator("datasource"), 
            "task": InteractiveCodeGenerator("task")
        }
        self.adapters = {
            unit_type: PyWebIOCodeReviewAdapter(generator)
            for unit_type, generator in self.generators.items()
        }
    
    # ==========================================================================
    # 策略模块AI代码生成
    # ==========================================================================
    
    async def show_strategy_code_generation(self, ctx: Dict[str, Any]):
        """显示策略代码生成界面"""
        try:
            from pywebio import output as pw_output
            from pywebio import input as pw_input
            from pywebio import pin
            
            # 清空页面
            pw_output.clear()
            
            # 显示标题
            pw_output.put_markdown("## 🤖 AI策略代码生成器")
            pw_output.put_text("使用AI智能生成策略处理函数代码")
            
            # 获取用户输入
            user_input = await pw_input.input_group("策略需求描述", [
                pw_input.textarea(
                    "需求描述",
                    name="requirement",
                    placeholder="请输入您的策略需求，例如：计算移动平均并生成交易信号",
                    rows=3,
                    required=True
                ),
                pw_input.textarea(
                    "输入数据示例 (可选)",
                    name="input_data_example",
                    placeholder="如果需要，可以提供输入数据的示例或描述",
                    rows=2
                ),
                pw_input.textarea(
                    "期望输出格式 (可选)",
                    name="output_format",
                    placeholder="描述期望的输出格式，例如：包含买卖信号的DataFrame",
                    rows=2
                ),
                pw_input.checkbox(
                    "生成选项",
                    name="generation_options",
                    options=[
                        {"label": "包含详细注释", "value": "include_comments", "selected": True},
                        {"label": "包含错误处理", "value": "include_error_handling", "selected": True},
                        {"label": "包含性能优化", "value": "include_optimization", "selected": False}
                    ]
                )
            ])
            
            if not user_input:
                return None
            
            # 构建上下文
            context = {
                "input_data_example": user_input.get("input_data_example", ""),
                "output_format": user_input.get("output_format", ""),
                "generation_options": user_input.get("generation_options", [])
            }
            
            # 生成并审核代码
            generator = self.generators["strategy"]
            review_result = await generator.generate_and_review(
                requirement=user_input["requirement"],
                context=context,
                show_comparison=True,
                enable_realtime_validation=True,
                input_schema=None,  # 可以添加数据结构分析
                output_schema=None,
                include_comments="include_comments" in user_input["generation_options"],
                include_error_handling="include_error_handling" in user_input["generation_options"],
                include_optimization="include_optimization" in user_input["generation_options"]
            )
            
            # 处理审核结果
            return await self._handle_code_review_result(review_result, "strategy", ctx)
            
        except Exception as e:
            log.error(f"策略代码生成界面错误: {e}")
            pw_output.put_error(f"界面错误: {str(e)}")
            return None
    
    # ==========================================================================
    # 数据源模块AI代码生成
    # ==========================================================================
    
    async def show_datasource_code_generation(self, ctx: Dict[str, Any]):
        """显示数据源代码生成界面"""
        try:
            from pywebio import output as pw_output
            from pywebio import input as pw_input
            
            # 清空页面
            pw_output.clear()
            
            # 显示标题
            pw_output.put_markdown("## 🤖 AI数据源代码生成器")
            pw_output.put_text("使用AI智能生成数据源获取函数代码")
            
            # 数据源类型选择
            user_input = await pw_input.input_group("数据源配置", [
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
                    "数据格式要求 (可选)",
                    name="data_format",
                    placeholder="描述期望的数据格式，例如：返回包含温度、湿度、风速的DataFrame",
                    rows=2
                ),
                pw_input.textarea(
                    "更新频率",
                    name="update_frequency",
                    placeholder="例如：每5分钟更新一次",
                    rows=1
                )
            ])
            
            if not user_input:
                return None
            
            # 构建上下文
            context = {
                "datasource_type": user_input["datasource_type"],
                "data_format": user_input.get("data_format", ""),
                "update_frequency": user_input.get("update_frequency", ""),
                "generation_options": ["include_comments", "include_error_handling"]  # 默认选项
            }
            
            # 生成并审核代码
            generator = self.generators["datasource"]
            review_result = await generator.generate_and_review(
                requirement=user_input["requirement"],
                context=context,
                show_comparison=True,
                enable_realtime_validation=True
            )
            
            # 处理审核结果
            return await self._handle_code_review_result(review_result, "datasource", ctx)
            
        except Exception as e:
            log.error(f"数据源代码生成界面错误: {e}")
            pw_output.put_error(f"界面错误: {str(e)}")
            return None
    
    # ==========================================================================
    # 任务模块AI代码生成
    # ==========================================================================
    
    async def show_task_code_generation(self, ctx: Dict[str, Any]):
        """显示任务代码生成界面"""
        try:
            from pywebio import output as pw_output
            from pywebio import input as pw_input
            
            # 清空页面
            pw_output.clear()
            
            # 显示标题
            pw_output.put_markdown("## 🤖 AI任务代码生成器")
            pw_output.put_text("使用AI智能生成定时任务函数代码")
            
            # 获取用户输入
            user_input = await pw_input.input_group("任务配置", [
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
                    "重试配置 (可选)",
                    name="retry_config",
                    placeholder="失败后重试次数和间隔，例如：重试3次，间隔5分钟",
                    rows=1
                ),
                pw_input.checkbox(
                    "任务选项",
                    name="task_options",
                    options=[
                        {"label": "失败后重试", "value": "enable_retry", "selected": True},
                        {"label": "发送执行通知", "value": "send_notification", "selected": False},
                        {"label": "记录详细日志", "value": "detailed_logging", "selected": True}
                    ]
                )
            ])
            
            if not user_input:
                return None
            
            # 转换任务类型
            task_type_map = {
                "interval": TaskType.INTERVAL,
                "cron": TaskType.CRON,
                "one_time": TaskType.ONE_TIME
            }
            task_type = task_type_map[user_input["task_type"]]
            
            # 构建上下文
            context = {
                "task_type": user_input["task_type"],
                "schedule_config": user_input.get("schedule_config", ""),
                "retry_config": user_input.get("retry_config", ""),
                "task_options": user_input.get("task_options", []),
                "enable_retry": "enable_retry" in user_input["task_options"],
                "send_notification": "send_notification" in user_input["task_options"],
                "detailed_logging": "detailed_logging" in user_input["task_options"]
            }
            
            # 生成并审核代码
            generator = self.generators["task"]
            review_result = await generator.generate_and_review(
                requirement=user_input["requirement"],
                context=context,
                show_comparison=True,
                enable_realtime_validation=True,
                task_type=task_type,
                include_monitoring=True,
                include_retry=context["enable_retry"]
            )
            
            # 处理审核结果
            return await self._handle_code_review_result(review_result, "task", ctx)
            
        except Exception as e:
            log.error(f"任务代码生成界面错误: {e}")
            pw_output.put_error(f"界面错误: {str(e)}")
            return None
    
    # ==========================================================================
    # 通用代码审核结果处理
    # ==========================================================================
    
    async def _handle_code_review_result(self, review_result: CodeReviewResult, unit_type: str, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理代码审核结果"""
        try:
            from pywebio import output as pw_output
            from pywebio import input as pw_input
            
            if not review_result.approved:
                # 用户拒绝或取消
                pw_output.put_warning("❌ 代码生成已取消")
                return None
            
            # 显示审核结果摘要
            pw_output.put_markdown("### 📊 代码生成结果摘要")
            
            result_info = [
                ["审核状态", "✅ 已通过" if review_result.approved else "❌ 已拒绝"],
                ["用户修改", "是" if review_result.user_modified else "否"],
                ["代码长度", f"{len(review_result.code)} 字符"],
                ["审核意见", review_result.review_comments or "无"]
            ]
            
            pw_output.put_table(result_info, header=["项目", "值"])
            
            # 显示最终代码
            with pw_output.put_collapse("📋 最终代码", open=True):
                pw_output.put_code(review_result.code, language="python")
            
            # 提供后续操作
            pw_output.put_markdown("### 🔧 后续操作")
            
            actions = await pw_input.input_group("选择操作", [
                pw_input.checkbox(
                    "操作选项",
                    name="actions",
                    options=[
                        {"label": "测试代码", "value": "test_code", "selected": True},
                        {"label": "保存到单元", "value": "save_to_unit", "selected": True},
                        {"label": "生成文档", "value": "generate_docs", "selected": False}
                    ]
                ),
                pw_input.textarea(
                    "备注 (可选)",
                    name="notes",
                    placeholder="添加关于此代码的备注信息...",
                    rows=2
                )
            ])
            
            # 返回处理结果
            return {
                "code": review_result.code,
                "unit_type": unit_type,
                "user_modified": review_result.user_modified,
                "review_comments": review_result.review_comments,
                "actions": actions["actions"],
                "notes": actions.get("notes", ""),
                "timestamp": ctx.get("current_time", "")
            }
            
        except Exception as e:
            log.error(f"处理代码审核结果错误: {e}")
            pw_output.put_error(f"处理结果时出错: {str(e)}")
            return None
    
    # ==========================================================================
    # 代码测试功能
    # ==========================================================================
    
    async def test_generated_code(self, code: str, unit_type: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """测试生成的代码"""
        try:
            from pywebio import output as pw_output
            
            pw_output.put_markdown("### 🧪 代码测试")
            pw_output.put_text("正在测试生成的代码...")
            
            test_result = {
                "syntax_check": False,
                "execution_test": False,
                "error": None,
                "execution_time": 0
            }
            
            # 语法检查
            try:
                import ast
                ast.parse(code)
                test_result["syntax_check"] = True
                pw_output.put_success("✅ 语法检查通过")
            except SyntaxError as e:
                test_result["error"] = f"语法错误: {e}"
                pw_output.put_error(f"❌ 语法错误: {e}")
                return test_result
            
            # 根据单元类型进行不同的测试
            if unit_type == "strategy":
                test_result = await self._test_strategy_code(code, ctx)
            elif unit_type == "datasource":
                test_result = await self._test_datasource_code(code, ctx)
            elif unit_type == "task":
                test_result = await self._test_task_code(code, ctx)
            
            return test_result
            
        except Exception as e:
            log.error(f"代码测试错误: {e}")
            return {"syntax_check": False, "execution_test": False, "error": str(e)}
    
    async def _test_strategy_code(self, code: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """测试策略代码"""
        import time
        from pywebio import output as pw_output
        
        test_result = {"syntax_check": True, "execution_test": False, "error": None, "execution_time": 0}
        
        try:
            start_time = time.time()
            
            # 创建测试环境
            test_env = {
                "pd": __import__("pandas"),
                "np": __import__("numpy"),
                "test_data": self._generate_test_dataframe()
            }
            
            # 执行代码
            local_vars = {}
            exec(code, test_env, local_vars)
            
            # 获取函数并测试
            if "process" in local_vars:
                process_func = local_vars["process"]
                result = process_func(test_env["test_data"])
                
                test_result["execution_test"] = True
                test_result["execution_time"] = time.time() - start_time
                
                pw_output.put_success(f"✅ 策略代码执行成功 (耗时: {test_result['execution_time']:.3f}s)")
                pw_output.put_text(f"返回结果类型: {type(result)}")
                
                if hasattr(result, 'shape'):
                    pw_output.put_text(f"结果形状: {result.shape}")
                
            else:
                test_result["error"] = "未找到process函数"
                pw_output.put_warning("⚠️  未找到process函数，请检查代码")
                
        except Exception as e:
            test_result["error"] = f"执行错误: {e}"
            pw_output.put_error(f"❌ 代码执行错误: {e}")
        
        return test_result
    
    async def _test_datasource_code(self, code: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """测试数据源代码"""
        import asyncio
        import time
        from pywebio import output as pw_output
        
        test_result = {"syntax_check": True, "execution_test": False, "error": None, "execution_time": 0}
        
        try:
            start_time = time.time()
            
            # 创建测试环境
            test_env = {
                "pd": __import__("pandas"),
                "np": __import__("numpy"),
                "asyncio": asyncio
            }
            
            # 执行代码
            local_vars = {}
            exec(code, test_env, local_vars)
            
            # 获取函数并测试
            if "fetch_data" in local_vars:
                fetch_func = local_vars["fetch_data"]
                
                # 异步执行
                if asyncio.iscoroutinefunction(fetch_func):
                    result = await fetch_func()
                else:
                    result = fetch_func()
                
                test_result["execution_test"] = True
                test_result["execution_time"] = time.time() - start_time
                
                pw_output.put_success(f"✅ 数据源代码执行成功 (耗时: {test_result['execution_time']:.3f}s)")
                pw_output.put_text(f"返回数据类型: {type(result)}")
                
                if hasattr(result, 'shape'):
                    pw_output.put_text(f"数据形状: {result.shape}")
                elif hasattr(result, '__len__'):
                    pw_output.put_text(f"数据长度: {len(result)}")
                
            else:
                test_result["error"] = "未找到fetch_data函数"
                pw_output.put_warning("⚠️  未找到fetch_data函数，请检查代码")
                
        except Exception as e:
            test_result["error"] = f"执行错误: {e}"
            pw_output.put_error(f"❌ 代码执行错误: {e}")
        
        return test_result
    
    async def _test_task_code(self, code: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """测试任务代码"""
        import asyncio
        import time
        from pywebio import output as pw_output
        
        test_result = {"syntax_check": True, "execution_test": False, "error": None, "execution_time": 0}
        
        try:
            start_time = time.time()
            
            # 创建测试环境
            test_env = {
                "asyncio": asyncio,
                "time": time,
                "datetime": __import__("datetime"),
                "log": log
            }
            
            # 执行代码
            local_vars = {}
            exec(code, test_env, local_vars)
            
            # 获取函数并测试
            if "execute" in local_vars:
                execute_func = local_vars["execute"]
                
                # 构建测试上下文
                test_context = {
                    "task_id": "test_task_001",
                    "task_name": "测试任务",
                    "retry_count": 0,
                    "retry_interval": 5
                }
                
                # 异步执行
                if asyncio.iscoroutinefunction(execute_func):
                    result = await execute_func(test_context)
                else:
                    result = execute_func(test_context)
                
                test_result["execution_test"] = True
                test_result["execution_time"] = time.time() - start_time
                
                pw_output.put_success(f"✅ 任务代码执行成功 (耗时: {test_result['execution_time']:.3f}s)")
                pw_output.put_text(f"返回结果: {result}")
                
            else:
                test_result["error"] = "未找到execute函数"
                pw_output.put_warning("⚠️  未找到execute函数，请检查代码")
                
        except Exception as e:
            test_result["error"] = f"执行错误: {e}"
            pw_output.put_error(f"❌ 代码执行错误: {e}")
        
        return test_result
    
    def _generate_test_dataframe(self) -> Any:
        """生成测试DataFrame"""
        import pandas as pd
        import numpy as np
        
        # 生成模拟股票数据
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        data = {
            'date': dates,
            'open': np.random.randn(100).cumsum() + 100,
            'high': np.random.randn(100).cumsum() + 102,
            'low': np.random.randn(100).cumsum() + 98,
            'close': np.random.randn(100).cumsum() + 100,
            'volume': np.random.randint(1000, 10000, 100)
        }
        
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        return df
    
    # ==========================================================================
    # 保存代码到单元
    # ==========================================================================
    
    async def save_code_to_unit(self, code: str, unit_type: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """保存代码到对应的单元"""
        try:
            from pywebio import output as pw_output
            from pywebio import input as pw_input
            
            pw_output.put_markdown("### 💾 保存代码到单元")
            
            # 获取单元信息
            unit_info = await pw_input.input_group("单元信息", [
                pw_input.text(
                    "单元名称",
                    name="unit_name",
                    placeholder="请输入单元名称",
                    required=True
                ),
                pw_input.textarea(
                    "单元描述",
                    name="unit_description",
                    placeholder="描述这个单元的功能...",
                    rows=2
                ),
                pw_input.text(
                    "标签 (逗号分隔)",
                    name="unit_tags",
                    placeholder="tag1, tag2, tag3"
                )
            ])
            
            if not unit_info:
                return {"success": False, "error": "用户取消保存"}
            
            # 根据单元类型保存到对应的管理器
            if unit_type == "strategy":
                return await self._save_to_strategy_manager(code, unit_info, ctx)
            elif unit_type == "datasource":
                return await self._save_to_datasource_manager(code, unit_info, ctx)
            elif unit_type == "task":
                return await self._save_to_task_manager(code, unit_info, ctx)
            else:
                return {"success": False, "error": f"不支持的单元类型: {unit_type}"}
                
        except Exception as e:
            log.error(f"保存代码到单元错误: {e}")
            return {"success": False, "error": str(e)}
    
    async def _save_to_strategy_manager(self, code: str, unit_info: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        """保存到策略管理器"""
        try:
            from pywebio import output as pw_output
            
            manager = get_strategy_manager()
            
            # 创建策略单元
            from .strategy_unit import StrategyUnit, StrategyMetadata, ExecutionState
            
            metadata = StrategyMetadata(
                id=f"ai_strategy_{unit_info['unit_name']}",
                name=unit_info["unit_name"],
                description=unit_info.get("unit_description", ""),
                tags=[tag.strip() for tag in unit_info.get("unit_tags", "").split(",") if tag.strip()]
            )
            
            state = ExecutionState()
            
            strategy_unit = StrategyUnit(
                metadata=metadata,
                state=state
            )
            
            # 设置代码
            result = strategy_unit.set_processor_from_code(code, "process")
            if not result["success"]:
                return {"success": False, "error": result["error"]}
            
            # 注册策略
            register_result = manager.register(strategy_unit)
            if register_result["success"]:
                pw_output.put_success(f"✅ 策略已保存: {unit_info['unit_name']}")
                return {"success": True, "unit_id": strategy_unit.id, "unit_name": strategy_unit.name}
            else:
                return {"success": False, "error": register_result.get("error", "注册失败")}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _save_to_datasource_manager(self, code: str, unit_info: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        """保存到数据源管理器"""
        try:
            from pywebio import output as pw_output
            
            manager = get_ds_manager()
            
            # 创建数据源单元
            from .datasource import DataSource, DataSourceMetadata, DataSourceState
            
            metadata = DataSourceMetadata(
                id=f"ai_datasource_{unit_info['unit_name']}",
                name=unit_info["unit_name"],
                description=unit_info.get("unit_description", ""),
                source_type="CUSTOM",
                data_func_code=code,
                tags=[tag.strip() for tag in unit_info.get("unit_tags", "").split(",") if tag.strip()]
            )
            
            state = DataSourceState()
            
            datasource = DataSource(
                metadata=metadata,
                state=state
            )
            
            # 注册数据源
            register_result = manager.register(datasource)
            if register_result["success"]:
                pw_output.put_success(f"✅ 数据源已保存: {unit_info['unit_name']}")
                return {"success": True, "unit_id": datasource.id, "unit_name": datasource.name}
            else:
                return {"success": False, "error": register_result.get("error", "注册失败")}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _save_to_task_manager(self, code: str, unit_info: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        """保存到任务管理器"""
        try:
            from pywebio import output as pw_output
            
            manager = get_task_manager()
            
            # 创建任务单元
            from .task_unit import TaskUnit, TaskMetadata, TaskState, TaskExecution
            
            metadata = TaskMetadata(
                id=f"ai_task_{unit_info['unit_name']}",
                name=unit_info["unit_name"],
                description=unit_info.get("unit_description", ""),
                task_type=TaskType.INTERVAL,  # 默认间隔任务
                func_code=code,
                tags=[tag.strip() for tag in unit_info.get("unit_tags", "").split(",") if tag.strip()]
            )
            
            state = TaskState()
            execution = TaskExecution(job_code=code)
            
            task_unit = TaskUnit(
                metadata=metadata,
                state=state,
                execution=execution
            )
            
            # 注册任务
            register_result = manager.register(task_unit)
            if register_result["success"]:
                pw_output.put_success(f"✅ 任务已保存: {unit_info['unit_name']}")
                return {"success": True, "unit_id": task_unit.id, "unit_name": task_unit.name}
            else:
                return {"success": False, "error": register_result.get("error", "注册失败")}
                
        except Exception as e:
            return {"success": False, "error": str(e)}


# 全局UI实例
_global_ai_ui: Optional[AICodeGenerationUI] = None


def get_ai_code_generation_ui() -> AICodeGenerationUI:
    """获取全局AI代码生成UI实例"""
    global _global_ai_ui
    if _global_ai_ui is None:
        _global_ai_ui = AICodeGenerationUI()
    return _global_ai_ui


# 使用示例
async def demo_ai_code_generation_ui():
    """演示AI代码生成UI"""
    ai_ui = get_ai_code_generation_ui()
    
    # 创建模拟上下文
    ctx = {
        "current_time": "2024-01-01 12:00:00",
        "global_ns": {}
    }
    
    # 演示策略代码生成
    print("=== 策略代码生成演示 ===")
    result = await ai_ui.show_strategy_code_generation(ctx)
    if result:
        print(f"生成成功: {result['unit_name']}")
    
    # 演示数据源代码生成
    print("\n=== 数据源代码生成演示 ===")
    result = await ai_ui.show_datasource_code_generation(ctx)
    if result:
        print(f"生成成功: {result['unit_name']}")
    
    # 演示任务代码生成
    print("\n=== 任务代码生成演示 ===")
    result = await ai_ui.show_task_code_generation(ctx)
    if result:
        print(f"生成成功: {result['unit_name']}")


if __name__ == "__main__":
    # 运行演示
    import asyncio
    asyncio.run(demo_ai_code_generation_ui())