"""任务管理器(Task Manager)

继承自BaseManager，提供专业的任务生命周期管理、调度集成和统计功能。

================================================================================
功能特性
================================================================================

1. **统一生命周期管理**: 继承BaseManager的注册、启动、停止功能
2. **调度器集成**: 集成APScheduler进行专业任务调度
3. **错误处理**: 集成统一的错误收集和处理
4. **统计监控**: 提供详细的任务执行统计
5. **依赖管理**: 支持任务依赖关系和影响分析
6. **批量操作**: 支持批量启动、停止、删除任务
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Dict, List, Optional, Type
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.job import Job

from deva import log

from ..common.base import BaseManager
from ..strategy.logging_context import task_log, log_task_event
from .task_unit import TaskUnit, TaskMetadata, TaskState, TaskStats, TaskExecution, TaskType
from ..strategy.error_handler import get_global_error_collector, ErrorLevel, ErrorCategory
from ..strategy.persistence import get_global_persistence_manager


class TaskManager(BaseManager[TaskUnit]):
    """任务管理器
    
    继承自BaseManager，提供专业的任务管理功能
    """
    
    def __init__(self, scheduler: AsyncIOScheduler = None):
        """
        Args:
            scheduler: APScheduler调度器实例，如果为None则创建默认实例
        """
        super().__init__()
        
        # 调度器
        self._scheduler = scheduler or AsyncIOScheduler()
        self._scheduler_lock = threading.Lock()
        
        # 执行统计
        self._execution_stats = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "total_duration": 0,
            "avg_duration": 0
        }
        self._stats_lock = threading.Lock()
        
        # 错误收集器
        self._error_collector = get_global_error_collector()
        
        # 持久化管理器
        self._persistence = get_global_persistence_manager()
        
        # 依赖关系图
        self._dependency_graph: Dict[str, List[str]] = {}
        self._dependency_lock = threading.Lock()
        
        task_log("info", "任务管理器已初始化")
    
    # ==========================================================================
    # BaseManager方法重写
    # ==========================================================================
    
    def _on_registered(self, item: TaskUnit):
        """注册后回调"""
        super()._on_registered(item)
        
        # 保存到持久化存储
        try:
            self._persistence.save_unit("task", item.id, item.to_dict())
        except Exception as e:
            log.error(f"任务注册时持久化失败: {e}")
        
        log.info(f"任务已注册: {item.name} ({item.id})")
    
    def _on_unregistered(self, item: TaskUnit):
        """注销后回调"""
        super()._on_unregistered(item)
        
        # 从持久化存储删除
        try:
            self._persistence.delete_unit("task", item.id)
        except Exception as e:
            log.error(f"任务注销时删除持久化失败: {e}")
        
        # 清理依赖关系
        with self._dependency_lock:
            self._dependency_graph.pop(item.id, None)
            for deps in self._dependency_graph.values():
                if item.id in deps:
                    deps.remove(item.id)
        
        log.info(f"任务已注销: {item.name} ({item.id})")
    
    def _do_start(self, item: TaskUnit) -> dict:
        """执行启动"""
        try:
            # 调用任务单元的启动方法
            result = item.start()
            if not result["success"]:
                return result
            
            # 调度任务
            schedule_result = self._schedule_task(item)
            if not schedule_result["success"]:
                # 如果调度失败，回滚任务状态
                item.stop()
                return schedule_result
            
            log.info(f"任务已启动并调度: {item.name}")
            return {"success": True, "message": "任务启动并调度成功"}
            
        except Exception as e:
            error_msg = f"任务启动失败: {str(e)}"
            log.error(error_msg)
            return {"success": False, "error": error_msg, "traceback": traceback.format_exc()}
    
    def _do_stop(self, item: TaskUnit) -> dict:
        """执行停止"""
        try:
            # 取消调度
            unschedule_result = self._unschedule_task(item)
            if not unschedule_result["success"]:
                log.warning(f"任务取消调度失败: {item.name} - {unschedule_result.get('error')}")
            
            # 调用任务单元的停止方法
            result = item.stop()
            
            log.info(f"任务已停止: {item.name}")
            return result
            
        except Exception as e:
            error_msg = f"任务停止失败: {str(e)}"
            log.error(error_msg)
            return {"success": False, "error": error_msg, "traceback": traceback.format_exc()}
    
    # ==========================================================================
    # 任务调度相关方法
    # ==========================================================================
    
    def _schedule_task(self, task: TaskUnit) -> Dict[str, Any]:
        """调度任务
        
        Args:
            task: 任务单元
            
        Returns:
            {"success": bool, "error": str}
        """
        try:
            with self._scheduler_lock:
                if task.metadata.task_type == TaskType.INTERVAL:
                    # 间隔任务
                    interval = task.metadata.schedule_config.get("interval", 60)
                    job = self._scheduler.add_job(
                        self._execute_task_wrapper,
                        "interval",
                        seconds=interval,
                        args=[task],
                        id=task.id,
                        name=task.name,
                        max_instances=1,  # 防止任务重叠
                        coalesce=True,    # 合并错过的执行
                        misfire_grace_time=300  # 错过执行的宽限时间
                    )
                    
                elif task.metadata.task_type == TaskType.CRON:
                    # 定时任务
                    hour = task.metadata.schedule_config.get("hour", 0)
                    minute = task.metadata.schedule_config.get("minute", 0)
                    job = self._scheduler.add_job(
                        self._execute_task_wrapper,
                        "cron",
                        hour=hour,
                        minute=minute,
                        args=[task],
                        id=task.id,
                        name=task.name,
                        max_instances=1,
                        coalesce=True,
                        misfire_grace_time=300
                    )
                    
                elif task.metadata.task_type == TaskType.ONE_TIME:
                    # 一次性任务
                    run_date = task.metadata.schedule_config.get("run_date")
                    if run_date:
                        job = self._scheduler.add_job(
                            self._execute_task_wrapper,
                            "date",
                            run_date=run_date,
                            args=[task],
                            id=task.id,
                            name=task.name,
                            max_instances=1
                        )
                    else:
                        return {"success": False, "error": "一次性任务需要指定run_date"}
                
                else:
                    return {"success": False, "error": f"不支持的任务类型: {task.metadata.task_type}"}
                
                # 保存调度任务引用
                task._scheduler_job = job
                task._scheduler = self._scheduler
                
                log.info(f"任务已调度: {task.name} (类型: {task.metadata.task_type.value})")
                return {"success": True, "message": "任务调度成功"}
                
        except Exception as e:
            error_msg = f"任务调度失败: {str(e)}"
            log.error(error_msg)
            return {"success": False, "error": error_msg, "traceback": traceback.format_exc()}
    
    def _unschedule_task(self, task: TaskUnit) -> Dict[str, Any]:
        """取消任务调度
        
        Args:
            task: 任务单元
            
        Returns:
            {"success": bool, "error": str}
        """
        try:
            with self._scheduler_lock:
                # 从调度器中移除任务
                try:
                    self._scheduler.remove_job(task.id)
                except Exception as e:
                    # 任务可能不存在，这不是严重错误
                    log.warning(f"从调度器移除任务失败: {task.name} - {e}")
                
                # 清理任务引用
                task._scheduler_job = None
                task._scheduler = None
                
                log.info(f"任务调度已取消: {task.name}")
                return {"success": True, "message": "任务调度取消成功"}
                
        except Exception as e:
            error_msg = f"任务调度取消失败: {str(e)}"
            log.error(error_msg)
            return {"success": False, "error": error_msg, "traceback": traceback.format_exc()}
    
    async def _execute_task_wrapper(self, task: TaskUnit):
        """任务执行包装器
        
        Args:
            task: 任务单元
        """
        start_time = time.time()
        
        try:
            # 更新执行统计
            with self._stats_lock:
                self._execution_stats["total_executions"] += 1
            
            # 构建执行上下文
            context = self._build_execution_context(task)
            
            # 执行任务
            result = await task.execute_task(context)
            
            # 更新成功统计
            with self._stats_lock:
                self._execution_stats["successful_executions"] += 1
                duration = time.time() - start_time
                self._execution_stats["total_duration"] += duration
                total_success = self._execution_stats["successful_executions"]
                self._execution_stats["avg_duration"] = self._execution_stats["total_duration"] / total_success
            
            log.info(f"任务执行成功: {task.name} (耗时: {duration:.2f}s)")
            
        except Exception as e:
            # 更新失败统计
            with self._stats_lock:
                self._execution_stats["failed_executions"] += 1
            
            # 记录错误
            self._error_collector.add_error(
                error=e,
                unit_id=task.id,
                unit_name=task.name,
                unit_type="task",
                level=ErrorLevel.HIGH,
                category=ErrorCategory.CODE_EXECUTION,
                context="任务执行失败"
            )
            
            duration = time.time() - start_time
            log.error(f"任务执行失败: {task.name} (耗时: {duration:.2f}s) - {e}")
            
            # 重新抛出异常，让调度器处理重试逻辑
            raise
    
    def _build_execution_context(self, task: TaskUnit) -> Dict[str, Any]:
        """构建任务执行上下文
        
        Args:
            task: 任务单元
            
        Returns:
            执行上下文
        """
        return {
            "task_id": task.id,
            "task_name": task.name,
            "task_type": task.metadata.task_type.value,
            "scheduler": self._scheduler,
            "task_manager": self,
            "log": log,
            "current_time": datetime.now(),
            "retry_count": task._retry_count,
            "retry_interval": task._retry_interval
        }
    
    # ==========================================================================
    # 依赖管理相关方法
    # ==========================================================================
    
    def add_dependency(self, task_id: str, depends_on: str) -> Dict[str, Any]:
        """添加任务依赖
        
        Args:
            task_id: 任务ID
            depends_on: 依赖的任务ID
            
        Returns:
            {"success": bool, "error": str}
        """
        try:
            # 检查任务是否存在
            task = self.get(task_id)
            if not task:
                return {"success": False, "error": f"任务不存在: {task_id}"}
            
            depends_on_task = self.get(depends_on)
            if not depends_on_task:
                return {"success": False, "error": f"依赖的任务不存在: {depends_on}"}
            
            # 检查循环依赖
            if self._has_circular_dependency(task_id, depends_on):
                return {"success": False, "error": "添加依赖会导致循环依赖"}
            
            # 添加依赖
            with self._dependency_lock:
                if task_id not in self._dependency_graph:
                    self._dependency_graph[task_id] = []
                if depends_on not in self._dependency_graph[task_id]:
                    self._dependency_graph[task_id].append(depends_on)
            
            log.info(f"任务依赖已添加: {task_id} -> {depends_on}")
            return {"success": True, "message": "依赖添加成功"}
            
        except Exception as e:
            error_msg = f"添加任务依赖失败: {str(e)}"
            log.error(error_msg)
            return {"success": False, "error": error_msg}
    
    def remove_dependency(self, task_id: str, depends_on: str) -> Dict[str, Any]:
        """移除任务依赖
        
        Args:
            task_id: 任务ID
            depends_on: 依赖的任务ID
            
        Returns:
            {"success": bool, "error": str}
        """
        try:
            with self._dependency_lock:
                if task_id in self._dependency_graph and depends_on in self._dependency_graph[task_id]:
                    self._dependency_graph[task_id].remove(depends_on)
                    if not self._dependency_graph[task_id]:
                        del self._dependency_graph[task_id]
                    
                    log.info(f"任务依赖已移除: {task_id} -/> {depends_on}")
                    return {"success": True, "message": "依赖移除成功"}
                else:
                    return {"success": False, "error": "依赖关系不存在"}
                    
        except Exception as e:
            error_msg = f"移除任务依赖失败: {str(e)}"
            log.error(error_msg)
            return {"success": False, "error": error_msg}
    
    def get_dependencies(self, task_id: str) -> List[str]:
        """获取任务依赖
        
        Args:
            task_id: 任务ID
            
        Returns:
            依赖的任务ID列表
        """
        with self._dependency_lock:
            return self._dependency_graph.get(task_id, []).copy()
    
    def get_dependents(self, task_id: str) -> List[str]:
        """获取依赖此任务的任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            依赖此任务的任务ID列表
        """
        with self._dependency_lock:
            dependents = []
            for task, deps in self._dependency_graph.items():
                if task_id in deps:
                    dependents.append(task)
            return dependents
    
    def _has_circular_dependency(self, task_id: str, depends_on: str) -> bool:
        """检查是否存在循环依赖
        
        Args:
            task_id: 任务ID
            depends_on: 依赖的任务ID
            
        Returns:
            是否存在循环依赖
        """
        # 使用深度优先搜索检查循环依赖
        visited = set()
        
        def dfs(current_task: str) -> bool:
            if current_task == task_id:
                return True  # 发现循环依赖
            if current_task in visited:
                return False
            
            visited.add(current_task)
            
            deps = self._dependency_graph.get(current_task, [])
            for dep in deps:
                if dfs(dep):
                    return True
            
            visited.remove(current_task)
            return False
        
        return dfs(depends_on)
    
    # ==========================================================================
    # 统计和监控相关方法
    # ==========================================================================
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """获取执行统计"""
        with self._stats_lock:
            stats = self._execution_stats.copy()
            
            # 添加一些派生指标
            total = stats["total_executions"]
            if total > 0:
                stats["success_rate"] = stats["successful_executions"] / total
                stats["failure_rate"] = stats["failed_executions"] / total
            else:
                stats["success_rate"] = 0
                stats["failure_rate"] = 0
            
            return stats
    
    def get_task_stats(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取特定任务的统计
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务统计信息，不存在返回None
        """
        task = self.get(task_id)
        if not task:
            return None
        
        return {
            "task_info": task.to_dict(),
            "dependencies": self.get_dependencies(task_id),
            "dependents": self.get_dependents(task_id),
            "execution_stats": {
                "total_executions": task.stats.success_count + task.stats.failure_count,
                "successful_executions": task.stats.success_count,
                "failed_executions": task.stats.failure_count,
                "success_rate": task.stats.success_count / (task.stats.success_count + task.stats.failure_count) if (task.stats.success_count + task.stats.failure_count) > 0 else 0,
                "avg_duration": task.stats.avg_duration,
                "total_duration": task.stats.total_duration,
                "retry_count": task.stats.retry_count
            }
        }
    
    def get_overall_stats(self) -> Dict[str, Any]:
        """获取整体统计"""
        basic_stats = self.get_stats()
        execution_stats = self.get_execution_stats()
        
        # 获取所有任务的统计
        all_task_stats = []
        for task in self.list_all():
            task_stat = self.get_task_stats(task.id)
            if task_stat:
                all_task_stats.append(task_stat)
        
        return {
            "basic_stats": basic_stats,
            "execution_stats": execution_stats,
            "task_details": all_task_stats,
            "dependency_stats": {
                "total_dependencies": sum(len(deps) for deps in self._dependency_graph.values()),
                "tasks_with_dependencies": len(self._dependency_graph),
                "dependency_graph": self._dependency_graph.copy()
            }
        }
    
    # ==========================================================================
    # 批量操作相关方法
    # ==========================================================================
    
    def start_all_tasks(self, task_type: TaskType = None) -> Dict[str, Any]:
        """启动所有任务
        
        Args:
            task_type: 任务类型过滤，None表示所有类型
            
        Returns:
            {"success": int, "failed": int, "skipped": int}
        """
        results = {"success": 0, "failed": 0, "skipped": 0}
        
        for task in self.list_all():
            # 类型过滤
            if task_type and task.metadata.task_type != task_type:
                continue
            
            # 检查是否已在运行
            if task.is_running:
                results["skipped"] += 1
                continue
            
            # 启动任务
            result = self.start(task.id)
            if result.get("success"):
                results["success"] += 1
            else:
                results["failed"] += 1
                log.error(f"批量启动任务失败: {task.name} - {result.get('error')}")
        
        log.info(f"批量启动任务完成: 成功={results['success']}, 失败={results['failed']}, 跳过={results['skipped']}")
        return results
    
    def stop_all_tasks(self, task_type: TaskType = None) -> Dict[str, Any]:
        """停止所有任务
        
        Args:
            task_type: 任务类型过滤，None表示所有类型
            
        Returns:
            {"success": int, "failed": int, "skipped": int}
        """
        results = {"success": 0, "failed": 0, "skipped": 0}
        
        for task in self.list_all():
            # 类型过滤
            if task_type and task.metadata.task_type != task_type:
                continue
            
            # 检查是否已停止
            if not task.is_running:
                results["skipped"] += 1
                continue
            
            # 停止任务
            result = self.stop(task.id)
            if result.get("success"):
                results["success"] += 1
            else:
                results["failed"] += 1
                log.error(f"批量停止任务失败: {task.name} - {result.get('error')}")
        
        log.info(f"批量停止任务完成: 成功={results['success']}, 失败={results['failed']}, 跳过={results['skipped']}")
        return results
    
    def load_from_db(self) -> int:
        """从数据库加载任务
        
        Returns:
            加载的任务数量
        """
        try:
            # 获取持久化管理器
            persistence = get_global_persistence_manager()
            
            # 获取所有任务ID
            task_ids = persistence.list_units("task")
            loaded_count = 0
            
            for task_id in task_ids:
                try:
                    # 加载任务数据
                    task_data = persistence.load_unit("task", task_id)
                    if not task_data:
                        log.warning(f"任务数据不存在: {task_id}")
                        continue
                    
                    # 创建任务单元
                    task_unit = TaskUnit.from_dict(task_data)
                    
                    # 注册任务（不启动）
                    result = self.register(task_unit)
                    if result["success"]:
                        loaded_count += 1
                        log.info(f"任务已从数据库加载: {task_unit.name}")
                    else:
                        log.error(f"任务注册失败: {task_unit.name} - {result.get('error')}")
                        
                except Exception as e:
                    log.error(f"加载任务失败: {task_id} - {e}")
                    continue
            
            log.info(f"任务加载完成: 成功加载 {loaded_count} 个任务")
            return loaded_count
            
        except Exception as e:
            log.error(f"从数据库加载任务失败: {e}")
            return 0
    
    # ==========================================================================
    # 工具方法
    # ==========================================================================
    
    def get_scheduler(self) -> AsyncIOScheduler:
        """获取调度器实例"""
        return self._scheduler
    
    def start_scheduler(self) -> Dict[str, Any]:
        """启动调度器
        
        Returns:
            {"success": bool, "error": str}
        """
        try:
            with self._scheduler_lock:
                if not self._scheduler.running:
                    self._scheduler.start()
                    log.info("任务调度器已启动")
                    return {"success": True, "message": "调度器启动成功"}
                else:
                    return {"success": False, "error": "调度器已在运行"}
        except Exception as e:
            error_msg = f"调度器启动失败: {str(e)}"
            log.error(error_msg)
            return {"success": False, "error": error_msg}
    
    def stop_scheduler(self) -> Dict[str, Any]:
        """停止调度器
        
        Returns:
            {"success": bool, "error": str}
        """
        try:
            with self._scheduler_lock:
                if self._scheduler.running:
                    self._scheduler.shutdown()
                    log.info("任务调度器已停止")
                    return {"success": True, "message": "调度器停止成功"}
                else:
                    return {"success": False, "error": "调度器未运行"}
        except Exception as e:
            error_msg = f"调度器停止失败: {str(e)}"
            log.error(error_msg)
            return {"success": False, "error": error_msg}


# 全局任务管理器实例
_global_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """获取全局任务管理器"""
    global _global_task_manager
    if _global_task_manager is None:
        _global_task_manager = TaskManager()
    return _global_task_manager


def set_task_manager(manager: TaskManager):
    """设置全局任务管理器"""
    global _global_task_manager
    _global_task_manager = manager