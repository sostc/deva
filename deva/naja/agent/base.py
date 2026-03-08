"""智能体基础架构模块

提供智能体的抽象基类和通用功能。
"""

from __future__ import annotations

import asyncio
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from deva import NB, Stream, timer, bus
import logging

# 使用标准日志
log = logging.getLogger(__name__)
from deva.core.namespace import NS


class AgentState(Enum):
    """智能体状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class AgentRole(Enum):
    """智能体角色"""
    STRATEGIST = "strategist"  # 策略师
    TRADER = "trader"  # 交易员
    RISK_MANAGER = "risk_manager"  # 风控官
    SUPERVISOR = "supervisor"  # 监督者


@dataclass
class AgentMetadata:
    """智能体元数据"""
    name: str
    role: AgentRole
    description: str = ""
    created_at: float = field(default_factory=time.time)
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentStateData:
    """智能体状态数据"""
    state: AgentState = AgentState.IDLE
    last_action_ts: float = 0
    action_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


class BaseAgent(Stream, ABC):
    """智能体抽象基类
    
    所有智能体都应继承此类并实现特定功能。
    """
    
    def __init__(self, metadata: AgentMetadata, config: Optional[Dict[str, Any]] = None):
        # 先初始化 Stream，使用 metadata.name 作为流的名称
        # 直接调用 Stream 的 __init__ 方法，不传递 name 参数
        # 而是在初始化后手动设置 metadata
        Stream.__init__(self)
        self._metadata = metadata
        # 手动设置 Stream 的 name 属性
        self._name = metadata.name
        self._state = AgentStateData()
        self._config = config or {}
        self._lock = threading.RLock()
        self._initialized = False
        
        self._message_queue: List[Dict[str, Any]] = []
        self._event_handlers: Dict[str, List[Callable]] = {}
        
        self._register_bus_routes()
    
    @property
    def name(self) -> str:
        return self._metadata.name
    
    @name.setter
    def name(self, value):
        # 当 Stream 类尝试设置 name 属性时，我们忽略它
        # 因为我们使用 metadata.name 作为智能体的名称
        pass
    

    
    @property
    def role(self) -> AgentRole:
        return self._metadata.role
    
    @property
    def state(self) -> AgentStateData:
        return self._state
    
    @property
    def metadata(self) -> AgentMetadata:
        return self._metadata
    
    def initialize(self):
        """初始化智能体"""
        with self._lock:
            if self._initialized:
                return
            
            self._do_initialize()
            self._initialized = True
            self._state.state = AgentState.IDLE
            log.info(f"智能体 [{self.name}] 初始化完成，角色：{self.role.value}")
    
    def start(self):
        """启动智能体"""
        with self._lock:
            if not self._initialized:
                self.initialize()
            
            self._do_start()
            self._state.state = AgentState.RUNNING
            self._state.last_action_ts = time.time()
            log.info(f"智能体 [{self.name}] 已启动")
    
    def stop(self):
        """停止智能体"""
        with self._lock:
            self._do_stop()
            self._state.state = AgentState.STOPPED
            log.info(f"智能体 [{self.name}] 已停止")
    
    def pause(self):
        """暂停智能体"""
        with self._lock:
            self._do_pause()
            self._state.state = AgentState.PAUSED
            log.info(f"智能体 [{self.name}] 已暂停")
    
    def resume(self):
        """恢复智能体"""
        with self._lock:
            self._do_resume()
            self._state.state = AgentState.RUNNING
            self._state.last_action_ts = time.time()
            log.info(f"智能体 [{self.name}] 已恢复")
    
    def send_message(self, message: Dict[str, Any]):
        """发送消息到消息总线"""
        message['from'] = self.name
        message['timestamp'] = time.time()
        self._message_queue.append(message)
        self._publish_message(message)
    
    def receive_message(self, message: Dict[str, Any]):
        """接收消息"""
        msg_type = message.get('type')
        from_agent = message.get('from', '未知')
        log.info(f"智能体 [{self.name}] 收到来自 [{from_agent}] 的消息，类型：{msg_type}")
        self._handle_message(message)
    
    def on_event(self, event_type: str, handler: Callable):
        """注册事件处理器"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    def _trigger_event(self, event_type: str, data: Any = None):
        """触发事件"""
        if event_type in self._event_handlers:
            for handler in self._event_handlers[event_type]:
                try:
                    handler(data)
                except Exception as e:
                    log.error(f"智能体 [{self.name}] 事件处理失败：{e}")
    
    def _update_metrics(self, key: str, value: Any):
        """更新指标"""
        self._state.metrics[key] = value
    
    def _increment_metric(self, key: str, delta: int = 1):
        """增加指标计数"""
        if key not in self._state.metrics:
            self._state.metrics[key] = 0
        self._state.metrics[key] += delta
    
    def _handle_error(self, error: Exception):
        """处理错误"""
        self._state.error_count += 1
        self._state.last_error = str(error)
        self._state.state = AgentState.ERROR
        log.error(f"智能体 [{self.name}] 错误：{error}")
        self._trigger_event('error', error)
    
    @abstractmethod
    def _do_initialize(self):
        """初始化实现（由子类实现）"""
        pass
    
    @abstractmethod
    def _do_start(self):
        """启动实现（由子类实现）"""
        pass
    
    @abstractmethod
    def _do_stop(self):
        """停止实现（由子类实现）"""
        pass
    
    @abstractmethod
    def _do_pause(self):
        """暂停实现（由子类实现）"""
        pass
    
    @abstractmethod
    def _do_resume(self):
        """恢复实现（由子类实现）"""
        pass
    
    @abstractmethod
    def _handle_message(self, message: Dict[str, Any]):
        """消息处理实现（由子类实现）"""
        pass
    
    def _register_bus_routes(self):
        """注册总线路由实现"""
        # 为每个智能体注册一个处理函数
        def handle_message(x):
            if isinstance(x, dict) and x.get('to') == self.name:
                self.receive_message(x)
        
        # 使用 bus.sink 来处理消息
        import deva
        deva.bus.sink(handle_message)
        log.info(f"智能体 [{self.name}] 已注册消息处理函数到消息总线")
    
    def _publish_message(self, message: Dict[str, Any]):
        """发布消息实现"""
        try:
            import deva
            # 检查当前线程是否有事件循环
            try:
                loop = asyncio.get_event_loop()
                # 如果有事件循环，直接发送
                deva.bus.emit(message)
            except RuntimeError:
                # 如果没有事件循环，创建一个临时的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    deva.bus.emit(message)
                finally:
                    loop.close()
        except Exception as e:
            log.error(f"智能体 [{self.name}] 发布消息失败：{e}")
