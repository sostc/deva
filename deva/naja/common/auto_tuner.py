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

    ================================================================================
    单例模式说明：为什么使用单例
    ================================================================================
    1. 全局调优决策：AutoTuner 是全局自动调优决策器，所有自动调优操作
       都通过这个实例。如果存在多个实例，可能导致调优冲突。

    2. 状态一致性：调优条件、触发状态等需要在全系统保持一致。

    3. 生命周期：Tuner 的生命周期与系统一致，随系统启动和关闭。

    4. 这是系统自动调优的设计选择，不是过度工程。
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
        pass

    def _ensure_initialized(self):
        if getattr(self, '_initialized', False):
            return
        with self._init_lock:
            if getattr(self, '_initialized', False):
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
            self._startup_grace_period = 86400
            self._startup_time = time.time()
            self._pending_llm_issues: List[Dict] = []
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
        self._conditions['datasource_error_rate'] = TuneCondition(
            cooldown=300,
            threshold=0.3,  # 错误率超过30%
            action='adjust_datasource_interval'
        )
        self._conditions['replay_processing'] = TuneCondition(
            cooldown=30,
            threshold=500,  # 500ms 处理时间阈值
            action='adjust_replay_interval'
        )
        self._conditions['pytorch_error_rate'] = TuneCondition(
            cooldown=300,
            threshold=0.3,  # 错误率超过 30%
            action='stop_pytorch'
        )
        self._conditions['memory_pressure'] = TuneCondition(
            cooldown=120,
            threshold=90,  # 内存使用 > 90%
            action='stop_pytorch'
        )
        self._conditions['upstream_inactive'] = TuneCondition(
            cooldown=30,
            threshold=0,
            action='adjust_consumer_interval'
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
        if time.time() - self._startup_time < self._startup_grace_period:
            return None
        try:
            from deva.naja.datasource import get_datasource_manager
            from deva.naja.common.recoverable import UnitStatus

            mgr = get_datasource_manager()
            datasources = mgr.list_all()

            delayed = []
            now = time.time()
            for ds in datasources:
                state = getattr(ds, '_state', None)
                if not state:
                    continue

                # 只检查运行中的数据源
                status = getattr(state, 'status', UnitStatus.STOPPED.value)
                if status != UnitStatus.RUNNING.value:
                    continue

                last_ts = getattr(state, 'last_data_ts', 0)
                # 如果从未产生过数据，跳过（避免将新启动的数据源误判为延迟）
                if last_ts == 0:
                    continue

                delay = (now - last_ts) * 1000
                threshold = self._conditions['datasource_delay'].threshold
                if delay > threshold:
                    delayed.append({
                        'id': ds.id,
                        'name': ds.name,
                        'delay_ms': delay
                    })

            if delayed:
                details = ", ".join([f"{d['name']}({d['delay_ms']:.0f}ms)" for d in delayed[:3]])
                if len(delayed) > 3:
                    details += f" 等{len(delayed)}个"
                log.info(f"[AutoTuner] 发现 {len(delayed)} 个延迟数据源，需要 LLM 分析: {details}")
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

    def _check_pytorch_error_rate(self) -> Optional[Dict]:
        """检查 PyTorch 错误率，超过阈值时停止 PyTorch 处理"""
        try:
            from deva.naja.attention.center import get_attention_orchestrator
            orchestrator = get_attention_orchestrator()
            stats = orchestrator.get_stats()

            pytorch_stats = stats.get('pytorch', {})
            total = pytorch_stats.get('total', 0)
            errors = pytorch_stats.get('errors', 0)

            if total < 10:
                return None

            error_rate = errors / total if total > 0 else 0
            threshold = self._conditions['pytorch_error_rate'].threshold

            if error_rate > threshold:
                log.warning(f"[AutoTuner] PyTorch 错误率过高 ({error_rate:.1%} > {threshold:.1%})，将停止 PyTorch 处理器")
                return {
                    'param': 'pytorch_error_rate',
                    'current': error_rate,
                    'suggested': 'stop',
                    'reason': f'PyTorch 错误率 {error_rate:.1%} 超过阈值 {threshold:.1%}',
                    'category': 'error_spike',
                    'action': 'stop_pytorch'
                }
        except Exception as e:
            log.debug(f"[AutoTuner] PyTorch 错误率检查失败: {e}")
        return None

    def _check_memory_pressure(self) -> Optional[Dict]:
        """检查内存压力，超过 90% 时停止 PyTorch 处理释放内存"""
        try:
            import psutil
            process = psutil.Process()
            memory_percent = process.memory_percent()

            threshold = self._conditions['memory_pressure'].threshold

            if memory_percent > threshold:
                log.warning(f"[AutoTuner] 内存压力过高 ({memory_percent:.1f}% > {threshold:.1f}%)，将停止 PyTorch 处理器释放内存")
                return {
                    'param': 'memory_pressure',
                    'current': memory_percent,
                    'suggested': 'stop',
                    'reason': f'内存使用 {memory_percent:.1f}% 超过阈值 {threshold:.1f}%',
                    'category': 'resource_exhaustion',
                    'action': 'stop_pytorch'
                }
        except Exception as e:
            log.debug(f"[AutoTuner] 内存压力检查失败: {e}")
        return None

    def _check_upstream_inactive(self) -> Optional[Dict]:
        """检测上游数据源/策略是否活跃，调整消费者组件间隔

        当上游（数据源、策略）不活跃时，相关消费者（SignalListener、MarketObserver）
        会进入低频模式，此时可以增大其轮询间隔以节省资源。
        """
        try:
            inactive_consumers = []

            listener_info = self._check_signal_listener_upstream()
            if listener_info:
                inactive_consumers.append(listener_info)

            observer_info = self._check_market_observer_upstream()
            if observer_info:
                inactive_consumers.append(observer_info)

            if inactive_consumers:
                return {
                    'param': 'upstream_inactive',
                    'inactive_consumers': inactive_consumers,
                    'action': 'adjust_consumer_interval',
                    'auto_executed': True,
                    'reason': f"检测到 {len(inactive_consumers)} 个消费者上游不活跃",
                    'category': 'resource_conservation'
                }
        except Exception as e:
            log.debug(f"[AutoTuner] 上游不活跃检查失败: {e}")
        return None

    def _check_signal_listener_upstream(self) -> Optional[Dict]:
        """检测 SignalListener 的上游（策略）是否活跃"""
        try:
            from deva.naja.bandit.signal_listener import get_signal_listener
            listener = get_signal_listener()

            if not listener._running:
                return None

            from deva.naja.strategy import get_strategy_manager
            mgr = get_strategy_manager()
            active_count = 0
            for entry in mgr.list_all():
                if entry.is_processing_data(timeout=300):
                    active_count += 1

            if active_count == 0:
                current_interval = listener._poll_interval
                target_interval = 60.0  # 低频模式目标间隔
                if current_interval < target_interval:
                    return {
                        'consumer_name': 'signal_listener',
                        'current_interval': current_interval,
                        'target_interval': target_interval,
                        'reason': f'无策略处理数据 (active_count=0)'
                    }
        except Exception as e:
            log.debug(f"[AutoTuner] SignalListener 上游检测失败: {e}")
        return None

    def _check_market_observer_upstream(self) -> Optional[Dict]:
        """检测 MarketObserver 的上游（数据源）是否可用"""
        try:
            from deva.naja.bandit.market_observer import get_market_observer
            observer = get_market_observer()

            if not observer._running:
                return None

            if observer._current_datasource is None:
                current_interval = observer._fetch_interval
                target_interval = 60.0  # 低频模式目标间隔
                if current_interval < target_interval:
                    return {
                        'consumer_name': 'market_observer',
                        'current_interval': current_interval,
                        'target_interval': target_interval,
                        'reason': f'数据源不可用 (_current_datasource is None)'
                    }
        except Exception as e:
            log.debug(f"[AutoTuner] MarketObserver 上游检测失败: {e}")
        return None

    def _adjust_consumer_intervals(self, inactive_consumers: List[Dict]):
        """调整消费者组件的轮询间隔"""
        for consumer in inactive_consumers:
            try:
                consumer_name = consumer['consumer_name']
                current_interval = consumer['current_interval']
                target_interval = consumer['target_interval']
                reason = consumer['reason']

                if consumer_name == 'signal_listener':
                    from deva.naja.bandit.signal_listener import get_signal_listener
                    listener = get_signal_listener()
                    listener.set_poll_interval(target_interval)
                    log.info(f"[AutoTuner] SignalListener 间隔调整: {current_interval}s → {target_interval}s ({reason})")

                elif consumer_name == 'market_observer':
                    from deva.naja.bandit.market_observer import get_market_observer
                    observer = get_market_observer()
                    observer.adjust_interval(target_interval, reason)
                    log.info(f"[AutoTuner] MarketObserver 间隔调整: {current_interval}s → {target_interval}s ({reason})")

            except Exception as e:
                log.warning(f"[AutoTuner] 调整 {consumer.get('consumer_name', 'unknown')} 间隔失败: {e}")

    def _check_datasource_error_rate(self) -> Optional[Dict]:
        """检查数据源错误率，自动调整执行间隔

        策略:
        - 错误率 > 50%: 间隔增加 2 倍
        - 错误率 > 30%: 间隔增加 1.5 倍
        - 连续成功 > 10 次: 间隔减少 10%（最小 5 秒）
        """
        try:
            from deva.naja.datasource import get_datasource_manager

            mgr = get_datasource_manager()
            datasources = mgr.list_all()

            adjusted = []
            for ds in datasources:
                state = getattr(ds, '_state', None)
                if not state:
                    continue

                run_count = getattr(state, 'run_count', 0)
                error_count = getattr(state, 'error_count', 0)

                # 至少需要 5 次运行才进行判断
                if run_count < 5:
                    continue

                error_rate = error_count / run_count if run_count > 0 else 0
                current_interval = getattr(ds._metadata, 'interval', 5.0)
                threshold = self._conditions['datasource_error_rate'].threshold

                # 高错误率：增加间隔
                if error_rate > 0.5:
                    new_interval = min(current_interval * 2, 300)  # 最大 5 分钟
                    if new_interval != current_interval:
                        ds.update_config(interval=new_interval)
                        adjusted.append({
                            'id': ds.id,
                            'name': ds.name,
                            'old_interval': current_interval,
                            'new_interval': new_interval,
                            'error_rate': error_rate,
                            'reason': f'错误率过高({error_rate:.1%})，自动增加执行间隔'
                        })
                elif error_rate > threshold:
                    new_interval = min(current_interval * 1.5, 300)
                    if new_interval != current_interval:
                        ds.update_config(interval=new_interval)
                        adjusted.append({
                            'id': ds.id,
                            'name': ds.name,
                            'old_interval': current_interval,
                            'new_interval': new_interval,
                            'error_rate': error_rate,
                            'reason': f'错误率较高({error_rate:.1%})，自动增加执行间隔'
                        })
                # 低错误率且间隔较大：可以尝试减少间隔
                elif error_rate < 0.05 and current_interval > 10:
                    new_interval = max(current_interval * 0.9, 5)  # 最小 5 秒
                    if new_interval != current_interval:
                        ds.update_config(interval=new_interval)
                        adjusted.append({
                            'id': ds.id,
                            'name': ds.name,
                            'old_interval': current_interval,
                            'new_interval': new_interval,
                            'error_rate': error_rate,
                            'reason': f'运行稳定(错误率{error_rate:.1%})，自动优化执行间隔'
                        })

            if adjusted:
                details = ", ".join([f"{d['name']}({d['old_interval']:.0f}s→{d['new_interval']:.0f}s)" for d in adjusted[:3]])
                if len(adjusted) > 3:
                    details += f" 等{len(adjusted)}个"
                log.info(f"[AutoTuner] 自动调整 {len(adjusted)} 个数据源的执行间隔: {details}")
                return {
                    'param': 'datasource_error_rate',
                    'current': len(adjusted),
                    'suggested': 'auto_adjusted',
                    'reason': f"自动调整 {len(adjusted)} 个数据源的执行间隔",
                    'category': 'performance_degradation',
                    'action': 'adjust',
                    'auto_executed': True,
                    'explanation': f"根据错误率自动调整数据源执行间隔，降低失败频率",
                    'impact': f"已调整 {len(adjusted)} 个数据源",
                    'datasources': adjusted
                }
        except Exception as e:
            log.error(f"[AutoTuner] 数据源错误率检查失败: {e}")
        return None

    def _check_replay_processing(self) -> Optional[Dict]:
        """检查回放处理性能，动态调整间隔"""
        try:
            from deva.naja.performance import ComponentType

            metrics_dict = self.get_metrics_by_type(ComponentType.DATASOURCE)
            replay_metrics = metrics_dict.get("datasource:replay_scheduler")

            if not replay_metrics:
                return None

            avg_time = replay_metrics.get('avg_execution_time_ms', 0)
            max_time = replay_metrics.get('max_execution_time_ms', 0)
            threshold = self._conditions['replay_processing'].threshold

            if max_time > threshold * 2:
                new_interval = 0.1
                return {
                    'param': 'replay_processing',
                    'current': max_time,
                    'suggested': new_interval,
                    'reason': f"处理时间过长 (max={max_time:.0f}ms)，大幅增加间隔",
                    'category': 'system_overload',
                    'action': 'adjust_replay_interval',
                    'auto_executed': True,
                    'explanation': f"检测到回放处理时间过长，系统自动增加间隔以减轻压力",
                    'impact': f"间隔调整为 {new_interval}s"
                }
            elif avg_time > threshold:
                new_interval = 2.0
                return {
                    'param': 'replay_processing',
                    'current': avg_time,
                    'suggested': new_interval,
                    'reason': f"处理时间较长 (avg={avg_time:.0f}ms)，增加间隔",
                    'category': 'system_overload',
                    'action': 'adjust_replay_interval',
                    'auto_executed': True,
                    'explanation': f"检测到回放处理时间超过阈值，系统自动增加间隔",
                    'impact': f"间隔调整为 {new_interval}s"
                }
            elif avg_time < threshold * 0.3 and avg_time > 0:
                new_interval = 0.5
                return {
                    'param': 'replay_processing',
                    'current': avg_time,
                    'suggested': new_interval,
                    'reason': f"处理时间充裕 (avg={avg_time:.0f}ms)，可以加快",
                    'category': 'performance_good',
                    'action': 'adjust_replay_interval',
                    'auto_executed': True,
                    'explanation': f"检测到回放处理时间充裕，系统自动加快处理节奏",
                    'impact': f"间隔调整为 {new_interval}s"
                }

        except Exception as e:
            log.debug(f"[AutoTuner] 回放处理检查失败: {e}")
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
                from deva.llm.worker_runtime import run_ai_in_worker, run_sync_in_worker
                controller = get_llm_controller()

                param = issue.get('param', 'unknown')
                reason = issue.get('reason', '')
                category = issue.get('category', '')

                log.info(f"[AutoTuner] 调用 LLM 调优: {param}, 原因: {reason}")

                result = run_sync_in_worker(
                    controller.review_and_adjust(
                        window_seconds=600,
                        dry_run=False
                    )
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

    def _call_llm_for_tuning_batch(self, issues: List[Dict]):
        """批量调用 LLM 进行调优（合并多个问题一次提交）"""
        now = time.time()

        # 合并待处理的请求和新请求
        if self._pending_llm_issues:
            issues = self._pending_llm_issues + issues
            self._pending_llm_issues.clear()
            log.info(f"[AutoTuner] 合并 {len(issues)} 个待处理请求一起提交")

        if now - self._last_llm_call_ts < self._llm_cooldown:
            log.info(f"[AutoTuner] LLM 调用冷却中 ({self._llm_cooldown}秒)，{len(issues)} 个请求暂缓")
            for issue in issues:
                self._pending_llm_issues.append(issue)
            return

        self._last_llm_call_ts = now

        if self._llm_thread and self._llm_thread.is_alive():
            log.info("[AutoTuner] LLM 线程忙碌中，将在下个周期重试")
            for issue in issues:
                self._pending_llm_issues.append(issue)
            return

        def _async_llm_batch():
            try:
                from deva.naja.llm_controller import get_llm_controller
                from deva.llm.worker_runtime import run_ai_in_worker, run_sync_in_worker
                controller = get_llm_controller()

                params = ", ".join([f"{i.get('param', 'unknown')}({i.get('reason', '')[:30]})" for i in issues[:5]])
                if len(issues) > 5:
                    params += f" 等{len(issues)}项"
                log.info(f"[AutoTuner] 批量调用 LLM 调优 ({len(issues)} 项): {params}")

                result = run_sync_in_worker(
                    controller.review_and_adjust(
                        window_seconds=600,
                        dry_run=False
                    )
                )

                if result.get('success'):
                    decision = result.get('decision', {})
                    log.info(f"[AutoTuner] LLM 批量调优完成: {decision.get('reasoning', '已完成')[:100]}")
                    for issue in issues:
                        issue['llm_suggestion'] = decision.get('reasoning', 'LLM 已完成分析')
                        issue['llm_action'] = decision.get('action', '无需操作')
                        issue['llm_success'] = True
                else:
                    log.warning(f"[AutoTuner] LLM 批量调优失败: {result.get('error')}")
                    for issue in issues:
                        issue['llm_suggestion'] = f"调优失败: {result.get('error')}"
                        issue['llm_success'] = False

            except Exception as e:
                log.error(f"[AutoTuner] LLM 批量调优调用失败: {e}")
                for issue in issues:
                    issue['llm_suggestion'] = f"调用失败: {str(e)}"
                    issue['llm_success'] = False

        self._llm_thread = threading.Thread(target=_async_llm_batch, daemon=True)
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
        time.sleep(60)
        while self._running:
            if self._enabled:
                self._perform_checks()
            time.sleep(60)

    def _perform_checks(self):
        if time.time() - self._startup_time < self._startup_grace_period:
            return

        check_methods = [
            self._check_thread_pool,
            self._check_thread_pool_rejected,
            self._check_memory,
            self._check_strategy_performance,
            self._check_lock_contention,
            self._check_datasource_delay,
            self._check_datasource_error_rate,
            self._check_cache_hit_rate,
            self._check_replay_processing,
            self._check_pytorch_error_rate,
            self._check_memory_pressure,
            self._check_upstream_inactive,
        ]

        # 先收集所有检测结果
        all_issues = []
        for method in check_methods:
            try:
                result = method()
                if result:
                    all_issues.append(result)
            except Exception as e:
                log.error(f"调优检查失败: {method.__name__}, {e}")

        if self._pending_llm_issues:
            all_issues.extend(self._pending_llm_issues)
            self._pending_llm_issues.clear()

        # 分类处理：自动执行的立即执行，需要 LLM 的收集起来
        llm_issues = []
        for issue in all_issues:
            action = issue.get('action', 'adjust')
            param = issue.get('param', 'unknown')

            condition = self._conditions.get(param)
            if condition:
                state = self._condition_states.get(param)
                if state:
                    state.trigger_count += 1
                    state.last_trigger_ts = time.time()

            if action == 'call_llm':
                llm_issues.append(issue)
                self._record_event(issue, triggered_by_llm=True)
            else:
                self._record_event(issue, triggered_by_llm=False)
                self._execute_auto_action(issue)

        # 合并所有 LLM 请求，一次性调用
        if llm_issues:
            self._call_llm_for_tuning_batch(llm_issues)

    def _execute_auto_action(self, issue: Dict):
        """执行自动动作（不需要 LLM 的调优动作）"""
        action = issue.get('action', 'adjust')
        param = issue.get('param', 'unknown')

        if action == 'adjust_replay_interval':
            new_interval = issue.get('suggested', 1.0)
            reason = issue.get('reason', '')
            try:
                from deva.naja.replay import get_replay_scheduler
                scheduler = get_replay_scheduler()
                if scheduler:
                    scheduler.adjust_interval(new_interval, reason)
                    log.info(f"[AutoTuner] 调整回放间隔: {reason}")
                    return
            except Exception as e:
                log.warning(f"[AutoTuner] 调整回放间隔失败: {e}")

        elif action == 'stop_pytorch':
            reason = issue.get('reason', '')
            try:
                from deva.naja.attention.center import get_attention_orchestrator
                orchestrator = get_attention_orchestrator()
                orchestrator.stop_pytorch_processor()
                log.info(f"[AutoTuner] 已停止 PyTorch 处理器: {reason}")
                return
            except Exception as e:
                log.warning(f"[AutoTuner] 停止 PyTorch 处理器失败: {e}")

        elif action == 'adjust_consumer_interval':
            inactive_consumers = issue.get('inactive_consumers', [])
            if inactive_consumers:
                self._adjust_consumer_intervals(inactive_consumers)
            return

        elif action == 'adjust_datasource_interval':
            try:
                from deva.naja.datasource import get_datasource_manager
                mgr = get_datasource_manager()
                for ds_info in issue.get('datasources', []):
                    ds_id = ds_info.get('id')
                    if ds_id:
                        ds = mgr.get(ds_id)
                        if ds and ds_info.get('new_interval'):
                            ds.update_config(interval=ds_info['new_interval'])
                log.info(f"[AutoTuner] 调整数据源间隔完成")
            except Exception as e:
                log.warning(f"[AutoTuner] 调整数据源间隔失败: {e}")

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

        if action == 'adjust_replay_interval':
            new_interval = issue.get('suggested', 1.0)
            reason = issue.get('reason', '')
            try:
                from deva.naja.replay import get_replay_scheduler
                scheduler = get_replay_scheduler()
                if scheduler:
                    scheduler.adjust_interval(new_interval, reason)
                    self._record_event(issue, triggered_by_llm=False)
                    return
            except Exception as e:
                log.warning(f"[AutoTuner] 调整回放间隔失败: {e}")

        if action == 'stop_pytorch':
            reason = issue.get('reason', '')
            try:
                from deva.naja.attention.center import get_attention_orchestrator
                orchestrator = get_attention_orchestrator()
                orchestrator.stop_pytorch_processor()
                log.info(f"[AutoTuner] 已停止 PyTorch 处理器: {reason}")
                self._record_event(issue, triggered_by_llm=False)
                return
            except Exception as e:
                log.warning(f"[AutoTuner] 停止 PyTorch 处理器失败: {e}")

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

        self._call_llm_for_tuning_batch([issue])

        return {
            'success': True,
            'requirement': user_requirement,
            'status': 'LLM 调优已启动，请稍候查看结果'
        }

    def add_condition(self, name: str, condition: TuneCondition):
        self._ensure_initialized()
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
        result = []
        for name in self._condition_states:
            condition = self._conditions.get(name)
            state = self._condition_states[name]
            result.append({
                'name': name,
                'has_condition': name in self._conditions,
                'trigger_count': state.trigger_count,
                'last_trigger_ts': state.last_trigger_ts,
                'action': condition.action if condition else '',
                'threshold': condition.threshold if condition else None,
                'cooldown': condition.cooldown if condition else None,
            })
        return result

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
    tuner._ensure_initialized()
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
