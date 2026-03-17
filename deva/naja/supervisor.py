"""Naja 系统监控与管理模块

提供系统级的监控、健康检查、故障恢复和状态管理功能。
"""

from __future__ import annotations

import time
import threading
from typing import Dict, List, Optional, Any

from deva import NB, log as deva_log
import logging

# 使用标准日志
log = logging.getLogger(__name__)


class NajaSupervisor:
    """Naja 系统监控器
    
    负责：
    1. 监控系统各个组件的运行状态
    2. 检测并处理系统故障
    3. 自动恢复异常组件
    4. 提供系统健康状态报告
    5. 管理系统生命周期
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._components = {
            'datasource': None,
            'strategy': None,
            'task': None,
            'dictionary': None,
            'signal': None,
            'agent': None,
            'radar': None,
            'llm_controller': None,
        }
        self._status_history: List[Dict[str, Any]] = []
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._check_interval = 5  # 检查间隔（秒）
        self._initialized = True
        
        log.info("Naja 监控器初始化完成")
    
    def register_component(self, name: str, component: Any):
        """注册系统组件"""
        if name in self._components:
            self._components[name] = component
            log.info(f"已注册组件: {name}")
    
    def _get_component(self, name: str) -> Optional[Any]:
        """获取组件实例"""
        if self._components[name] is not None:
            return self._components[name]
        
        # 延迟加载组件
        try:
            if name == 'datasource':
                from .datasource import get_datasource_manager
                self._components[name] = get_datasource_manager()
            elif name == 'strategy':
                from .strategy import get_strategy_manager
                self._components[name] = get_strategy_manager()
            elif name == 'task':
                from .tasks import get_task_manager
                self._components[name] = get_task_manager()
            elif name == 'dictionary':
                from .dictionary import get_dictionary_manager
                self._components[name] = get_dictionary_manager()
            elif name == 'signal':
                from .signal.stream import get_signal_stream
                self._components[name] = get_signal_stream()
            elif name == 'agent':
                from .agent.manager import get_agent_manager
                self._components[name] = get_agent_manager()
            elif name == 'radar':
                from .radar import get_radar_engine
                self._components[name] = get_radar_engine()
            elif name == 'llm_controller':
                from .llm_controller import get_llm_controller
                self._components[name] = get_llm_controller()
        except Exception as e:
            log.error(f"加载组件 {name} 失败: {e}")
        
        return self._components[name]
    
    def start_monitoring(self):
        """开始监控系统"""
        if self._running:
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        # 启动统一性能监控
        try:
            from .performance import start_performance_monitoring
            start_performance_monitoring()
            log.info("统一性能监控已启动")
        except Exception as e:
            log.error(f"统一性能监控启动失败: {e}")
        
        # 启用存储性能监控
        try:
            from .performance.storage_monitor import enable_storage_monitoring
            enable_storage_monitoring()
            log.info("存储性能监控已启用")
        except Exception as e:
            log.error(f"存储性能监控启用失败: {e}")
        
        # 启动自动调优
        try:
            from .common.auto_tuner import _init_help_to_db, start_auto_tuner
            _init_help_to_db()
            start_auto_tuner()
            log.info("自动调优已启动")
        except Exception as e:
            log.error(f"自动调优启动失败: {e}")
        
        log.info("系统监控已启动")
    
    def stop_monitoring(self):
        """停止监控系统"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        log.info("系统监控已停止")
    
    def _monitor_loop(self):
        """监控循环"""
        while self._running:
            try:
                status = self.get_system_status()
                self._status_history.append(status)
                
                # 保持历史记录不超过100条
                if len(self._status_history) > 100:
                    self._status_history.pop(0)
                
                # 检查系统健康状态
                self._check_health(status)
                
                time.sleep(self._check_interval)
            except Exception as e:
                log.error(f"监控循环错误: {e}")
                time.sleep(self._check_interval)
    
    def _check_health(self, status: Dict[str, Any]):
        """检查系统健康状态并进行恢复"""
        # 检查策略运行状态
        strategy_status = status.get('components', {}).get('strategy', {})
        if strategy_status.get('status') == 'error':
            self._recover_strategy()
        
        # 检查数据源运行状态
        datasource_status = status.get('components', {}).get('datasource', {})
        if datasource_status.get('status') == 'error':
            self._recover_datasource()
        
        # 检查任务运行状态
        task_status = status.get('components', {}).get('task', {})
        if task_status.get('status') == 'error':
            self._recover_task()
    
    def _recover_strategy(self):
        """恢复策略系统"""
        log.info("开始恢复策略系统...")
        try:
            strategy_mgr = self._get_component('strategy')
            if strategy_mgr:
                # 重新加载策略
                strategy_mgr.load_from_db()
                # 恢复运行状态
                result = strategy_mgr.restore_running_states()
                log.info(f"策略系统恢复完成: {result}")
        except Exception as e:
            log.error(f"策略系统恢复失败: {e}")
    
    def _recover_datasource(self):
        """恢复数据源系统"""
        log.info("开始恢复数据源系统...")
        try:
            ds_mgr = self._get_component('datasource')
            if ds_mgr:
                # 重新加载数据源
                ds_mgr.load_from_db()
                # 恢复运行状态
                result = ds_mgr.restore_running_states()
                log.info(f"数据源系统恢复完成: {result}")
        except Exception as e:
            log.error(f"数据源系统恢复失败: {e}")
    
    def _recover_task(self):
        """恢复任务系统"""
        log.info("开始恢复任务系统...")
        try:
            task_mgr = self._get_component('task')
            if task_mgr:
                # 重新加载任务
                task_mgr.load_from_db()
                # 恢复运行状态
                result = task_mgr.restore_running_states()
                log.info(f"任务系统恢复完成: {result}")
        except Exception as e:
            log.error(f"任务系统恢复失败: {e}")
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        status = {
            'timestamp': time.time(),
            'components': {}
        }
        
        # 检查数据源状态
        try:
            ds_mgr = self._get_component('datasource')
            if ds_mgr:
                ds_status = ds_mgr.get_stats()
                status['components']['datasource'] = {
                    'status': 'healthy' if ds_status.get('total', 0) >= 0 else 'error',
                    'stats': ds_status
                }
        except Exception as e:
            status['components']['datasource'] = {
                'status': 'error',
                'error': str(e)
            }
        
        # 检查策略状态
        try:
            strategy_mgr = self._get_component('strategy')
            if strategy_mgr:
                strategy_status = strategy_mgr.get_stats()
                status['components']['strategy'] = {
                    'status': 'healthy' if strategy_status.get('total', 0) >= 0 else 'error',
                    'stats': strategy_status
                }
        except Exception as e:
            status['components']['strategy'] = {
                'status': 'error',
                'error': str(e)
            }
        
        # 检查任务状态
        try:
            task_mgr = self._get_component('task')
            if task_mgr:
                task_status = task_mgr.get_stats()
                status['components']['task'] = {
                    'status': 'healthy' if task_status.get('total', 0) >= 0 else 'error',
                    'stats': task_status
                }
        except Exception as e:
            status['components']['task'] = {
                'status': 'error',
                'error': str(e)
            }
        
        # 检查字典状态
        try:
            dict_mgr = self._get_component('dictionary')
            if dict_mgr:
                dict_status = dict_mgr.get_stats()
                status['components']['dictionary'] = {
                    'status': 'healthy' if dict_status.get('total', 0) >= 0 else 'error',
                    'stats': dict_status
                }
        except Exception as e:
            status['components']['dictionary'] = {
                'status': 'error',
                'error': str(e)
            }
        
        # 检查智能体状态
        try:
            agent_mgr = self._get_component('agent')
            if agent_mgr:
                agent_status = agent_mgr.get_system_status()
                status['components']['agent'] = {
                    'status': 'healthy',
                    'stats': agent_status
                }
        except Exception as e:
            status['components']['agent'] = {
                'status': 'error',
                'error': str(e)
            }
        
        # 检查信号流状态
        try:
            signal_stream = self._get_component('signal')
            if signal_stream:
                status['components']['signal'] = {
                    'status': 'healthy',
                    'info': 'Signal stream active'
                }
        except Exception as e:
            status['components']['signal'] = {
                'status': 'error',
                'error': str(e)
            }

        # 检查雷达状态
        try:
            radar_engine = self._get_component('radar')
            if radar_engine:
                status['components']['radar'] = {
                    'status': 'healthy',
                    'info': 'Radar engine active'
                }
        except Exception as e:
            status['components']['radar'] = {
                'status': 'error',
                'error': str(e)
            }

        # 检查 LLM 调节器状态
        try:
            llm_controller = self._get_component('llm_controller')
            if llm_controller:
                status['components']['llm_controller'] = {
                    'status': 'healthy',
                    'info': 'LLM controller ready'
                }
        except Exception as e:
            status['components']['llm_controller'] = {
                'status': 'error',
                'error': str(e)
            }
        
        # 计算整体状态
        all_statuses = [comp.get('status') for comp in status['components'].values()]
        if 'error' in all_statuses:
            status['overall_status'] = 'unhealthy'
        else:
            status['overall_status'] = 'healthy'
        
        return status
    
    def get_status_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取状态历史"""
        return self._status_history[-limit:]
    
    def get_health_summary(self) -> Dict[str, Any]:
        """获取健康状态摘要"""
        current_status = self.get_system_status()
        history = self.get_status_history(10)
        
        # 计算最近的健康状态趋势
        recent_statuses = [h.get('overall_status') for h in history]
        healthy_count = recent_statuses.count('healthy')
        
        return {
            'current_status': current_status['overall_status'],
            'component_statuses': {
                name: comp.get('status') 
                for name, comp in current_status['components'].items()
            },
            'recent_health_rate': healthy_count / len(recent_statuses) if recent_statuses else 0,
            'timestamp': time.time()
        }
    
    def restart_system(self) -> Dict[str, Any]:
        """重启整个系统"""
        log.info("开始重启系统...")
        
        results = {}
        
        # 重启各个组件
        try:
            # 先停止所有组件
            self._stop_all_components()
            
            # 重新加载所有组件
            results['datasource'] = self._reload_component('datasource')
            results['strategy'] = self._reload_component('strategy')
            results['task'] = self._reload_component('task')
            results['dictionary'] = self._reload_component('dictionary')
            
            # 恢复运行状态
            results['restore'] = self.restore_all_states()
            
            log.info("系统重启完成")
            return {
                'success': True,
                'results': results
            }
        except Exception as e:
            log.error(f"系统重启失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _stop_all_components(self):
        """停止所有组件"""
        # 停止策略
        try:
            strategy_mgr = self._get_component('strategy')
            if strategy_mgr:
                for entry in strategy_mgr.list_all():
                    entry.stop()
        except Exception as e:
            log.error(f"停止策略失败: {e}")
        
        # 停止数据源
        try:
            ds_mgr = self._get_component('datasource')
            if ds_mgr:
                for entry in ds_mgr.list_all():
                    entry.stop()
        except Exception as e:
            log.error(f"停止数据源失败: {e}")
        
        # 停止任务
        try:
            task_mgr = self._get_component('task')
            if task_mgr:
                for entry in task_mgr.list_all():
                    entry.stop()
        except Exception as e:
            log.error(f"停止任务失败: {e}")
    
    def _reload_component(self, name: str) -> Dict[str, Any]:
        """重新加载组件"""
        try:
            component = self._get_component(name)
            if hasattr(component, 'load_from_db'):
                count = component.load_from_db()
                return {'success': True, 'loaded_count': count}
            return {'success': True, 'message': 'Component reloaded'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def restore_all_states(self) -> Dict[str, Any]:
        """恢复所有组件的运行状态"""
        results = {}
        
        # 恢复数据源
        try:
            ds_mgr = self._get_component('datasource')
            if ds_mgr:
                results['datasource'] = ds_mgr.restore_running_states()
        except Exception as e:
            results['datasource'] = {'success': False, 'error': str(e)}
        
        # 恢复策略
        try:
            strategy_mgr = self._get_component('strategy')
            if strategy_mgr:
                results['strategy'] = strategy_mgr.restore_running_states()
        except Exception as e:
            results['strategy'] = {'success': False, 'error': str(e)}
        
        # 恢复任务
        try:
            task_mgr = self._get_component('task')
            if task_mgr:
                results['task'] = task_mgr.restore_running_states()
        except Exception as e:
            results['task'] = {'success': False, 'error': str(e)}
        
        return results
    
    def shutdown(self) -> Dict[str, Any]:
        """关闭系统"""
        log.info("开始关闭系统...")
        
        try:
            # 停止监控
            self.stop_monitoring()
            
            # 停止所有组件
            self._stop_all_components()
            
            log.info("系统已关闭")
            return {'success': True}
        except Exception as e:
            log.error(f"系统关闭失败: {e}")
            return {'success': False, 'error': str(e)}


_naja_supervisor: Optional[NajaSupervisor] = None
_supervisor_lock = threading.Lock()


def get_naja_supervisor() -> NajaSupervisor:
    """获取 Naja 监控器单例"""
    global _naja_supervisor
    if _naja_supervisor is None:
        with _supervisor_lock:
            if _naja_supervisor is None:
                _naja_supervisor = NajaSupervisor()
    return _naja_supervisor


def start_supervisor() -> NajaSupervisor:
    """启动 Naja 监控器"""
    supervisor = get_naja_supervisor()
    supervisor.start_monitoring()
    return supervisor


def stop_supervisor() -> None:
    """停止 Naja 监控器"""
    supervisor = get_naja_supervisor()
    supervisor.stop_monitoring()
