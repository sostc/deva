"""AI代码生成工具类(AI Code Generation Utils)

为策略和数据源提供统一的AI代码生成、验证和优化能力。

================================================================================
功能特性
================================================================================

1. **统一的数据结构分析**: 分析输入/输出数据模式
2. **智能代码生成**: 根据需求生成策略或数据源代码
3. **代码验证**: 验证生成的代码语法和安全性
4. **代码优化**: 优化现有代码的性能和可读性
5. **模板管理**: 管理代码模板和最佳实践
"""

from __future__ import annotations

import ast
import traceback
from typing import Any, Dict, List, Optional, Type

from deva import log

from .executable_unit import ExecutableUnit, ExecutableUnitMetadata, ExecutableUnitState


class AICodeGenerator:
    """AI代码生成器基类
    
    为不同类型的可执行单元提供统一的AI代码生成能力
    """
    
    def __init__(self, unit_type: str):
        """
        Args:
            unit_type: 单元类型 ("strategy" 或 "datasource")
        """
        self.unit_type = unit_type
        
        # 默认的代码模板
        self._templates = {
            "strategy": self._get_default_strategy_template(),
            "datasource": self._get_default_datasource_template(),
            "task": self._get_default_task_template(),
        }
    
    # ==========================================================================
    # 数据结构分析方法
    # ==========================================================================
    
    def analyze_data_schema(self, data: Any) -> Dict[str, Any]:
        """分析数据结构
        
        分析输入数据的类型、结构和特征，为AI代码生成提供上下文
        
        Args:
            data: 输入数据
            
        Returns:
            数据结构描述
        """
        schema = {
            "type": type(data).__name__,
            "python_type": str(type(data)),
            "is_empty": False,
            "size": 0,
            "fields": [],
            "sample": None,
        }
        
        try:
            import pandas as pd
            import numpy as np
            
            if data is None:
                schema["is_empty"] = True
                schema["description"] = "数据为空"
                
            elif isinstance(data, pd.DataFrame):
                schema["type"] = "DataFrame"
                schema["row_count"] = len(data)
                schema["column_count"] = len(data.columns)
                schema["columns"] = list(data.columns)
                schema["dtypes"] = {col: str(dtype) for col, dtype in data.dtypes.items()}
                schema["memory_usage"] = data.memory_usage(deep=True).sum()
                schema["has_index"] = data.index.name is not None
                schema["index_type"] = str(type(data.index))
                
                # 数据样本
                if len(data) > 0:
                    sample_data = data.head(3).to_dict('records')
                    schema["sample"] = sample_data
                    
                # 字段详细信息
                for col in data.columns:
                    field_info = {
                        "name": col,
                        "type": str(data[col].dtype),
                        "null_count": data[col].isnull().sum(),
                        "null_ratio": data[col].isnull().sum() / len(data) if len(data) > 0 else 0,
                        "unique_count": data[col].nunique(),
                        "is_numeric": pd.api.types.is_numeric_dtype(data[col]),
                        "is_datetime": pd.api.types.is_datetime64_any_dtype(data[col]),
                        "is_categorical": pd.api.types.is_categorical_dtype(data[col]),
                    }
                    
                    # 数值字段的统计信息
                    if field_info["is_numeric"] and field_info["null_ratio"] < 1:
                        field_info.update({
                            "min": float(data[col].min()),
                            "max": float(data[col].max()),
                            "mean": float(data[col].mean()),
                            "std": float(data[col].std()),
                        })
                    
                    schema["fields"].append(field_info)
                
            elif isinstance(data, pd.Series):
                schema["type"] = "Series"
                schema["length"] = len(data)
                schema["dtype"] = str(data.dtype)
                schema["name"] = data.name
                schema["null_count"] = data.isnull().sum()
                schema["null_ratio"] = data.isnull().sum() / len(data) if len(data) > 0 else 0
                schema["unique_count"] = data.nunique()
                
                if len(data) > 0:
                    schema["sample"] = data.head(3).tolist()
                    
            elif isinstance(data, (list, tuple)):
                schema["type"] = "list" if isinstance(data, list) else "tuple"
                schema["length"] = len(data)
                schema["element_types"] = list(set(type(item).__name__ for item in data))
                
                if len(data) > 0:
                    schema["sample"] = data[:3]
                    
            elif isinstance(data, dict):
                schema["type"] = "dict"
                schema["key_count"] = len(data)
                schema["keys"] = list(data.keys())
                schema["sample_keys"] = list(data.keys())[:3]
                
                # 分析值类型
                value_types = {}
                for key, value in data.items():
                    value_type = type(value).__name__
                    if value_type not in value_types:
                        value_types[value_type] = 0
                    value_types[value_type] += 1
                schema["value_types"] = value_types
                
                if data:
                    # 取前几个键值对作为样本
                    sample_items = list(data.items())[:2]
                    schema["sample"] = {k: str(v)[:100] for k, v in sample_items}  # 限制长度
                    
            elif isinstance(data, (str, int, float, bool)):
                schema["type"] = type(data).__name__
                schema["value"] = data
                schema["length"] = len(str(data)) if hasattr(data, '__len__') else 1
                
            else:
                # 其他类型
                schema["description"] = str(data)[:200]  # 限制长度
                
        except Exception as e:
            log.error(f"数据结构分析失败: {e}")
            schema["analysis_error"] = str(e)
            schema["traceback"] = traceback.format_exc()
        
        return schema
    
    # ==========================================================================
    # 代码生成方法
    # ==========================================================================
    
    def generate_code(
        self,
        requirement: str,
        input_schema: Dict[str, Any] = None,
        output_schema: Dict[str, Any] = None,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """生成代码
        
        Args:
            requirement: 需求描述
            input_schema: 输入数据结构
            output_schema: 输出数据结构
            context: 额外的上下文信息
            
        Returns:
            {"success": bool, "code": str, "error": str, "explanation": str}
        """
        try:
            # 构建提示词
            prompt = self._build_generation_prompt(
                requirement, input_schema, output_schema, context
            )
            
            # TODO: 集成实际的AI模型调用
            # 这里先用模板模拟AI生成
            code = self._generate_from_template(
                requirement, input_schema, output_schema, context
            )
            
            # 验证生成的代码
            validation_result = self.validate_code(code)
            if not validation_result["success"]:
                return {
                    "success": False,
                    "error": f"生成的代码验证失败: {validation_result['error']}",
                    "code": code
                }
            
            # 生成代码说明
            explanation = self._generate_explanation(code, requirement)
            
            return {
                "success": True,
                "code": code,
                "explanation": explanation,
                "prompt": prompt
            }
            
        except Exception as e:
            error_msg = f"代码生成失败: {str(e)}"
            log.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "traceback": traceback.format_exc()
            }
    
    def _build_generation_prompt(
        self,
        requirement: str,
        input_schema: Dict[str, Any] = None,
        output_schema: Dict[str, Any] = None,
        context: Dict[str, Any] = None
    ) -> str:
        """构建代码生成提示词"""
        prompt_parts = []
        
        # 基础说明
        if self.unit_type == "strategy":
            prompt_parts.append("你是一个策略开发专家。请根据需求生成一个Python处理函数。")
            prompt_parts.append("函数名称必须是 'process(data)'，接收一个参数 'data'。")
            prompt_parts.append("函数应该返回处理后的数据结果。")
        else:
            prompt_parts.append("你是一个数据源开发专家。请根据需求生成一个Python数据获取函数。")
            prompt_parts.append("函数名称必须是 'fetch_data()'，不需要参数。")
            prompt_parts.append("函数应该返回获取到的数据。")
        
        # 需求描述
        prompt_parts.append(f"\n需求描述: {requirement}")
        
        # 输入数据结构
        if input_schema:
            prompt_parts.append(f"\n输入数据结构: {self._format_schema(input_schema)}")
        
        # 输出数据结构
        if output_schema:
            prompt_parts.append(f"\n期望的输出数据结构: {self._format_schema(output_schema)}")
        
        # 上下文信息
        if context:
            prompt_parts.append(f"\n额外的上下文信息: {context}")
        
        # 代码要求
        prompt_parts.extend([
            "\n代码要求:",
            "1. 使用pandas和numpy进行数据处理",
            "2. 代码必须简洁、高效、可读性好",
            "3. 添加适当的错误处理",
            "4. 包含必要的注释说明",
            "5. 遵循Python最佳实践",
            "6. 只能使用提供的安全库",
        ])
        
        # 返回格式
        prompt_parts.extend([
            "\n返回格式:",
            "只返回Python函数代码，不要返回其他解释。",
            "代码必须可以直接执行。",
        ])
        
        return "\n".join(prompt_parts)
    
    def _format_schema(self, schema: Dict[str, Any]) -> str:
        """格式化数据结构描述"""
        if not schema:
            return "无"
        
        parts = []
        parts.append(f"类型: {schema.get('type', '未知')}")
        
        if schema.get('type') == 'DataFrame':
            parts.append(f"行数: {schema.get('row_count', 0)}")
            parts.append(f"列数: {schema.get('column_count', 0)}")
            parts.append(f"列名: {', '.join(schema.get('columns', []))}")
            
            if schema.get('fields'):
                parts.append("字段详情:")
                for field in schema['fields'][:5]:  # 只显示前5个字段
                    parts.append(f"  - {field['name']}: {field['type']}")
                if len(schema['fields']) > 5:
                    parts.append(f"  ... 还有 {len(schema['fields']) - 5} 个字段")
                    
        elif schema.get('type') == 'list':
            parts.append(f"长度: {schema.get('length', 0)}")
            parts.append(f"元素类型: {', '.join(schema.get('element_types', []))}")
            
        elif schema.get('type') == 'dict':
            parts.append(f"键数量: {schema.get('key_count', 0)}")
            parts.append(f"键名: {', '.join(schema.get('keys', []))}")
        
        return "; ".join(parts)
    
    def _generate_from_template(
        self,
        requirement: str,
        input_schema: Dict[str, Any] = None,
        output_schema: Dict[str, Any] = None,
        context: Dict[str, Any] = None
    ) -> str:
        """基于模板生成代码（模拟AI生成）"""
        # 这里可以根据需求选择不同的模板
        # 实际实现中会调用真正的AI模型
        
        if self.unit_type == "strategy":
            return self._generate_strategy_template(requirement, input_schema, output_schema)
        else:
            return self._generate_datasource_template(requirement, input_schema, output_schema)
    
    def _generate_strategy_template(
        self,
        requirement: str,
        input_schema: Dict[str, Any] = None,
        output_schema: Dict[str, Any] = None
    ) -> str:
        """生成策略代码模板"""
        code_lines = []
        
        # 函数定义
        code_lines.append("def process(data):")
        code_lines.append('    """处理数据"""')
        
        # 参数验证
        code_lines.append("    if data is None:")
        code_lines.append("        return None")
        code_lines.append("")
        
        # 主要逻辑（基于需求关键词）
        requirement_lower = requirement.lower()
        
        if any(word in requirement_lower for word in ["平均", "mean", "avg"]):
            code_lines.append("    # 计算平均值")
            code_lines.append("    if isinstance(data, pd.DataFrame):")
            code_lines.append("        return data.mean()")
            code_lines.append("    elif isinstance(data, (list, tuple)):")
            code_lines.append("        return sum(data) / len(data) if data else 0")
            
        elif any(word in requirement_lower for word in ["过滤", "filter", "筛选"]):
            code_lines.append("    # 过滤数据")
            code_lines.append("    if isinstance(data, pd.DataFrame):")
            code_lines.append("        # 示例：过滤出数值列")
            code_lines.append("        numeric_cols = data.select_dtypes(include=[np.number]).columns")
            code_lines.append("        return data[numeric_cols]")
            code_lines.append("    elif isinstance(data, list):")
            code_lines.append("        # 示例：过滤出正数")
            code_lines.append("        return [x for x in data if x > 0]")
            
        elif any(word in requirement_lower for word in ["转换", "transform", "转换"]):
            code_lines.append("    # 转换数据")
            code_lines.append("    if isinstance(data, pd.DataFrame):")
            code_lines.append("        # 示例：标准化数据")
            code_lines.append("        return (data - data.mean()) / data.std()")
            code_lines.append("    elif isinstance(data, list):")
            code_lines.append("        # 示例：转换为字符串")
            code_lines.append("        return [str(x) for x in data]")
            
        else:
            # 默认处理
            code_lines.append("    # 默认处理：返回原数据")
            code_lines.append("    return data")
        
        code_lines.append("")
        code_lines.append("    return None  # 默认返回None")
        
        return "\n".join(code_lines)
    
    def _generate_datasource_template(
        self,
        requirement: str,
        input_schema: Dict[str, Any] = None,
        output_schema: Dict[str, Any] = None
    ) -> str:
        """生成数据源代码模板"""
        code_lines = []
        
        # 函数定义
        code_lines.append("def fetch_data():")
        code_lines.append('    """获取数据"""')
        code_lines.append("")
        
        # 主要逻辑（基于需求关键词）
        requirement_lower = requirement.lower()
        
        if any(word in requirement_lower for word in ["随机", "random", "模拟"]):
            code_lines.append("    # 生成模拟数据")
            code_lines.append("    import random")
            code_lines.append("    data = []")
            code_lines.append("    for i in range(100):")
            code_lines.append("        data.append({")
            code_lines.append("            'id': i,")
            code_lines.append("            'value': random.randint(1, 100),")
            code_lines.append("            'timestamp': time.time()")
            code_lines.append("        })")
            code_lines.append("    return pd.DataFrame(data)")
            
        elif any(word in requirement_lower for word in ["时间序列", "time series", "序列"]):
            code_lines.append("    # 生成时间序列数据")
            code_lines.append("    import datetime")
            code_lines.append("    dates = pd.date_range(start='2023-01-01', periods=100, freq='D')")
            code_lines.append("    values = np.random.randn(100).cumsum()")
            code_lines.append("    return pd.DataFrame({")
            code_lines.append("        'date': dates,")
            code_lines.append("        'value': values")
            code_lines.append("    })")
            
        elif any(word in requirement_lower for word in ["股票", "stock", "金融"]):
            code_lines.append("    # 模拟股票数据")
            code_lines.append("    import random")
            code_lines.append("    symbols = ['AAPL', 'GOOGL', 'MSFT', 'AMZN']")
            code_lines.append("    data = []")
            code_lines.append("    for symbol in symbols:")
            code_lines.append("        data.append({")
            code_lines.append("            'symbol': symbol,")
            code_lines.append("            'price': random.uniform(100, 500),")
            code_lines.append("            'volume': random.randint(1000, 10000),")
            code_lines.append("            'timestamp': time.time()")
            code_lines.append("        })")
            code_lines.append("    return pd.DataFrame(data)")
            
        else:
            # 默认处理
            code_lines.append("    # 默认：返回示例数据")
            code_lines.append("    data = {")
            code_lines.append("        'id': [1, 2, 3],")
            code_lines.append("        'name': ['A', 'B', 'C'],")
            code_lines.append("        'value': [10, 20, 30]")
            code_lines.append("    }")
            code_lines.append("    return pd.DataFrame(data)")
        
        return "\n".join(code_lines)
    
    # ==========================================================================
    # 代码验证和优化方法
    # ==========================================================================
    
    def validate_code(self, code: str) -> Dict[str, Any]:
        """验证代码
        
        Args:
            code: Python代码
            
        Returns:
            {"success": bool, "error": str, "warnings": List[str]}
        """
        try:
            # 语法检查
            ast.parse(code)
            
            # 安全性检查
            security_result = self._check_security(code)
            if not security_result["success"]:
                return security_result
            
            # 功能性检查
            functional_result = self._check_functionality(code)
            if not functional_result["success"]:
                return functional_result
            
            return {
                "success": True,
                "warnings": security_result.get("warnings", []) + functional_result.get("warnings", [])
            }
            
        except SyntaxError as e:
            return {
                "success": False,
                "error": f"语法错误: {str(e)}",
                "line": getattr(e, 'lineno', None),
                "offset": getattr(e, 'offset', None)
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"代码验证失败: {str(e)}",
                "traceback": traceback.format_exc()
            }
    
    def _check_security(self, code: str) -> Dict[str, Any]:
        """安全性检查"""
        warnings = []
        
        # 危险关键字检查
        dangerous_keywords = [
            'eval', 'exec', 'compile', '__import__', 
            'open', 'file', 'input', 'raw_input',
            'os.system', 'subprocess', 'socket',
            'delete', 'remove', 'unlink', 'rmdir',
            'globals', 'locals', '__dict__'
        ]
        
        for keyword in dangerous_keywords:
            if keyword in code:
                warnings.append(f"检测到潜在危险关键字: {keyword}")
        
        # 文件操作检查
        if any(op in code for op in ['open(', 'with open', 'file(']):
            warnings.append("代码中包含文件操作，请确保安全性")
        
        # 网络操作检查
        if any(op in code for op in ['urllib', 'requests', 'http']):
            warnings.append("代码中包含网络操作，请确保安全性")
        
        return {
            "success": True,
            "warnings": warnings
        }
    
    def _check_functionality(self, code: str) -> Dict[str, Any]:
        """功能性检查"""
        warnings = []
        
        # 检查是否包含所需函数
        if self.unit_type == "strategy":
            if 'def process(' not in code:
                return {
                    "success": False,
                    "error": "策略代码必须包含 'process(data)' 函数"
                }
        else:
            if 'def fetch_data(' not in code:
                return {
                    "success": False,
                    "error": "数据源代码必须包含 'fetch_data()' 函数"
                }
        
        # 检查是否有返回值
        if 'return' not in code:
            warnings.append("代码中没有return语句，函数可能不会返回有效结果")
        
        # 检查错误处理
        if 'try:' not in code and 'except' not in code:
            warnings.append("建议添加错误处理机制")
        
        # 检查注释
        if '"""' not in code and "'''" not in code:
            warnings.append("建议添加函数文档字符串")
        
        return {
            "success": True,
            "warnings": warnings
        }
    
    def _generate_explanation(self, code: str, requirement: str) -> str:
        """生成代码说明"""
        lines = []
        lines.append("## 代码说明")
        lines.append("")
        lines.append(f"**需求**: {requirement}")
        lines.append("")
        
        # 分析代码结构
        if self.unit_type == "strategy":
            lines.append("**函数**: `process(data)` - 处理输入数据并返回结果")
        else:
            lines.append("**函数**: `fetch_data()` - 获取数据并返回")
        
        lines.append("")
        lines.append("**主要功能**:")
        
        # 简单的功能分析
        if 'pandas' in code or 'pd.' in code:
            lines.append("- 使用pandas进行数据处理")
        if 'numpy' in code or 'np.' in code:
            lines.append("- 使用numpy进行数值计算")
        if 'random' in code:
            lines.append("- 包含随机数据生成")
        if 'time' in code:
            lines.append("- 包含时间相关操作")
        
        # 返回说明
        lines.append("- 返回处理后的数据结果")
        
        return "\n".join(lines)
    
    # ==========================================================================
    # 模板方法
    # ==========================================================================
    
    def _get_default_strategy_template(self) -> str:
        """获取默认策略模板"""
        return '''def process(data):
    """处理数据
    
    Args:
        data: 输入数据
        
    Returns:
        处理后的数据
    """
    # 参数验证
    if data is None:
        return None
    
    # TODO: 在这里实现你的数据处理逻辑
    
    return data
'''
    
    def _get_default_datasource_template(self) -> str:
        """获取默认数据源模板"""
        return '''def fetch_data():
    """获取数据
    
    Returns:
        获取到的数据
    """
    # TODO: 在这里实现你的数据获取逻辑
    
    return None
'''
    
    def _get_default_task_template(self) -> str:
        """获取默认任务模板"""
        return '''async def execute(context=None):
    """执行任务
    
    Args:
        context: 执行上下文，包含任务信息
        
    Returns:
        任务执行结果
    """
    # TODO: 在这里实现你的任务逻辑
    
    return "任务执行完成"
'''
    
    # ==========================================================================
    # 工具方法
    # ==========================================================================
    
    def optimize_code(self, code: str) -> Dict[str, Any]:
        """优化代码
        
        Args:
            code: 原始代码
            
        Returns:
            {"success": bool, "optimized_code": str, "improvements": List[str]}
        """
        # 这里可以实现代码优化逻辑
        # 比如：简化表达式、优化循环、改进变量名等
        
        improvements = []
        optimized_code = code
        
        # 示例优化规则
        if 'import pandas' in code and 'as pd' not in code:
            improvements.append("建议使用 'import pandas as pd' 的简写形式")
        
        if 'for i in range(len(' in code:
            improvements.append("建议使用枚举或更Pythonic的循环方式")
        
        if '==' in code and 'None' in code:
            improvements.append("建议使用 'is None' 而不是 '== None'")
        
        return {
            "success": True,
            "optimized_code": optimized_code,
            "improvements": improvements
        }


class StrategyAIGenerator(AICodeGenerator):
    """策略AI代码生成器"""
    
    def __init__(self):
        super().__init__("strategy")


class DataSourceAIGenerator(AICodeGenerator):
    """数据源AI代码生成器"""
    
    def __init__(self):
        super().__init__("datasource")


class TaskAIGenerator(AICodeGenerator):
    """任务AI代码生成器"""
    
    def __init__(self):
        super().__init__("task")