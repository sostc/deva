"""NajaSupervisor 监控功能 Mixin"""

from __future__ import annotations

import time
import threading
from typing import Dict, Any

from deva import log as deva_log
import logging

log = logging.getLogger(__name__)


class MonitoringMixin:
    """监控系统启动、停止、循环检查"""

    def start_monitoring(self):
        """开始监控系统"""
        if self._running:
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        # 启动统一性能监控
        try:
            from deva.naja.infra.observability.performance_monitor import start_performance_monitoring
            start_performance_monitoring()
        except Exception as e:
            log.warning(f"统一性能监控启动失败: {e}")

        # 启用存储性能监控
        try:
            from deva.naja.infra.observability.storage_monitor import enable_storage_monitoring
            enable_storage_monitoring()
        except Exception as e:
            log.warning(f"存储性能监控启用失败: {e}")

        # 启动自动调优
        try:
            from deva.naja.infra.observability.auto_tuner import _init_help_to_db, start_auto_tuner
            _init_help_to_db()
            start_auto_tuner()
        except Exception as e:
            log.warning(f"自动调优启动失败: {e}")
        
        # 启动注意力系统
        try:
            from deva.naja.market_hotspot.integration.market_hotspot_config import load_config
            from deva.naja.market_hotspot.integration.market_hotspot_integration import initialize_hotspot_system

            attention_config = load_config()

            if attention_config.enabled:
                config = attention_config.to_hotspot_system_config()
                force_realtime = getattr(self, '_force_realtime', False)
                lab_mode = getattr(self, '_lab_mode', False)
                attention_system = initialize_hotspot_system(
                    config,
                    force_realtime=force_realtime,
                    lab_mode=lab_mode
                )
                self._components['attention'] = attention_system
                self._components['hotspot_integration'] = attention_system

                try:
                    attention_system.load_state()
                except Exception as e:
                    log.debug(f"加载市场热点系统状态失败: {e}")

                # 启动注意力策略系统
                try:
                    from deva.naja.market_hotspot.strategies import setup_attention_strategies
                    strategy_manager = setup_attention_strategies()
                    self._components['attention_strategy_manager'] = strategy_manager
                except Exception as se:
                    log.warning(f"注意力策略系统启动失败: {se}")

                # 启动报告生成器
                try:
                    from deva.naja.attention.tracking.report_generator import start_report_generator
                    report_generator = start_report_generator()
                    self._components['attention_report_generator'] = report_generator
                except Exception as re:
                    log.warning(f"注意力报告生成器启动失败: {re}")

            # 启动 Bandit 自动运行器
            try:
                from deva.naja.bandit.runner import ensure_bandit_auto_runner
                bandit_runner = ensure_bandit_auto_runner(auto_start=True)
                self._components['bandit_runner'] = bandit_runner
                log.info("BanditAutoRunner 已启动")
            except Exception as be:
                log.warning(f"BanditAutoRunner 启动失败: {be}")

            # 启动 PositionMonitor (持仓监控)
            try:
                from deva.naja.attention.tracking.hotspot_signal_tracker import ensure_hotspot_signal_tracker
                from deva.naja.attention.tracking.position_monitor import ensure_position_monitor

                hotspot_signal_tracker = ensure_hotspot_signal_tracker(
                    observation_duration=3600.0,
                    min_confidence=0.5,
                )
                self._components['hotspot_signal_tracker'] = hotspot_signal_tracker

                position_monitor = ensure_position_monitor(
                    update_interval=10.0,
                )
                self._components['position_monitor'] = position_monitor

                log.info("HotspotSignalTracker 和 PositionMonitor 已启动")

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
                                tracked = hotspot_signal_tracker.get_tracked(metrics.symbol)
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
                                        log.info(f"[HotspotSignalTracker] 价格反馈计数: {_price_feedback_count}, 跟踪中: {len(hotspot_signal_tracker.get_all_tracked())}")
                    except Exception as e:
                        log.warning(f"价格更新反馈处理失败: {e}")

                position_monitor.register_callback(_on_price_update)

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
                            log.info(f"[PositionTracker] 观察完成: {result.symbol} 收益={result.return_pct:+.2f}% 时长={result.holding_seconds:.0f}s")
                    except Exception as e:
                        log.warning(f"观察结果反馈处理失败: {e}")

                hotspot_signal_tracker.register_observation_callback(_on_observation_result)

                # 将 position_monitor 的价格更新同步到 hotspot_signal_tracker
                def _sync_price_to_tracker(metrics_list):
                    for metrics in metrics_list:
                        hotspot_signal_tracker.update_price(metrics.symbol, metrics.current_price)

                position_monitor.register_callback(_sync_price_to_tracker)

                log.info("HotspotSignalTracker 和 PositionMonitor 回调注册完成")

                # SignalTuner 已禁用 (自动调参导致策略过于激进)
                log.info("SignalTuner 已禁用 (NAJA_DISABLE_SIGNAL_TUNER)")

            except Exception as te:
                log.warning(f"HotspotSignalTracker 启动失败: {te}")

        except Exception as e:
            log.warning(f"注意力调度系统启动失败: {e}")
    
    def stop_monitoring(self):
        """停止监控系统"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        
        # 停止报告生成器
        try:
            from deva.naja.attention.tracking.report_generator import stop_report_generator
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
