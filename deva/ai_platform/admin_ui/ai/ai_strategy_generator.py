"""AI策略代码生成服务

提供基于数据源数据结构和用户需求自动生成策略代码的功能。

================================================================================
工作流程
================================================================================

1. 用户选择数据源
2. 分析数据源的数据结构（Schema）
3. 用户描述需求
4. AI根据数据结构和需求生成代码
5. 用户审核确认
6. 保存策略到数据库

================================================================================
生成策略代码模板
================================================================================

```python
def process(data):
    '''
    策略处理函数
    
    输入数据结构:
    - code: 股票代码
    - name: 股票名称
    - now: 当前价
    - p_change: 涨跌幅
    ...
    
    处理逻辑:
    ...
    '''
    # 用户需求实现
    return result
```
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional
import pandas as pd

from deva import NB, log


def analyze_data_schema(data: Any) -> dict:
    """分析数据结构，生成Schema描述"""
    if data is None:
        return {"type": "null", "description": "数据为空"}
    
    schema = {
        "type": type(data).__name__,
        "fields": [],
        "sample": None,
    }
    
    if isinstance(data, pd.DataFrame):
        schema["type"] = "DataFrame"
        schema["row_count"] = len(data)
        schema["column_count"] = len(data.columns)
        
        for col in data.columns:
            field_info = {
                "name": col,
                "dtype": str(data[col].dtype),
                "sample_values": data[col].head(3).tolist() if len(data) > 0 else [],
            }
            schema["fields"].append(field_info)
        
        schema["sample"] = data.head(2).to_dict(orient="records") if len(data) > 0 else []
        
    elif isinstance(data, dict):
        schema["type"] = "dict"
        for key, value in data.items():
            field_info = {
                "name": key,
                "dtype": type(value).__name__,
                "sample_values": [str(value)[:50]],
            }
            schema["fields"].append(field_info)
        schema["sample"] = {k: str(v)[:100] for k, v in list(data.items())[:5]}
        
    elif isinstance(data, (list, tuple)):
        schema["type"] = "list" if isinstance(data, list) else "tuple"
        schema["length"] = len(data)
        if len(data) > 0:
            first_item = data[0]
            schema["item_type"] = type(first_item).__name__
            if isinstance(first_item, dict):
                for key, value in first_item.items():
                    field_info = {
                        "name": key,
                        "dtype": type(value).__name__,
                        "sample_values": [str(value)[:50]],
                    }
                    schema["fields"].append(field_info)
        schema["sample"] = str(data[:2])[:200]
    else:
        schema["sample"] = str(data)[:200]
    
    return schema


def build_datasource_context(source) -> dict:
    """从数据源构建上下文信息，包括元数据和代码"""
    context = {
        "name": source.name,
        "type": source.metadata.source_type.value,
        "description": source.metadata.description or "",
        "interval": source.metadata.interval,
        "data_func_code": source.metadata.data_func_code or "",
        "status": source.status.value,
    }
    return context


def build_schema_from_metadata(source) -> dict:
    """从数据源元数据推断数据结构（当没有实际数据时）"""
    schema = {
        "type": "unknown",
        "fields": [],
        "sample": None,
        "datasource_info": {
            "name": source.name,
            "type": source.metadata.source_type.value,
            "description": source.metadata.description or "",
        }
    }
    
    data_func_code = source.metadata.data_func_code or ""
    
    if data_func_code:
        schema["data_func_code"] = data_func_code
        schema["note"] = "数据源暂无实际数据，以下为数据获取函数代码，请根据代码推断数据结构"
        
        import re
        return_patterns = re.findall(r'return\s+(.+?)(?:\n|$)', data_func_code, re.MULTILINE)
        if return_patterns:
            schema["return_hints"] = return_patterns[:3]
        
        akshare_patterns = re.findall(r'ak\.(\w+)\(', data_func_code)
        if akshare_patterns:
            schema["akshare_functions"] = list(set(akshare_patterns))
            schema["note"] += f"。检测到akshare函数: {', '.join(akshare_patterns)}"
    else:
        schema["note"] = "数据源暂无实际数据和代码，请根据数据源类型和描述推断数据结构"
    
    return schema


def build_strategy_generation_prompt(
    data_schema: dict,
    user_requirement: str,
    strategy_name: str = "",
    output_format: str = "html",
    datasource_context: dict = None,
) -> str:
    """构建AI生成策略代码的Prompt"""
    
    schema_desc = json.dumps(data_schema, ensure_ascii=False, indent=2)
    
    datasource_info = ""
    if datasource_context:
        datasource_info = f"""
## 数据源信息

- 名称: {datasource_context.get('name', '未知')}
- 类型: {datasource_context.get('type', '未知')}
- 描述: {datasource_context.get('description', '无')}
- 定时间隔: {datasource_context.get('interval', 5)}秒
"""
        if datasource_context.get('data_func_code'):
            datasource_info += f"""
## 数据获取函数代码

```python
{datasource_context['data_func_code']}
```

请根据上述数据获取函数代码推断数据结构，并生成相应的策略处理代码。
"""
    
    has_actual_data = data_schema.get("type") not in ["null", "unknown"]
    
    prompt = f"""你是一个专业的量化策略代码生成助手。请根据以下信息生成Python策略代码。

## 数据源结构

```json
{schema_desc}
```
{datasource_info}
## 用户需求

{user_requirement}

## 输出要求

请生成一个完整的策略处理函数，函数名必须为 `process`，接收一个参数 `data`（数据源产生的数据）。

### 代码规范

1. 函数必须返回处理结果，可以是DataFrame、字典或字符串
2. 如果返回HTML字符串，将用于直接显示
3. 使用pandas进行数据处理
4. 添加必要的注释说明处理逻辑
5. 处理可能的异常情况
{"6. 数据源暂无实际数据，请根据数据获取函数代码或akshare函数推断数据结构" if not has_actual_data else ""}

### 输出格式

请按以下格式输出：

```python
def process(data):
    '''
    策略说明: [简要说明策略功能]
    输入: [输入数据描述]
    输出: [输出数据描述]
    '''
    import pandas as pd
    
    # 处理逻辑
    ...
    
    return result
```

### 策略名称
{strategy_name or "未命名策略"}

请只输出代码，不要输出其他说明文字。
"""
    return prompt


def build_strategy_documentation_prompt(
    code: str,
    strategy_name: str,
    data_schema: dict,
) -> str:
    """构建生成策略文档的Prompt"""
    
    prompt = f"""请为以下策略生成Markdown格式的说明文档。

## 策略名称
{strategy_name}

## 策略代码
```python
{code}
```

## 输入数据结构
```json
{json.dumps(data_schema, ensure_ascii=False, indent=2)}
```

## 输出要求

请生成包含以下内容的文档：

1. 策略概述
2. 输入数据说明
3. 处理逻辑说明
4. 输出数据说明
5. 使用示例（可选）

请使用Markdown格式输出，简洁明了。
"""
    return prompt


def extract_code_from_response(response: str) -> str:
    """从AI响应中提取代码"""
    if not response or not response.strip():
        return ""
    
    if "```python" in response:
        start = response.find("```python") + len("```python")
        end = response.find("```", start)
        if end > start:
            code = response[start:end].strip()
            if "def process" in code or "def " in code:
                return code
    
    if "```" in response:
        start = response.find("```") + len("```")
        end = response.find("```", start)
        if end > start:
            code = response[start:end].strip()
            if "def process" in code or "def " in code:
                return code
    
    if "def process" in response:
        start = response.find("def process")
        lines = response[start:].split("\n")
        code_lines = []
        indent_level = None
        for line in lines:
            if line.strip().startswith("def process"):
                indent_level = len(line) - len(line.lstrip())
                code_lines.append(line)
            elif indent_level is not None:
                if line.strip() == "" or (len(line) > indent_level and line[:indent_level].isspace()):
                    code_lines.append(line)
                elif line.strip() and not line.strip().startswith("#") and len(line) - len(line.lstrip()) <= indent_level and not code_lines[-1].strip().endswith(":"):
                    break
                else:
                    code_lines.append(line)
        code = "\n".join(code_lines).strip()
        if code:
            return code
    
    return response.strip()


def validate_strategy_code(code: str) -> dict:
    """验证策略代码"""
    result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "raw_code": code[:500] if code else "",
    }
    
    if not code or not code.strip():
        result["valid"] = False
        result["errors"].append("AI返回的代码为空，请检查AI响应")
        return result
    
    if "def process" not in code:
        result["valid"] = False
        result["errors"].append(f"代码必须包含 'def process' 函数。AI返回内容预览: {code[:200]}...")
        return result
    
    try:
        local_ns = {"__builtins__": __builtins__, "pd": pd}
        exec(code, local_ns, local_ns)
        
        if "process" not in local_ns or not callable(local_ns["process"]):
            result["valid"] = False
            result["errors"].append("代码执行后未找到 'process' 函数")
            return result
        
        import inspect
        sig = inspect.signature(local_ns["process"])
        if len(sig.parameters) < 1:
            result["warnings"].append("process 函数应该接受至少一个参数")
        
    except SyntaxError as e:
        result["valid"] = False
        result["errors"].append(f"语法错误: {e}")
    except Exception as e:
        result["valid"] = False
        result["errors"].append(f"代码执行错误: {e}")
    
    return result


def test_strategy_code(
    code: str,
    test_data: Any,
) -> dict:
    """测试策略代码"""
    result = {
        "success": False,
        "output": None,
        "error": None,
        "execution_time_ms": 0,
    }
    
    try:
        local_ns = {"__builtins__": __builtins__, "pd": pd}
        exec(code, local_ns, local_ns)
        
        process_func = local_ns.get("process")
        if not process_func:
            result["error"] = "未找到 process 函数"
            return result
        
        import copy
        import time
        
        start_time = time.time()
        output = process_func(copy.deepcopy(test_data))
        execution_time = (time.time() - start_time) * 1000
        
        result["success"] = True
        result["output"] = output
        result["execution_time_ms"] = execution_time
        
    except Exception as e:
        import traceback
        result["error"] = f"{str(e)}\n{traceback.format_exc()}"
    
    return result


async def generate_strategy_code(
    ctx: dict,
    data_schema: dict,
    user_requirement: str,
    strategy_name: str = "",
    datasource_context: dict = None,
) -> str:
    """调用AI生成策略代码"""
    from ..llm_service import get_gpt_response
    
    prompt = build_strategy_generation_prompt(
        data_schema=data_schema,
        user_requirement=user_requirement,
        strategy_name=strategy_name,
        datasource_context=datasource_context,
    )
    
    response = await get_gpt_response(
        ctx,
        prompt,
        model_type="deepseek",
    )
    
    code = extract_code_from_response(response)
    return code


async def generate_strategy_documentation(
    ctx: dict,
    code: str,
    strategy_name: str,
    data_schema: dict,
) -> str:
    """调用AI生成策略文档"""
    from ..llm_service import get_gpt_response
    
    prompt = build_strategy_documentation_prompt(
        code=code,
        strategy_name=strategy_name,
        data_schema=data_schema,
    )
    
    response = await get_gpt_response(
        ctx,
        prompt,
        model_type="deepseek",
    )
    
    return response
