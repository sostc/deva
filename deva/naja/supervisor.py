"""Naja 系统监控与管理模块

提供系统级的监控、健康检查、故障恢复和状态管理功能。
"""

from __future__ import annotations

import time
import threading
from typing import Dict, List, Optional, Any

from deva import NB, log as deva_log
from deva.naja.register import SR
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
            'attention_tracker': None,
            'price_monitor': None,
            'cognition': None,
        }
        self._status_history: list = []
        self._monitor_thread: Optional[threading.Thread] = None
        self._check_interval = 5

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

            self._components = {
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
                'attention_tracker': None,
                'price_monitor': None,
                'cognition': None,
            }
            self._status_history: List[Dict[str, Any]] = []
            self._monitor_thread: Optional[threading.Thread] = None
            self._running = False
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
                from .datasource import get_datasource_manager
                self._components[name] = get_datasource_manager()
            elif name == 'strategy':
                from .strategy import get_strategy_manager
                self._components[name] = get_strategy_manager()
            elif name == 'task':
                self._components[name] = SR('task_manager')
            elif name == 'dictionary':
                self._components[name] = SR('dictionary_manager')
            elif name == 'signal':
                from .signal.stream import get_signal_stream
                self._components[name] = get_signal_stream()
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
        except Exception as e:
            log.warning(f"统一性能监控启动失败: {e}")

        # 启用存储性能监控
        try:
            from .performance.storage_monitor import enable_storage_monitoring
            enable_storage_monitoring()
        except Exception as e:
            log.warning(f"存储性能监控启用失败: {e}")

        # 启动自动调优
        try:
            from .common.auto_tuner import _init_help_to_db, start_auto_tuner
            _init_help_to_db()
            start_auto_tuner()
        except Exception as e:
            log.warning(f"自动调优启动失败: {e}")
        
        # 启动注意力系统
        try:
            from .attention.config import load_config, get_intelligence_config
            from .market_hotspot.integration.extended import initialize_hotspot_system as initialize_attention_system

            attention_config = load_config()
            intelligence_config = get_intelligence_config()

            if attention_config.enabled:
                config = attention_config.to_attention_system_config()
                force_realtime = getattr(self, '_force_realtime', False)
                lab_mode = getattr(self, '_lab_mode', False)
                attention_system = initialize_attention_system(
                    config,
                    intelligence_config=intelligence_config,
                    force_realtime=force_realtime,
                    lab_mode=lab_mode
                )
                self._components['attention'] = attention_system

                # 启动注意力策略系统
                try:
                    from deva.naja.market_hotspot.strategies import setup_attention_strategies
                    strategy_manager = setup_attention_strategies()
                    self._components['attention_strategy_manager'] = strategy_manager
                except Exception as se:
                    log.warning(f"注意力策略系统启动失败: {se}")

                # 启动报告生成器
                try:
                    from .attention.report_generator import start_report_generator
                    report_generator = start_report_generator()
                    self._components['attention_report_generator'] = report_generator
                except Exception as re:
                    log.warning(f"注意力报告生成器启动失败: {re}")

            # 启动 Bandit 自动运行器
            if intelligence_config.get('enable_feedback') or intelligence_config.get('enable_strategy_learning'):
                try:
                    from .bandit.runner import ensure_bandit_auto_runner
                    bandit_runner = ensure_bandit_auto_runner(auto_start=True)
                    self._components['bandit_runner'] = bandit_runner
                    log.info("BanditAutoRunner 已启动")
                except Exception as be:
                    log.warning(f"BanditAutoRunner 启动失败: {be}")

            # 启动 AttentionTracker (注意力跟踪器)
            if intelligence_config.get('enable_feedback'):
                try:
                    from .attention.tracker import ensure_attention_tracker
                    from .attention.price_monitor import ensure_price_monitor

                    freq_scheduler = None
                    freq_controller = None
                    if attention_system and hasattr(attention_system, 'frequency_scheduler'):
                        freq_scheduler = attention_system.frequency_scheduler
                        freq_controller = attention_system.frequency_controller

                    attention_tracker = ensure_attention_tracker(
                        observation_duration=3600.0,
                        min_confidence=0.5,
                        frequency_scheduler=freq_scheduler,
                    )
                    self._components['attention_tracker'] = attention_tracker

                    price_monitor = ensure_price_monitor(
                        update_interval=60.0,
                        frequency_scheduler=freq_scheduler,
                        adaptive_frequency_controller=freq_controller,
                    )
                    self._components['price_monitor'] = price_monitor

                    if freq_scheduler:
                        log.info(f"频率调度已启用: HIGH=1s, MEDIUM=10s, LOW=60s")
                    else:
                        log.warning("频率调度未启用，PriceMonitor 使用固定间隔")

                    # 注册价格更新回调：将价格更新传递给 FeedbackLoop
                    _price_feedback_count = 0
                    _last_insight_emit_time = time.time()

                    def _on_price_update(metrics_list):
                        nonlocal _price_feedback_count
                        try:
                            from deva.naja.market_hotspot.integration import get_market_hotspot_integration
                            integration = get_market_hotspot_integration()
                            if hasattr(integration, 'feedback_loop') and integration.feedback_loop:
                                feedback_loop = integration.feedback_loop
                                for metrics in metrics_list:
                                    tracked = attention_tracker.get_tracked(metrics.symbol)
                                    if tracked:
                                        feedback_loop.record_price_feedback(
                                            symbol=metrics.symbol,
                                            attention_score=tracked.attention_score,
                                            prediction_score=tracked.prediction_score,
                                            current_price=metrics.current_price,
                                            entry_price=tracked.entry_price,
                                            holding_seconds=metrics.holding_seconds,
                                            market_state=tracked.market_state,
                                            is_new_high=metrics.max_favorable_move > tracked.max_favorable_move if tracked.max_favorable_move > 0 else False,
                                            is_new_low=metrics.max_adverse_move < tracked.max_adverse_move if tracked.max_adverse_move < 0 else False,
                                        )
                                        _price_feedback_count += 1
                                        if _price_feedback_count % 10 == 0:
                                            log.info(f"[AttentionTracker] 价格反馈计数: {_price_feedback_count}, 跟踪中: {len(attention_tracker.get_all_tracked())}")
                        except Exception as e:
                            log.warning(f"价格更新反馈处理失败: {e}")

                    price_monitor.register_callback(_on_price_update)

                    # 注册观察结果回调
                    def _on_observation_result(result):
                        try:
                            from deva.naja.market_hotspot.integration import get_market_hotspot_integration
                            integration = get_market_hotspot_integration()
                            if hasattr(integration, 'feedback_loop') and integration.feedback_loop:
                                feedback_loop = integration.feedback_loop
                                feedback_loop.record_observation(
                                    symbol=result.symbol,
                                    block_id=result.block_id,
                                    strategy_id=result.strategy_id,
                                    attention_score=result.attention_score,
                                    prediction_score=result.prediction_score,
                                    action=result.action,
                                    entry_price=result.entry_price,
                                    exit_price=result.exit_price,
                                    holding_seconds=result.holding_seconds,
                                    market_state=result.market_state,
                                    max_favorable_move=result.max_favorable_move,
                                    max_adverse_move=result.max_adverse_move,
                                )
                                log.info(f"[AttentionTracker] 观察完成: {result.symbol} 收益={result.return_pct:+.2f}% 时长={result.holding_seconds:.0f}s")
                        except Exception as e:
                            log.warning(f"观察结果反馈处理失败: {e}")

                    attention_tracker.register_observation_callback(_on_observation_result)

                    # 将 price_monitor 的价格更新同步到 attention_tracker
                    def _sync_price_to_tracker(metrics_list):
                        for metrics in metrics_list:
                            attention_tracker.update_price(metrics.symbol, metrics.current_price)

                    price_monitor.register_callback(_sync_price_to_tracker)

                    log.info("AttentionTracker 和 PriceMonitor 已启动")

                    # SignalTuner 已禁用 (自动调参导致策略过于激进)
                    log.info("SignalTuner 已禁用 (NAJA_DISABLE_SIGNAL_TUNER)")

                except Exception as te:
                    log.warning(f"AttentionTracker 启动失败: {te}")

        except Exception as e:
            log.warning(f"注意力调度系统启动失败: {e}")
    
    def stop_monitoring(self):
        """停止监控系统"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        
        # 停止报告生成器
        try:
            from .attention.report_generator import stop_report_generator
            stop_report_generator()
            log.info("注意力报告生成器已停止")
        except:
            pass
        
        log.info("系统监控已停止")
    
    def _monitor_loop(self):
        """监控循环"""
        _last_insight_emit = time.time()
        _insight_emit_interval = 60.0

        while self._running:
            try:
                status = self.get_system_status()
                self._status_history.append(status)

                # 保持历史记录不超过100条
                if len(self._status_history) > 100:
                    self._status_history.pop(0)

                # 检查系统健康状态
                self._check_health(status)

                # 定期将注意力反馈结果发送到认知中心
                now = time.time()
                if now - _last_insight_emit >= _insight_emit_interval:
                    _last_insight_emit = now
                    self._emit_feedback_to_cognition()

                time.sleep(self._check_interval)
            except Exception as e:
                log.error(f"监控循环错误: {e}")
                time.sleep(self._check_interval)

    def _emit_feedback_to_cognition(self):
        """将注意力反馈结果发送到认知中心"""
        try:
            attention_system = self._get_component('attention')
            if not attention_system or not hasattr(attention_system, 'feedback_loop') or not attention_system.feedback_loop:
                return

            feedback_loop = attention_system.feedback_loop
            summary = feedback_loop.get_summary()

            if summary['total_outcomes'] == 0:
                return

            count = feedback_loop._emit_to_insight()
            if count > 0:
                log.info(f"[Cognition] 已发送 {count} 个注意力有效性洞察到 InsightPool")

        except Exception as e:
            log.debug(f"发送反馈到认知中心失败: {e}")
    
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
        from .signal.stream import get_signal_stream
        from .strategy.result_store import get_result_store

        try:
            signal_stream = get_signal_stream()
            if hasattr(signal_stream, 'close'):
                signal_stream.close(persist=True)
        except Exception as e:
            log.error(f"停止信号流失败: {e}")

        try:
            result_store = get_result_store()
            if hasattr(result_store, 'close'):
                result_store.close()
        except Exception as e:
            log.error(f"停止结果存储失败: {e}")

        try:
            insight_pool = SR('insight_pool')
            if hasattr(insight_pool, 'persist'):
                insight_pool.persist()
        except Exception as e:
            log.error(f"持久化洞察池失败: {e}")

        try:
            bandit_runner = self._get_component('bandit_runner')
            if bandit_runner and hasattr(bandit_runner, 'stop'):
                bandit_runner.stop()
        except Exception as e:
            log.error(f"停止 Bandit Runner 失败: {e}")

        try:
            attention = self._get_component('attention')
            if attention and hasattr(attention, 'persist_state'):
                attention.persist_state()
        except Exception as e:
            log.error(f"持久化注意力系统状态失败: {e}")

        try:
            radar_engine = self._get_component('radar')
            if radar_engine and hasattr(radar_engine, 'save_state'):
                radar_engine.save_state()
        except Exception as e:
            log.error(f"保存雷达状态失败: {e}")

        try:
            cognition = self._get_component('cognition')
            if cognition and hasattr(cognition, 'save_state'):
                cognition.save_state()
        except Exception as e:
            log.error(f"保存认知状态失败: {e}")

        try:
            bandit_runner = self._get_component('bandit_runner')
            if bandit_runner and hasattr(bandit_runner, 'stop'):
                bandit_runner.stop()
        except Exception as e:
            log.error(f"停止 Bandit Runner 失败: {e}")

        try:
            attention = self._get_component('attention')
            if attention and hasattr(attention, 'persist_state'):
                attention.persist_state()
        except Exception as e:
            log.error(f"持久化注意力系统状态失败: {e}")

        try:
            strategy_mgr = self._get_component('strategy')
            if strategy_mgr:
                for entry in strategy_mgr.list_all():
                    entry.stop()
        except Exception as e:
            log.error(f"停止策略失败: {e}")

        try:
            ds_mgr = self._get_component('datasource')
            if ds_mgr:
                for entry in ds_mgr.list_all():
                    entry.stop()
        except Exception as e:
            log.error(f"停止数据源失败: {e}")

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
        """恢复所有组件的运行状态（并行执行）"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = {}
        components = {
            'datasource': lambda: self._get_component('datasource'),
            'strategy': lambda: self._get_component('strategy'),
            'task': lambda: self._get_component('task'),
        }

        def restore_component(name, getter):
            try:
                comp = getter()
                if comp:
                    return (name, comp.restore_running_states(), None)
                return (name, None, "Component not found")
            except Exception as e:
                return (name, None, str(e))

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(restore_component, name, getter): name
                for name, getter in components.items()
            }

            for future in as_completed(futures):
                name, result, error = future.result()
                if error:
                    results[name] = {'success': False, 'error': error}
                else:
                    results[name] = result

        return results
    
    def shutdown(self) -> Dict[str, Any]:
        """关闭系统"""
        log.info("开始关闭系统...")

        try:
            # 保存 HistoryTracker 热点历史
            try:
                from deva.naja.market_hotspot.market_hotspot_history_tracker import get_history_tracker
                tracker = get_history_tracker()
                if tracker:
                    tracker.save_state()
                    log.info("[shutdown] 热点历史已保存")
            except Exception as e:
                log.warning(f"[shutdown] 保存热点历史失败: {e}")

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
                _register_atexit_cleanup()
    return _naja_supervisor


def _register_atexit_cleanup():
    """注册退出时的清理函数"""
    import atexit

    supervisor = get_naja_supervisor()

    def _cleanup():
        try:
            from deva.naja.market_hotspot.market_hotspot_history_tracker import get_history_tracker
            tracker = get_history_tracker()
            if tracker:
                tracker.save_state()
                log.info("[atexit] 热点历史已保存")
        except Exception as e:
            log.warning(f"[atexit] 保存热点历史失败: {e}")

        try:
            attention = supervisor._get_component('attention')
            if attention and hasattr(attention, 'persist_state'):
                attention.persist_state()
                log.info("[atexit] 注意力系统状态已持久化")
        except Exception as e:
            log.warning(f"[atexit] 持久化注意力系统状态失败: {e}")

    atexit.register(_cleanup)


def stop_supervisor() -> None:
    """停止 Naja 监控器"""
    supervisor = get_naja_supervisor()
    supervisor.stop_monitoring()


def start_supervisor(force_realtime: bool = False, lab_mode: bool = False) -> None:
    """启动 Naja 监控器

    Args:
        force_realtime: 是否强制实时模式（暂未使用）
        lab_mode: 是否为实验模式（暂未使用）
    """
    supervisor = get_naja_supervisor()
    if hasattr(supervisor, 'start_monitoring'):
        supervisor.start_monitoring()


# 别名，保持向后兼容
def get_supervisor() -> NajaSupervisor:
    """获取 Naja 监控器单例（向后兼容别名）"""
    return get_naja_supervisor()
