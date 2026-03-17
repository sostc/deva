"""策略调试工具

提供策略的调试功能:
- 单步执行调试
- 信号追踪
- 性能分析
- 配置检查

使用方式:
    from deva.naja.strategy.debugger import StrategyDebugger

    debugger = StrategyDebugger(strategy)
    debugger.run_step(data)
    debugger.print_signal()
    debugger.get_stats()
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class DebugStep:
    """调试步骤"""

    step: int
    timestamp: float
    input_data: Any
    output_signal: Any
    process_time_ms: float
    error: Optional[str] = None


@dataclass
class DebugStats:
    """调试统计"""

    total_steps: int = 0
    total_errors: int = 0
    avg_process_time_ms: float = 0
    max_process_time_ms: float = 0
    min_process_time_ms: float = float("inf")
    signals_history: List[Any] = field(default_factory=list)


class StrategyDebugger:
    """策略调试器"""

    def __init__(
        self,
        strategy: Any,
        name: Optional[str] = None,
        verbose: bool = True,
    ):
        self.strategy = strategy
        self.name = name or getattr(strategy, "__class__", "Unknown").__name__
        self.verbose = verbose

        self._steps: List[DebugStep] = []
        self._stats = DebugStats()
        self._current_step = 0

    def run_step(self, data: Any) -> Any:
        """单步执行

        Args:
            data: 输入数据

        Returns:
            Any: 策略信号
        """
        self._current_step += 1
        start_time = time.time()

        try:
            if hasattr(self.strategy, "on_data"):
                self.strategy.on_data(data)
            signal = getattr(self.strategy, "get_signal", lambda: None)()

            process_time = (time.time() - start_time) * 1000

            step = DebugStep(
                step=self._current_step,
                timestamp=start_time,
                input_data=data,
                output_signal=signal,
                process_time_ms=process_time,
            )
            self._steps.append(step)
            self._update_stats(signal, process_time, None)

            if self.verbose:
                self._print_step(step)

            return signal

        except Exception as e:
            process_time = (time.time() - start_time) * 1000
            error_msg = str(e)

            step = DebugStep(
                step=self._current_step,
                timestamp=start_time,
                input_data=data,
                output_signal=None,
                process_time_ms=process_time,
                error=error_msg,
            )
            self._steps.append(step)
            self._update_stats(None, process_time, error_msg)

            if self.verbose:
                print(f"[ERROR] Step {self._current_step}: {error_msg}")

            raise

    def run_batch(self, data_list: List[Any]) -> List[Any]:
        """批量执行

        Args:
            data_list: 数据列表

        Returns:
            List[Any]: 信号列表
        """
        signals = []
        for data in data_list:
            signal = self.run_step(data)
            signals.append(signal)
        return signals

    def _update_stats(
        self,
        signal: Any,
        process_time: float,
        error: Optional[str],
    ) -> None:
        """更新统计"""
        self._stats.total_steps += 1
        if error:
            self._stats.total_errors += 1

        if process_time > 0:
            if self._stats.total_steps == 1:
                self._stats.avg_process_time_ms = process_time
            else:
                self._stats.avg_process_time_ms = (
                    self._stats.avg_process_time_ms * 0.9 + process_time * 0.1
                )

            self._stats.max_process_time_ms = max(
                self._stats.max_process_time_ms, process_time
            )
            self._stats.min_process_time_ms = min(
                self._stats.min_process_time_ms, process_time
            )

        if signal is not None:
            self._stats.signals_history.append(signal)

    def _print_step(self, step: DebugStep) -> None:
        """打印步骤信息"""
        print(f"\n[Step {step.step}] {self.name}")
        print(f"  Time: {step.timestamp:.3f}")
        print(f"  Process: {step.process_time_ms:.2f}ms")
        print(f"  Input: {self._truncate(str(step.input_data), 100)}")
        print(f"  Output: {self._truncate(str(step.output_signal), 100)}")

    def _truncate(self, s: str, max_len: int) -> str:
        """截断字符串"""
        if len(s) <= max_len:
            return s
        return s[: max_len - 3] + "..."

    def print_signal(self) -> None:
        """打印当前信号"""
        signal = getattr(self.strategy, "get_signal", lambda: None)()
        print(f"\n=== Current Signal ===")
        print(signal)

    def print_history(self, last_n: Optional[int] = None) -> None:
        """打印历史信号"""
        history = self._stats.signals_history
        if last_n:
            history = history[-last_n:]

        print(f"\n=== Signal History ({len(history)} signals) ===")
        for i, sig in enumerate(history):
            print(f"  [{i + 1}] {self._truncate(str(sig), 80)}")

    def print_stats(self) -> None:
        """打印统计信息"""
        stats = self._stats

        print(f"\n=== Debug Stats ===")
        print(f"  Total Steps: {stats.total_steps}")
        print(f"  Total Errors: {stats.total_errors}")
        if stats.total_steps > 0:
            error_rate = (stats.total_errors / stats.total_steps) * 100
            print(f"  Error Rate: {error_rate:.1f}%")
        if stats.total_steps > 0:
            print(f"  Avg Process Time: {stats.avg_process_time_ms:.2f}ms")
            print(f"  Max Process Time: {stats.max_process_time_ms:.2f}ms")
            print(f"  Min Process Time: {stats.min_process_time_ms:.2f}ms")

    def get_stats(self) -> DebugStats:
        """获取统计信息"""
        return self._stats

    def get_history(self) -> List[DebugStep]:
        """获取执行历史"""
        return self._steps

    def reset(self) -> None:
        """重置调试器"""
        self._steps.clear()
        self._stats = DebugStats()
        self._current_step = 0

        if hasattr(self.strategy, "reset"):
            self.strategy.reset()

        if self.verbose:
            print(f"[Debugger] Reset: {self.name}")


def create_test_strategy(
    strategy_type: str,
    config: Dict[str, Any],
) -> Any:
    """创建测试用策略

    Args:
        strategy_type: 策略类型
        config: 配置

    Returns:
        Any: 策略实例
    """
    from deva.naja.strategy.runtime import StrategyRegistry

    return StrategyRegistry.create(strategy_type, config)


def debug_strategy(
    strategy_type: str,
    config: Dict[str, Any],
    test_data: Any,
    verbose: bool = True,
) -> DebugStats:
    """快速调试策略

    Args:
        strategy_type: 策略类型
        config: 配置
        test_data: 测试数据
        verbose: 是否打印详细信息

    Returns:
        DebugStats: 调试统计
    """
    strategy = create_test_strategy(strategy_type, config)
    debugger = StrategyDebugger(strategy, verbose=verbose)

    if isinstance(test_data, list):
        debugger.run_batch(test_data)
    else:
        debugger.run_step(test_data)

    debugger.print_stats()
    return debugger.get_stats()


class SignalTracer:
    """信号追踪器"""

    def __init__(self, strategy: Any):
        self.strategy = strategy
        self._traces: List[Dict] = []
        self._enabled = False

    def enable(self) -> None:
        """启用追踪"""
        self._enabled = True
        self._traces.clear()

    def disable(self) -> None:
        """禁用追踪"""
        self._enabled = False

    def trace(self, data: Any, context: Optional[Dict] = None) -> None:
        """记录追踪点"""
        if not self._enabled:
            return

        signal = getattr(self.strategy, "get_signal", lambda: None)()
        self._traces.append(
            {
                "timestamp": time.time(),
                "input": data,
                "signal": signal,
                "context": context or {},
            }
        )

    def get_traces(self) -> List[Dict]:
        """获取追踪记录"""
        return self._traces

    def clear(self) -> None:
        """清空追踪记录"""
        self._traces.clear()
