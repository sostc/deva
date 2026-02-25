"""增强版AI代码生成器(Enhanced AI Code Generator with User Review)

为策略、数据源和任务模块提供AI代码生成功能，包含用户审核和编辑界面。

================================================================================
功能特性
================================================================================

1. **AI代码生成**: 智能代码生成和分析
2. **用户审核界面**: 提供代码编辑框供用户审核修改
3. **代码验证**: 实时语法检查和安全性验证
4. **版本对比**: 显示生成代码与模板的差异
5. **交互式编辑**: 支持用户实时编辑和预览
6. **确认流程**: 用户确认后才进入后续流程
"""

from __future__ import annotations

import difflib
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable, Union

from deva import log

from .ai_code_generator import AICodeGenerator, StrategyAIGenerator, DataSourceAIGenerator, TaskAIGenerator
from .task_unit import TaskType


@dataclass
class CodeReviewResult:
    """代码审核结果"""
    approved: bool
    code: str
    user_modified: bool
    review_comments: str = ""
    original_code: str = ""
    validation_result: Dict[str, Any] = None


@dataclass
class CodeComparison:
    """代码对比信息"""
    original_lines: List[str]
    generated_lines: List[str]  
    diff_lines: List[str]
    similarity_ratio: float
    changes_summary: str


class InteractiveCodeGenerator:
    """交互式代码生成器
    
    提供AI代码生成和用户审核编辑的完整流程
    """
    
    def __init__(self, unit_type: str):
        """
        Args:
            unit_type: 单元类型 ("strategy", "datasource", "task")
        """
        self.unit_type = unit_type
        self.ai_generator = self._create_ai_generator(unit_type)
        self._review_callbacks: List[Callable[[str, str], str]] = []
    
    def _create_ai_generator(self, unit_type: str) -> AICodeGenerator:
        """创建AI生成器实例"""
        if unit_type == "strategy":
            return StrategyAIGenerator()
        elif unit_type == "datasource":
            return DataSourceAIGenerator()
        elif unit_type == "task":
            return TaskAIGenerator()
        else:
            raise ValueError(f"不支持的单元类型: {unit_type}")
    
    def add_review_callback(self, callback: Callable[[str, str], str]):
        """添加审核回调函数
        
        Args:
            callback: 回调函数，接收(生成的代码, 审核意见)参数，返回修改后的代码
        """
        self._review_callbacks.append(callback)
    
    # ==========================================================================
    # 主要交互流程
    # ==========================================================================
    
    async def generate_and_review(
        self,
        requirement: str,
        context: Dict[str, Any] = None,
        show_comparison: bool = True,
        enable_realtime_validation: bool = True,
        **kwargs
    ) -> CodeReviewResult:
        """生成代码并引导用户审核
        
        完整的交互式代码生成和审核流程：
        1. AI生成代码
        2. 显示代码和说明
        3. 提供编辑界面
        4. 实时验证
        5. 用户确认或重新生成
        
        Args:
            requirement: 需求描述
            context: 上下文信息
            show_comparison: 是否显示代码对比
            enable_realtime_validation: 是否启用实时验证
            **kwargs: 其他参数传递给AI生成器
            
        Returns:
            CodeReviewResult: 审核结果
        """
        try:
            # 第1步: AI生成代码
            log.info(f"开始AI代码生成: {self.unit_type}")
            generation_result = await self._generate_code(requirement, context, **kwargs)
            
            if not generation_result["success"]:
                return CodeReviewResult(
                    approved=False,
                    code="",
                    user_modified=False,
                    review_comments=f"代码生成失败: {generation_result['error']}"
                )
            
            original_code = generation_result["code"]
            explanation = generation_result.get("explanation", "")
            
            # 第2步: 准备审核界面
            review_context = {
                "requirement": requirement,
                "generated_code": original_code,
                "explanation": explanation,
                "unit_type": self.unit_type,
                "context": context,
                "generation_result": generation_result
            }
            
            # 第3步: 显示代码对比（可选）
            if show_comparison:
                comparison = self._generate_code_comparison(original_code, requirement)
                review_context["code_comparison"] = comparison
            
            # 第4步: 启动交互式审核流程
            review_result = await self._interactive_review_process(review_context, enable_realtime_validation)
            
            log.info(f"代码审核完成: approved={review_result.approved}, user_modified={review_result.user_modified}")
            return review_result
            
        except Exception as e:
            error_msg = f"交互式代码生成流程失败: {str(e)}"
            log.error(error_msg)
            return CodeReviewResult(
                approved=False,
                code="",
                user_modified=False,
                review_comments=error_msg
            )
    
    async def _generate_code(self, requirement: str, context: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        """生成代码"""
        try:
            if self.unit_type == "task":
                # 任务类型需要额外的参数
                task_type = kwargs.get("task_type", TaskType.INTERVAL)
                return self.ai_generator.generate_task_code(
                    requirement=requirement,
                    task_type=task_type,
                    context=context,
                    include_monitoring=kwargs.get("include_monitoring", True),
                    include_retry=kwargs.get("include_retry", True)
                )
            else:
                # 策略和数据源类型
                return self.ai_generator.generate_code(
                    requirement=requirement,
                    input_schema=kwargs.get("input_schema"),
                    output_schema=kwargs.get("output_schema"),
                    context=context
                )
        except Exception as e:
            log.error(f"AI代码生成失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
    
    async def _interactive_review_process(
        self, 
        review_context: Dict[str, Any], 
        enable_realtime_validation: bool
    ) -> CodeReviewResult:
        """交互式审核流程
        
        提供完整的用户交互界面，包括：
        - 代码展示和编辑
        - 实时验证
        - 确认/拒绝选项
        - 重新生成功能
        """
        
        current_code = review_context["generated_code"]
        user_comments = ""
        validation_result = None
        
        # 审核循环 - 用户可以多次修改和验证
        while True:
            try:
                # 显示审核界面
                review_ui = self._build_review_interface(review_context, current_code, user_comments, validation_result)
                
                # 获取用户输入
                user_input = await self._get_user_review_input(review_ui, enable_realtime_validation)
                
                if user_input["action"] == "approve":
                    # 用户确认通过
                    return CodeReviewResult(
                        approved=True,
                        code=current_code,
                        user_modified=current_code != review_context["generated_code"],
                        review_comments=user_comments,
                        original_code=review_context["generated_code"],
                        validation_result=validation_result
                    )
                    
                elif user_input["action"] == "reject":
                    # 用户拒绝
                    return CodeReviewResult(
                        approved=False,
                        code="",
                        user_modified=False,
                        review_comments=user_input.get("comments", "用户拒绝代码"),
                        original_code=review_context["generated_code"]
                    )
                    
                elif user_input["action"] == "edit":
                    # 用户编辑代码
                    current_code = user_input["edited_code"]
                    user_comments = user_input.get("comments", "")
                    
                    # 实时验证（如果启用）
                    if enable_realtime_validation:
                        validation_result = self._validate_user_code(current_code)
                    
                    # 运行审核回调
                    for callback in self._review_callbacks:
                        try:
                            current_code = callback(current_code, user_comments)
                        except Exception as e:
                            log.warning(f"审核回调执行失败: {e}")
                    
                elif user_input["action"] == "regenerate":
                    # 用户要求重新生成
                    regenerate_context = user_input.get("regenerate_context", {})
                    new_result = await self._generate_code(
                        review_context["requirement"], 
                        review_context["context"], 
                        **regenerate_context
                    )
                    
                    if new_result["success"]:
                        current_code = new_result["code"]
                        review_context["generated_code"] = current_code
                        review_context["explanation"] = new_result.get("explanation", "")
                        user_comments = f"重新生成: {user_input.get('comments', '')}"
                        validation_result = None  # 重置验证结果
                    else:
                        user_comments = f"重新生成失败: {new_result.get('error', '')}"
                
            except KeyboardInterrupt:
                # 用户取消
                return CodeReviewResult(
                    approved=False,
                    code="",
                    user_modified=False,
                    review_comments="用户取消审核"
                )
            except Exception as e:
                log.error(f"交互式审核流程错误: {e}")
                user_comments = f"审核流程错误: {str(e)}"
    
    # ==========================================================================
    # 审核界面构建
    # ==========================================================================
    
    def _build_review_interface(
        self, 
        review_context: Dict[str, Any],
        current_code: str,
        user_comments: str,
        validation_result: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """构建审核界面配置"""
        
        ui_config = {
            "title": f"AI代码生成审核 - {self.unit_type.title()}",
            "requirement": review_context["requirement"],
            "current_code": current_code,
            "original_code": review_context["generated_code"],
            "explanation": review_context["explanation"],
            "unit_type": self.unit_type,
            "validation_result": validation_result,
            "user_comments": user_comments,
            "show_comparison": "code_comparison" in review_context,
            "enable_validation": True
        }
        
        # 添加代码对比信息（如果有）
        if "code_comparison" in review_context:
            ui_config["code_comparison"] = review_context["code_comparison"]
        
        # 添加生成结果的其他信息
        if "generation_result" in review_context:
            gen_result = review_context["generation_result"]
            ui_config["requirement_analysis"] = gen_result.get("requirement_analysis", {})
            ui_config["prompt"] = gen_result.get("prompt", "")
        
        return ui_config
    
    async def _get_user_review_input(
        self, 
        ui_config: Dict[str, Any], 
        enable_realtime_validation: bool
    ) -> Dict[str, Any]:
        """获取用户审核输入
        
        这是一个模拟方法，实际实现需要集成具体的UI框架
        这里提供标准的输入格式和处理逻辑
        """
        
        # 这里应该集成实际的UI框架，比如PyWebIO、Streamlit等
        # 以下是标准输入格式的定义
        
        print(f"\n{'='*60}")
        print(f"🤖 AI代码生成审核 - {ui_config['unit_type'].title()}")
        print(f"{'='*60}")
        
        print(f"\n📋 需求描述:")
        print(f"{ui_config['requirement']}")
        
        print(f"\n📝 生成的代码:")
        print("-" * 40)
        print(ui_config['current_code'])
        print("-" * 40)
        
        if ui_config['explanation']:
            print(f"\n📖 代码说明:")
            print(ui_config['explanation'])
        
        # 显示验证结果
        if ui_config['validation_result']:
            self._display_validation_result(ui_config['validation_result'])
        
        # 显示代码对比（可选）
        if ui_config.get('show_comparison') and 'code_comparison' in ui_config:
            self._display_code_comparison(ui_config['code_comparison'])
        
        # 显示操作选项
        print(f"\n🔧 操作选项:")
        print("1. ✅ 确认通过 (approve)")
        print("2. ❌ 拒绝 (reject)")
        print("3. ✏️  编辑代码 (edit)")
        print("4. 🔄 重新生成 (regenerate)")
        print("5. 🛑 取消 (cancel)")
        
        # 模拟用户输入（实际应该通过UI获取）
        # 这里返回一个示例编辑操作
        return {
            "action": "edit",
            "edited_code": ui_config['current_code'],  # 用户编辑后的代码
            "comments": "用户审核意见：代码看起来不错，稍作修改"
        }
    
    def _display_validation_result(self, validation_result: Dict[str, Any]):
        """显示验证结果"""
        print(f"\n🔍 代码验证结果:")
        if validation_result.get("success"):
            print("✅ 代码验证通过")
            warnings = validation_result.get("warnings", [])
            if warnings:
                print(f"⚠️  警告 ({len(warnings)} 个):")
                for warning in warnings:
                    print(f"   - {warning}")
        else:
            print(f"❌ 代码验证失败: {validation_result.get('error', '未知错误')}")
    
    def _display_code_comparison(self, comparison: CodeComparison):
        """显示代码对比"""
        print(f"\n📊 代码对比分析:")
        print(f"相似度: {comparison.similarity_ratio:.1%}")
        print(f"变更摘要: {comparison.changes_summary}")
        
        if comparison.diff_lines:
            print(f"\n详细差异:")
            for line in comparison.diff_lines[:10]:  # 显示前10行差异
                print(line)
            if len(comparison.diff_lines) > 10:
                print(f"... 还有 {len(comparison.diff_lines) - 10} 行差异")
    
    # ==========================================================================
    # 代码验证和对比
    # ==========================================================================
    
    def _validate_user_code(self, code: str) -> Dict[str, Any]:
        """验证用户编辑的代码"""
        try:
            # 使用AI生成器的验证功能
            if self.unit_type == "task":
                # 任务类型需要额外的验证参数
                validation_result = self.ai_generator.validate_task_code(code, TaskType.INTERVAL)
            else:
                validation_result = self.ai_generator.validate_code(code)
            
            return validation_result
            
        except Exception as e:
            return {
                "success": False,
                "error": f"验证过程出错: {str(e)}",
                "traceback": traceback.format_exc()
            }
    
    def _generate_code_comparison(self, generated_code: str, requirement: str) -> CodeComparison:
        """生成代码对比信息"""
        try:
            # 获取基础模板作为对比基准
            if self.unit_type == "strategy":
                template = self.ai_generator._get_default_strategy_template()
            elif self.unit_type == "datasource":
                template = self.ai_generator._get_default_datasource_template()
            elif self.unit_type == "task":
                template = self.ai_generator._get_interval_task_template()
            else:
                template = ""
            
            # 分割成行进行对比
            template_lines = template.strip().split('\n')
            generated_lines = generated_code.strip().split('\n')
            
            # 计算相似度
            similarity = difflib.SequenceMatcher(None, template, generated_code).ratio()
            
            # 生成差异
            diff = difflib.unified_diff(
                template_lines, 
                generated_lines,
                fromfile='模板',
                tofile='生成代码',
                lineterm=''
            )
            diff_lines = list(diff)
            
            # 分析变更
            changes_summary = self._analyze_code_changes(template_lines, generated_lines)
            
            return CodeComparison(
                original_lines=template_lines,
                generated_lines=generated_lines,
                diff_lines=diff_lines,
                similarity_ratio=similarity,
                changes_summary=changes_summary
            )
            
        except Exception as e:
            log.error(f"代码对比生成失败: {e}")
            return CodeComparison(
                original_lines=[],
                generated_lines=generated_code.split('\n'),
                diff_lines=[],
                similarity_ratio=0.0,
                changes_summary="对比生成失败"
            )
    
    def _analyze_code_changes(self, original_lines: List[str], generated_lines: List[str]) -> str:
        """分析代码变更"""
        added_lines = len(generated_lines) - len(original_lines)
        
        if added_lines > 0:
            return f"增加了 {added_lines} 行代码，基于模板进行了功能扩展"
        elif added_lines < 0:
            return f"减少了 {abs(added_lines)} 行代码，进行了精简优化"
        else:
            return "代码行数相同，主要进行了逻辑实现"
    
    # ==========================================================================
    # 工具方法
    # ==========================================================================
    
    def get_generation_stats(self) -> Dict[str, Any]:
        """获取生成统计信息"""
        return {
            "unit_type": self.unit_type,
            "review_callbacks_count": len(self._review_callbacks),
            "ai_generator_type": type(self.ai_generator).__name__
        }


# ==========================================================================
# UI集成适配器
# ==========================================================================

class PyWebIOCodeReviewAdapter:
    """PyWebIO代码审核界面适配器
    
    为PyWebIO框架提供完整的代码审核界面
    """
    
    def __init__(self, interactive_generator: InteractiveCodeGenerator):
        self.generator = interactive_generator
    
    async def show_code_review_interface(self, ui_config: Dict[str, Any]) -> Dict[str, Any]:
        """显示PyWebIO代码审核界面
        
        这是一个完整的PyWebIO界面实现示例
        """
        try:
            from pywebio import input as pw_input
            from pywebio import output as pw_output
            from pywebio import session
            
            # 清空当前页面
            pw_output.clear()
            
            # 显示标题
            pw_output.put_markdown(f"# 🤖 AI代码生成审核 - {ui_config['unit_type'].title()}")
            
            # 显示需求描述
            with pw_output.put_collapse("📋 需求描述", open=True):
                pw_output.put_text(ui_config['requirement'])
            
            # 显示代码说明
            if ui_config['explanation']:
                with pw_output.put_collapse("📖 代码说明", open=False):
                    pw_output.put_markdown(ui_config['explanation'])
            
            # 显示验证结果
            if ui_config['validation_result']:
                self._show_validation_result(ui_config['validation_result'])
            
            # 显示代码编辑区域
            pw_output.put_markdown("## ✏️ 代码编辑")
            
            # 代码编辑器
            edited_code = await pw_input.textarea(
                "编辑代码",
                value=ui_config['current_code'],
                rows=20,
                code={"mode": "python", "theme": "monokai"},
                help_text="您可以在这里修改生成的代码，修改后的代码会自动验证"
            )
            
            # 用户评论
            user_comments = await pw_input.textarea(
                "审核意见 (可选)",
                placeholder="请输入您对代码的意见或修改说明...",
                value=ui_config['user_comments']
            )
            
            # 操作按钮
            pw_output.put_markdown("## 🔧 操作")
            
            # 创建按钮组
            buttons = [
                pw_input.actions(name="action", buttons=[
                    {"label": "✅ 确认通过", "value": "approve", "color": "success"},
                    {"label": "❌ 拒绝", "value": "reject", "color": "danger"},
                    {"label": "🔄 重新生成", "value": "regenerate", "color": "warning"},
                    {"label": "🛑 取消", "value": "cancel", "color": "secondary"}
                ])
            ]
            
            # 高级选项
            with pw_output.put_collapse("⚙️ 高级选项", open=False):
                # 重新生成参数
                regenerate_params = await pw_input.input_group("重新生成参数", [
                    pw_input.textarea(
                        "修改需求描述",
                        name="modified_requirement",
                        value=ui_config['requirement'],
                        help_text="如果需要重新生成，可以在这里修改需求描述"
                    ),
                    pw_input.checkbox(
                        "生成选项",
                        name="generation_options",
                        options=["包含监控代码", "包含重试逻辑", "使用高级模板"],
                        value=["包含监控代码", "包含重试逻辑"]
                    )
                ])
            
            # 获取用户操作
            action_result = await pw_input.input_group("选择操作", buttons)
            action = action_result["action"]
            
            # 构建返回结果
            result = {
                "action": action,
                "edited_code": edited_code,
                "comments": user_comments
            }
            
            # 添加重新生成参数
            if action == "regenerate":
                result["regenerate_context"] = {
                    "requirement": regenerate_params["modified_requirement"],
                    "include_monitoring": "包含监控代码" in regenerate_params["generation_options"],
                    "include_retry": "包含重试逻辑" in regenerate_params["generation_options"],
                    "use_advanced_template": "使用高级模板" in regenerate_params["generation_options"]
                }
            
            return result
            
        except ImportError:
            # PyWebIO未安装，返回模拟结果
            log.warning("PyWebIO未安装，使用模拟界面")
            return self._get_mock_review_input(ui_config)
        except Exception as e:
            log.error(f"PyWebIO界面显示失败: {e}")
            return self._get_mock_review_input(ui_config)
    
    def _show_validation_result(self, validation_result: Dict[str, Any]):
        """显示验证结果"""
        from pywebio import output as pw_output
        
        if validation_result.get("success"):
            pw_output.put_success("✅ 代码验证通过")
            warnings = validation_result.get("warnings", [])
            if warnings:
                pw_output.put_warning(f"⚠️  警告 ({len(warnings)} 个):")
                for warning in warnings:
                    pw_output.put_text(f"   • {warning}")
        else:
            pw_output.put_error(f"❌ 代码验证失败: {validation_result.get('error', '未知错误')}")
    
    def _get_mock_review_input(self, ui_config: Dict[str, Any]) -> Dict[str, Any]:
        """获取模拟审核输入（用于测试）"""
        # 模拟用户编辑代码
        edited_code = ui_config["current_code"]
        
        # 模拟用户添加注释
        if "# 用户添加的注释" not in edited_code:
            edited_code = f"# 用户添加的注释\n{edited_code}"
        
        return {
            "action": "approve",
            "edited_code": edited_code,
            "comments": "用户审核通过，添加了必要的注释"
        }


# ==========================================================================
# 使用示例和集成指南
# ==========================================================================

async def demo_interactive_code_generation():
    """演示交互式代码生成"""
    
    print("=== 交互式AI代码生成演示 ===")
    
    # 创建交互式生成器
    generator = InteractiveCodeGenerator("task")
    
    # 添加审核回调
    def custom_review_callback(code: str, comments: str) -> str:
        """自定义审核回调"""
        # 可以在这里添加自定义的代码修改逻辑
        if "# TODO" not in code:
            code = f"# TODO: 请在这里添加具体的任务逻辑\n{code}"
        return code
    
    generator.add_review_callback(custom_review_callback)
    
    # 需求描述
    requirement = "创建一个定时任务，每天检查磁盘空间使用情况，如果使用率超过80%则发送钉钉通知"
    
    # 生成并审核代码
    review_result = await generator.generate_and_review(
        requirement=requirement,
        context={"monitoring_disk": "/", "threshold": 80},
        show_comparison=True,
        enable_realtime_validation=True,
        task_type=TaskType.CRON,
        include_monitoring=True,
        include_retry=True
    )
    
    # 显示审核结果
    print(f"\n📊 审核结果:")
    print(f"是否通过: {review_result.approved}")
    print(f"用户是否修改: {review_result.user_modified}")
    print(f"审核意见: {review_result.review_comments}")
    
    if review_result.approved:
        print(f"\n📝 最终代码:")
        print("-" * 50)
        print(review_result.code)
        print("-" * 50)
        
        # 验证最终代码
        if review_result.validation_result:
            print(f"\n🔍 验证结果:")
            if review_result.validation_result.get("success"):
                print("✅ 最终代码验证通过")
            else:
                print(f"⚠️  最终代码验证警告: {review_result.validation_result.get('error', '')}")
    
    # 显示生成统计
    stats = generator.get_generation_stats()
    print(f"\n📈 生成统计: {stats}")


# 集成指南
"""
集成指南:

1. 基础集成:
   generator = InteractiveCodeGenerator("strategy")
   result = await generator.generate_and_review(requirement, context)

2. PyWebIO集成:
   adapter = PyWebIOCodeReviewAdapter(generator)
   ui_config = generator._build_review_interface(...)
   user_input = await adapter.show_code_review_interface(ui_config)

3. 自定义审核逻辑:
   def my_review_callback(code: str, comments: str) -> str:
       # 自定义代码修改逻辑
       return modified_code
   
   generator.add_review_callback(my_review_callback)

4. 批量处理:
   requirements = ["需求1", "需求2", "需求3"]
   results = []
   for req in requirements:
       result = await generator.generate_and_review(req, context)
       results.append(result)
"""

if __name__ == "__main__":
    # 运行演示
    import asyncio
    asyncio.run(demo_interactive_code_generation())