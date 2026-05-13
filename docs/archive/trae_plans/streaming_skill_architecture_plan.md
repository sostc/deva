# Skill 流式执行架构规划

## 1. 问题分析

### 1.1 当前 Skill 执行的局限性

当前的 Skill 执行模式是**确定性的、一次性的函数调用**：

```
Agent -> Skill.invoke() -> 执行 -> 返回结果
```

**存在的问题：**

1. **无法动态干预**: Skill 一旦开始执行，就无法在执行过程中接收新的指令或参数
2. **上下文丢失**: 遇到不确定性时只能返回错误，执行上下文无法保留
3. **缺乏状态管理**: 长时间运行的 Skill 无法保存和恢复中间状态
4. **单向通信**: 只能等待 Skill 完成，无法实时获取执行进度或中间结果

### 1.2 目标架构

将 Skill 执行转变为**有状态的任务流（Stateful Task Stream）**：

```
Agent -> Skill.start() -> [流式执行] -> 动态干预/澄清请求 -> 继续执行 -> 完成
                    ↓
              实时状态同步
                    ↓
              上下文保持
```

## 2. 核心概念设计

### 2.1 流式 Skill 生命周期

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  CREATED │ -> │ STARTING│ -> │ RUNNING │ -> │PAUSING  │ -> │PAUSED   │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
                                     ↓              ↓
                              ┌─────────┐    ┌─────────┐
                              │CLARIFY  │    │RESUMING │
                              │REQUESTED│    │         │
                              └─────────┘    └─────────┘
                                     ↓              ↓
                              ┌─────────┐         │
                              │COMPLETED│ <-------┘
                              │ FAILED  │
                              └─────────┘
```

### 2.2 关键组件

#### 2.2.1 StreamSkill (流式 Skill 基类)

```python
class StreamSkill:
    """流式执行 Skill 基类"""

    def __init__(self):
        self._state = SkillState.CREATED
        self._context = SkillContext()  # 执行上下文
        self._control_channel = ControlChannel()  # 控制通道
        self._output_stream = OutputStream()  # 输出流
        self._checkpoint_store = CheckpointStore()  # 检查点存储

    async def execute_stream(self, input_data: Any) -> AsyncIterator[SkillEvent]:
        """流式执行入口"""
        pass

    async def on_control_message(self, message: ControlMessage):
        """处理控制消息（动态注入）"""
        pass

    async def on_clarification_response(self, response: ClarificationResponse):
        """处理澄清响应"""
        pass
```

#### 2.2.2 SkillContext (执行上下文)

```python
@dataclass
class SkillContext:
    """Skill 执行上下文 - 保持状态不丢失"""
    skill_id: str
    execution_id: str
    start_time: float
    input_data: Any
    intermediate_results: List[Any] = field(default_factory=list)
    current_stage: str = ""
    stage_progress: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def checkpoint(self) -> dict:
        """创建检查点"""
        return {
            "execution_id": self.execution_id,
            "current_stage": self.current_stage,
            "stage_progress": self.stage_progress,
            "intermediate_results": self.intermediate_results,
            "timestamp": time.time()
        }

    def restore(self, checkpoint: dict):
        """从检查点恢复"""
        self.current_stage = checkpoint["current_stage"]
        self.stage_progress = checkpoint["stage_progress"]
        self.intermediate_results = checkpoint["intermediate_results"]
```

#### 2.2.3 ControlChannel (控制通道)

```python
class ControlChannel:
    """控制通道 - 允许主 Agent 动态注入指令"""

    def __init__(self):
        self._message_queue = asyncio.Queue()
        self._handlers: Dict[str, Callable] = {}

    async def inject(self, message: ControlMessage):
        """注入控制消息"""
        await self._message_queue.put(message)

    def register_handler(self, message_type: str, handler: Callable):
        """注册消息处理器"""
        self._handlers[message_type] = handler

    async def process_messages(self):
        """处理消息循环"""
        while True:
            message = await self._message_queue.get()
            handler = self._handlers.get(message.type)
            if handler:
                await handler(message)
```

#### 2.2.4 ClarificationRequest (澄清请求)

```python
@dataclass
class ClarificationRequest:
    """澄清请求 - 当遇到不确定性时发起"""
    request_id: str
    skill_id: str
    execution_id: str
    question: str  # 需要澄清的问题
    context: dict  # 当前执行上下文快照
    options: Optional[List[str]] = None  # 可选答案
    timeout_seconds: float = 60.0
    urgency: str = "normal"  # normal, high, critical

@dataclass
class ClarificationResponse:
    """澄清响应"""
    request_id: str
    answer: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 2.3 事件流设计

```python
class SkillEventType(Enum):
    # 生命周期事件
    STARTED = "started"
    PROGRESS = "progress"
    STAGE_COMPLETED = "stage_completed"

    # 交互事件
    CLARIFICATION_REQUESTED = "clarification_requested"
    CLARIFICATION_RECEIVED = "clarification_received"

    # 控制事件
    PAUSED = "paused"
    RESUMED = "resumed"
    CANCELLED = "cancelled"

    # 完成事件
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class SkillEvent:
    event_type: SkillEventType
    timestamp: float
    execution_id: str
    data: Any
    context_snapshot: Optional[dict] = None
```

## 3. 架构实现方案

### 3.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Main Agent                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │ Skill Router │  │ State Manager│  │ Control Panel│                   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                   │
└─────────┼─────────────────┼─────────────────┼───────────────────────────┘
          │                 │                 │
          │    ┌────────────┴─────────────────┘
          │    │
          ▼    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Skill Execution Engine                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Stream Skill Instance                         │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │    │
│  │  │   Execute   │  │   Context   │  │      Control Channel    │  │    │
│  │  │   Stream    │◄─┤   Store     │◄─┤  (Dynamic Injection)    │  │    │
│  │  └──────┬──────┘  └─────────────┘  └─────────────────────────┘  │    │
│  │         │                                                        │    │
│  │  ┌──────┴──────────────────────────────────────────────────┐    │    │
│  │  │                    Event Stream                          │    │    │
│  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐        │    │    │
│  │  │  │Progress │ │ Clarify │ │  Stage  │ │ Complete│        │    │    │
│  │  │  │ Events  │ │ Request │ │ Events  │ │ Events  │        │    │    │
│  │  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘        │    │    │
│  │  └──────────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 核心实现步骤

#### 步骤 1: 创建流式 Skill 基类

```python
# deva/naja/skill/stream_skill.py

from abc import ABC, abstractmethod
from typing import AsyncIterator, Any, Optional, Callable
import asyncio
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid

class SkillState(Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    CLARIFICATION_REQUESTED = "clarification_requested"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class SkillContext:
    """执行上下文 - 保持完整状态"""
    skill_id: str
    execution_id: str
    start_time: float
    input_data: Any
    current_stage: str = ""
    stage_progress: Dict[str, Any] = field(default_factory=dict)
    intermediate_results: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    checkpoints: List[dict] = field(default_factory=list)

    def create_checkpoint(self, stage: str) -> dict:
        """创建检查点"""
        checkpoint = {
            "execution_id": self.execution_id,
            "stage": stage,
            "stage_progress": dict(self.stage_progress),
            "intermediate_results": list(self.intermediate_results),
            "timestamp": time.time()
        }
        self.checkpoints.append(checkpoint)
        return checkpoint

    def restore_from_checkpoint(self, checkpoint: dict):
        """从检查点恢复"""
        self.current_stage = checkpoint["stage"]
        self.stage_progress = dict(checkpoint["stage_progress"])
        self.intermediate_results = list(checkpoint["intermediate_results"])

@dataclass
class SkillEvent:
    """Skill 事件"""
    event_type: str
    timestamp: float
    execution_id: str
    data: Any
    stage: Optional[str] = None

@dataclass
class ControlMessage:
    """控制消息"""
    message_type: str  # "pause", "resume", "update_params", "cancel"
    data: Any
    timestamp: float = field(default_factory=time.time)

@dataclass
class ClarificationRequest:
    """澄清请求"""
    request_id: str
    question: str
    context: dict
    options: Optional[List[str]] = None
    timeout_seconds: float = 60.0
    urgency: str = "normal"

@dataclass
class ClarificationResponse:
    """澄清响应"""
    request_id: str
    answer: Any
    metadata: Dict[str, Any] = field(default_factory=dict)

class StreamSkill(ABC):
    """流式 Skill 基类"""

    def __init__(self, skill_id: str):
        self.skill_id = skill_id
        self._state = SkillState.CREATED
        self._context: Optional[SkillContext] = None
        self._control_queue: asyncio.Queue[ControlMessage] = asyncio.Queue()
        self._clarification_queue: asyncio.Queue[ClarificationResponse] = asyncio.Queue()
        self._event_subscribers: List[Callable[[SkillEvent], None]] = []
        self._current_task: Optional[asyncio.Task] = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # 默认不暂停

    @abstractmethod
    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """子类实现具体的执行逻辑"""
        pass

    async def start(self, input_data: Any) -> AsyncIterator[SkillEvent]:
        """启动流式执行"""
        execution_id = str(uuid.uuid4())
        self._context = SkillContext(
            skill_id=self.skill_id,
            execution_id=execution_id,
            start_time=time.time(),
            input_data=input_data
        )
        self._state = SkillState.STARTING

        # 发送启动事件
        yield SkillEvent(
            event_type="started",
            timestamp=time.time(),
            execution_id=execution_id,
            data={"input": input_data}
        )

        self._state = SkillState.RUNNING

        # 启动控制消息处理任务
        control_task = asyncio.create_task(self._process_control_messages())

        try:
            async for event in self.execute(input_data, self._context):
                # 等待暂停事件（如果被暂停）
                await self._pause_event.wait()

                # 检查状态
                if self._state == SkillState.CANCELLED:
                    break

                # 发送事件
                yield event

                # 广播给订阅者
                for subscriber in self._event_subscribers:
                    try:
                        subscriber(event)
                    except Exception:
                        pass

        except Exception as e:
            self._state = SkillState.FAILED
            yield SkillEvent(
                event_type="failed",
                timestamp=time.time(),
                execution_id=execution_id,
                data={"error": str(e)}
            )
        finally:
            control_task.cancel()
            try:
                await control_task
            except asyncio.CancelledError:
                pass

            if self._state not in (SkillState.FAILED, SkillState.CANCELLED):
                self._state = SkillState.COMPLETED
                yield SkillEvent(
                    event_type="completed",
                    timestamp=time.time(),
                    execution_id=execution_id,
                    data={"context": self._context.checkpoint() if self._context else None}
                )

    async def _process_control_messages(self):
        """处理控制消息"""
        while True:
            try:
                message = await asyncio.wait_for(
                    self._control_queue.get(),
                    timeout=1.0
                )

                if message.message_type == "pause":
                    self._state = SkillState.PAUSED
                    self._pause_event.clear()
                    await self._emit_event("paused", {"reason": message.data})

                elif message.message_type == "resume":
                    self._state = SkillState.RUNNING
                    self._pause_event.set()
                    await self._emit_event("resumed", {})

                elif message.message_type == "update_params":
                    if self._context:
                        self._context.metadata.update(message.data)
                    await self._emit_event("params_updated", message.data)

                elif message.message_type == "cancel":
                    self._state = SkillState.CANCELLED
                    if self._current_task:
                        self._current_task.cancel()
                    await self._emit_event("cancelled", {})

                elif message.message_type == "clarification_response":
                    await self._clarification_queue.put(message.data)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def _emit_event(self, event_type: str, data: Any, stage: Optional[str] = None):
        """发送事件"""
        if self._context:
            event = SkillEvent(
                event_type=event_type,
                timestamp=time.time(),
                execution_id=self._context.execution_id,
                data=data,
                stage=stage or self._context.current_stage
            )
            for subscriber in self._event_subscribers:
                try:
                    subscriber(event)
                except Exception:
                    pass

    async def request_clarification(
        self,
        question: str,
        options: Optional[List[str]] = None,
        timeout_seconds: float = 60.0,
        urgency: str = "normal"
    ) -> ClarificationResponse:
        """发起澄清请求并等待响应"""
        if not self._context:
            raise RuntimeError("Skill not started")

        request = ClarificationRequest(
            request_id=str(uuid.uuid4()),
            question=question,
            context=self._context.checkpoint(),
            options=options,
            timeout_seconds=timeout_seconds,
            urgency=urgency
        )

        self._state = SkillState.CLARIFICATION_REQUESTED

        # 发送澄清请求事件
        await self._emit_event("clarification_requested", {
            "request_id": request.request_id,
            "question": question,
            "options": options,
            "urgency": urgency
        })

        try:
            # 等待响应
            response = await asyncio.wait_for(
                self._clarification_queue.get(),
                timeout=timeout_seconds
            )

            if response.request_id != request.request_id:
                raise RuntimeError("Response ID mismatch")

            self._state = SkillState.RUNNING

            # 发送澄清接收事件
            await self._emit_event("clarification_received", {
                "request_id": request.request_id,
                "answer": response.answer
            })

            return response

        except asyncio.TimeoutError:
            self._state = SkillState.FAILED
            raise RuntimeError(f"Clarification request timed out after {timeout_seconds}s")

    def inject_control_message(self, message: ControlMessage):
        """注入控制消息（由主 Agent 调用）"""
        asyncio.create_task(self._control_queue.put(message))

    def subscribe_to_events(self, callback: Callable[[SkillEvent], None]):
        """订阅事件"""
        self._event_subscribers.append(callback)

    def unsubscribe_from_events(self, callback: Callable[[SkillEvent], None]):
        """取消订阅"""
        if callback in self._event_subscribers:
            self._event_subscribers.remove(callback)

    @property
    def state(self) -> SkillState:
        return self._state

    @property
    def context(self) -> Optional[SkillContext]:
        return self._context
```

#### 步骤 2: 创建 Skill 执行引擎

```python
# deva/naja/skill/execution_engine.py

from typing import Dict, List, Optional, Callable, Any
import asyncio
from dataclasses import dataclass
import time

@dataclass
class ExecutionSession:
    """执行会话"""
    session_id: str
    skill_id: str
    skill_instance: 'StreamSkill'
    start_time: float
    status: str = "running"
    events: List[SkillEvent] = field(default_factory=list)

class SkillExecutionEngine:
    """Skill 执行引擎 - 管理所有流式 Skill 的执行"""

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._sessions: Dict[str, ExecutionSession] = {}
        self._skill_registry: Dict[str, type] = {}
        self._event_bus = asyncio.Queue()
        self._initialized = True

    def register_skill(self, skill_id: str, skill_class: type):
        """注册 Skill 类型"""
        self._skill_registry[skill_id] = skill_class

    async def execute(
        self,
        skill_id: str,
        input_data: Any,
        session_id: Optional[str] = None
    ) -> str:
        """执行 Skill，返回会话 ID"""
        if skill_id not in self._skill_registry:
            raise ValueError(f"Unknown skill: {skill_id}")

        # 创建会话
        session_id = session_id or f"session_{int(time.time() * 1000)}"
        skill_class = self._skill_registry[skill_id]
        skill_instance = skill_class(skill_id)

        session = ExecutionSession(
            session_id=session_id,
            skill_id=skill_id,
            skill_instance=skill_instance,
            start_time=time.time()
        )
        self._sessions[session_id] = session

        # 订阅事件
        def on_event(event: SkillEvent):
            session.events.append(event)
            # 广播到事件总线
            asyncio.create_task(self._event_bus.put({
                "session_id": session_id,
                "event": event
            }))

        skill_instance.subscribe_to_events(on_event)

        # 启动执行
        async def run_skill():
            async for event in skill_instance.start(input_data):
                pass  # 事件通过订阅者处理

        asyncio.create_task(run_skill())

        return session_id

    async def inject_control(
        self,
        session_id: str,
        message_type: str,
        data: Any
    ):
        """向执行会话注入控制消息"""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        message = ControlMessage(
            message_type=message_type,
            data=data
        )
        session.skill_instance.inject_control_message(message)

    async def request_clarification_response(
        self,
        session_id: str,
        request_id: str,
        answer: Any
    ):
        """响应澄清请求"""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        response = ClarificationResponse(
            request_id=request_id,
            answer=answer
        )
        message = ControlMessage(
            message_type="clarification_response",
            data=response
        )
        session.skill_instance.inject_control_message(message)

    def get_session_status(self, session_id: str) -> Optional[dict]:
        """获取会话状态"""
        session = self._sessions.get(session_id)
        if not session:
            return None

        return {
            "session_id": session_id,
            "skill_id": session.skill_id,
            "status": session.status,
            "start_time": session.start_time,
            "event_count": len(session.events),
            "current_state": session.skill_instance.state.value,
            "latest_events": [e.__dict__ for e in session.events[-5:]]
        }

    def get_session_events(
        self,
        session_id: str,
        since_index: int = 0
    ) -> List[SkillEvent]:
        """获取会话事件"""
        session = self._sessions.get(session_id)
        if not session:
            return []
        return session.events[since_index:]

    async def subscribe_to_events(
        self,
        callback: Callable[[dict], None]
    ):
        """订阅全局事件"""
        while True:
            try:
                event_data = await self._event_bus.get()
                callback(event_data)
            except Exception:
                pass

def get_execution_engine() -> SkillExecutionEngine:
    return SkillExecutionEngine()
```

#### 步骤 3: 创建 Agent-Skill 交互层

```python
# deva/naja/skill/agent_interface.py

from typing import AsyncIterator, Optional, Callable
import asyncio

class AgentSkillInterface:
    """Agent 与 Skill 的交互接口"""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._engine = get_execution_engine()
        self._active_sessions: Dict[str, str] = {}  # task -> session_id

    async def invoke_skill_stream(
        self,
        skill_id: str,
        input_data: Any,
        on_event: Optional[Callable[[SkillEvent], None]] = None,
        on_clarification: Optional[Callable[[ClarificationRequest], Any]] = None
    ) -> AsyncIterator[SkillEvent]:
        """
        流式调用 Skill

        特性：
        1. 实时接收执行事件
        2. 自动处理澄清请求
        3. 支持动态干预
        """
        session_id = await self._engine.execute(skill_id, input_data)
        self._active_sessions[skill_id] = session_id

        last_event_index = 0

        try:
            while True:
                # 获取新事件
                events = self._engine.get_session_events(session_id, last_event_index)

                for event in events:
                    last_event_index += 1

                    # 处理澄清请求
                    if event.event_type == "clarification_requested":
                        if on_clarification:
                            # 调用 Agent 的澄清处理函数
                            request_data = event.data
                            request = ClarificationRequest(
                                request_id=request_data["request_id"],
                                question=request_data["question"],
                                context={},
                                options=request_data.get("options"),
                                urgency=request_data.get("urgency", "normal")
                            )
                            answer = await on_clarification(request)

                            # 发送澄清响应
                            await self._engine.request_clarification_response(
                                session_id,
                                request.request_id,
                                answer
                            )

                    # 回调通知
                    if on_event:
                        on_event(event)

                    yield event

                    # 检查是否完成
                    if event.event_type in ("completed", "failed", "cancelled"):
                        return

                # 短暂等待新事件
                await asyncio.sleep(0.1)

        finally:
            self._active_sessions.pop(skill_id, None)

    async def pause_skill(self, skill_id: str):
        """暂停 Skill 执行"""
        session_id = self._active_sessions.get(skill_id)
        if session_id:
            await self._engine.inject_control(session_id, "pause", {})

    async def resume_skill(self, skill_id: str):
        """恢复 Skill 执行"""
        session_id = self._active_sessions.get(skill_id)
        if session_id:
            await self._engine.inject_control(session_id, "resume", {})

    async def update_skill_params(self, skill_id: str, params: dict):
        """动态更新 Skill 参数"""
        session_id = self._active_sessions.get(skill_id)
        if session_id:
            await self._engine.inject_control(session_id, "update_params", params)

    async def cancel_skill(self, skill_id: str):
        """取消 Skill 执行"""
        session_id = self._active_sessions.get(skill_id)
        if session_id:
            await self._engine.inject_control(session_id, "cancel", {})
```

## 4. 使用示例

### 4.1 定义一个流式 Skill

```python
# skills/data_analysis_skill.py

from deva.naja.skill.stream_skill import StreamSkill, SkillContext, SkillEvent
from typing import AsyncIterator, Any

class DataAnalysisSkill(StreamSkill):
    """数据分析 Skill - 支持流式执行和澄清请求"""

    async def execute(
        self,
        input_data: Any,
        context: SkillContext
    ) -> AsyncIterator[SkillEvent]:
        """执行数据分析"""

        # Stage 1: 数据加载
        context.current_stage = "data_loading"
        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"message": "正在加载数据...", "progress": 10},
            stage="data_loading"
        )

        data = await self._load_data(input_data)
        context.intermediate_results.append({"raw_data": data})
        context.create_checkpoint("data_loading")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "data_loading", "rows": len(data)},
            stage="data_loading"
        )

        # Stage 2: 数据清洗（可能需要澄清）
        context.current_stage = "data_cleaning"
        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"message": "正在清洗数据...", "progress": 30},
            stage="data_cleaning"
        )

        # 检测到异常值，发起澄清请求
        outliers = self._detect_outliers(data)
        if outliers:
            response = await self.request_clarification(
                question=f"检测到 {len(outliers)} 个异常值，如何处理？",
                options=["删除", "保留", "标记", "替换为均值"],
                timeout_seconds=30
            )
            data = self._handle_outliers(data, outliers, response.answer)

        context.intermediate_results.append({"cleaned_data": data})
        context.create_checkpoint("data_cleaning")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "data_cleaning"},
            stage="data_cleaning"
        )

        # Stage 3: 数据分析
        context.current_stage = "analysis"
        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"message": "正在进行分析...", "progress": 60},
            stage="analysis"
        )

        # 长时间运行的分析可以被暂停
        for i, chunk in enumerate(self._analyze_in_chunks(data)):
            await self._pause_event.wait()  # 检查是否被暂停

            context.stage_progress["analysis_chunk"] = i
            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"message": f"分析进度: {i+1}/{len(data)//1000}", "progress": 60 + (i * 30 // (len(data)//1000))},
                stage="analysis"
            )

        result = self._compile_results(context.intermediate_results)

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "analysis", "result": result},
            stage="analysis"
        )

    async def _load_data(self, input_data):
        # 实现数据加载
        pass

    def _detect_outliers(self, data):
        # 检测异常值
        pass

    def _handle_outliers(self, data, outliers, method):
        # 处理异常值
        pass

    def _analyze_in_chunks(self, data):
        # 分块分析
        pass

    def _compile_results(self, intermediate_results):
        # 编译最终结果
        pass
```

### 4.2 Agent 调用流式 Skill

```python
# agent.py

async def run_analysis_task(agent):
    """运行分析任务"""

    interface = AgentSkillInterface(agent_id="agent_001")

    async def on_event(event: SkillEvent):
        """处理 Skill 事件"""
        if event.event_type == "progress":
            print(f"进度: {event.data['progress']}% - {event.data['message']}")
        elif event.event_type == "clarification_requested":
            print(f"需要澄清: {event.data['question']}")

    async def on_clarification(request: ClarificationRequest) -> str:
        """处理澄清请求 - 这里可以调用 LLM 或询问用户"""
        # 示例：自动选择第一个选项
        if request.options:
            return request.options[0]
        return "继续"

    # 流式调用
    async for event in interface.invoke_skill_stream(
        skill_id="data_analysis",
        input_data={"file": "sales_data.csv"},
        on_event=on_event,
        on_clarification=on_clarification
    ):
        if event.event_type == "completed":
            print(f"分析完成: {event.data}")
        elif event.event_type == "failed":
            print(f"分析失败: {event.data['error']}")

    # 动态干预示例
    await interface.pause_skill("data_analysis")  # 暂停
    await interface.update_skill_params("data_analysis", {"threshold": 0.8})  # 更新参数
    await interface.resume_skill("data_analysis")  # 恢复
```

## 5. 集成到现有系统

### 5.1 与现有 Skill 系统的兼容

```python
# deva/naja/skill/adapter.py

class LegacySkillAdapter(StreamSkill):
    """适配器：将传统 Skill 包装为流式 Skill"""

    def __init__(self, legacy_skill: 'LegacySkill'):
        super().__init__(skill_id=legacy_skill.skill_id)
        self._legacy_skill = legacy_skill

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """包装传统 Skill 的执行"""

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"message": "执行传统 Skill...", "progress": 0}
        )

        try:
            # 在后台线程执行传统 Skill
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._legacy_skill.execute,
                input_data
            )

            yield SkillEvent(
                event_type="stage_completed",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"result": result}
            )

        except Exception as e:
            yield SkillEvent(
                event_type="failed",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"error": str(e)}
            )
```

### 5.2 与 Naja 策略系统的集成

```python
# deva/naja/strategy/stream_integration.py

class StreamStrategyEntry(StrategyEntry):
    """支持流式执行的策略条目"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stream_skill: Optional[StreamSkill] = None
        self._execution_session: Optional[str] = None

    async def start_streaming(self) -> str:
        """启动流式执行"""
        # 创建流式 Skill 包装器
        self._stream_skill = StrategyStreamSkill(self)

        # 启动执行
        engine = get_execution_engine()
        session_id = await engine.execute(
            skill_id=self.id,
            input_data={"strategy_config": self._get_strategy_config()}
        )
        self._execution_session = session_id
        return session_id

    async def inject_control(self, message_type: str, data: Any):
        """注入控制消息"""
        if self._execution_session:
            engine = get_execution_engine()
            await engine.inject_control(self._execution_session, message_type, data)

class StrategyStreamSkill(StreamSkill):
    """策略的流式 Skill 包装"""

    def __init__(self, strategy_entry: StrategyEntry):
        super().__init__(skill_id=strategy_entry.id)
        self._strategy = strategy_entry

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """流式执行策略"""

        # 绑定数据源
        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"message": "绑定数据源...", "progress": 10}
        )

        # 处理数据流
        while self._strategy.is_running:
            await self._pause_event.wait()

            # 获取数据并处理
            data = await self._get_next_data()
            if data is None:
                await asyncio.sleep(0.1)
                continue

            # 执行策略逻辑
            result = await self._process_data(data, context)

            if result:
                yield SkillEvent(
                    event_type="progress",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={"result": result, "progress": 50}
                )

    async def _get_next_data(self):
        # 从数据源获取数据
        pass

    async def _process_data(self, data, context):
        # 处理数据
        pass
```

## 6. 实施计划

### 阶段 1: 基础架构 (2-3 周)

1. 创建 `StreamSkill` 基类
2. 实现 `SkillContext` 上下文管理
3. 实现 `ControlChannel` 控制通道
4. 实现 `ClarificationRequest/Response` 机制

### 阶段 2: 执行引擎 (2 周)

1. 创建 `SkillExecutionEngine`
2. 实现会话管理
3. 实现事件总线
4. 添加状态持久化

### 阶段 3: Agent 接口 (1-2 周)

1. 创建 `AgentSkillInterface`
2. 实现流式调用 API
3. 实现动态干预 API
4. 添加事件订阅机制

### 阶段 4: 集成与适配 (2 周)

1. 创建 `LegacySkillAdapter`
2. 集成到 Naja 策略系统
3. 添加与现有系统的兼容性层
4. 编写迁移指南

### 阶段 5: 测试与优化 (2 周)

1. 编写单元测试
2. 编写集成测试
3. 性能测试与优化
4. 文档编写

## 7. 预期收益

1. **动态智能**: Skill 可以在执行过程中接收新的指令和参数
2. **上下文保持**: 遇到不确定性时可以发起澄清请求，不丢失执行上下文
3. **实时反馈**: Agent 可以实时获取 Skill 的执行进度和中间结果
4. **可干预性**: 主 Agent 可以随时暂停、恢复、修改 Skill 的执行
5. **容错性**: 支持检查点和恢复机制，失败后可以从中断点继续

## 8. 风险评估

| 风险      | 可能性 | 影响 | 缓解措施          |
| ------- | --- | -- | ------------- |
| 性能开销    | 中   | 中  | 使用异步编程，优化事件处理 |
| 复杂度增加   | 高   | 中  | 提供清晰的 API 和文档 |
| 向后兼容性   | 中   | 高  | 提供适配器层        |
| 状态管理复杂性 | 中   | 中  | 使用成熟的序列化方案    |

## 9. 下一步行动

1. **确认需求**: 与用户确认规划是否符合预期
2. **细化设计**: 针对具体使用场景细化设计
3. **原型开发**: 开发一个最小可行原型验证方案
4. **逐步实施**: 按照阶段计划逐步实施

