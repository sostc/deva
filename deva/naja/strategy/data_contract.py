"""数据源到策略的数据契约

定义数据源输出的标准数据结构和校验机制，
确保策略能正确处理数据源的数据。

数据流:
  DataSource -> DataContract.validate() -> Strategy.on_data()

使用方式:
    from deva.naja.strategy.data_contract import (
        DataContract,
        validate_input_data,
        get_contract_for_datasource,
    )
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


class DataType(Enum):
    """数据类型"""

    TICK = "tick"           # 逐笔数据
    KLINE = "kline"        # K线数据
    NEWS = "news"          # 新闻数据
    CUSTOM = "custom"      # 自定义数据


class DataQuality(Enum):
    """数据质量等级"""

    HIGH = "high"          # 高质量，完整无缺失
    MEDIUM = "medium"      # 中等质量，部分字段缺失
    LOW = "low"            # 低质量，数据异常


@dataclass
class FieldSpec:
    """字段规范"""

    name: str
    type: str              # int, float, str, bool, dict, list
    required: bool = True
    default: Any = None
    description: str = ""
    validators: List[Callable] = field(default_factory=list)


@dataclass
class DataContract:
    """数据契约

    定义数据源输出的数据结构规范，包括：
    - 数据类型
    - 必填字段
    - 可选字段
    - 字段验证器
    """

    datasource_type: str
    data_type: DataType
    fields: List[FieldSpec] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_required_fields(self) -> Set[str]:
        """获取必填字段"""
        return {f.name for f in self.fields if f.required}

    def get_all_fields(self) -> Set[str]:
        """获取所有字段"""
        return {f.name for f in self.fields}

    def validate(self, data: Dict) -> tuple[bool, List[str], DataQuality]:
        """验证数据是否符合契约

        Returns:
            (是否有效, 错误列表, 数据质量等级)
        """
        errors = []
        missing_fields = set()
        optional_missing = set()

        for field_spec in self.fields:
            if field_spec.name not in data:
                if field_spec.required:
                    missing_fields.add(field_spec.name)
                    errors.append(f"缺少必填字段: {field_spec.name}")
                else:
                    optional_missing.add(field_spec.name)

        if missing_fields:
            return False, errors, DataQuality.LOW

        for field_spec in self.fields:
            value = data.get(field_spec.name)
            if value is None:
                continue

            for validator in field_spec.validators:
                try:
                    if not validator(value):
                        errors.append(f"字段 {field_spec.name} 验证失败")
                except Exception as e:
                    errors.append(f"字段 {field_spec.name} 验证异常: {e}")

        if errors:
            return False, errors, DataQuality.MEDIUM

        if optional_missing:
            return True, [], DataQuality.MEDIUM

        return True, [], DataQuality.HIGH

    def fill_defaults(self, data: Dict) -> Dict:
        """填充默认值"""
        result = dict(data)
        for field_spec in self.fields:
            if field_spec.name not in result and field_spec.default is not None:
                result[field_spec.name] = field_spec.default
        return result


TICK_CONTRACT = DataContract(
    datasource_type="tick",
    data_type=DataType.TICK,
    fields=[
        FieldSpec("ts", "float", True, description="时间戳"),
        FieldSpec("code", "str", True, description="股票代码"),
        FieldSpec("price", "float", True, description="价格"),
        FieldSpec("volume", "float", False, 0.0, description="成交量"),
        FieldSpec("amount", "float", False, 0.0, description="成交额"),
        FieldSpec("direction", "str", False, "unknown", description="买卖方向"),
    ],
    metadata={"description": "逐笔成交数据"}
)

KLINE_CONTRACT = DataContract(
    datasource_type="kline",
    data_type=DataType.KLINE,
    fields=[
        FieldSpec("ts", "float", True, description="时间戳"),
        FieldSpec("code", "str", True, description="股票代码"),
        FieldSpec("open", "float", True, description="开盘价"),
        FieldSpec("high", "float", True, description="最高价"),
        FieldSpec("low", "float", True, description="最低价"),
        FieldSpec("close", "float", True, description="收盘价"),
        FieldSpec("volume", "float", False, 0.0, description="成交量"),
        FieldSpec("amount", "float", False, 0.0, description="成交额"),
    ],
    metadata={"description": "K线数据"}
)

NEWS_CONTRACT = DataContract(
    datasource_type="news",
    data_type=DataType.NEWS,
    fields=[
        FieldSpec("ts", "float", True, description="时间戳"),
        FieldSpec("title", "str", True, description="标题"),
        FieldSpec("content", "str", True, description="内容"),
        FieldSpec("source", "str", False, "", description="来源"),
        FieldSpec("url", "str", False, "", description="链接"),
    ],
    metadata={"description": "新闻数据"}
)

CONTRACT_REGISTRY: Dict[str, DataContract] = {
    "tick": TICK_CONTRACT,
    "kline": KLINE_CONTRACT,
    "news": NEWS_CONTRACT,
}


def get_contract(datasource_type: str) -> Optional[DataContract]:
    """获取数据源类型的契约"""
    return CONTRACT_REGISTRY.get(datasource_type)


def register_contract(contract: DataContract) -> None:
    """注册数据契约"""
    CONTRACT_REGISTRY[contract.datasource_type] = contract


def validate_input_data(
    data: Any,
    datasource_type: Optional[str] = None,
    contract: Optional[DataContract] = None,
) -> tuple[bool, List[str], DataQuality, Optional[Dict]]:
    """验证输入数据

    Args:
        data: 输入数据
        datasource_type: 数据源类型
        contract: 数据契约 (优先使用)

    Returns:
        (是否有效, 错误列表, 数据质量, 规范化后的数据)
    """
    if data is None:
        return False, ["数据为空"], DataQuality.LOW, None

    if not isinstance(data, dict):
        return False, [f"数据类型错误: {type(data)}"], DataQuality.LOW, None

    if contract is None and datasource_type:
        contract = get_contract(datasource_type)

    if contract is None:
        return True, [], DataQuality.HIGH, data

    valid, errors, quality = contract.validate(data)

    if valid:
        normalized = contract.fill_defaults(data)
        return True, errors, quality, normalized

    return False, errors, quality, None


class DataPipeline:
    """数据处理管道

    负责数据从数据源到策略的转换和验证
    """

    def __init__(self, datasource_type: str):
        self.datasource_type = datasource_type
        self.contract = get_contract(datasource_type)
        self._transformers: List[Callable[[Dict], Dict]] = []

    def add_transformer(self, transformer: Callable[[Dict], Dict]) -> None:
        """添加数据转换器"""
        self._transformers.append(transformer)

    def process(self, data: Dict) -> tuple[bool, Optional[Dict], List[str]]:
        """处理数据

        Returns:
            (是否成功, 处理后的数据, 错误列表)
        """
        if self.contract:
            valid, errors, quality, normalized = self.contract.validate(data)
            if not valid:
                return False, None, errors
            data = normalized

        for transformer in self._transformers:
            try:
                data = transformer(data)
            except Exception as e:
                return False, None, [f"转换失败: {e}"]

        return True, data, []


def create_pipeline(datasource_type: str) -> DataPipeline:
    """创建数据处理管道"""
    return DataPipeline(datasource_type)
