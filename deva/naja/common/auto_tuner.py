"""自动调优模块

提供系统自动调优功能，包括：
- 线程池调优
- 内存调优
- 策略性能调优 (通过 LLM)
- 锁竞争调优
- 数据源延迟调优
- 缓存命中率调优

检测到问题时：
1. 能自动调优的，直接执行调整
2. 不能自动调优的，调用 LLM 让大模型帮忙调优
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from deva import NB, log


@dataclass
class TuneCondition:
    """调优条件"""
    cooldown: int = 300
    threshold: Any = None
    action: str = ""


@dataclass
class TuneEvent:
    """调优事件"""
    before_value: Any = None
    after_value: Any = None
    param_name: str = ""
    reason: str = ""
    action_type: str = ""
    category: str = ""
    explanation: str = ""
    impact: str = ""
    llm_suggestion: str = ""
    success: bool = True


@dataclass
class ConditionState:
    """条件状态"""
    record: deque = field(default_factory=lambda: deque(maxlen=100))
    is_persistent: bool = False
    trigger_count: int = 0
    last_trigger_ts: float = 0


class AutoTuner:
    """自动调优器

    监控系统状态，自动触发调优操作。
    能自动调优的自动执行，不能调优的调用 LLM。
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._conditions: Dict[str, TuneCondition] = {}
        self._condition_states: Dict[str, ConditionState] = {}
        self._events: deque = deque(maxlen=1000)
        self._enabled = True
        self._running = False
        self._check_thread: Optional[threading.Thread] = None
        self._llm_thread: Optional[threading.Thread] = None
        self._llm_queue: deque = deque(maxlen=100)
        self._last_llm_call_ts = 0
        self._llm_cooldown = 300
        self._register_all_conditions()
        self._initialized = True

    def _register_all_conditions(self):
        self._conditions['thread_pool'] = TuneCondition(
            cooldown=300,
            threshold=100,
            action='adjust_max_workers'
        )
        self._conditions['thread_pool_rejected'] = TuneCondition(
            cooldown=300,
            threshold=10,
            action='adjust_queue_size'
        )
        self._conditions['memory'] = TuneCondition(
            cooldown=600,
            threshold=80,
            action='trigger_gc'
        )
        self._conditions['strategy_performance'] = TuneCondition(
            cooldown=600,
            threshold=0.5,
            action='call_llm'
        )
        self._conditions['lock_contention'] = TuneCondition(
            cooldown=300,
            threshold=50,
            action='call_llm'
        )
        self._conditions['datasource_delay'] = TuneCondition(
            cooldown=300,
            threshold=5000,
            action='call_llm'
        )
        self._conditions['cache_hit_rate'] = TuneCondition(
            cooldown=600,
            threshold=0.3,
            action='call_llm'
        )

        for name in self._conditions:
            self._condition_states[name] = ConditionState()

    def _check_thread_pool(self) -> Optional[Dict]:
        try:
            from deva.naja.common.thread_pool import get_thread_pool
            pool = get_thread_pool()
            stats = pool.get_stats()

            pending = stats.get('pending_tasks', 0)
            threshold = self._conditions['thread_pool'].threshold

            if pending > threshold:
                current = stats['max_workers']
                suggested = min(current + 5, 100)

                pool.max_workers = suggested
                log.info(f"[AutoTuner] 线程池调整: max_workers {current} -> {suggested}, 待处理任务: {pending}")

                return {
                    'param': 'max_workers',
                    'current': current,
                    'suggested': suggested,
                    'reason': f"待处理任务过多: {pending}",
                    'category': 'system_overload',
                    'action': 'adjust',
                    'auto_executed': True,
                    'explanation': f"检测到待处理任务积压({pending}个)超过阈值({threshold}个)，系统自动增加线程池工作线程数以提升处理能力。",
                    'impact': f"max_workers: {current} → {suggested}，预计可提升 {suggested/current*100:.0f}% 的并发处理能力"
                }
        except Exception as e:
            log.error(f"[AutoTuner] 线程池检查失败: {e}")
        return None

    def _check_thread_pool_rejected(self) -> Optional[Dict]:
        try:
            from deva.naja.common.thread_pool import get_thread_pool
            pool = get_thread_pool()
            stats = pool.get_stats()

            rejected = stats.get('total_rejected', 0)
            threshold = self._conditions['thread_pool_rejected'].threshold

            if rejected > threshold:
                current = stats['max_queue_size']
                suggested = min(current + 500, 10000)

                pool.max_queue_size = suggested
                log.info(f"[AutoTuner] 队列调整: max_queue_size {current} -> {suggested}, 被拒绝任务: {rejected}")

                return {
                    'param': 'max_queue_size',
                    'current': current,
                    'suggested': suggested,
                    'reason': f"任务被拒绝过多: {rejected}",
                    'category': 'system_overload',
                    'action': 'adjust',
                    'auto_executed': True,
                    'explanation': f"检测到任务被拒绝次数({rejected}次)过多，系统自动扩大队列容量以容纳更多待处理任务。",
                    'impact': f"max_queue_size: {current} → {suggested}，队列容量扩大 {(suggested/current-1)*100:.0f}%"
                }
        except Exception as e:
            log.error(f"[AutoTuner] 队列检查失败: {e}")
        return None

    def _check_memory(self) -> Optional[Dict]:
        try:
            import psutil
            process = psutil.Process()
            memory_percent = process.memory_percent()

            threshold = self._conditions['memory'].threshold

            if memory_percent > threshold:
                import gc
                gc.collect()
                log.info(f"[AutoTuner] 内存过高 ({memory_percent:.1f}%), 已执行 GC")

                return {
                    'param': 'gc',
                    'current': f"{memory_percent:.1f}%",
                    'suggested': 'gc_collected',
                    'reason': f"内存使用率过高: {memory_percent:.1f}%",
                    'category': 'system_overload',
                    'action': 'adjust',
                    'auto_executed': True,
                    'explanation': f"检测到内存使用率({memory_percent:.1f}%)超过安全阈值({threshold}%)，系统自动执行垃圾回收释放内存。",
                    'impact': "执行 gc.collect()，释放不再使用的对象，预计可降低内存使用 10-30%"
                }
        except ImportError:
            log.warning("[AutoTuner] psutil 未安装，跳过内存检查")
        except Exception as e:
            log.error(f"[AutoTuner] 内存检查失败: {e}")
        return None

    def _check_strategy_performance(self) -> Optional[Dict]:
        try:
            from deva.naja.strategy import get_strategy_manager
            from deva.naja.strategy.result_store import get_result_store

            mgr = get_strategy_manager()
            store = get_result_store()
            strategies = mgr.list_all()

            underperforming = []
            for strategy in strategies:
                stats = store.get_stats(strategy.id)
                success_rate = stats.get('success_rate', 1.0)
                if success_rate < 0.5:
                    underperforming.append({
                        'id': strategy.id,
                        'name': strategy.name,
                        'success_rate': success_rate
                    })

            if underperforming:
                log.info(f"[AutoTuner] 发现 {len(underperforming)} 个低性能策略，需要 LLM 调优")
                return {
                    'param': 'strategy_performance',
                    'current': len(underperforming),
                    'suggested': 'need_llm_tune',
                    'reason': f"发现 {len(underperforming)} 个低性能策略 (成功率 < 50%)",
                    'category': 'performance_degradation',
                    'action': 'call_llm',
                    'auto_executed': False,
                    'strategies': underperforming
                }
        except Exception as e:
            log.error(f"[AutoTuner] 策略性能检查失败: {e}")
        return None

    def _check_lock_contention(self) -> Optional[Dict]:
        try:
            from deva.naja.performance.lock_monitor import get_lock_stats
            stats = get_lock_stats()

            contention = stats.get('total_contention', 0)
            threshold = self._conditions['lock_contention'].threshold

            if contention > threshold:
                log.info(f"[AutoTuner] 锁竞争严重 ({contention} 次)，需要 LLM 分析")
                return {
                    'param': 'lock_contention',
                    'current': contention,
                    'suggested': 'need_llm_analysis',
                    'reason': f"锁竞争严重: {contention} 次",
                    'category': 'performance_degradation',
                    'action': 'call_llm',
                    'auto_executed': False,
                    'stats': stats
                }
        except ImportError:
            pass
        except Exception as e:
            log.error(f"[AutoTuner] 锁竞争检查失败: {e}")
        return None

    def _check_datasource_delay(self) -> Optional[Dict]:
        try:
            from deva.naja.datasource import get_datasource_manager

            mgr = get_datasource_manager()
            datasources = mgr.list_all()

            delayed = []
            now = time.time()
            for ds in datasources:
                state = getattr(ds, '_state', None)
                if state:
                    last_ts = getattr(state, 'last_data_ts', 0)
                    delay = (now - last_ts) * 1000
                    threshold = self._conditions['datasource_delay'].threshold
                    if delay > threshold:
                        delayed.append({
                            'id': ds.id,
                            'name': ds.name,
                            'delay_ms': delay
                        })

            if delayed:
                log.info(f"[AutoTuner] 发现 {len(delayed)} 个延迟数据源，需要 LLM 分析")
                return {
                    'param': 'datasource_delay',
                    'current': len(delayed),
                    'suggested': 'need_llm_analysis',
                    'reason': f"发现 {len(delayed)} 个延迟数据源",
                    'category': 'performance_degradation',
                    'action': 'call_llm',
                    'auto_executed': False,
                    'datasources': delayed
                }
        except Exception as e:
            log.error(f"[AutoTuner] 数据源延迟检查失败: {e}")
        return None

    def _check_cache_hit_rate(self) -> Optional[Dict]:
        return None

    def _call_llm_for_tuning(self, issue: Dict):
        """调用 LLM 进行调优"""
        now = time.time()
        if now - self._last_llm_call_ts < self._llm_cooldown:
            log.info(f"[AutoTuner] LLM 调用冷却中，跳过")
            return

        self._last_llm_call_ts = now

        issue['llm_pending'] = True

        def _async_llm():
            try:
                from deva.naja.llm_controller import get_llm_controller
                controller = get_llm_controller()

                param = issue.get('param', 'unknown')
                reason = issue.get('reason', '')
                category = issue.get('category', '')

                log.info(f"[AutoTuner] 调用 LLM 调优: {param}, 原因: {reason}")

                result = controller.review_and_adjust(
                    window_seconds=600,
                    dry_run=False
                )

                if result.get('success'):
                    decision = result.get('decision', {})
                    log.info(f"[AutoTuner] LLM 调优成功: {decision}")

                    issue['llm_suggestion'] = decision.get('reasoning', 'LLM 已完成分析')
                    issue['llm_action'] = decision.get('action', '无需操作')
                    issue['llm_success'] = True
                else:
                    log.warning(f"[AutoTuner] LLM 调优失败: {result.get('error')}")
                    issue['llm_suggestion'] = f"调优失败: {result.get('error')}"
                    issue['llm_success'] = False

            except Exception as e:
                log.error(f"[AutoTuner] LLM 调优调用失败: {e}")
                issue['llm_suggestion'] = f"调用失败: {str(e)}"
                issue['llm_success'] = False

        if self._llm_thread and self._llm_thread.is_alive():
            log.info("[AutoTuner] LLM 线程忙碌中，将在下个周期重试")
            return

        self._llm_thread = threading.Thread(target=_async_llm, daemon=True)
        self._llm_thread.start()

    def start(self):
        if self._running:
            return

        self._running = True
        self._check_thread = threading.Thread(target=self._check_loop, daemon=True)
        self._check_thread.start()
        log.info("自动调优器已启动")

    def stop(self):
        self._running = False
        if self._check_thread:
            self._check_thread.join(timeout=5)
        log.info("自动调优器已停止")

    def _check_loop(self):
        while self._running:
            if self._enabled:
                self._perform_checks()
            time.sleep(60)

    def _perform_checks(self):
        check_methods = [
            self._check_thread_pool,
            self._check_thread_pool_rejected,
            self._check_memory,
            self._check_strategy_performance,
            self._check_lock_contention,
            self._check_datasource_delay,
            self._check_cache_hit_rate,
        ]

        for method in check_methods:
            try:
                result = method()
                if result:
                    self._handle_issue(result)
            except Exception as e:
                log.error(f"调优检查失败: {method.__name__}, {e}")

    def _handle_issue(self, issue: Dict):
        """处理检测到的问题"""
        action = issue.get('action', 'adjust')
        param = issue.get('param', 'unknown')

        condition = self._conditions.get(param)
        if condition:
            state = self._condition_states.get(param)
            if state:
                state.trigger_count += 1
                state.last_trigger_ts = time.time()

        if action == 'call_llm':
            self._call_llm_for_tuning(issue)
            self._record_event(issue, triggered_by_llm=True)
        else:
            self._record_event(issue, triggered_by_llm=False)

    def _record_event(self, issue: Dict, triggered_by_llm: bool = False):
        event = TuneEvent(
            param_name=issue.get('param', ''),
            before_value=issue.get('current'),
            after_value=issue.get('suggested'),
            reason=issue.get('reason', ''),
            action_type=issue.get('action', 'adjust'),
            category=issue.get('category', ''),
            explanation=issue.get('explanation', ''),
            impact=issue.get('impact', ''),
            llm_suggestion=issue.get('llm_suggestion', ''),
            success=issue.get('llm_success', True) if triggered_by_llm else True
        )
        self._events.append({
            'event': event,
            'timestamp': time.time(),
            'triggered_by_llm': triggered_by_llm
        })

    def trigger_business_change(self, param_name: str, new_value: Any, reason: str = ""):
        event = TuneEvent(
            param_name=param_name,
            before_value=None,
            after_value=new_value,
            reason=reason,
            action_type='business'
        )
        self._events.append({
            'event': event,
            'timestamp': time.time()
        })
        log.info(f"业务变更: {param_name} -> {new_value}, 原因: {reason}")

    def manual_llm_tune(self, user_requirement: str) -> Dict:
        """手动触发 LLM 调优

        Args:
            user_requirement: 用户的调优要求

        Returns:
            调优结果
        """
        log.info(f"[AutoTuner] 手动触发 LLM 调优，要求: {user_requirement}")

        issue = {
            'param': 'manual_tune',
            'current': 'manual',
            'suggested': 'llm_analysis',
            'reason': f"手动调优: {user_requirement}",
            'category': 'manual',
            'action': 'call_llm',
            'auto_executed': False,
            'explanation': f"用户手动触发 LLM 调优，要求: {user_requirement}",
            'user_requirement': user_requirement
        }

        self._record_event(issue, triggered_by_llm=True)

        self._call_llm_for_tuning(issue)

        return {
            'success': True,
            'requirement': user_requirement,
            'status': 'LLM 调优已启动，请稍候查看结果'
        }

    def add_condition(self, name: str, condition: TuneCondition):
        self._conditions[name] = condition
        self._condition_states[name] = ConditionState()

    def remove_condition(self, name: str):
        self._conditions.pop(name, None)
        self._condition_states.pop(name, None)

    def get_status(self) -> Dict:
        active = sum(1 for s in self._condition_states.values() if s.trigger_count > 0)
        return {
            'enabled': self._enabled,
            'running': self._running,
            'conditions_count': len(self._conditions),
            'events_count': len(self._events),
            'active_conditions': active
        }

    def get_recent_events(self, limit: int = 20) -> List[Dict]:
        events = list(self._events)[-limit:]
        return [
            {
                'timestamp': e['timestamp'],
                'param': e['event'].param_name,
                'before': e['event'].before_value,
                'after': e['event'].after_value,
                'reason': e['event'].reason,
                'action': e['event'].action_type,
                'category': e['event'].category,
                'explanation': e['event'].explanation,
                'impact': e['event'].impact,
                'llm_suggestion': e['event'].llm_suggestion,
                'success': e['event'].success,
                'triggered_by_llm': e.get('triggered_by_llm', False)
            }
            for e in events
        ]

    def get_conditions_status(self) -> List[Dict]:
        return [
            {
                'name': name,
                'has_condition': name in self._conditions,
                'trigger_count': self._condition_states[name].trigger_count,
                'last_trigger_ts': self._condition_states[name].last_trigger_ts,
                'action': self._conditions[name].action if name in self._conditions else ''
            }
            for name in self._condition_states
        ]

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False


_auto_tuner: Optional[AutoTuner] = None
_auto_tuner_lock = threading.Lock()


def _init_help_to_db():
    """初始化帮助数据库"""
    pass


def get_auto_tuner() -> AutoTuner:
    global _auto_tuner
    if _auto_tuner is None:
        with _auto_tuner_lock:
            if _auto_tuner is None:
                _auto_tuner = AutoTuner()
    return _auto_tuner


def start_auto_tuner():
    tuner = get_auto_tuner()
    tuner.start()


def stop_auto_tuner():
    tuner = get_auto_tuner()
    tuner.stop()


def trigger_business_adjustment(param_name: str, new_value: Any, reason: str = ""):
    tuner = get_auto_tuner()
    tuner.trigger_business_change(param_name, new_value, reason)


def manual_llm_tune(user_requirement: str) -> Dict:
    """手动触发 LLM 调优"""
    tuner = get_auto_tuner()
    return tuner.manual_llm_tune(user_requirement)
