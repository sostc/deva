"""
MarketHotspotSystemIntegration - 与 Naja 系统的集成层

提供与现有 DataSource 和 Strategy 的集成接口。
从 market_hotspot_system.py 中抽出。
"""

import time
import numpy as np
from typing import Dict, List, Optional, Any, Callable

from deva.naja.dictionary.blocks import get_stock_name


class MarketHotspotSystemIntegration:
    """
    与 Naja 系统的集成层

    提供与现有 DataSource 和 Strategy 的集成接口
    """

    def __init__(self, hotspot_system):
        self.hotspot_system = hotspot_system
        self._datasource_callbacks: List[Callable] = []
        self._strategy_callbacks: List[Callable] = []

        self._push_center = None
        self._push_to_frontend = True

    def _get_push_center(self):
        """获取推送中心（延迟导入避免循环依赖）"""
        if self._push_center is None:
            try:
                from deva.naja.market_hotspot.push_center import get_push_center
                self._push_center = get_push_center()
            except ImportError:
                return None
        return self._push_center

    def set_push_to_frontend(self, enabled: bool):
        """启用/禁用推送到前端"""
        self._push_to_frontend = enabled

    def _convert_to_push_data(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """将 process_snapshot 返回的 result 转换为推送格式"""
        block_hotspot = result.get('block_hotspot', {})
        symbol_weights = result.get('symbol_weights', {})

        top_blocks = []
        for bid, w in sorted(block_hotspot.items(), key=lambda x: -x[1])[:10]:
            top_blocks.append({
                'block_id': bid,
                'name': bid,
                'weight': float(w)
            })

        top_stocks = []
        for sym, w in sorted(symbol_weights.items(), key=lambda x: -x[1])[:10]:
            top_stocks.append({
                'symbol': sym,
                'name': get_stock_name(sym),
                'weight': float(w)
            })

        return {
            'timestamp': result.get('timestamp', time.time()),
            'market': result.get('market', 'CN'),
            'global_hotspot': result.get('global_hotspot', 0.0),
            'activity': result.get('market_state', {}).get('activity', 0.0),
            'hot_blocks': top_blocks,
            'hot_stocks': top_stocks,
            'block_changes': [],
            'stock_changes': [],
            'raw_snapshot': result,
        }

    def on_datasource_data(self, data: Dict[str, Any]):
        """
        处理数据源数据

        将数据源数据转换为快照格式并处理
        """
        snapshot_data = self._parse_datasource_data(data)

        if snapshot_data:
            result = self.hotspot_system.process_snapshot(**snapshot_data)

            for callback in self._datasource_callbacks:
                try:
                    callback(result)
                except Exception as e:
                    pass

            if self._push_to_frontend:
                push_center = self._get_push_center()
                if push_center is not None:
                    push_data = self._convert_to_push_data(result)
                    push_center.push_dict(push_data)

    def _parse_datasource_data(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析数据源数据为快照格式"""
        try:
            return {
                'symbols': np.array(data['symbols']),
                'returns': np.array(data['returns']),
                'volumes': np.array(data['volumes']),
                'prices': np.array(data['prices']),
                'block_ids': np.array(data.get('block_ids', [])),
                'timestamp': data.get('timestamp', time.time())
            }
        except Exception as e:
            return None

    def register_datasource_callback(self, callback: Callable):
        """注册数据源回调"""
        self._datasource_callbacks.append(callback)

    def register_strategy_callback(self, callback: Callable):
        """注册策略回调"""
        self._strategy_callbacks.append(callback)

    def get_datasource_config(self) -> Dict[str, Any]:
        """
        获取数据源配置

        用于动态调整数据源订阅
        """
        return self.hotspot_system.get_datasource_control()

    def should_process_strategy(self, strategy_id: str) -> bool:
        """判断是否应该处理指定策略"""
        active_strategies = self.hotspot_system.strategy_allocator.get_active_strategies()
        return strategy_id in active_strategies

    def save_state(self) -> Dict[str, Any]:
        """保存市场热点系统状态用于持久化（包含A股和美股）"""
        return self.hotspot_system.save_state()

    def load_state(self, state: Dict[str, Any]) -> bool:
        """从持久化状态恢复市场热点系统"""
        return self.hotspot_system.load_state(state)
