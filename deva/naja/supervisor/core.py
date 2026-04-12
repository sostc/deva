"""NajaSupervisor 核心定义 — 单例、初始化、组件注册"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional, Any

from deva.naja.register import SR
import logging

from .monitoring import MonitoringMixin
from .status import StatusMixin
from .recovery import RecoveryLifecycleMixin

log = logging.getLogger(__name__)


class NajaSupervisor(MonitoringMixin, StatusMixin, RecoveryLifecycleMixin):
    """Naja 系统监控器

    负责：
    1. 监控系统各个组件的运行状态
    2. 检测并处理系统故障
    3. 自动恢复异常组件
    4. 提供系统健康状态报告
    5. 管理系统生命周期

    ================================================================================
    单例模式说明：为什么使用单例
    ================================================================================
    1. 全局系统监控：系统监控必须是全局的，才能准确反映整个系统的状态。
       如果存在多个实例，会导致状态不一致，无法准确监控。

    2. 组件协调：Supervisor 负责协调所有组件的健康检查和故障恢复，
       必须全局唯一才能正确工作。

    3. 生命周期：Supervisor 的生命周期与系统一致，随系统启动和关闭。

    4. 这是系统监控的设计选择，不是过度工程。
    ================================================================================
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
                    cls._instance._init_lock = threading.Lock()
        return cls._instance

    def __init__(self):
        self._ensure_initialized()

    def configure_attention(self, force_realtime: bool = False, lab_mode: bool = False):
        """配置注意力系统启动参数（在调用 start_monitoring 之前设置）"""
        self._force_realtime = force_realtime
        self._lab_mode = lab_mode
        log.info(f"[NajaSupervisor] 配置注意力系统: force_realtime={force_realtime}, lab_mode={lab_mode}")

    def _ensure_initialized(self):
        if getattr(self, '_initialized', False):
            return
        with self._init_lock:
            if getattr(self, '_initialized', False):
                return

            self._force_realtime = False
            self._lab_mode = False
            self._running = False
            self._components: Dict[str, Any] = {
                'datasource': None,
                'strategy': None,
                'task': None,
                'dictionary': None,
                'signal': None,
                'radar': None,
                'llm_controller': None,
                'attention': None,
                'attention_strategy_manager': None,
                'attention_report_generator': None,
                'bandit_runner': None,
                'hotspot_signal_tracker': None,
                'position_monitor': None,
                'cognition': None,
            }
            self._status_history: List[Dict[str, Any]] = []
            self._monitor_thread: Optional[threading.Thread] = None
            self._check_interval = 5
            self._initialized = True
    
    def register_component(self, name: str, component: Any):
        """注册系统组件"""
        if name in self._components:
            self._components[name] = component
            log.debug(f"已注册组件: {name}")
    
    def _get_component(self, name: str) -> Optional[Any]:
        """获取组件实例"""
        if self._components[name] is not None:
            return self._components[name]
        
        # 延迟加载组件
        try:
            if name == 'datasource':
                from deva.naja.datasource import get_datasource_manager
                self._components[name] = get_datasource_manager()
            elif name == 'strategy':
                from deva.naja.strategy import get_strategy_manager
                self._components[name] = get_strategy_manager()
            elif name == 'task':
                self._components[name] = SR('task_manager')
            elif name == 'dictionary':
                self._components[name] = SR('dictionary_manager')
            elif name == 'signal':
                from deva.naja.signal.stream import get_signal_stream
                self._components[name] = get_signal_stream()
            elif name == 'radar':
                from deva.naja.radar import get_radar_engine
                self._components[name] = get_radar_engine()
            elif name == 'llm_controller':
                from deva.naja.llm_controller import get_llm_controller
                self._components[name] = get_llm_controller()
        except Exception as e:
            log.error(f"加载组件 {name} 失败: {e}")
        
        return self._components[name]
