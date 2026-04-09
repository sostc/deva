"""EnrichStage - 题材数据合并阶段"""

import pandas as pd
import logging
from typing import Optional, Dict, Any, TYPE_CHECKING

from .base import Stage, StageResult, StageType
from deva.naja.register import SR

if TYPE_CHECKING:
    from deva.naja.dictionary import DictionaryManager


logger = logging.getLogger(__name__)


class EnrichStage(Stage):
    """
    数据增强阶段 - 合并题材信息

    从题材字典获取股票所属题材信息，合并到行情数据中

    设计:
    - 优先使用注入的字典管理器
    - 其次使用 SR('dictionary_manager') 单例
    - 降级方案：从 tongdaxin_blocks 直接加载
    """

    def __init__(
        self,
        name: str = "enrich_block",
        dictionary_manager: Optional["DictionaryManager"] = None,
        block_dict_name: str = "通达信概念题材",
        use_direct_load: bool = True,
    ):
        super().__init__(name=name, stage_type=StageType.ENRICH)
        self.dictionary_manager = dictionary_manager
        self.block_dict_name = block_dict_name
        self.use_direct_load = use_direct_load

        self._block_df = None
        self._load_attempted = False

    def _load_block_data(self) -> Optional[pd.DataFrame]:
        """加载题材数据"""
        if self._block_df is not None:
            return self._block_df

        if self._load_attempted:
            return self._block_df

        self._load_attempted = True

        if self.dictionary_manager is not None:
            entry = self.dictionary_manager.get_by_name(self.block_dict_name)
            if entry is not None:
                payload = entry.get_payload()
                if payload is not None and isinstance(payload, pd.DataFrame):
                    logger.info(f"[{self.name}] 从字典加载题材数据: {payload.shape}")
                    self._block_df = payload
                    return self._block_df

        if self.use_direct_load:
            try:
                from deva.naja.dictionary.tongdaxin_blocks import get_dataframe
                self._block_df = get_dataframe()
                if self._block_df is not None:
                    logger.info(f"[{self.name}] 从文件加载题材数据: {self._block_df.shape}")
                    return self._block_df
            except Exception as e:
                logger.warning(f"[{self.name}] 从文件加载题材数据失败: {e}")

        return self._block_df

    def _process(self, data: pd.DataFrame, context: Optional[Dict[str, Any]] = None) -> StageResult:
        """合并题材数据"""
        block_df = self._load_block_data()

        if block_df is None or block_df.empty:
            return StageResult(
                success=True,
                data=data,
                warning="题材数据为空，跳过合并",
                rows_in=len(data),
                rows_out=len(data),
                metadata={'enriched': False, 'reason': 'no_block_data'}
            )

        original_index_name = data.index.name
        original_columns = set(data.columns)

        try:
            data = data.reset_index()

            if 'code' not in data.columns:
                if len(data.columns) > 0 and data.iloc[:, 0].name == 'code':
                    pass
                else:
                    return StageResult(
                        success=True,
                        data=data,
                        warning="数据中没有 code 列，跳过合并",
                        rows_in=len(data),
                        rows_out=len(data),
                        metadata={'enriched': False, 'reason': 'no_code_column'}
                    )

            if 'blocks' not in block_df.columns:
                return StageResult(
                    success=True,
                    data=data,
                    warning="题材数据中没有 blocks 列",
                    rows_in=len(data),
                    rows_out=len(data),
                    metadata={'enriched': False, 'reason': 'no_blocks_column'}
                )

            block_df = block_df.copy()
            block_df['code'] = block_df['code'].astype(str).str.zfill(6)

            if 'code' in data.columns:
                data = data.copy()
                data['code'] = data['code'].astype(str)
                data['code'] = data['code'].str.replace(r'^(sh|sz|bj)', '', regex=True).str.zfill(6)

            data = data.merge(
                block_df[['code', 'blocks']],
                on='code',
                how='left'
            )

            if 'blocks' in data.columns:
                if 'blocks' in data.columns and 'block' not in data.columns:
                    data = data.rename(columns={'blocks': 'block'})
                if 'sector' in data.columns and 'block' not in data.columns:
                    data = data.rename(columns={'sector': 'block'})
                if 'block' in data.columns:
                    data['block'] = data['block'].fillna('')

            if original_index_name and original_index_name != 'code' and original_index_name in data.columns:
                data = data.set_index(original_index_name)

            enriched_count = 0
            if 'block' in data.columns:
                enriched_count = (data['block'] != '').sum()

            new_columns = set(data.columns) - original_columns
            removed_columns = original_columns - set(data.columns)

            return StageResult(
                success=True,
                data=data,
                rows_in=len(data),
                rows_out=len(data),
                metadata={
                    'enriched': True,
                    'enriched_count': enriched_count,
                    'total_count': len(data),
                    'new_columns': list(new_columns),
                    'removed_columns': list(removed_columns) if removed_columns else [],
                }
            )

        except Exception as e:
            logger.exception(f"[{self.name}] 合并题材数据失败: {e}")

            try:
                data = data.set_index(original_index_name or data.columns[0])
            except Exception:
                pass

            return StageResult(
                success=False,
                data=data,
                error=str(e),
                rows_in=len(data),
                rows_out=len(data),
                metadata={'enriched': False, 'error': str(e)}
            )

    def refresh(self):
        """刷新题材数据（供外部调用）"""
        self._block_df = None
        self._load_attempted = False
        return self._load_block_data()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = super().get_stats()
        stats['has_block_data'] = self._block_df is not None
        stats['block_data_shape'] = (
            self._block_df.shape if self._block_df is not None else None
        )
        return stats


__all__ = ['EnrichStage']
