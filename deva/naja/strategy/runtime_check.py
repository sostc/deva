"""策略运行时类型检查

提供策略运行时的类型检查功能:
- 输入数据验证
- 输出信号验证
- 策略状态检查
- 性能指标监控

使用方式:
    from deva.naja.strategy.runtime_check import (
        RuntimeTypeChecker,
        check_strategy_input,
        check_strategy_output,
    )
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type


class CheckLevel(Enum):
    """检查级别"""

    DISABLED = "disabled"
    WARNING = "warning"
    STRICT = "strict"


class DataType(Enum):
    """数据类型"""

    DICT = "dict"
    LIST = "list"
    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    NONE = "none"
    ANY = "any"


@dataclass
class TypeRule:
    """类型规则"""

    input_types: List[DataType] = field(default_factory=list)
    output_type: Optional[DataType] = None
    feature_key: Optional[str] = None
    label_key: Optional[str] = None


@dataclass
class CheckResult:
    """检查结果"""

    passed: bool
    message: str
    details: Optional[Dict] = None


@dataclass
class RuntimeStats:
    """运行时统计"""

    total_calls: int = 0
    total_errors: int = 0
    last_check_time: float = 0
    avg_process_time_ms: float = 0
    error_rate: float = 0


DEFAULT_TYPE_RULES: Dict[str, TypeRule] = {
    "river": TypeRule(
        input_types=[DataType.DICT, DataType.ANY],
        output_type=DataType.DICT,
    ),
    "plugin": TypeRule(
        input_types=[DataType.DICT, DataType.LIST, DataType.ANY],
        output_type=DataType.ANY,
    ),
    "declarative": TypeRule(
        input_types=[DataType.DICT, DataType.ANY],
        output_type=DataType.ANY,
    ),
    "legacy": TypeRule(
        input_types=[DataType.ANY],
        output_type=DataType.ANY,
    ),
}


class RuntimeTypeChecker:
    """运行时类型检查器"""

    def __init__(
        self,
        strategy_type: str,
        level: CheckLevel = CheckLevel.WARNING,
        rules: Optional[Dict[str, TypeRule]] = None,
    ):
        self.strategy_type = strategy_type
        self.level = level
        self.rules = rules or DEFAULT_TYPE_RULES
        self.stats = RuntimeStats()
        self._last_process_time = 0

    def _detect_type(self, value: Any) -> DataType:
        """检测数据类型"""
        if value is None:
            return DataType.NONE
        if isinstance(value, dict):
            return DataType.DICT
        if isinstance(value, list):
            return DataType.LIST
        if isinstance(value, bool):
            return DataType.BOOL
        if isinstance(value, int):
            return DataType.INT
        if isinstance(value, float):
            return DataType.FLOAT
        if isinstance(value, str):
            return DataType.STR
        return DataType.ANY

    def check_input(self, data: Any) -> CheckResult:
        """检查输入数据"""
        if self.level == CheckLevel.DISABLED:
            return CheckResult(passed=True, message="检查已禁用")

        rule = self.rules.get(self.strategy_type)
        if rule is None:
            return CheckResult(passed=True, message="无类型规则")

        detected_type = self._detect_type(data)

        if not rule.input_types:
            return CheckResult(passed=True, message="无输入类型限制")

        if DataType.ANY in rule.input_types:
            return CheckResult(passed=True, message="接受任意类型")

        if detected_type not in rule.input_types:
            msg = (
                f"输入类型不匹配: 期望 {([t.value for t in rule.input_types])}，"
                f"实际 {detected_type.value}"
            )
            if self.level == CheckLevel.STRICT:
                return CheckResult(passed=False, message=msg)
            return CheckResult(passed=True, message=f"警告: {msg}")

        return CheckResult(passed=True, message="输入类型检查通过")

    def check_output(self, signal: Any) -> CheckResult:
        """检查输出信号"""
        if self.level == CheckLevel.DISABLED:
            return CheckResult(passed=True, message="检查已禁用")

        rule = self.rules.get(self.strategy_type)
        if rule is None or rule.output_type is None:
            return CheckResult(passed=True, message="无输出类型限制")

        detected_type = self._detect_type(signal)

        if rule.output_type == DataType.ANY:
            return CheckResult(passed=True, message="接受任意输出类型")

        if detected_type != rule.output_type:
            msg = (
                f"输出类型不匹配: 期望 {rule.output_type.value}，"
                f"实际 {detected_type.value}"
            )
            if self.level == CheckLevel.STRICT:
                return CheckResult(passed=False, message=msg)
            return CheckResult(passed=True, message=f"警告: {msg}")

        return CheckResult(passed=True, message="输出类型检查通过")

    def check_signal_structure(self, signal: Any) -> CheckResult:
        """检查信号结构"""
        if self.level == CheckLevel.DISABLED:
            return CheckResult(passed=True, message="检查已禁用")

        if not isinstance(signal, dict):
            if self.level == CheckLevel.STRICT:
                return CheckResult(passed=False, message="信号应为字典类型")
            return CheckResult(passed=True, message="警告: 信号应为字典")

        required_fields = ["signal"]
        missing = [f for f in required_fields if f not in signal]

        if missing:
            msg = f"信号缺少必要字段: {missing}"
            if self.level == CheckLevel.STRICT:
                return CheckResult(passed=False, message=msg)
            return CheckResult(passed=True, message=f"警告: {msg}")

        return CheckResult(passed=True, message="信号结构检查通过")

    def record_call(self, process_time_ms: float, error: bool = False) -> None:
        """记录调用"""
        self.stats.total_calls += 1
        if error:
            self.stats.total_errors += 1

        alpha = 0.1
        self.stats.avg_process_time_ms = (
            alpha * process_time_ms
            + (1 - alpha) * self.stats.avg_process_time_ms
        )

        if self.stats.total_calls > 0:
            self.stats.error_rate = self.stats.total_errors / self.stats.total_calls

        self.stats.last_check_time = time.time()

    def get_stats(self) -> RuntimeStats:
        """获取统计信息"""
        return self.stats

    def reset_stats(self) -> None:
        """重置统计"""
        self.stats = RuntimeStats()


def check_strategy_input(
    strategy_type: str,
    data: Any,
    level: CheckLevel = CheckLevel.WARNING,
) -> CheckResult:
    """便捷函数：检查策略输入"""
    checker = RuntimeTypeChecker(strategy_type, level)
    return checker.check_input(data)


def check_strategy_output(
    strategy_type: str,
    signal: Any,
    level: CheckLevel = CheckLevel.WARNING,
) -> CheckResult:
    """便捷函数：检查策略输出"""
    checker = RuntimeTypeChecker(strategy_type, level)
    result = checker.check_output(signal)
    if result.passed and isinstance(signal, dict):
        result = checker.check_signal_structure(signal)
    return result


def create_checker(
    strategy_type: str,
    level: CheckLevel = CheckLevel.WARNING,
    custom_rules: Optional[Dict[str, TypeRule]] = None,
) -> RuntimeTypeChecker:
    """创建类型检查器"""
    rules = {**DEFAULT_TYPE_RULES, **(custom_rules or {})}
    return RuntimeTypeChecker(strategy_type, level, rules)
