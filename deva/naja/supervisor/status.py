"""NajaSupervisor 状态查询 Mixin"""

from __future__ import annotations

import time
from typing import Dict, List, Any

import logging

log = logging.getLogger(__name__)


class StatusMixin:
    """系统状态查询"""

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
