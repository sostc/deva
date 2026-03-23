"""FilterStage - 过滤器阶段"""

import pandas as pd
import logging
from typing import Optional, Dict, Any, Set, List

from .base import Stage, StageResult, StageType

logger = logging.getLogger(__name__)


class FilterStage(Stage):
    """
    过滤器阶段 - 过滤低质量数据

    支持的过滤规则:
    1. 金额过滤：低于阈值的记录
    2. 成交量过滤：低于阈值的记录
    3. Symbol 白名单：只在白名单中的记录
    4. 涨跌过滤：过滤涨跌停等特殊情况
    """

    def __init__(
        self,
        name: str = "filter",
        min_amount: float = 100000,
        min_volume: int = 10000,
        whitelist_symbols: Optional[Set[str]] = None,
        filter_limit_up: bool = False,
        filter_limit_down: bool = False,
        limit_threshold: float = 9.8,
    ):
        super().__init__(name=name, stage_type=StageType.FILTER)
        self.min_amount = min_amount
        self.min_volume = min_volume
        self.whitelist_symbols = whitelist_symbols
        self.filter_limit_up = filter_limit_up
        self.filter_limit_down = filter_limit_down
        self.limit_threshold = limit_threshold

        self._stats['rows_before_filter'] = 0
        self._stats['rows_after_filter'] = 0

    def _process(self, data: pd.DataFrame, context: Optional[Dict[str, Any]] = None) -> StageResult:
        """执行过滤"""
        self._stats['rows_before_filter'] += len(data)

        if data.empty:
            return StageResult(
                success=True,
                data=data,
                rows_in=len(data),
                rows_out=0,
                rows_filtered=0,
            )

        original_len = len(data)
        mask = pd.Series(True, index=data.index)

        try:
            if 'amount' in data.columns:
                amount_mask = (
                    (data['amount'] >= self.min_amount) |
                    data.index.astype(str).isin(self.whitelist_symbols or set())
                )
                mask = mask & amount_mask

            if 'volume' in data.columns:
                volume_mask = (
                    (data['volume'] >= self.min_volume) |
                    data.index.astype(str).isin(self.whitelist_symbols or set())
                )
                mask = mask & volume_mask

            if self.filter_limit_up and 'p_change' in data.columns:
                limit_up_mask = data['p_change'] < self.limit_threshold
                mask = mask & limit_up_mask

            if self.filter_limit_down and 'p_change' in data.columns:
                limit_down_mask = data['p_change'] > -self.limit_threshold
                mask = mask & limit_down_mask

            filtered_data = data[mask]

            rows_filtered = original_len - len(filtered_data)
            self._stats['rows_after_filter'] += len(filtered_data)

            filter_reasons = {}
            if 'amount' in data.columns:
                low_amount = (data['amount'] < self.min_amount).sum()
                if low_amount > 0:
                    filter_reasons['low_amount'] = int(low_amount)

            if 'volume' in data.columns:
                low_volume = (data['volume'] < self.min_volume).sum()
                if low_volume > 0:
                    filter_reasons['low_volume'] = int(low_volume)

            if self.filter_limit_up and 'p_change' in data.columns:
                limit_ups = (data['p_change'] >= self.limit_threshold).sum()
                if limit_ups > 0:
                    filter_reasons['limit_up'] = int(limit_ups)

            if self.filter_limit_down and 'p_change' in data.columns:
                limit_downs = (data['p_change'] <= -self.limit_threshold).sum()
                if limit_downs > 0:
                    filter_reasons['limit_down'] = int(limit_downs)

            return StageResult(
                success=True,
                data=filtered_data,
                rows_in=original_len,
                rows_out=len(filtered_data),
                rows_filtered=rows_filtered,
                metadata={
                    'filter_reasons': filter_reasons,
                    'filter_rate': rows_filtered / original_len if original_len > 0 else 0,
                }
            )

        except Exception as e:
            logger.exception(f"[{self.name}] 过滤失败: {e}")
            return StageResult(
                success=False,
                data=data,
                error=str(e),
                rows_in=len(data),
                rows_out=len(data),
                rows_filtered=0,
            )

    def update_whitelist(self, symbols: Set[str]):
        """更新白名单"""
        self.whitelist_symbols = symbols

    def add_to_whitelist(self, symbol: str):
        """添加单个 symbol 到白名单"""
        if self.whitelist_symbols is None:
            self.whitelist_symbols = set()
        self.whitelist_symbols.add(symbol)

    def remove_from_whitelist(self, symbol: str):
        """从白名单移除"""
        if self.whitelist_symbols:
            self.whitelist_symbols.discard(symbol)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = super().get_stats()
        total_before = stats.get('rows_before_filter', 0)
        total_after = stats.get('rows_after_filter', 0)
        if total_before > 0:
            stats['overall_filter_rate'] = (total_before - total_after) / total_before
        else:
            stats['overall_filter_rate'] = 0
        return stats


class NoiseFilterStage(FilterStage):
    """
    噪音过滤器 - 专门过滤 Tick 数据中的噪音

    这是原来 attention_orchestrator 中的 TickFilter 的封装
    """

    def __init__(
        self,
        name: str = "noise_filter",
        min_amount: float = 100000,
        min_volume: int = 10000,
    ):
        super().__init__(
            name=name,
            min_amount=min_amount,
            min_volume=min_volume,
        )


__all__ = ['FilterStage', 'NoiseFilterStage']
