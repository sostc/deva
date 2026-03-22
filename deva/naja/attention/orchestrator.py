"""
Attention Orchestrator - 注意力协调器

负责:
1. 接收数据源数据
2. 协调各模块处理
3. 管理注意力计算流程
4. 提供统一的缓存访问接口
"""

import numpy as np
from typing import Dict, List, Optional, Any, Set
from collections import deque
import logging
import time

from .integration.attention_system import AttentionSystem
from .integration.integration import _IntelligenceAugmentedSystemInternal

log = logging.getLogger(__name__)

_orchestrator_instance = None


def get_orchestrator():
    """获取 orchestrator 单例"""
    return _orchestrator_instance


class AttentionOrchestrator:
    """
    注意力系统协调器

    数据流:
    DataSource → Orchestrator → AttentionSystem → IntelligenceSystem
    """

    def __init__(
        self,
        attention_system: AttentionSystem,
        intelligence_system: Optional[_IntelligenceAugmentedSystemInternal] = None
    ):
        self._integration = attention_system
        self._intelligence_system = intelligence_system

        self._processed_frames = 0
        self._filtered_frames = 0
        self._last_market_time = 0.0

        self._cached_high_attention_symbols: Set[str] = set()
        self._cached_active_sectors: Set[str] = set()
        self._cached_global_attention = 0.5
        self._cached_activity = 0.5
        self._cached_market_time_str: str = ""

        global _orchestrator_instance
        _orchestrator_instance = self

    def process_datasource_data(
        self,
        data: Dict[str, np.ndarray],
        market_time: Any = None
    ):
        """
        处理数据源数据

        Args:
            data: 包含 symbols, returns, volumes, prices, sector_ids 的字典
            market_time: 市场时间
        """
        self._processed_frames += 1

        symbols = data.get('symbols')
        returns = data.get('returns')
        volumes = data.get('volumes')
        prices = data.get('prices')
        sector_ids = data.get('sector_ids')

        if symbols is None or len(symbols) == 0:
            return

        market_time_str = ""
        if market_time:
            if isinstance(market_time, (int, float)):
                market_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(market_time))
                self._last_market_time = market_time
            else:
                market_time_str = str(market_time)

        returns = np.nan_to_num(returns, nan=0.0, posinf=50.0, neginf=-50.0)
        returns = np.clip(returns, -50.0, 50.0)

        symbols = np.array(symbols) if not isinstance(symbols, np.ndarray) else symbols
        sector_ids = np.array(sector_ids) if sector_ids is not None else np.array([])

        result = self._integration.attention_system.process_snapshot(
            symbols=symbols,
            returns=returns,
            volumes=volumes,
            prices=prices,
            sector_ids=sector_ids,
            timestamp=market_time_str
        )

        if self._intelligence_system is not None:
            try:
                intelligence_result = self._intelligence_system.process_snapshot(
                    symbols=symbols,
                    returns=returns,
                    volumes=volumes,
                    prices=prices,
                    sector_ids=sector_ids,
                    timestamp=market_time_str
                )
                if intelligence_result and 'prediction_scores' in intelligence_result:
                    pred_count = len(intelligence_result['prediction_scores'])
                    if self._processed_frames % 50 == 0:
                        log.info(f"[Intelligence] 预测分数已更新: {pred_count} 个symbol")

                sector_attention = intelligence_result.get('sector_attention', {}) if intelligence_result else {}
                if sector_attention and hasattr(self._intelligence_system, 'predictive_engine'):
                    sector_returns = {}
                    sector_volumes = {}
                    sector_counts = {}
                    for i, sid in enumerate(sector_ids):
                        sid_str = str(sid)
                        sector_returns[sid_str] = sector_returns.get(sid_str, 0.0) + returns[i]
                        sector_volumes[sid_str] = sector_volumes.get(sid_str, 0.0) + (volumes[i] if volumes is not None else 0)
                        sector_counts[sid_str] = sector_counts.get(sid_str, 0) + 1

                    for sid in sector_returns:
                        if sector_counts[sid] > 0:
                            sector_returns[sid] /= sector_counts[sid]

                    base_volume = np.mean(list(sector_volumes.values())) if sector_volumes else 1.0
                    sector_volume_ratios = {sid: vol / base_volume for sid, vol in sector_volumes.items()}

                    self._intelligence_system.predictive_engine.batch_predict_sectors(
                        sector_attentions=sector_attention,
                        sector_returns=sector_returns,
                        sector_volume_ratios=sector_volume_ratios,
                        timestamp=market_time_str
                    )
                    if self._processed_frames % 50 == 0:
                        log.info(f"[Intelligence] 板块预测已更新: {len(sector_attention)} 个板块")
            except Exception as e:
                log.debug(f"智能增强处理失败: {e}")

        self._cached_global_attention = self._integration.attention_system._last_global_attention
        self._cached_activity = self._integration.attention_system._last_activity
        if market_time_str:
            self._cached_market_time_str = market_time_str

    def get_cached_market_time(self) -> str:
        """获取缓存的市场时间字符串"""
        return self._cached_market_time_str

    def get_attention_context(self) -> Dict[str, Any]:
        """获取注意力上下文"""
        return {
            'global_attention': self._cached_global_attention,
            'high_attention_symbols': self._cached_high_attention_symbols,
            'active_sectors': self._cached_active_sectors,
            'processed_frames': self._processed_frames,
            'filtered_frames': self._filtered_frames,
            'filter_ratio': self._filtered_frames / max(self._processed_frames, 1),
            'market_time': self._cached_market_time_str
        }