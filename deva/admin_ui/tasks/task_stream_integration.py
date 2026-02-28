"""任务流处理集成(Task Stream Processing Integration)

为任务模块提供流处理能力，支持任务间的数据流转和实时处理。

================================================================================
功能特性
================================================================================

1. **任务流集成**: 任务可以作为流的生产者和消费者
2. **数据流转**: 支持任务间的数据传递和转换
3. **实时处理**: 支持实时数据流处理
4. **背压处理**: 流量控制和背压机制
5. **流式监控**: 实时任务执行监控
6. **事件驱动**: 基于事件的任务触发机制
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Union
from datetime import datetime

from deva import Stream, NS, log

from .stream_utils import StreamWrapper, StreamManager, StreamRole
from .task_unit import TaskUnit, TaskType, TaskStatus
from .task_manager import TaskManager


class TaskStreamWrapper(StreamWrapper):
    """任务流包装器
    
    扩展StreamWrapper，专门为任务流处理提供增强功能
    """
    
    def __init__(
        self,
        stream: Stream,
        task_unit: TaskUnit,
        role: StreamRole,
        cache_size: int = 100,
        enable_metrics: bool = True,
        auto_process: bool = True
    ):
        """
        Args:
            stream: 原始流对象
            task_unit: 关联的任务单元
            role: 流角色 (input/output/internal)
            cache_size: 缓存大小
            enable_metrics: 是否启用指标收集
            auto_process: 是否自动处理流数据
        """
        super().__init__(
            stream=stream,
            name=f"{task_unit.name}_{role.value}",
            role=role,
            cache_size=cache_size,
            enable_metrics=enable_metrics,
            error_handler=self._handle_stream_error
        )
        
        self.task_unit = task_unit
        self.auto_process = auto_process
        self._processing_task: Optional[asyncio.Task] = None
        self._stop_event = threading.Event()
        
        # 任务特定的指标
        self._task_metrics = {
            "processed_count": 0,
            "processing_errors": 0,
            "last_process_time": 0,
            "avg_process_time": 0
        }
    
    # ==========================================================================
    # 任务流处理方法
    # ==========================================================================
    
    async def process_stream_data(self, data: Any) -> Any:
        """处理流数据
        
        Args:
            data: 流数据
            
        Returns:
            处理结果
        """
        start_time = time.time()
        
        try:
            # 检查任务状态
            if not self.task_unit.is_running:
                log.warning(f"任务 {self.task_unit.name} 未运行，跳过流数据处理")
                return None
            
            # 调用任务的处理逻辑
            if self.task_unit._func:
                # 构建处理上下文
                context = {
                    "stream_data": data,
                    "task_id": self.task_unit.id,
                    "task_name": self.task_unit.name,
                    "stream_name": self.name,
                    "process_time": datetime.now().isoformat()
                }
                
                # 执行任务函数
                result = await self.task_unit._func(context)
                
                # 更新指标
                process_time = time.time() - start_time
                self._update_task_metrics(process_time)
                
                log.debug(f"任务流数据处理完成: {self.task_unit.name} (耗时: {process_time:.3f}s)")
                
                return result
            else:
                log.warning(f"任务 {self.task_unit.name} 没有可执行的函数")
                return None
                
        except Exception as e:
            # 更新错误指标
            self._task_metrics["processing_errors"] += 1
            
            # 使用统一的错误处理
            self.task_unit.error_handler.handle_error(
                e,
                context=f"流数据处理失败: {self.name}",
                data=data
            )
            
            # 重新抛出异常，让上游处理
            raise
    
    def start_auto_processing(self):
        """启动自动流处理"""
        if not self.auto_process:
            return
        
        if self.role == StreamRole.INPUT and self.task_unit.is_running:
            # 启动异步处理任务
            self._processing_task = asyncio.create_task(self._auto_process_input_stream())
            log.info(f"任务流自动处理已启动: {self.name}")
    
    def stop_auto_processing(self):
        """停止自动流处理"""
        self._stop_event.set()
        
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
            
        log.info(f"任务流自动处理已停止: {self.name}")
    
    async def _auto_process_input_stream(self):
        """自动处理输入流"""
        try:
            while not self._stop_event.is_set() and self.task_unit.is_running:
                try:
                    # 从流接收数据
                    data = self.receive(timeout=1.0)
                    
                    if data is not None:
                        # 处理数据
                        result = await self.process_stream_data(data)
                        
                        # 如果有输出流，发送结果
                        if result is not None:
                            await self._send_to_output_streams(result)
                    
                    # 短暂休眠，避免CPU占用过高
                    await asyncio.sleep(0.01)
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.error(f"任务流自动处理错误: {self.name} - {e}")
                    await asyncio.sleep(1.0)  # 错误后等待
                    
        except Exception as e:
            log.error(f"任务流自动处理任务异常终止: {self.name} - {e}")
    
    async def _send_to_output_streams(self, data: Any):
        """发送数据到输出流
        
        Args:
            data: 要发送的数据
        """
        # 获取任务管理器
        task_manager = self._get_task_manager()
        if not task_manager:
            return
        
        # 获取任务的所有输出流
        output_streams = task_manager.get_task_output_streams(self.task_unit.id)
        
        for stream_wrapper in output_streams:
            try:
                stream_wrapper.emit(data)
                log.debug(f"数据已发送到输出流: {stream_wrapper.name}")
            except Exception as e:
                log.error(f"发送数据到输出流失败: {stream_wrapper.name} - {e}")
    
    def _update_task_metrics(self, process_time: float):
        """更新任务指标"""
        self._task_metrics["processed_count"] += 1
        self._task_metrics["last_process_time"] = process_time
        
        # 更新平均处理时间
        total_time = self._task_metrics["avg_process_time"] * (self._task_metrics["processed_count"] - 1) + process_time
        self._task_metrics["avg_process_time"] = total_time / self._task_metrics["processed_count"]
    
    def _handle_stream_error(self, error: Exception, operation: str, data: Any = None):
        """处理流错误"""
        log.error(f"任务流错误: {self.name} - 操作: {operation} - 错误: {error}")
        
        # 更新错误指标
        self._task_metrics["processing_errors"] += 1
        
        # 如果错误率过高，可以暂停自动处理
        error_rate = self._task_metrics["processing_errors"] / max(self._task_metrics["processed_count"], 1)
        if error_rate > 0.1:  # 错误率超过10%
            log.warning(f"任务流错误率过高，暂停自动处理: {self.name} (错误率: {error_rate:.2%})")
            self.stop_auto_processing()
    
    def get_task_metrics(self) -> Dict[str, Any]:
        """获取任务流指标"""
        stream_metrics = self.metrics.to_dict()
        task_metrics = self._task_metrics.copy()
        
        return {
            "stream_metrics": stream_metrics,
            "task_metrics": task_metrics,
            "error_rate": task_metrics["processing_errors"] / max(task_metrics["processed_count"], 1)
        }
    
    def _get_task_manager(self) -> Optional[TaskManager]:
        """获取任务管理器"""
        try:
            from .task_manager import get_task_manager
            return get_task_manager()
        except Exception:
            return None


class TaskStreamManager:
    """任务流管理器
    
    统一管理任务相关的流，支持任务间的数据流转
    """
    
    def __init__(self, stream_manager: StreamManager = None):
        """
        Args:
            stream_manager: 流管理器实例，如果为None则使用全局实例
        """
        self._stream_manager = stream_manager or StreamManager()
        self._task_streams: Dict[str, Dict[str, TaskStreamWrapper]] = {}  # task_id -> {stream_role -> stream}
        self._stream_tasks: Dict[str, str] = {}  # stream_name -> task_id
        self._lock = threading.Lock()
    
    # ==========================================================================
    # 任务流创建和管理
    # ==========================================================================
    
    def create_task_input_stream(
        self,
        task_unit: TaskUnit,
        stream_name: str = None,
        cache_size: int = 100,
        enable_metrics: bool = True,
        auto_process: bool = True
    ) -> TaskStreamWrapper:
        """创建任务输入流
        
        Args:
            task_unit: 任务单元
            stream_name: 流名称，如果为None则自动生成
            cache_size: 缓存大小
            enable_metrics: 是否启用指标收集
            auto_process: 是否自动处理流数据
            
        Returns:
            任务流包装器
        """
        if stream_name is None:
            stream_name = f"{task_unit.name}_input"
        
        # 创建基础流
        base_stream = NS(stream_name, cache_max_len=cache_size)
        
        # 创建任务流包装器
        task_stream = TaskStreamWrapper(
            stream=base_stream,
            task_unit=task_unit,
            role=StreamRole.INPUT,
            cache_size=cache_size,
            enable_metrics=enable_metrics,
            auto_process=auto_process
        )
        
        with self._lock:
            # 保存到管理器
            if task_unit.id not in self._task_streams:
                self._task_streams[task_unit.id] = {}
            self._task_streams[task_unit.id]["input"] = task_stream
            self._stream_tasks[stream_name] = task_unit.id
        
        log.info(f"任务输入流已创建: {stream_name} (任务: {task_unit.name})")
        return task_stream
    
    def create_task_output_stream(
        self,
        task_unit: TaskUnit,
        stream_name: str = None,
        cache_size: int = 100,
        enable_metrics: bool = True
    ) -> TaskStreamWrapper:
        """创建任务输出流
        
        Args:
            task_unit: 任务单元
            stream_name: 流名称，如果为None则自动生成
            cache_size: 缓存大小
            enable_metrics: 是否启用指标收集
            
        Returns:
            任务流包装器
        """
        if stream_name is None:
            stream_name = f"{task_unit.name}_output"
        
        # 创建基础流
        base_stream = NS(stream_name, cache_max_len=cache_size)
        
        # 创建任务流包装器
        task_stream = TaskStreamWrapper(
            stream=base_stream,
            task_unit=task_unit,
            role=StreamRole.OUTPUT,
            cache_size=cache_size,
            enable_metrics=enable_metrics,
            auto_process=False  # 输出流不自动处理
        )
        
        with self._lock:
            # 保存到管理器
            if task_unit.id not in self._task_streams:
                self._task_streams[task_unit.id] = {}
            self._task_streams[task_unit.id]["output"] = task_stream
            self._stream_tasks[stream_name] = task_unit.id
        
        log.info(f"任务输出流已创建: {stream_name} (任务: {task_unit.name})")
        return task_stream
    
    def create_task_internal_stream(
        self,
        task_unit: TaskUnit,
        stream_name: str = None,
        cache_size: int = 50,
        enable_metrics: bool = True
    ) -> TaskStreamWrapper:
        """创建任务内部流
        
        Args:
            task_unit: 任务单元
            stream_name: 流名称，如果为None则自动生成
            cache_size: 缓存大小
            enable_metrics: 是否启用指标收集
            
        Returns:
            任务流包装器
        """
        if stream_name is None:
            stream_name = f"{task_unit.name}_internal"
        
        # 创建基础流
        base_stream = NS(stream_name, cache_max_len=cache_size)
        
        # 创建任务流包装器
        task_stream = TaskStreamWrapper(
            stream=base_stream,
            task_unit=task_unit,
            role=StreamRole.INTERNAL,
            cache_size=cache_size,
            enable_metrics=enable_metrics,
            auto_process=False  # 内部流不自动处理
        )
        
        with self._lock:
            # 保存到管理器
            if task_unit.id not in self._task_streams:
                self._task_streams[task_unit.id] = {}
            self._task_streams[task_unit.id]["internal"] = task_stream
            self._stream_tasks[stream_name] = task_unit.id
        
        log.info(f"任务内部流已创建: {stream_name} (任务: {task_unit.name})")
        return task_stream
    
    def get_task_streams(self, task_id: str) -> Dict[str, TaskStreamWrapper]:
        """获取任务的所有流
        
        Args:
            task_id: 任务ID
            
        Returns:
            流字典 {role: stream}
        """
        with self._lock:
            return self._task_streams.get(task_id, {}).copy()
    
    def get_task_input_stream(self, task_id: str) -> Optional[TaskStreamWrapper]:
        """获取任务输入流
        
        Args:
            task_id: 任务ID
            
        Returns:
            输入流，不存在返回None
        """
        with self._lock:
            task_streams = self._task_streams.get(task_id, {})
            return task_streams.get("input")
    
    def get_task_output_stream(self, task_id: str) -> Optional[TaskStreamWrapper]:
        """获取任务输出流
        
        Args:
            task_id: 任务ID
            
        Returns:
            输出流，不存在返回None
        """
        with self._lock:
            task_streams = self._task_streams.get(task_id, {})
            return task_streams.get("output")
    
    def get_task_internal_stream(self, task_id: str) -> Optional[TaskStreamWrapper]:
        """获取任务内部流
        
        Args:
            task_id: 任务ID
            
        Returns:
            内部流，不存在返回None
        """
        with self._lock:
            task_streams = self._task_streams.get(task_id, {})
            return task_streams.get("internal")
    
    def remove_task_streams(self, task_id: str) -> bool:
        """移除任务的所有流
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功移除
        """
        with self._lock:
            if task_id not in self._task_streams:
                return False
            
            # 停止自动处理
            for stream_wrapper in self._task_streams[task_id].values():
                stream_wrapper.stop_auto_processing()
                stream_wrapper.close()
                
                # 从流任务映射中移除
                if stream_wrapper.name in self._stream_tasks:
                    del self._stream_tasks[stream_wrapper.name]
            
            # 移除任务流
            del self._task_streams[task_id]
            
            log.info(f"任务流已移除: 任务 {task_id}")
            return True
    
    # ==========================================================================
    # 任务流连接和流转
    # ==========================================================================
    
    def connect_tasks(
        self,
        source_task_id: str,
        target_task_id: str,
        transform_func: Callable[[Any], Any] = None,
        filter_func: Callable[[Any], bool] = None
    ) -> bool:
        """连接两个任务，建立数据流转
        
        Args:
            source_task_id: 源任务ID
            target_task_id: 目标任务ID
            transform_func: 数据转换函数
            filter_func: 数据过滤函数
            
        Returns:
            是否成功连接
        """
        try:
            # 获取源流和目標流
            source_output = self.get_task_output_stream(source_task_id)
            target_input = self.get_task_input_stream(target_task_id)
            
            if not source_output:
                log.error(f"源任务没有输出流: {source_task_id}")
                return False
            
            if not target_input:
                log.error(f"目标任务没有输入流: {target_task_id}")
                return False
            
            # 构建处理链
            def process_and_forward(data):
                try:
                    # 过滤
                    if filter_func and not filter_func(data):
                        return
                    
                    # 转换
                    if transform_func:
                        data = transform_func(data)
                    
                    # 转发到目标流
                    if data is not None:
                        target_input.emit(data)
                        
                except Exception as e:
                    log.error(f"任务流连接处理错误: {e}")
            
            # 订阅源流
            source_output.subscribe(process_and_forward)
            
            log.info(f"任务流连接已建立: {source_task_id} -> {target_task_id}")
            return True
            
        except Exception as e:
            log.error(f"连接任务流失败: {e}")
            return False
    
    def create_task_pipeline(
        self,
        task_ids: List[str],
        pipeline_name: str = None
    ) -> str:
        """创建任务处理管道
        
        Args:
            task_ids: 任务ID列表，按处理顺序排列
            pipeline_name: 管道名称，如果为None则自动生成
            
        Returns:
            管道名称
        """
        if not task_ids or len(task_ids) < 2:
            raise ValueError("任务管道至少需要2个任务")
        
        if pipeline_name is None:
            pipeline_name = f"pipeline_{'_'.join(task_ids)}"
        
        # 连接任务
        for i in range(len(task_ids) - 1):
            source_task = task_ids[i]
            target_task = task_ids[i + 1]
            
            success = self.connect_tasks(source_task, target_task)
            if not success:
                log.error(f"任务管道连接失败: {source_task} -> {target_task}")
                return ""
        
        log.info(f"任务管道已创建: {pipeline_name} (任务数: {len(task_ids)})")
        return pipeline_name
    
    # ==========================================================================
    # 事件驱动任务触发
    # ==========================================================================
    
    def create_event_triggered_task(
        self,
        task_unit: TaskUnit,
        event_stream: Stream,
        trigger_condition: Callable[[Any], bool] = None
    ) -> bool:
        """创建事件触发的任务
        
        Args:
            task_unit: 任务单元
            event_stream: 事件流
            trigger_condition: 触发条件函数
            
        Returns:
            是否成功创建
        """
        try:
            def event_handler(event_data):
                try:
                    # 检查触发条件
                    if trigger_condition and not trigger_condition(event_data):
                        return
                    
                    # 检查任务状态
                    if not task_unit.is_running:
                        log.warning(f"事件触发任务未运行，跳过: {task_unit.name}")
                        return
                    
                    # 构建执行上下文
                    context = {
                        "event_data": event_data,
                        "trigger_time": datetime.now().isoformat(),
                        "trigger_type": "event",
                        "task_id": task_unit.id,
                        "task_name": task_unit.name
                    }
                    
                    # 异步执行任务
                    asyncio.create_task(task_unit.execute_task(context))
                    
                    log.info(f"事件触发任务执行: {task_unit.name}")
                    
                except Exception as e:
                    log.error(f"事件触发任务处理错误: {task_unit.name} - {e}")
            
            # 订阅事件流
            event_stream.subscribe(event_handler)
            
            log.info(f"事件触发任务已创建: {task_unit.name}")
            return True
            
        except Exception as e:
            log.error(f"创建事件触发任务失败: {e}")
            return False
    
    # ==========================================================================
    # 流式监控和指标
    # ==========================================================================
    
    def get_task_stream_metrics(self, task_id: str) -> Dict[str, Any]:
        """获取任务流指标
        
        Args:
            task_id: 任务ID
            
        Returns:
            流指标字典
        """
        task_streams = self.get_task_streams(task_id)
        metrics = {}
        
        for role, stream_wrapper in task_streams.items():
            metrics[role] = stream_wrapper.get_task_metrics()
        
        return {
            "task_id": task_id,
            "streams": metrics,
            "total_streams": len(task_streams)
        }
    
    def get_all_task_stream_metrics(self) -> Dict[str, Any]:
        """获取所有任务流指标"""
        all_metrics = {}
        
        with self._lock:
            for task_id in self._task_streams.keys():
                all_metrics[task_id] = self.get_task_stream_metrics(task_id)
        
        return {
            "total_tasks": len(all_metrics),
            "task_metrics": all_metrics,
            "summary": {
                "total_streams": sum(len(metrics["streams"]) for metrics in all_metrics.values()),
                "total_processed": sum(
                    sum(stream_metrics.get("task_metrics", {}).get("processed_count", 0) 
                        for stream_metrics in metrics["streams"].values())
                    for metrics in all_metrics.values()
                )
            }
        }
    
    # ==========================================================================
    # 工具方法
    # ==========================================================================
    
    def start_all_task_streams(self):
        """启动所有任务流的自动处理"""
        with self._lock:
            for task_id, streams in self._task_streams.items():
                for stream_wrapper in streams.values():
                    if stream_wrapper.role == StreamRole.INPUT:
                        stream_wrapper.start_auto_processing()
    
    def stop_all_task_streams(self):
        """停止所有任务流的自动处理"""
        with self._lock:
            for task_id, streams in self._task_streams.items():
                for stream_wrapper in streams.values():
                    stream_wrapper.stop_auto_processing()
    
    def remove_all_task_streams(self):
        """移除所有任务流"""
        with self._lock:
            task_ids = list(self._task_streams.keys())
            for task_id in task_ids:
                self.remove_task_streams(task_id)


# 全局任务流管理器实例
_global_task_stream_manager: Optional[TaskStreamManager] = None


def get_task_stream_manager() -> TaskStreamManager:
    """获取全局任务流管理器"""
    global _global_task_stream_manager
    if _global_task_stream_manager is None:
        _global_task_stream_manager = TaskStreamManager()
    return _global_task_stream_manager


def set_task_stream_manager(manager: TaskStreamManager):
    """设置全局任务流管理器"""
    global _global_task_stream_manager
    _global_task_stream_manager = manager