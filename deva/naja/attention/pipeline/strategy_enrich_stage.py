"""StrategyEnrichStage - 策略数据补齐阶段"""

import pandas as pd
import logging
from typing import Optional, Dict, Any, List

from .base import Stage, StageResult, StageType
from deva.naja.register import SR

logger = logging.getLogger(__name__)


class StrategyEnrichStage(Stage):
    """
    策略数据补齐阶段 - 使用字典数据补齐行情数据

    从配置的字典档案中获取维表数据，与行情数据进行关联补齐

    设计:
    - 支持多个字典档案（profile_ids）
    - 自动推断关联键
    - 失败安全：补齐失败不影响原始数据
    """

    def __init__(
        self,
        name: str = "strategy_enrich",
        profile_ids: Optional[List[str]] = None,
    ):
        super().__init__(name=name, stage_type=StageType.ENRICH)
        self.profile_ids = profile_ids or []

        self._dict_cache: Dict[str, pd.DataFrame] = {}

    def _process(self, data: Any, context: Optional[Dict[str, Any]] = None) -> StageResult:
        """执行数据补齐"""
        if not self.profile_ids:
            return StageResult(
                success=True,
                data=data,
                rows_in=len(data) if hasattr(data, '__len__') else 0,
                rows_out=len(data) if hasattr(data, '__len__') else 0,
                metadata={'skipped': True, 'reason': 'no_profile_ids'}
            )

        actual_data = data.get('data', data) if isinstance(data, dict) else data

        if not isinstance(actual_data, pd.DataFrame):
            return StageResult(
                success=True,
                data=data,
                rows_in=0,
                rows_out=0,
                metadata={'skipped': True, 'reason': 'not_dataframe'}
            )

        enriched = actual_data.copy()
        total_enriched_cols = 0

        try:
            for profile_id in self.profile_ids:
                dim_df = self._load_dictionary(profile_id)
                if dim_df is None:
                    continue

                join_key = self._infer_join_key(enriched, dim_df)
                if not join_key:
                    logger.warning(f"[{self.name}] 无法推断 {profile_id} 的关联键")
                    continue

                left_df = enriched.copy()
                right_df = dim_df.copy()

                if join_key == "code":
                    left_df[join_key] = left_df[join_key].astype(str)
                    right_df[join_key] = right_df[join_key].astype(str)

                enrich_cols = [c for c in right_df.columns if c != join_key]

                merged = left_df.merge(
                    right_df[[join_key] + enrich_cols],
                    on=join_key,
                    how='left',
                    suffixes=('', f'_dict_{profile_id[:8]}')
                )

                enriched_cols = [c for c in merged.columns if c not in enriched.columns]
                total_enriched_cols += len(enriched_cols)

                enriched = merged

            if isinstance(data, dict) and 'data' in data:
                data['data'] = enriched
                result_data = data
            else:
                result_data = enriched

            return StageResult(
                success=True,
                data=result_data,
                rows_in=len(actual_data),
                rows_out=len(enriched),
                metadata={
                    'enriched': True,
                    'enriched_columns': total_enriched_cols,
                    'profile_count': len(self.profile_ids),
                }
            )

        except Exception as e:
            logger.exception(f"[{self.name}] 数据补齐失败: {e}")

            if isinstance(data, dict) and 'data' in data:
                result_data = data
            else:
                result_data = actual_data

            return StageResult(
                success=False,
                data=result_data,
                error=str(e),
                rows_in=len(actual_data),
                rows_out=len(actual_data),
            )

    def _load_dictionary(self, profile_id: str) -> Optional[pd.DataFrame]:
        """加载字典数据"""
        if profile_id in self._dict_cache:
            return self._dict_cache[profile_id]

        try:
            mgr = SR('dictionary_manager')
            entry = mgr.get(profile_id)

            if entry is None:
                logger.warning(f"[{self.name}] 字典不存在: {profile_id}")
                return None

            payload = entry.get_payload()
            if payload is None:
                logger.warning(f"[{self.name}] 字典数据为空: {profile_id}")
                return None

            if isinstance(payload, pd.DataFrame):
                self._dict_cache[profile_id] = payload
                return payload
            else:
                logger.warning(f"[{self.name}] 字典数据格式不正确: {profile_id}")
                return None

        except Exception as e:
            logger.exception(f"[{self.name}] 加载字典失败: {profile_id}, {e}")
            return None

    def _infer_join_key(self, left_df: pd.DataFrame, right_df: pd.DataFrame) -> Optional[str]:
        """推断关联键"""
        common_cols = set(left_df.columns) & set(right_df.columns)

        priority_keys = ['code', 'symbol', 'stock_code', 'stockcode']
        for key in priority_keys:
            if key in common_cols:
                return key

        if common_cols:
            return list(common_cols)[0]

        return None

    def add_profile(self, profile_id: str):
        """添加字典档案"""
        if profile_id not in self.profile_ids:
            self.profile_ids.append(profile_id)
            self._dict_cache.clear()

    def remove_profile(self, profile_id: str):
        """移除字典档案"""
        if profile_id in self.profile_ids:
            self.profile_ids.remove(profile_id)
            if profile_id in self._dict_cache:
                del self._dict_cache[profile_id]

    def clear_cache(self):
        """清空缓存"""
        self._dict_cache.clear()


__all__ = ['StrategyEnrichStage']
