"""策略输出结构规范

根据不同的输出目标，策略需要产出符合规范的数据结构：

1. SignalStream (通用存储)
   - 任意结构，结果直接存储

2. Radar (技术指标)
   - signal_type: 信号类型
   - score: 分数 (用于漂移检测)
   - value: 数值 (用于异常检测)

3. Memory (语义分析)
   - content: 文本内容
   - topic: 主题标签
   - sentiment: 情绪 (可选)

4. Bandit (交易信号)
   - signal_type: BUY/SELL
   - stock_code: 股票代码
   - stock_name: 股票名称
   - price: 价格
   - confidence: 置信度
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class OutputSchema:
    """输出结构规范"""
    target: str  # signal, radar, memory, bandit
    required_fields: List[str] = field(default_factory=list)
    optional_fields: List[str] = field(default_factory=list)
    field_types: Dict[str, str] = field(default_factory=dict)
    description: str = ""


# 各目标的输出规范
OUTPUT_SCHEMAS = {
    "radar": OutputSchema(
        target="radar",
        required_fields=["signal_type", "score"],
        optional_fields=["value", "message", "strategy_name"],
        field_types={
            "signal_type": "str",
            "score": "float",
            "value": "float",
            "message": "str",
        },
        description="技术指标检测，需要 signal_type 和 score 字段"
    ),
    "memory": OutputSchema(
        target="memory",
        required_fields=["content"],
        optional_fields=["topic", "sentiment", "tags", "metadata"],
        field_types={
            "content": "str",
            "topic": "str",
            "sentiment": "float",
            "tags": "list",
        },
        description="语义分析，需要 content 字段用于主题聚类"
    ),
    "bandit": OutputSchema(
        target="bandit",
        required_fields=["signal_type", "stock_code", "price"],
        optional_fields=["stock_name", "confidence", "amount", "reason"],
        field_types={
            "signal_type": "str",  # BUY, SELL
            "stock_code": "str",
            "stock_name": "str",
            "price": "float",
            "confidence": "float",
            "amount": "float",
            "reason": "str",
        },
        description="交易信号，需要 BUY/SELL、股票代码、价格"
    ),
}


def normalize_radar_output(result: Any) -> Optional[Dict]:
    """规范化雷达输出"""
    if result is None:
        return None
    
    # 如果已经是 dict
    if isinstance(result, dict):
        output = {
            "signal_type": str(result.get("signal_type", "unknown")),
            "score": float(result.get("score", 0)),
        }
        if "value" in result:
            output["value"] = float(result["value"])
        if "message" in result:
            output["message"] = str(result["message"])
        return output
    
    # 如果有属性
    output = {
        "signal_type": str(getattr(result, "signal_type", "unknown")),
        "score": float(getattr(result, "score", 0)),
    }
    if hasattr(result, "value"):
        output["value"] = float(result.value)
    if hasattr(result, "message"):
        output["message"] = str(result.message)
    
    return output


def normalize_memory_output(result: Any) -> Optional[Dict]:
    """规范化记忆输出"""
    if result is None:
        return None
    
    if isinstance(result, dict):
        output = {
            "content": str(result.get("content", str(result))),
        }
        if "topic" in result:
            output["topic"] = str(result["topic"])
        if "sentiment" in result:
            output["sentiment"] = float(result["sentiment"])
        if "tags" in result:
            output["tags"] = result["tags"]
        return output
    
    # 如果有 content 属性
    if hasattr(result, "content"):
        output = {"content": str(result.content)}
        if hasattr(result, "topic"):
            output["topic"] = str(result.topic)
        if hasattr(result, "sentiment"):
            output["sentiment"] = float(result.sentiment)
        return output
    
    # 默认为字符串内容
    return {"content": str(result)}


def normalize_bandit_output(result: Any) -> Optional[Dict]:
    """规范化交易信号输出
    
    兼容多种字段命名：
    - stock_code: code, symbol, Code, Symbol
    - stock_name: name, stock_name
    - price: close, current, last, Price
    - signal_type: type, signal
    """
    if result is None:
        return None
    
    if isinstance(result, dict):
        signal_type = str(result.get("signal_type", result.get("type", result.get("signal", "")))).upper()
        if signal_type not in ["BUY", "SELL", "买入", "卖出"]:
            return None
        
        # 兼容多种字段名
        stock_code = (
            result.get("stock_code") or 
            result.get("code") or 
            result.get("symbol") or 
            ""
        )
        
        stock_name = (
            result.get("stock_name") or 
            result.get("name") or 
            ""
        )
        
        price = (
            result.get("price") or 
            result.get("close") or 
            result.get("current") or 
            result.get("last") or 
            0
        )
        
        output = {
            "signal_type": signal_type,
            "stock_code": str(stock_code),
            "price": float(price) if price else 0.0,
        }
        if stock_name:
            output["stock_name"] = str(stock_name)
        if "confidence" in result:
            output["confidence"] = float(result["confidence"])
        if "amount" in result:
            output["amount"] = float(result["amount"])
        if "reason" in result:
            output["reason"] = str(result["reason"])
        return output
    
    # 如果有属性
    signal_type = str(getattr(result, "signal_type", getattr(result, "type", ""))).upper()
    if signal_type not in ["BUY", "SELL", "买入", "卖出"]:
        return None
    
    output = {
        "signal_type": signal_type,
        "stock_code": str(getattr(result, "stock_code", getattr(result, "code", ""))),
        "price": float(getattr(result, "price", getattr(result, "close", 0))),
    }
    if hasattr(result, "stock_name"):
        output["stock_name"] = str(result.stock_name)
    elif hasattr(result, "name"):
        output["stock_name"] = str(result.name)
    if hasattr(result, "confidence"):
        output["confidence"] = float(result.confidence)
    
    return output


def normalize_output(result: Any, targets: set) -> Dict[str, Any]:
    """根据目标规范化输出
    
    返回结构:
    {
        "radar": {...},  # 规范化后的雷达数据
        "memory": {...}, # 规范化后的记忆数据
        "bandit": {...}, # 规范胡后的交易信号
    }
    """
    normalized = {}
    
    if "radar" in targets:
        radar_data = normalize_radar_output(result)
        if radar_data:
            normalized["radar"] = radar_data
    
    if "memory" in targets:
        memory_data = normalize_memory_output(result)
        if memory_data:
            normalized["memory"] = memory_data
    
    if "bandit" in targets:
        bandit_data = normalize_bandit_output(result)
        if bandit_data:
            normalized["bandit"] = bandit_data
    
    return normalized


def validate_output(result: Any, target: str) -> tuple[bool, Optional[str]]:
    """验证输出是否符合规范
    
    返回: (是否有效, 错误信息)
    """
    schema = OUTPUT_SCHEMAS.get(target)
    if not schema:
        return True, None  # 无规范，默认通过
    
    if result is None:
        return False, "结果为空"
    
    # 转换为 dict
    if isinstance(result, dict):
        data = result
    elif hasattr(result, "__dict__"):
        data = vars(result)
    else:
        return False, f"不支持的结果类型: {type(result)}"
    
    # 检查必需字段
    for field in schema.required_fields:
        if field not in data or data[field] is None:
            return False, f"缺少必需字段: {field}"
    
    return True, None


# 默认输出模板
DEFAULT_OUTPUT_TEMPLATES = {
    "radar": {
        "signal_type": "trend",
        "score": 0.5,
        "value": 0.0,
        "message": ""
    },
    "memory": {
        "content": "",
        "topic": "general",
        "sentiment": 0.0,
        "tags": []
    },
    "bandit": {
        "signal_type": "BUY",
        "stock_code": "",
        "stock_name": "",
        "price": 0.0,
        "confidence": 0.5,
        "amount": 10000.0,
        "reason": ""
    }
}
