"""NajaSupervisor 恢复与生命周期 Mixin"""

from __future__ import annotations

import time
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from deva.naja.register import SR
import logging

log = logging.getLogger(__name__)


class RecoveryLifecycleMixin:
    """故障恢复和系统生命周期管理"""

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
        from deva.naja.signal.stream import get_signal_stream
        from deva.naja.strategy.result_store import get_result_store

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
            hotspot_integration = self._get_component('hotspot_integration')
            if hotspot_integration and hasattr(hotspot_integration, 'persist_state'):
                hotspot_integration.persist_state()
        except Exception as e:
            log.error(f"持久化市场热点系统状态失败: {e}")

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
                from deva.naja.market_hotspot.tracking.history_tracker import get_history_tracker
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
