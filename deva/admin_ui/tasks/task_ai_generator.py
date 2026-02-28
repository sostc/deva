"""任务AI代码生成器(Task AI Code Generator)

继承自AICodeGenerator，提供专门针对定时任务的AI代码生成能力。

================================================================================
功能特性
================================================================================

1. **任务特定模板**: 针对interval/cron/one_time任务类型的代码模板
2. **调度上下文**: 集成调度器上下文和任务生命周期管理
3. **错误重试**: 内置错误处理和重试机制
4. **流式集成**: 支持deva流式编程模型
5. **监控集成**: 集成任务执行监控和统计
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..ai.ai_code_generator import AICodeGenerator
from .task_unit import TaskType


class TaskAIGenerator(AICodeGenerator):
    """任务AI代码生成器
    
    专门为定时任务生成Python异步函数代码
    """
    
    def __init__(self):
        super().__init__("task")  # 设置为任务类型
        
        # 任务特定的代码模板
        self._task_templates = {
            TaskType.INTERVAL: self._get_interval_task_template(),
            TaskType.CRON: self._get_cron_task_template(),
            TaskType.ONE_TIME: self._get_one_time_task_template(),
        }
    
    # ==========================================================================
    # 任务特定代码生成方法
    # ==========================================================================
    
    def generate_task_code(
        self,
        requirement: str,
        task_type: TaskType,
        context: Dict[str, Any] = None,
        include_monitoring: bool = True,
        include_retry: bool = True
    ) -> Dict[str, Any]:
        """生成任务代码
        
        Args:
            requirement: 任务需求描述
            task_type: 任务类型
            context: 额外上下文
            include_monitoring: 是否包含监控代码
            include_retry: 是否包含重试逻辑
            
        Returns:
            {"success": bool, "code": str, "error": str, "explanation": str}
        """
        try:
            # 分析需求
            requirement_analysis = self._analyze_task_requirement(requirement)
            
            # 构建提示词
            prompt = self._build_task_generation_prompt(
                requirement, task_type, requirement_analysis, context
            )
            
            # 生成代码（这里可以集成真正的AI模型）
            # 目前使用模板生成
            code = self._generate_from_task_template(
                requirement, task_type, requirement_analysis, context, include_monitoring, include_retry
            )
            
            # 验证生成的代码
            validation_result = self.validate_code(code)
            if not validation_result["success"]:
                return {
                    "success": False,
                    "error": f"生成的任务代码验证失败: {validation_result['error']}",
                    "code": code
                }
            
            # 生成代码说明
            explanation = self._generate_task_explanation(code, requirement, task_type)
            
            return {
                "success": True,
                "code": code,
                "explanation": explanation,
                "prompt": prompt,
                "requirement_analysis": requirement_analysis
            }
            
        except Exception as e:
            error_msg = f"任务代码生成失败: {str(e)}"
            return {
                "success": False,
                "error": error_msg
            }
    
    def _analyze_task_requirement(self, requirement: str) -> Dict[str, Any]:
        """分析任务需求
        
        Args:
            requirement: 需求描述
            
        Returns:
            需求分析结果
        """
        requirement_lower = requirement.lower()
        
        analysis = {
            "primary_function": "general",  # 主要功能
            "data_operations": [],         # 数据操作类型
            "external_integrations": [],   # 外部集成
            "complexity_level": "simple",  # 复杂度级别
            "suggested_patterns": []      # 建议的设计模式
        }
        
        # 功能关键词分析
        function_keywords = {
            "抓取": "web_scraping",
            "爬取": "web_scraping", 
            "监控": "monitoring",
            "检查": "monitoring",
            "备份": "backup",
            "清理": "cleanup",
            "分析": "analysis",
            "统计": "statistics",
            "报告": "reporting",
            "通知": "notification",
            "提醒": "notification",
            "同步": "synchronization",
            "更新": "update",
            "维护": "maintenance"
        }
        
        for keyword, function in function_keywords.items():
            if keyword in requirement_lower:
                analysis["primary_function"] = function
                break
        
        # 数据操作分析
        data_operations = {
            "读取": "read",
            "写入": "write", 
            "处理": "process",
            "转换": "transform",
            "过滤": "filter",
            "排序": "sort",
            "聚合": "aggregate",
            "计算": "calculate"
        }
        
        for keyword, operation in data_operations.items():
            if keyword in requirement_lower:
                analysis["data_operations"].append(operation)
        
        # 外部集成分析
        integrations = {
            "钉钉": "dingtalk",
            "微信": "wechat", 
            "邮件": "email",
            "数据库": "database",
            "API": "api",
            "网页": "web",
            "文件": "file",
            "日志": "log"
        }
        
        for keyword, integration in integrations.items():
            if keyword in requirement_lower:
                analysis["external_integrations"].append(integration)
        
        # 复杂度分析
        complexity_indicators = {
            "简单": "simple",
            "基础": "simple", 
            "复杂": "complex",
            "高级": "complex",
            "多步骤": "complex",
            "多个": "complex"
        }
        
        for keyword, level in complexity_indicators.items():
            if keyword in requirement_lower:
                analysis["complexity_level"] = level
                break
        
        # 建议模式
        if analysis["primary_function"] == "web_scraping":
            analysis["suggested_patterns"] = ["error_handling", "retry_mechanism", "data_validation"]
        elif analysis["primary_function"] == "monitoring":
            analysis["suggested_patterns"] = ["threshold_checking", "alert_generation", "status_tracking"]
        elif "流" in requirement_lower:
            analysis["suggested_patterns"] = ["stream_processing", "real_time_handling"]
        
        return analysis
    
    def _build_task_generation_prompt(
        self,
        requirement: str,
        task_type: TaskType,
        requirement_analysis: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> str:
        """构建任务代码生成提示词"""
        prompt_parts = []
        
        # 基础说明
        prompt_parts.append("你是一个专业的Python定时任务开发专家。")
        prompt_parts.append("请根据需求生成一个高质量的异步任务函数。")
        prompt_parts.append("")
        
        # 任务类型特定要求
        if task_type == TaskType.INTERVAL:
            prompt_parts.append("【间隔任务要求】")
            prompt_parts.append("- 函数将每隔指定时间间隔执行")
            prompt_parts.append("- 需要考虑执行时间可能超过间隔的情况")
            prompt_parts.append("- 实现适当的并发控制")
            
        elif task_type == TaskType.CRON:
            prompt_parts.append("【定时任务要求】")
            prompt_parts.append("- 函数将在每天的固定时间执行")
            prompt_parts.append("- 考虑时区和夏令时的影响")
            prompt_parts.append("- 实现错过执行的补偿机制")
            
        elif task_type == TaskType.ONE_TIME:
            prompt_parts.append("【一次性任务要求】")
            prompt_parts.append("- 函数将在指定时间执行一次")
            prompt_parts.append("- 执行完成后任务自动完成")
            prompt_parts.append("- 不需要考虑重复执行的问题")
        
        prompt_parts.append("")
        
        # 需求分析结果
        prompt_parts.append("【需求分析结果】")
        prompt_parts.append(f"主要功能: {requirement_analysis['primary_function']}")
        prompt_parts.append(f"数据操作: {', '.join(requirement_analysis['data_operations'])}")
        prompt_parts.append(f"外部集成: {', '.join(requirement_analysis['external_integrations'])}")
        prompt_parts.append(f"复杂度级别: {requirement_analysis['complexity_level']}")
        prompt_parts.append(f"建议模式: {', '.join(requirement_analysis['suggested_patterns'])}")
        prompt_parts.append("")
        
        # 具体需求
        prompt_parts.append("【具体需求】")
        prompt_parts.append(f"任务描述: {requirement}")
        prompt_parts.append("")
        
        # 上下文信息
        if context:
            prompt_parts.append("【上下文信息】")
            for key, value in context.items():
                prompt_parts.append(f"{key}: {value}")
            prompt_parts.append("")
        
        # 技术要求
        prompt_parts.append("【技术要求】")
        prompt_parts.append("1. 函数签名: async def execute(context=None)")
        prompt_parts.append("2. 必须返回执行结果或状态信息")
        prompt_parts.append("3. 使用适当的错误处理和重试机制")
        prompt_parts.append("4. 充分利用deva的流式编程模型")
        prompt_parts.append("5. 添加详细的代码注释和文档字符串")
        prompt_parts.append("6. 考虑性能和资源使用优化")
        prompt_parts.append("7. 实现适当的日志记录")
        prompt_parts.append("")
        
        # deva核心功能
        prompt_parts.append("【可用的deva核心功能】")
        prompt_parts.append("- 日志记录: 'message' >> log")
        prompt_parts.append("- 文件操作: 'content' >> write_to_file('filename')")
        prompt_parts.append("- 网络请求: response = await httpx(url)")
        prompt_parts.append("- 数据流: 'data' >> bus")
        prompt_parts.append("- 钉钉通知: 'message' >> Dtalk()")
        prompt_parts.append("- 数据库流: db_stream = DBStream('name')")
        prompt_parts.append("- 文件日志流: file_stream = FileLogStream('app.log')")
        prompt_parts.append("- 流操作: stream.map(), stream.filter(), stream.reduce()")
        prompt_parts.append("")
        
        # 返回格式要求
        prompt_parts.append("【返回格式要求】")
        prompt_parts.append("- 只返回Python函数代码")
        prompt_parts.append("- 代码必须可以直接执行")
        prompt_parts.append("- 包含完整的错误处理")
        prompt_parts.append("- 添加适当的性能监控")
        
        return "\n".join(prompt_parts)
    
    def _generate_from_task_template(
        self,
        requirement: str,
        task_type: TaskType,
        requirement_analysis: Dict[str, Any],
        context: Dict[str, Any] = None,
        include_monitoring: bool = True,
        include_retry: bool = True
    ) -> str:
        """基于任务模板生成代码"""
        
        # 基础函数定义
        code_lines = []
        code_lines.append("async def execute(context=None):")
        code_lines.append('    """任务执行函数"""')
        code_lines.append("")
        
        # 导入语句
        code_lines.append("    # 标准库导入")
        code_lines.append("    import asyncio")
        code_lines.append("    import time")
        code_lines.append("    from datetime import datetime")
        code_lines.append("")
        
        # deva库导入
        code_lines.append("    # deva库导入")
        code_lines.append("    from deva import log, write_to_file, httpx, bus, Dtalk")
        code_lines.append("    from deva import DBStream, IndexStream, FileLogStream")
        code_lines.append("")
        
        # 上下文处理
        code_lines.append("    # 上下文处理")
        code_lines.append("    task_name = context.get('task_name', 'unknown') if context else 'unknown'")
        code_lines.append("    start_time = time.time()")
        code_lines.append("    ")
        
        # 主要逻辑
        code_lines.append("    try:")
        code_lines.append(f"        # 任务开始: {requirement[:50]}...")
        code_lines.append("        f'任务 {task_name} 开始执行' >> log")
        
        # 根据需求分析生成主要逻辑
        main_logic = self._generate_main_logic(requirement_analysis, include_monitoring)
        code_lines.extend(main_logic)
        
        # 结果处理
        code_lines.append("        ")
        code_lines.append("        # 执行成功")
        code_lines.append("        duration = time.time() - start_time")
        code_lines.append("        result = f'任务执行成功 (耗时: {duration:.2f}s)'")
        code_lines.append("        result >> log")
        code_lines.append("        return result")
        
        # 错误处理
        code_lines.append("        ")
        code_lines.append("    except Exception as e:")
        code_lines.append("        # 错误处理")
        code_lines.append("        duration = time.time() - start_time")
        code_lines.append("        error_msg = f'任务执行失败 (耗时: {duration:.2f}s): {e}'")
        code_lines.append("        error_msg >> log")
        
        if include_retry:
            code_lines.append("        # 重试逻辑")
            code_lines.append("        if context and context.get('retry_count', 0) > 0:")
            code_lines.append("            retry_info = f'将在 {context.get(\"retry_interval\", 5)} 秒后重试'")
            code_lines.append("            retry_info >> log")
        
        code_lines.append("        raise")
        
        return "\n".join(code_lines)
    
    def _generate_main_logic(self, requirement_analysis: Dict[str, Any], include_monitoring: bool) -> List[str]:
        """生成主要逻辑代码"""
        lines = []
        
        primary_function = requirement_analysis["primary_function"]
        data_operations = requirement_analysis["data_operations"]
        external_integrations = requirement_analysis["external_integrations"]
        
        # 监控代码（如果需要）
        if include_monitoring:
            lines.append("        ")
            lines.append("        # 性能监控")
            lines.append("        monitor_start = time.time()")
        
        # 根据主要功能生成代码
        if primary_function == "web_scraping":
            lines.extend(self._generate_web_scraping_logic(external_integrations))
        elif primary_function == "monitoring":
            lines.extend(self._generate_monitoring_logic(external_integrations))
        elif primary_function == "backup":
            lines.extend(self._generate_backup_logic(external_integrations))
        elif primary_function == "cleanup":
            lines.extend(self._generate_cleanup_logic(external_integrations))
        elif primary_function == "analysis":
            lines.extend(self._generate_analysis_logic(data_operations))
        else:
            lines.extend(self._generate_general_logic(external_integrations))
        
        # 监控结束（如果需要）
        if include_monitoring:
            lines.append("        ")
            lines.append("        # 监控结束")
            lines.append("        monitor_duration = time.time() - monitor_start")
            lines.append("        f'主要逻辑执行耗时: {monitor_duration:.2f}s' >> log")
        
        return lines
    
    def _generate_web_scraping_logic(self, integrations: List[str]) -> List[str]:
        """生成网页抓取逻辑"""
        lines = []
        
        lines.append("        # 网页抓取逻辑")
        lines.append("        url = 'https://example.com'  # 请替换为实际URL")
        lines.append("        '开始抓取网页...' >> log")
        
        if "api" in integrations:
            lines.append("        # API调用")
            lines.append("        response = await httpx(url)")
            lines.append("        if response.status_code == 200:")
            lines.append("            data = response.text")
            lines.append("            f'成功获取数据，大小: {len(data)} 字符' >> log")
            lines.append("            # 处理数据...")
            lines.append("            result = data[:100]  # 示例：返回前100字符")
            lines.append("        else:")
            lines.append("            f'请求失败，状态码: {response.status_code}' >> log")
            lines.append("            result = None")
        else:
            lines.append("        # 模拟数据获取")
            lines.append("        result = '模拟网页数据获取结果'")
            lines.append("        result >> log")
        
        return lines
    
    def _generate_monitoring_logic(self, integrations: List[str]) -> List[str]:
        """生成监控逻辑"""
        lines = []
        
        lines.append("        # 监控逻辑")
        lines.append("        '开始系统监控检查...' >> log")
        
        if "database" in integrations:
            lines.append("        # 数据库监控")
            lines.append("        db_stream = DBStream('monitoring')")
            lines.append("        # 检查数据库连接状态...")
            lines.append("        result = '数据库连接正常'")
        elif "file" in integrations:
            lines.append("        # 文件监控")
            lines.append("        import os")
            lines.append("        file_path = '/tmp/monitor.log'")
            lines.append("        if os.path.exists(file_path):")
            lines.append("            file_size = os.path.getsize(file_path)")
            lines.append("            result = f'文件存在，大小: {file_size} 字节'")
            lines.append("        else:")
            lines.append("            result = '文件不存在'")
        else:
            lines.append("        # 模拟监控检查")
            lines.append("        import random")
            lines.append("        status = random.choice(['正常', '警告', '异常'])")
            lines.append("        result = f'系统状态: {status}'")
        
        if "notification" in integrations:
            lines.append("        # 发送通知")
            lines.append("        if result:")
            lines.append("            notification_msg = f'监控结果: {result}'")
            lines.append("            notification_msg >> Dtalk()")
        
        return lines
    
    def _generate_backup_logic(self, integrations: List[str]) -> List[str]:
        """生成备份逻辑"""
        lines = []
        
        lines.append("        # 备份逻辑")
        lines.append("        '开始数据备份...' >> log")
        
        if "database" in integrations:
            lines.append("        # 数据库备份")
            lines.append("        backup_data = '模拟数据库备份数据'")
            lines.append("        backup_file = f'backup_{datetime.now().strftime(\"%Y%m%d_%H%M%S\")}.sql'")
            lines.append("        backup_data >> write_to_file(backup_file)")
            lines.append("        result = f'备份完成: {backup_file}'")
        else:
            lines.append("        # 文件备份")
            lines.append("        import os")
            lines.append("        source_file = '/tmp/source.txt'")
            lines.append("        if os.path.exists(source_file):")
            lines.append("            with open(source_file, 'r') as f:")
            lines.append("                content = f.read()")
            lines.append("            backup_file = f'backup_{os.path.basename(source_file)}'")
            lines.append("            content >> write_to_file(backup_file)")
            lines.append("            result = f'文件备份完成: {backup_file}'")
            lines.append("        else:")
            lines.append("            result = '源文件不存在'")
        
        return lines
    
    def _generate_cleanup_logic(self, integrations: List[str]) -> List[str]:
        """生成清理逻辑"""
        lines = []
        
        lines.append("        # 清理逻辑")
        lines.append("        '开始系统清理...' >> log")
        
        lines.append("        import os")
        lines.append("        import glob")
        lines.append("        ")
        lines.append("        # 清理临时文件")
        lines.append("        temp_files = glob.glob('/tmp/temp_*.txt')")
        lines.append("        deleted_count = 0")
        lines.append("        for file_path in temp_files:")
        lines.append("            try:")
        lines.append("                os.remove(file_path)")
        lines.append("                deleted_count += 1")
        lines.append("            except Exception as e:")
        lines.append("                f'删除文件失败: {file_path} - {e}' >> log")
        lines.append("        ")
        lines.append("        result = f'清理完成，删除 {deleted_count} 个文件'")
        
        return lines
    
    def _generate_analysis_logic(self, data_operations: List[str]) -> List[str]:
        """生成分析逻辑"""
        lines = []
        
        lines.append("        # 分析逻辑")
        lines.append("        '开始数据分析...' >> log")
        
        if "process" in data_operations or "calculate" in data_operations:
            lines.append("        # 数据处理")
            lines.append("        import pandas as pd")
            lines.append("        import numpy as np")
            lines.append("        ")
            lines.append("        # 模拟数据")
            lines.append("        data = pd.DataFrame({")
            lines.append("            'value': np.random.randn(100),")
            lines.append("            'timestamp': pd.date_range(start='2023-01-01', periods=100, freq='D')")
            lines.append("        })")
            lines.append("        ")
            lines.append("        # 数据分析")
            lines.append("        mean_value = data['value'].mean()")
            lines.append("        max_value = data['value'].max()")
            lines.append("        min_value = data['value'].min()")
            lines.append("        ")
            lines.append("        result = f'分析结果: 均值={mean_value:.2f}, 最大={max_value:.2f}, 最小={min_value:.2f}'")
        else:
            lines.append("        # 简单分析")
            lines.append("        import random")
            lines.append("        data = [random.randint(1, 100) for _ in range(10)]")
            lines.append("        result = f'数据分析: {len(data)} 个数据点'")
        
        return lines
    
    def _generate_general_logic(self, integrations: List[str]) -> List[str]:
        """生成通用逻辑"""
        lines = []
        
        lines.append("        # 通用任务逻辑")
        lines.append("        '开始执行任务...' >> log")
        
        if integrations:
            integration = integrations[0]
            if integration == "api":
                lines.append("        # API调用")
                lines.append("        '调用外部API...' >> log")
                lines.append("        result = 'API调用成功'")
            elif integration == "database":
                lines.append("        # 数据库操作")
                lines.append("        '执行数据库操作...' >> log")
                lines.append("        result = '数据库操作成功'")
            elif integration == "file":
                lines.append("        # 文件操作")
                lines.append("        '执行文件操作...' >> log")
                lines.append("        result = '文件操作成功'")
            else:
                lines.append("        # 默认操作")
                lines.append("        '执行默认任务...' >> log")
                lines.append("        result = '任务执行成功'")
        else:
            lines.append("        # 默认任务逻辑")
            lines.append("        import random")
            lines.append("        task_result = random.choice(['成功', '完成', '正常'])")
            lines.append("        result = f'任务执行{task_result}'")
        
        return lines
    
    def _generate_task_explanation(self, code: str, requirement: str, task_type: TaskType) -> str:
        """生成任务代码说明"""
        lines = []
        
        lines.append("## 任务代码说明")
        lines.append("")
        lines.append(f"**原始需求**: {requirement}")
        lines.append(f"**任务类型**: {task_type.value}")
        lines.append("")
        
        # 功能分析
        lines.append("**主要功能**:")
        if "网页" in requirement or "抓取" in requirement:
            lines.append("- 网页数据抓取和处理")
        elif "监控" in requirement:
            lines.append("- 系统状态监控和检查")
        elif "备份" in requirement:
            lines.append("- 数据备份和存档")
        elif "清理" in requirement:
            lines.append("- 系统清理和维护")
        elif "分析" in requirement:
            lines.append("- 数据分析和处理")
        else:
            lines.append("- 通用任务执行")
        
        # 技术特性
        lines.append("")
        lines.append("**技术特性**:")
        lines.append("- 异步函数设计，支持并发执行")
        lines.append("- 完整的错误处理和异常捕获")
        lines.append("- 详细的执行日志记录")
        lines.append("- 性能监控和执行时间统计")
        lines.append("- 与deva生态系统的深度集成")
        
        # 集成能力
        if "钉钉" in requirement:
            lines.append("- 钉钉通知集成")
        if "数据库" in requirement:
            lines.append("- 数据库操作支持")
        if "文件" in requirement:
            lines.append("- 文件系统操作")
        if "API" in requirement or "网页" in requirement:
            lines.append("- 网络请求和API调用")
        
        # 使用说明
        lines.append("")
        lines.append("**使用说明**:")
        lines.append("1. 此函数将被定时调度器调用")
        lines.append("2. 接收context参数，包含任务上下文信息")
        lines.append("3. 返回执行结果或状态信息")
        lines.append("4. 所有异常都会被捕获并记录")
        lines.append("5. 支持重试机制和失败恢复")
        
        return "\n".join(lines)
    
    # ==========================================================================
    # 任务特定验证方法
    # ==========================================================================
    
    def validate_task_code(self, code: str, task_type: TaskType) -> Dict[str, Any]:
        """验证任务代码
        
        Args:
            code: Python代码
            task_type: 任务类型
            
        Returns:
            {"success": bool, "error": str, "warnings": List[str]}
        """
        # 基础验证
        base_validation = self.validate_code(code)
        if not base_validation["success"]:
            return base_validation
        
        warnings = base_validation.get("warnings", []).copy()
        
        # 任务特定验证
        if task_type == TaskType.INTERVAL:
            # 间隔任务验证
            if "time.sleep" in code:
                warnings.append("间隔任务中不建议使用time.sleep()，可能影响调度精度")
            
            if "asyncio.sleep" in code and "context" not in code:
                warnings.append("建议通过context获取重试间隔配置")
        
        elif task_type == TaskType.CRON:
            # 定时任务验证
            if "datetime" not in code:
                warnings.append("定时任务建议使用datetime处理时间相关操作")
        
        # 通用任务验证
        if "execute" not in code:
            warnings.append("函数名应该是execute()")
        
        if "context" in code and "context.get" not in code:
            warnings.append("使用context时建议通过get()方法获取值，避免KeyError")
        
        if "except Exception" not in code:
            warnings.append("建议添加通用的异常捕获处理")
        
        return {
            "success": True,
            "warnings": warnings
        }
    
    # ==========================================================================
    # 任务特定模板
    # ==========================================================================
    
    def _get_interval_task_template(self) -> str:
        """获取间隔任务模板"""
        return '''async def execute(context=None):
    """间隔任务执行函数"""
    import asyncio
    import time
    from datetime import datetime
    from deva import log, write_to_file, httpx, bus, Dtalk
    
    # 获取任务信息
    task_name = context.get('task_name', 'unknown') if context else 'unknown'
    start_time = time.time()
    
    try:
        # 任务开始
        f'间隔任务 {task_name} 开始执行' >> log
        
        # TODO: 在这里实现具体的任务逻辑
        
        # 模拟工作
        await asyncio.sleep(1)
        result = f'间隔任务执行完成 (耗时: {time.time() - start_time:.2f}s)'
        
        # 记录成功
        result >> log
        return result
        
    except Exception as e:
        # 错误处理
        error_msg = f'间隔任务执行失败: {e}'
        error_msg >> log
        
        # 重试逻辑
        if context and context.get('retry_count', 0) > 0:
            retry_info = f'将在 {context.get("retry_interval", 5)} 秒后重试'
            retry_info >> log
        
        raise
'''
    
    def _get_cron_task_template(self) -> str:
        """获取定时任务模板"""
        return '''async def execute(context=None):
    """定时任务执行函数"""
    import time
    from datetime import datetime
    from deva import log, write_to_file, httpx, bus, Dtalk
    
    # 获取任务信息
    task_name = context.get('task_name', 'unknown') if context else 'unknown'
    current_time = datetime.now()
    start_time = time.time()
    
    try:
        # 任务开始
        f'定时任务 {task_name} 开始执行 (时间: {current_time.strftime("%Y-%m-%d %H:%M:%S")})' >> log
        
        # TODO: 在这里实现具体的任务逻辑
        
        # 模拟工作
        result = f'定时任务执行完成 (耗时: {time.time() - start_time:.2f}s)'
        
        # 记录成功
        result >> log
        return result
        
    except Exception as e:
        # 错误处理
        error_msg = f'定时任务执行失败: {e}'
        error_msg >> log
        raise
'''
    
    def _get_one_time_task_template(self) -> str:
        """获取一次性任务模板"""
        return '''async def execute(context=None):
    """一次性任务执行函数"""
    import time
    from datetime import datetime
    from deva import log, write_to_file, httpx, bus, Dtalk
    
    # 获取任务信息
    task_name = context.get('task_name', 'unknown') if context else 'unknown'
    start_time = time.time()
    
    try:
        # 任务开始
        f'一次性任务 {task_name} 开始执行' >> log
        
        # TODO: 在这里实现具体的任务逻辑
        
        # 模拟工作
        result = f'一次性任务执行完成 (耗时: {time.time() - start_time:.2f}s)'
        
        # 记录成功
        result >> log
        return result
        
    except Exception as e:
        # 错误处理
        error_msg = f'一次性任务执行失败: {e}'
        error_msg >> log
        raise
'''


class TaskCodeOptimizer:
    """任务代码优化器
    
    专门优化定时任务代码的性能和可维护性
    """
    
    @staticmethod
    def optimize_task_code(code: str, task_type: TaskType) -> Dict[str, Any]:
        """优化任务代码
        
        Args:
            code: 原始代码
            task_type: 任务类型
            
        Returns:
            {"success": bool, "optimized_code": str, "improvements": List[str]}
        """
        improvements = []
        optimized_code = code
        
        # 性能优化
        if "time.time()" in code and code.count("time.time()") > 3:
            improvements.append("建议将time.time()结果缓存到变量中，避免重复调用")
        
        # 异步优化
        if "await" not in code and "asyncio.sleep" not in code:
            improvements.append("考虑使用异步IO操作提升性能")
        
        # 内存优化
        if "read()" in code and "large" in code:
            improvements.append("大文件处理建议使用分块读取方式")
        
        # 任务类型特定优化
        if task_type == TaskType.INTERVAL:
            if "global" in code:
                improvements.append("间隔任务中避免使用全局变量，考虑使用任务状态存储")
        
        return {
            "success": True,
            "optimized_code": optimized_code,
            "improvements": improvements
        }