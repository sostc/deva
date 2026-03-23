"""PipelineManager - 管道管理器"""

import pandas as pd
import logging
import time
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field

from .base import Stage, StageResult, StageType

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Pipeline 配置"""
    name: str = "default"
    stop_on_error: bool = False
    enable_stats: bool = True
    enable_quality_gate: bool = True
    quality_gate_config: Optional[Dict[str, Any]] = None


class PipelineManager:
    """
    Pipeline 管理器 - 统一管理数据流

    功能:
    1. 按顺序执行所有 Stage
    2. 支持 Stage 启用/禁用
    3. 收集和聚合统计信息
    4. 失败安全（可选）

    设计:
    - 单一数据流入口
    - 每个 Stage 的输出传给下一个 Stage
    - Stage 出错时可选停止或跳过
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.name = self.config.name

        self._stages: List[Stage] = []
        self._stage_map: Dict[str, Stage] = {}

        self._total_stats = {
            'total_executions': 0,
            'total_rows_processed': 0,
            'total_rows_filtered': 0,
            'total_errors': 0,
            'total_warnings': 0,
            'total_duration_ms': 0.0,
        }

        self._last_execution_result: Optional[StageResult] = None

    def add_stage(self, stage: Stage, position: Optional[int] = None) -> "PipelineManager":
        """
        添加 Stage

        Args:
            stage: 要添加的 Stage
            position: 可选的位置，默认添加到末尾

        Returns:
            self（支持链式调用）
        """
        if stage.name in self._stage_map:
            raise ValueError(f"Stage name '{stage.name}' already exists")

        if position is None or position >= len(self._stages):
            self._stages.append(stage)
        else:
            self._stages.insert(position, stage)

        self._stage_map[stage.name] = stage
        return self

    def remove_stage(self, name: str) -> bool:
        """移除 Stage"""
        if name not in self._stage_map:
            return False

        stage = self._stage_map[name]
        self._stages.remove(stage)
        del self._stage_map[name]
        return True

    def get_stage(self, name: str) -> Optional[Stage]:
        """获取 Stage"""
        return self._stage_map.get(name)

    def has_stage(self, name: str) -> bool:
        """检查是否存在 Stage"""
        return name in self._stage_map

    def execute(
        self,
        data: pd.DataFrame,
        context: Optional[Dict[str, Any]] = None,
    ) -> StageResult:
        """
        执行 Pipeline

        Args:
            data: 输入数据
            context: 可选的上下文信息

        Returns:
            StageResult: 最后一个 Stage 的结果
        """
        if data is None or not isinstance(data, pd.DataFrame):
            logger.error(f"[{self.name}] 输入数据无效: {type(data)}")
            return StageResult(
                success=False,
                error=f"Invalid input data: {type(data)}",
                stage_name=self.name,
            )

        if not self._stages:
            logger.warning(f"[{self.name}] 没有配置任何 Stage")
            return StageResult(
                success=True,
                data=data,
                rows_in=len(data),
                rows_out=len(data),
                stage_name=self.name,
            )

        start_time = time.time()
        self._total_stats['total_executions'] += 1

        current_data = data
        current_result: Optional[StageResult] = None
        total_filtered = 0
        errors = []
        warnings = []

        for stage in self._stages:
            if not stage.enabled:
                logger.debug(f"[{self.name}] 跳过禁用的 Stage: {stage.name}")
                continue

            try:
                result = stage.process(current_data, context)
                current_result = result

                if not result.passed:
                    errors.append(f"{stage.name}: {result.error}")
                    if self.config.stop_on_error:
                        break

                if result.warning:
                    warnings.append(f"{stage.name}: {result.warning}")

                total_filtered += result.rows_filtered

                if result.data is not None:
                    current_data = result.data
                else:
                    break

            except Exception as e:
                logger.exception(f"[{self.name}] Stage {stage.name} 异常: {e}")
                errors.append(f"{stage.name}: {str(e)}")
                if self.config.stop_on_error:
                    break

        duration_ms = (time.time() - start_time) * 1000
        self._total_stats['total_duration_ms'] += duration_ms

        final_result = StageResult(
            success=len(errors) == 0,
            data=current_data if current_data is not None else data,
            error="; ".join(errors) if errors else None,
            warning="; ".join(warnings) if warnings else None,
            duration_ms=duration_ms,
            rows_in=len(data),
            rows_out=len(current_data) if current_data is not None else 0,
            rows_filtered=total_filtered,
            stage_name=self.name,
            metadata={
                'stage_count': len(self._stages),
                'enabled_count': sum(1 for s in self._stages if s.enabled),
                'executed_stages': [
                    {
                        'name': s.name,
                        'type': s.stage_type.value,
                        'success': s.get_stats().get('success_count', 0) > 0,
                    }
                    for s in self._stages if s.enabled
                ],
            }
        )

        self._last_execution_result = final_result

        self._update_total_stats(final_result)

        if final_result.passed:
            if warnings:
                final_result.warning = "; ".join(warnings)
                logger.info(f"[{self.name}] Pipeline 完成 (有警告): {len(warnings)} 个")
            else:
                logger.debug(f"[{self.name}] Pipeline 完成: {final_result.rows_in}→{final_result.rows_out}")
        else:
            logger.error(f"[{self.name}] Pipeline 失败: {errors}")

        return final_result

    def _update_total_stats(self, result: StageResult):
        """更新总统计"""
        self._total_stats['total_rows_processed'] += result.rows_out
        self._total_stats['total_rows_filtered'] += result.rows_filtered

        if not result.passed:
            self._total_stats['total_errors'] += 1
        elif result.warning:
            self._total_stats['total_warnings'] += 1

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'pipeline': self.name,
            'config': {
                'stop_on_error': self.config.stop_on_error,
                'stage_count': len(self._stages),
                'enabled_count': sum(1 for s in self._stages if s.enabled),
            },
            'total': self._total_stats.copy(),
            'stages': {
                name: stage.get_stats()
                for name, stage in self._stage_map.items()
            },
            'last_execution': (
                str(self._last_execution_result)
                if self._last_execution_result else None
            ),
        }

    def reset_stats(self):
        """重置统计"""
        self._total_stats = {
            'total_executions': 0,
            'total_rows_processed': 0,
            'total_rows_filtered': 0,
            'total_errors': 0,
            'total_warnings': 0,
            'total_duration_ms': 0.0,
        }
        for stage in self._stages:
            stage.reset_stats()

    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        healthy = True
        issues = []

        for stage in self._stages:
            if not stage.is_healthy:
                healthy = False
                issues.append(f"{stage.name}: {stage.get_stats().get('error_count', 0)} errors")

        return {
            'healthy': healthy,
            'pipeline': self.name,
            'stage_count': len(self._stages),
            'enabled_count': sum(1 for s in self._stages if s.enabled),
            'issues': issues,
        }

    def __repr__(self) -> str:
        return f"PipelineManager({self.name}, stages={len(self._stages)})"


def create_default_pipeline(
    enable_enrich: bool = True,
    enable_filter: bool = True,
    **kwargs
) -> PipelineManager:
    """
    创建默认 Pipeline

    默认顺序: Enrich -> Filter
    """
    from .enrich_stage import EnrichStage
    from .filter_stage import FilterStage

    config = PipelineConfig(
        name="default_attention",
        stop_on_error=False,
        enable_stats=True,
    )

    pipeline = PipelineManager(config)

    if enable_enrich:
        enrich_stage = EnrichStage(
            name="enrich_sector",
            **kwargs
        )
        pipeline.add_stage(enrich_stage)

    if enable_filter:
        filter_stage = FilterStage(
            name="filter_noise",
            **kwargs
        )
        pipeline.add_stage(filter_stage)

    return pipeline


__all__ = ['PipelineManager', 'PipelineConfig', 'create_default_pipeline']
