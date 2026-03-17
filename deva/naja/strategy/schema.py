"""策略配置 schema 验证

提供策略配置的验证功能，支持:
- 策略类型验证 (strategy_type)
- 配置字段验证
- 必填字段检查
- 类型检查

使用方式:
    from deva.naja.strategy.schema import validate_strategy_config, get_schema

    # 验证配置
    result = validate_strategy_config(config)
    if not result.valid:
        print(result.errors)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class ValidationError:
    """验证错误"""

    field: str
    message: str
    code: str = "invalid"


@dataclass
class ValidationResult:
    """验证结果"""

    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, field: str, message: str, code: str = "invalid") -> None:
        self.errors.append(ValidationError(field=field, message=message, code=code))
        self.valid = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


BASE_SCHEMA = {
    "strategy_type": {
        "type": str,
        "required": True,
        "choices": ["legacy", "river", "plugin", "declarative"],
    },
    "strategy_name": {"type": str, "required": False},
    "strategy_id": {"type": str, "required": False},
}


LEGACY_SCHEMA = {
    "process_func": {"type": callable, "required": True},
}


RIVER_SCHEMA = {
    "model_path": {"type": str, "required": False},
    "model": {"type": object, "required": False},
    "model_params": {"type": dict, "required": False},
    "feature_key": {"type": str, "required": False, "default": "features"},
    "label_key": {"type": str, "required": False, "default": "label"},
    "learn_on_label": {"type": bool, "required": False, "default": True},
    "signal_type": {"type": str, "required": False, "default": "river"},
}


PLUGIN_SCHEMA = {
    "class_path": {"type": str, "required": True},
    "init_args": {"type": dict, "required": False},
}


DECLARATIVE_SCHEMA = {
    "pipeline": {"type": dict, "required": False},
    "model": {"type": dict, "required": False},
    "model_type": {"type": str, "required": False},
    "params": {"type": dict, "required": False},
    "logic": {"type": dict, "required": False},
    "plugin": {"type": str, "required": False},
    "code": {"type": str, "required": False},
    "state_persist": {"type": bool, "required": False},
    "state_persist_interval": {"type": int, "required": False},
}


TYPE_SCHEMA_MAP: Dict[str, Dict] = {
    "legacy": {**BASE_SCHEMA, **LEGACY_SCHEMA},
    "river": {**BASE_SCHEMA, **RIVER_SCHEMA},
    "plugin": {**BASE_SCHEMA, **PLUGIN_SCHEMA},
    "declarative": {**BASE_SCHEMA, **DECLARATIVE_SCHEMA},
}


def get_schema(strategy_type: str) -> Dict:
    """获取策略类型的 schema

    Args:
        strategy_type: 策略类型

    Returns:
        Dict: schema 定义
    """
    return TYPE_SCHEMA_MAP.get(strategy_type, BASE_SCHEMA)


def validate_field(
    field_name: str,
    value: Any,
    field_schema: Dict,
) -> List[ValidationError]:
    """验证单个字段

    Args:
        field_name: 字段名
        value: 字段值
        field_schema: 字段 schema

    Returns:
        List[ValidationError]: 错误列表
    """
    errors = []

    if field_schema.get("required", False) and value is None:
        errors.append(
            ValidationError(
                field=field_name,
                message=f"必填字段 {field_name} 不能为空",
                code="required",
            )
        )
        return errors

    if value is None:
        return errors

    expected_type = field_schema.get("type")
    if expected_type and not isinstance(value, expected_type):
        errors.append(
            ValidationError(
                field=field_name,
                message=f"字段 {field_name} 类型错误，期望 {expected_type.__name__}，实际 {type(value).__name__}",
                code="type_error",
            )
        )

    choices = field_schema.get("choices")
    if choices and value not in choices:
        errors.append(
            ValidationError(
                field=field_name,
                message=f"字段 {field_name} 值无效，可选值: {choices}",
                code="invalid_choice",
            )
        )

    return errors


def validate_strategy_config(config: Dict[str, Any]) -> ValidationResult:
    """验证策略配置

    Args:
        config: 策略配置

    Returns:
        ValidationResult: 验证结果
    """
    result = ValidationResult(valid=True)

    strategy_type = config.get("strategy_type", "legacy")

    if not strategy_type:
        result.add_error("strategy_type", "strategy_type 不能为空", "required")
        return result

    if strategy_type not in TYPE_SCHEMA_MAP:
        result.add_error(
            "strategy_type",
            f"未知的策略类型: {strategy_type}，可选值: {list(TYPE_SCHEMA_MAP.keys())}",
            "invalid_choice",
        )
        return result

    schema = TYPE_SCHEMA_MAP[strategy_type]

    for field_name, field_schema in schema.items():
        value = config.get(field_name)
        field_errors = validate_field(field_name, value, field_schema)
        result.errors.extend(field_errors)

    if result.errors:
        result.valid = False

    if strategy_type == "river":
        has_model = config.get("model") is not None or config.get("model_path")
        if not has_model:
            result.add_warning("River 策略建议配置 model 或 model_path")

    if strategy_type == "plugin":
        class_path = config.get("class_path", "")
        if class_path and not re.match(r"^[a-zA-Z_][a-zA-Z0-9_.]*$", class_path):
            result.add_warning(f"class_path 格式可能不正确: {class_path}")

    if strategy_type == "declarative":
        has_logic = config.get("logic") or config.get("code") or config.get("plugin")
        if not has_logic:
            result.add_warning("declarative 策略建议配置 logic, code 或 plugin")

    return result


def validate_config_for_type(
    config: Dict[str, Any],
    strategy_type: str,
) -> ValidationResult:
    """验证特定类型的配置

    Args:
        config: 策略配置
        strategy_type: 策略类型

    Returns:
        ValidationResult: 验证结果
    """
    config_with_type = {**config, "strategy_type": strategy_type}
    return validate_strategy_config(config_with_type)


def get_required_fields(strategy_type: str) -> List[str]:
    """获取策略类型的必填字段

    Args:
        strategy_type: 策略类型

    Returns:
        List[str]: 必填字段列表
    """
    schema = TYPE_SCHEMA_MAP.get(strategy_type, {})
    return [
        field_name
        for field_name, field_schema in schema.items()
        if field_schema.get("required", False)
    ]


def get_optional_fields(strategy_type: str) -> List[str]:
    """获取策略类型的可选字段

    Args:
        strategy_type: 策略类型

    Returns:
        List[str]: 可选字段列表
    """
    schema = TYPE_SCHEMA_MAP.get(strategy_type, {})
    return [
        field_name
        for field_name, field_schema in schema.items()
        if not field_schema.get("required", False)
    ]
