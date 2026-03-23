"""StrategyProcessStage - 策略处理阶段"""

import logging
import time
import asyncio
import concurrent.futures
from typing import Optional, Dict, Any, Callable

from .base import Stage, StageResult, StageType

logger = logging.getLogger(__name__)


class StrategyProcessStage(Stage):
    """
    策略处理阶段 - 执行用户定义的策略函数

    支持:
    - 同步函数
    - 异步函数（自动检测并正确执行）
    - 窗口处理模式
    - 记录处理统计

    设计:
    - 失败安全：处理失败不影响数据流
    - 支持异步：自动处理 asyncio 协程
    - 性能监控：记录处理时间和结果
    """

    def __init__(
        self,
        name: str = "strategy_process",
        process_func: Optional[Callable] = None,
        compute_mode: str = "record",
        window_type: str = "sliding",
        timeout: float = 30.0,
    ):
        super().__init__(name=name, stage_type=StageType.TRANSFORM)
        self.process_func = process_func
        self.compute_mode = compute_mode
        self.window_type = window_type
        self.timeout = timeout

        self._stats['process_count'] = 0
        self._stats['success_count'] = 0
        self._stats['error_count'] = 0
        self._stats['total_duration_ms'] = 0

    def set_process_func(self, func: Callable):
        """设置处理函数"""
        self.process_func = func

    def _process(self, data: Any, context: Optional[Dict[str, Any]] = None) -> StageResult:
        """执行策略处理"""
        if self.process_func is None:
            return StageResult(
                success=True,
                data=data,
                rows_in=0,
                rows_out=0,
                metadata={'skipped': True, 'reason': 'no_process_func'}
            )

        start_time = time.time()
        self._stats['process_count'] += 1

        try:
            if self.compute_mode == "window":
                result = self._process_window(data, context)
            else:
                result = self._process_record(data, context)

            duration_ms = (time.time() - start_time) * 1000
            self._stats['total_duration_ms'] += duration_ms

            if result is not None:
                self._stats['success_count'] += 1
                return StageResult(
                    success=True,
                    data=result,
                    rows_in=1,
                    rows_out=1,
                    duration_ms=duration_ms,
                    metadata={
                        'process': True,
                        'result_type': type(result).__name__,
                    }
                )
            else:
                return StageResult(
                    success=True,
                    data=data,
                    rows_in=1,
                    rows_out=0,
                    duration_ms=duration_ms,
                    metadata={'skipped': True, 'reason': 'window_not_ready'}
                )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._stats['error_count'] += 1
            self._stats['total_duration_ms'] += duration_ms

            logger.exception(f"[{self.name}] 处理失败: {e}")

            return StageResult(
                success=False,
                data=data,
                error=str(e),
                rows_in=1,
                rows_out=0,
                duration_ms=duration_ms,
            )

    def _process_record(self, data: Any, context: Optional[Dict[str, Any]]) -> Any:
        """处理单条记录"""
        try:
            result = self._call_func(self.process_func, data, context)
            return result
        except Exception as e:
            logger.exception(f"[{self.name}] _process_record 失败: {e}")
            raise

    def _process_window(self, data: Any, context: Optional[Dict[str, Any]]) -> Any:
        """处理窗口数据"""
        try:
            result = self._call_func(self.process_func, data, context)
            return result
        except Exception as e:
            logger.exception(f"[{self.name}] _process_window 失败: {e}")
            raise

    def _call_func(self, func: Callable, data: Any, context: Optional[Dict[str, Any]]) -> Any:
        """调用处理函数，自动处理同步/异步"""
        import inspect

        if inspect.iscoroutinefunction(func):
            return self._call_async_func(func, data, context)
        else:
            return func(data, context)

    def _call_async_func(self, func: Callable, data: Any, context: Optional[Dict[str, Any]]) -> Any:
        """调用异步处理函数"""
        try:
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, func(data, context))
                return future.result(timeout=self.timeout)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(func(data, context))
            finally:
                loop.close()
        except Exception as e:
            logger.exception(f"[{self.name}] 异步调用失败: {e}")
            raise

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = super().get_stats()
        stats['avg_duration_ms'] = (
            stats['total_duration_ms'] / stats['process_count']
            if stats['process_count'] > 0 else 0
        )
        return stats


__all__ = ['StrategyProcessStage']
