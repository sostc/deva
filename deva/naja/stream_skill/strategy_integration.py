"""
Naja 策略系统集成

将流式 Skill 架构集成到 Naja 策略系统中
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, Any, Optional, Dict, List

from .models import SkillContext, SkillEvent
from .stream_skill import StreamSkill
from .execution_engine import get_execution_engine
from .agent_interface import AgentSkillInterface


class StrategyStreamSkill(StreamSkill):
    """策略流式 Skill 包装器

    将 Naja 策略包装为流式 Skill，使其支持：
    1. 流式执行
    2. 动态参数调整
    3. 实时状态报告
    4. 澄清请求
    """

    def __init__(self, strategy_entry: Any):
        """
        Args:
            strategy_entry: Naja StrategyEntry 实例
        """
        skill_id = getattr(strategy_entry, 'id', 'unknown_strategy')
        super().__init__(skill_id)
        self._strategy = strategy_entry
        self._is_running = False

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """流式执行策略"""
        self._is_running = True

        # 获取策略配置
        strategy_config = input_data.get("strategy_config", {})

        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "strategy_init", "strategy_id": self.skill_id},
            stage="strategy_init"
        )

        # 初始化阶段
        try:
            # 绑定数据源
            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"progress": 10, "message": "绑定数据源..."},
                stage="strategy_init"
            )

            # 模拟数据源绑定
            await asyncio.sleep(0.1)

            # 检查是否需要参数澄清
            params = strategy_config.get("params", {})
            if not params.get("confirmed", False):
                response = await self.request_clarification(
                    question="策略参数未确认，是否使用默认参数？",
                    options=["使用默认", "自定义参数"],
                    timeout_seconds=30
                )

                if response.answer == "自定义参数":
                    # 这里可以进一步请求具体参数
                    yield SkillEvent(
                        event_type="progress",
                        timestamp=time.time(),
                        execution_id=context.execution_id,
                        data={"progress": 20, "message": "等待自定义参数..."},
                        stage="strategy_init"
                    )

            context.create_checkpoint("strategy_init")

            yield SkillEvent(
                event_type="stage_completed",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"stage": "strategy_init"},
                stage="strategy_init"
            )

        except Exception as e:
            yield SkillEvent(
                event_type="failed",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"error": f"初始化失败: {e}", "stage": "strategy_init"},
                stage="strategy_init"
            )
            return

        # 数据处理阶段
        context.current_stage = "data_processing"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "data_processing"},
            stage="data_processing"
        )

        # 模拟持续的数据处理
        iteration = 0
        while self._is_running:
            # 检查是否被暂停
            await self._pause_event.wait()

            # 检查是否被取消
            if self._state.value == "cancelled":
                break

            iteration += 1

            # 模拟处理数据
            await asyncio.sleep(0.5)

            # 模拟产生信号
            if iteration % 5 == 0:
                signal = {
                    "type": "buy",
                    "code": "000001.SZ",
                    "confidence": 0.75,
                    "iteration": iteration
                }

                yield SkillEvent(
                    event_type="progress",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={
                        "progress": min(50 + iteration * 2, 90),
                        "message": f"产生交易信号 #{iteration}",
                        "signal": signal
                    },
                    stage="data_processing"
                )

                context.intermediate_results.append({"signal": signal})

            # 每 10 次迭代创建一个检查点
            if iteration % 10 == 0:
                context.create_checkpoint(f"iteration_{iteration}")

                yield SkillEvent(
                    event_type="checkpoint_created",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={"checkpoint": f"iteration_{iteration}", "signals_count": len(context.intermediate_results)},
                    stage="data_processing"
                )

            # 模拟策略完成条件
            if iteration >= 20:
                break

        if self._is_running:
            yield SkillEvent(
                event_type="stage_completed",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"stage": "data_processing", "total_iterations": iteration},
                stage="data_processing"
            )

            # 总结阶段
            context.current_stage = "summary"
            yield SkillEvent(
                event_type="stage_started",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"stage": "summary"},
                stage="summary"
            )

            summary = {
                "total_signals": len(context.intermediate_results),
                "iterations": iteration,
                "checkpoints": len(context.checkpoints)
            }

            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"progress": 100, "message": "策略执行完成", "summary": summary},
                stage="summary"
            )

            yield SkillEvent(
                event_type="stage_completed",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"stage": "summary", "summary": summary},
                stage="summary"
            )

        self._is_running = False

    def _handle_update_params(self, data: Any):
        """处理参数更新"""
        super()._handle_update_params(data)
        # 更新策略参数
        if hasattr(self._strategy, 'update_params') and callable(getattr(self._strategy, 'update_params')):
            try:
                self._strategy.update_params(data)
            except Exception:
                pass

    def _handle_cancel(self, data: Any):
        """处理取消"""
        self._is_running = False
        if hasattr(self._strategy, 'stop') and callable(getattr(self._strategy, 'stop')):
            try:
                self._strategy.stop()
            except Exception:
                pass
        return super()._handle_cancel(data)


class StreamStrategyManager:
    """流式策略管理器

    管理策略的流式执行
    """

    def __init__(self):
        self._engine = get_execution_engine()
        self._interface = AgentSkillInterface("strategy_manager")
        self._strategy_sessions: Dict[str, str] = {}  # strategy_id -> session_id

    async def start_strategy_streaming(
        self,
        strategy_entry: Any,
        on_event: Optional[Any] = None
    ) -> str:
        """启动策略的流式执行

        Args:
            strategy_entry: 策略条目
            on_event: 事件回调

        Returns:
            会话 ID
        """
        strategy_id = getattr(strategy_entry, 'id', 'unknown')

        # 创建流式 Skill 包装器
        stream_skill = StrategyStreamSkill(strategy_entry)

        # 注册到引擎
        self._engine.register_skill(strategy_id, StrategyStreamSkill)

        # 启动执行
        session_id = await self._engine.execute(
            skill_id=strategy_id,
            input_data={"strategy_config": self._get_strategy_config(strategy_entry)}
        )

        self._strategy_sessions[strategy_id] = session_id

        return session_id

    def _get_strategy_config(self, strategy_entry: Any) -> Dict[str, Any]:
        """获取策略配置"""
        config = {}

        # 尝试从策略条目中提取配置
        if hasattr(strategy_entry, '_metadata'):
            metadata = strategy_entry._metadata
            config['params'] = getattr(metadata, 'strategy_params', {})
            config['type'] = getattr(metadata, 'strategy_type', 'unknown')

        return config

    async def pause_strategy(self, strategy_id: str) -> bool:
        """暂停策略"""
        session_id = self._strategy_sessions.get(strategy_id)
        if session_id:
            return await self._engine.inject_control(session_id, "pause", {})
        return False

    async def resume_strategy(self, strategy_id: str) -> bool:
        """恢复策略"""
        session_id = self._strategy_sessions.get(strategy_id)
        if session_id:
            return await self._engine.inject_control(session_id, "resume", {})
        return False

    async def update_strategy_params(self, strategy_id: str, params: Dict[str, Any]) -> bool:
        """更新策略参数"""
        session_id = self._strategy_sessions.get(strategy_id)
        if session_id:
            return await self._engine.inject_control(session_id, "update_params", params)
        return False

    async def stop_strategy(self, strategy_id: str) -> bool:
        """停止策略"""
        session_id = self._strategy_sessions.get(strategy_id)
        if session_id:
            result = await self._engine.inject_control(session_id, "cancel", {})
            if result:
                del self._strategy_sessions[strategy_id]
            return result
        return False

    def get_strategy_status(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """获取策略状态"""
        session_id = self._strategy_sessions.get(strategy_id)
        if session_id:
            return self._engine.get_session_status(session_id)
        return None

    def list_active_strategies(self) -> Dict[str, str]:
        """列出活跃的策略"""
        return dict(self._strategy_sessions)


class StreamEnhancedStrategy:
    """流式增强的策略基类

    可以被继承以创建原生支持流式执行的策略
    """

    def __init__(self, strategy_id: str):
        self.id = strategy_id
        self._stream_skill: Optional[StrategyStreamSkill] = None
        self._is_streaming = False

    async def start_streaming(self) -> str:
        """启动流式执行"""
        self._stream_skill = StrategyStreamSkill(self)
        self._is_streaming = True

        engine = get_execution_engine()
        engine.register_skill(self.id, type(self._stream_skill))

        session_id = await engine.execute(
            skill_id=self.id,
            input_data={"strategy_config": self.get_config()}
        )

        return session_id

    def get_config(self) -> Dict[str, Any]:
        """获取策略配置（子类可重写）"""
        return {"params": {}}

    def update_params(self, params: Dict[str, Any]):
        """更新参数（子类可重写）"""
        pass

    def stop(self):
        """停止策略（子类可重写）"""
        self._is_streaming = False


# 便捷函数
def enable_streaming_for_strategy(strategy_entry: Any) -> StrategyStreamSkill:
    """为策略启用流式执行

    Args:
        strategy_entry: 策略条目

    Returns:
        流式 Skill 包装器
    """
    return StrategyStreamSkill(strategy_entry)


async def run_strategy_with_streaming(
    strategy_entry: Any,
    on_event: Optional[Any] = None,
    on_clarification: Optional[Any] = None
) -> Dict[str, Any]:
    """使用流式执行运行策略

    Args:
        strategy_entry: 策略条目
        on_event: 事件回调
        on_clarification: 澄清处理回调

    Returns:
        执行结果
    """
    strategy_id = getattr(strategy_entry, 'id', 'unknown')

    # 创建流式 Skill
    stream_skill = StrategyStreamSkill(strategy_entry)

    # 注册到引擎
    engine = get_execution_engine()
    engine.register_skill(strategy_id, StrategyStreamSkill)

    # 创建 Agent 接口
    interface = AgentSkillInterface("strategy_runner")

    # 执行并返回结果
    return await interface.invoke_skill(
        skill_id=strategy_id,
        input_data={"strategy_config": {}}
    )
