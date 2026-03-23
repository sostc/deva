"""Stage 基类 - Pipe-and-Filter 模式的基础组件"""

import pandas as pd
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List
from collections import defaultdict


logger = logging.getLogger(__name__)


class StageType(Enum):
    """Stage 类型"""
    SOURCE = "source"           # 数据源
    ENRICH = "enrich"          # 数据增强/合并
    FILTER = "filter"          # 过滤
    TRANSFORM = "transform"     # 转换
    AGGREGATE = "aggregate"     # 聚合
    DISTRIBUTE = "distribute"   # 分发


class StageStatus(Enum):
    """Stage 状态"""
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class StageResult:
    """Stage 执行结果"""
    success: bool
    data: Optional[pd.DataFrame] = None
    error: Optional[str] = None
    warning: Optional[str] = None
    stage_name: str = ""
    stage_type: StageType = StageType.TRANSFORM
    duration_ms: float = 0.0
    rows_in: int = 0
    rows_out: int = 0
    rows_filtered: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.success and self.error is None

    def __str__(self) -> str:
        status = "✓" if self.passed else "✗"
        if self.warning:
            status = "⚠"
        return f"{status} {self.stage_name}: {self.rows_in}→{self.rows_out} ({self.duration_ms:.1f}ms)"


class Stage(ABC):
    """
    Pipeline Stage 基类

    所有数据处理阶段都继承自此类

    设计原则:
    1. 单一职责：每个 Stage 只做一件事
    2. 失败安全：出错时返回上游数据，不中断管道
    3. 可追踪：记录处理统计信息
    4. 可配置：支持启用/禁用
    """

    def __init__(
        self,
        name: str,
        stage_type: StageType = StageType.TRANSFORM,
        enabled: bool = True,
        required: bool = False,
    ):
        self.name = name
        self.stage_type = stage_type
        self.enabled = enabled
        self.required = required

        self._status = StageStatus.IDLE
        self._stats = {
            'exec_count': 0,
            'success_count': 0,
            'warning_count': 0,
            'error_count': 0,
            'total_duration_ms': 0.0,
            'rows_processed': 0,
            'rows_filtered': 0,
        }

        self._last_result: Optional[StageResult] = None

    @abstractmethod
    def _process(self, data: pd.DataFrame, context: Optional[Dict[str, Any]] = None) -> StageResult:
        """
        实际处理逻辑（子类实现）

        Args:
            data: 输入数据
            context: 可选的上下文信息

        Returns:
            StageResult: 处理结果
        """
        pass

    def process(
        self,
        data: pd.DataFrame,
        context: Optional[Dict[str, Any]] = None
    ) -> StageResult:
        """
        处理数据（入口方法）

        - 检查启用状态
        - 计时
        - 调用子类实现
        - 记录统计
        """
        if not self.enabled:
            return StageResult(
                success=True,
                data=data,
                stage_name=self.name,
                stage_type=self.stage_type,
                rows_in=len(data),
                rows_out=len(data),
                metadata={'skipped': True, 'reason': 'disabled'}
            )

        start_time = time.time()
        self._status = StageStatus.RUNNING

        try:
            result = self._process(data, context)
            result.stage_name = self.name
            result.stage_type = self.stage_type

            duration = (time.time() - start_time) * 1000
            result.duration_ms = duration
            result.rows_in = len(data)
            if result.data is not None:
                result.rows_out = len(result.data)
            else:
                result.rows_out = 0

            self._update_stats(result)
            self._last_result = result

            if not result.passed:
                self._status = StageStatus.ERROR
                logger.error(f"[{self.name}] 处理失败: {result.error}")
            elif result.warning:
                self._status = StageStatus.WARNING
                logger.warning(f"[{self.name}] 处理有警告: {result.warning}")
            else:
                self._status = StageStatus.SUCCESS

            return result

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self._status = StageStatus.ERROR

            result = StageResult(
                success=False,
                data=data,
                error=str(e),
                stage_name=self.name,
                stage_type=self.stage_type,
                duration_ms=duration,
                rows_in=len(data),
                rows_out=0,
            )
            self._update_stats(result)
            self._last_result = result

            logger.exception(f"[{self.name}] 处理异常: {e}")

            if self.required:
                raise

            return result

    def _update_stats(self, result: StageResult):
        """更新统计信息"""
        self._stats['exec_count'] += 1
        self._stats['total_duration_ms'] += result.duration_ms

        if result.passed:
            self._stats['success_count'] += 1
            self._stats['rows_processed'] += result.rows_out
            self._stats['rows_filtered'] += result.rows_filtered
        elif result.warning:
            self._stats['warning_count'] += 1
        else:
            self._stats['error_count'] += 1

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        avg_duration = (
            self._stats['total_duration_ms'] / self._stats['exec_count']
            if self._stats['exec_count'] > 0 else 0
        )
        return {
            **self._stats,
            'avg_duration_ms': avg_duration,
            'status': self._status.value,
            'last_result': str(self._last_result) if self._last_result else None,
        }

    def reset_stats(self):
        """重置统计"""
        self._stats = {
            'exec_count': 0,
            'success_count': 0,
            'warning_count': 0,
            'error_count': 0,
            'total_duration_ms': 0.0,
            'rows_processed': 0,
            'rows_filtered': 0,
        }
        self._last_result = None

    @property
    def is_healthy(self) -> bool:
        """是否健康"""
        return (
            self._status in (StageStatus.SUCCESS, StageStatus.WARNING, StageStatus.IDLE)
            and self.enabled
        )

    def __repr__(self) -> str:
        return f"Stage({self.name}, type={self.stage_type.value}, status={self._status.value})"


class CompositeStage(Stage):
    """
    组合 Stage - 将多个 Stage 组合成一个

    用于将多个相关操作封装为一个逻辑阶段
    """

    def __init__(
        self,
        name: str,
        stages: List[Stage],
        stage_type: StageType = StageType.TRANSFORM,
        stop_on_error: bool = False,
    ):
        super().__init__(name=name, stage_type=stage_type)
        self.stages = stages
        self.stop_on_error = stop_on_error

    def _process(self, data: pd.DataFrame, context: Optional[Dict[str, Any]] = None) -> StageResult:
        """顺序执行所有子 Stage"""
        current_data = data
        total_filtered = 0
        warnings = []

        for stage in self.stages:
            result = stage.process(current_data, context)

            if not result.passed and self.stop_on_error:
                result.success = False
                result.error = f"{stage.name} failed: {result.error}"
                return result

            if result.warning:
                warnings.append(f"{stage.name}: {result.warning}")

            total_filtered += result.rows_filtered

            if result.data is not None:
                current_data = result.data
            elif not result.passed:
                break

        warning_msg = "; ".join(warnings) if warnings else None

        return StageResult(
            success=True,
            data=current_data,
            warning=warning_msg,
            rows_filtered=total_filtered,
        )

    def add_stage(self, stage: Stage):
        """添加子 Stage"""
        self.stages.append(stage)

    def get_stats(self) -> Dict[str, Any]:
        """获取所有子 Stage 的统计"""
        stats = super().get_stats()
        stats['stages'] = {
            s.name: s.get_stats() for s in self.stages
        }
        return stats


__all__ = ['Stage', 'StageResult', 'StageType', 'StageStatus', 'CompositeStage']
