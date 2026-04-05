"""
Block Attention Module - 板块注意力计算

功能:
- 每个板块独立计算注意力
- 反映板块内部"变化是否扩散"
- 支持多板块并行
- 支持半衰期衰减
- 集成噪音板块过滤

性能优化:
- 使用预分配 numpy 数组避免动态扩容
- 增量更新，避免全量 groupby
- O(num_sectors) 复杂度
"""

import numpy as np
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import time
import logging
import os

log = logging.getLogger(__name__)


def _get_noise_detector():
    """延迟导入避免循环依赖"""
    try:
        from deva.naja.attention.processing.block_noise_detector import get_block_noise_detector
        return get_block_noise_detector()
    except ImportError:
        return None


@dataclass
class BlockConfig:
    """板块配置"""
    block_id: str
    name: str
    symbols: Set[str] = field(default_factory=set)
    decay_half_life: float = 300.0  # 半衰期(秒)，默认5分钟
    activation_threshold: float = 0.3  # 激活阈值


class BlockAttentionEngine:
    """
    板块注意力引擎

    计算逻辑:
    1. 板块内领涨股数量比例
    2. 板块内成交量集中度
    3. 板块内相关性变化
    4. 半衰期衰减

    修复内容:
    - 添加不活跃板块的清理机制
    """

    def __init__(
        self,
        sectors: Optional[List[BlockConfig]] = None,
        max_sectors: int = 5000,
        update_threshold: float = 0.05,
        stale_threshold_seconds: float = 1800.0
    ):
        self.max_sectors = max_sectors
        self.update_threshold = update_threshold
        self.stale_threshold_seconds = stale_threshold_seconds

        # 板块配置
        self._blocks: Dict[str, BlockConfig] = {}
        self._symbol_to_blocks: Dict[str, List[str]] = defaultdict(list)

        # 预分配注意力分数数组
        self._attention_scores = np.zeros(max_sectors)
        self._block_id_to_idx: Dict[str, int] = {}
        self._idx_to_block_id: Dict[int, str] = {}

        # 历史状态 (用于增量计算)
        self._last_update_time: Dict[str, float] = {}
        self._leader_counts: Dict[str, int] = {}
        self._volume_concentration: Dict[str, float] = {}
        self._block_last_activity: Dict[str, float] = {}  # 跟踪板块最后活跃时间

        # 日志节流
        self._last_summary_log_time: float = 0.0
        self._summary_log_interval: float = 60.0

        # 初始化板块
        if sectors:
            for sector in sectors:
                self.register_block(sector)

        self._last_calc_time = 0.0
    
    def register_block(self, config: BlockConfig) -> bool:
        """注册板块"""
        if len(self._blocks) >= self.max_sectors:
            return False
        
        block_id = config.block_id
        idx = len(self._blocks)
        
        self._blocks[block_id] = config
        self._block_id_to_idx[block_id] = idx
        self._idx_to_block_id[idx] = block_id
        
        # 建立 symbol -> blocks 映射（同步到 BlockRegistry）
        for symbol in config.symbols:
            self._symbol_to_blocks[symbol].append(block_id)
            registry.link_symbol_to_block(symbol, block_id)

        self._last_update_time[block_id] = time.time()
        return True
    
    def update(
        self,
        symbols: np.ndarray,
        returns: np.ndarray,
        volumes: np.ndarray,
        timestamp: float,
        block_ids: Optional[np.ndarray] = None
    ) -> Dict[str, float]:
        """
        更新板块注意力分数

        Args:
            symbols: 股票代码数组
            returns: 涨跌幅数组
            volumes: 成交量数组
            timestamp: 当前时间戳
            block_ids: 板块ID数组（可选，如果提供将优先使用，否则使用内部映射）

        Returns:
            block_attention: 板块注意力字典
        """
        start_time = time.time()

        returns = np.nan_to_num(returns, nan=0.0, posinf=50.0, neginf=-50.0)
        returns = np.clip(returns, -50.0, 50.0)
        volumes = np.nan_to_num(volumes, nan=0.0, posinf=1e15, neginf=0.0)
        volumes = np.clip(volumes, 0, 1e15)

        try:
            sector_data = self._aggregate_by_block(symbols, returns, volumes, block_ids)

            if not sector_data:
                log.warning(f"[SectorAttention] 警告: sector_data为空! symbols数量={len(symbols)}")
                # 调试：检查 symbols 和 block_ids 的内容
                if os.environ.get("NAJA_LAB_DEBUG") == "true":
                    log.info(f"[Lab-Debug] symbols[:5]={symbols[:5]}, returns[:5]={returns[:5]}")
            elif all(len(d.get('returns', [])) == 0 for d in sector_data.values()):
                log.warning(f"[SectorAttention] 警告: 所有板块的returns为空! sector_data keys={list(sector_data.keys())[:5]}")
            else:
                sectors_with_data = [k for k, v in sector_data.items() if len(v.get('returns', [])) > 0]
                if len(sectors_with_data) > 0:
                    current_time = time.time()
                    if current_time - self._last_summary_log_time >= self._summary_log_interval:
                        sample_names = [self._blocks[k].name if k in self._blocks else k for k in sectors_with_data[:3]]
                        log.info(f"[SectorAttention] 有数据的板块数: {len(sectors_with_data)}, 样本: {sample_names}")
                        self._last_summary_log_time = current_time

            noise_detector = _get_noise_detector()
            active_sectors = set()
            use_external_sectors = block_ids is not None and len(block_ids) == len(symbols)
            for block_id, data in sector_data.items():
                if noise_detector and noise_detector.is_noise(block_id, self._blocks.get(block_id).name if block_id in self._blocks else block_id):
                    continue
                if block_id not in self._blocks:
                    if use_external_sectors and block_id and block_id != '0':
                        config = BlockConfig(
                            block_id=block_id,
                            name=block_id,
                            symbols=set(),
                            decay_half_life=300.0
                        )
                        result = self.register_block(config)
                        log.info(f"[SectorAttention] 自动注册外部板块: {block_id}, result={result}, current count={len(self._blocks)}")
                        if block_id not in self._blocks:
                            log.warning(f"[SectorAttention] 注册后仍然不在 _sectors 中!")
                            continue
                    else:
                        continue

                active_blocks.add(block_id)
                if block_id not in self._blocks:
                    continue
                sector = self._blocks[block_id]
                idx = self._block_id_to_idx[block_id]

                new_score = self._calc_block_attention(
                    data['returns'],
                    data['volumes'],
                    sector
                )

                if len(sector_data) <= 5:
                    log.info(f"[SectorAttention] sector={sector.name}, new_score={new_score:.3f}, data_returns={list(data['returns'][:3]) if len(data['returns']) > 0 else 'empty'}")

                last_time = self._last_update_time.get(block_id, timestamp)
                time_delta = timestamp - last_time
                max_time_delta = sector.decay_half_life * 10
                time_delta = min(time_delta, max_time_delta)
                try:
                    decay_factor = 0.5 ** (time_delta / sector.decay_half_life)
                except OverflowError:
                    decay_factor = 0.0

                old_score = float(self._attention_scores[idx])
                if old_score > 1e10 or old_score < -1e10:
                    log.warning(f"[SectorAttention] block_id={block_id} old_score 异常={old_score:.2f}, 重置")
                    old_score = 0.0

                new_score_capped = max(0.0, min(1.0, new_score))
                blended_score = max(new_score_capped, old_score * decay_factor)
                blended_score = max(0.0, min(1.0, blended_score))

                if abs(blended_score - old_score) > self.update_threshold:
                    self._attention_scores[idx] = blended_score
                    self._last_update_time[block_id] = timestamp

                self._block_last_activity[block_id] = timestamp

            self._cleanup_stale_blocks(timestamp)
        except Exception as e:
            import traceback
            log.error(f"SectorAttention 计算失败: {e}")
            log.error(traceback.format_exc())

        # 构建返回字典（使用限制后的值）
        result = {}
        for block_id, idx in self._block_id_to_idx.items():
            raw_score = float(self._attention_scores[idx])
            result[block_id] = max(0.0, min(1.0, raw_score))

        # 调试日志（过滤噪音板块）
        import os
        if os.environ.get("NAJA_LAB_DEBUG") == "true":
            noise_detector = _get_noise_detector()
            all_items = [(s, float(self._attention_scores[idx])) for s, idx in self._block_id_to_idx.items() if hasattr(self._blocks.get(s), 'name') and self._blocks.get(s).name]
            if noise_detector:
                valid_items = [(s, w) for s, w in all_items if not noise_detector.is_noise(s, self._blocks[s].name)]
            else:
                valid_items = all_items
            valid_items.sort(key=lambda x: x[1], reverse=True)
            if valid_items:
                log.info(f"[Lab-Debug] 板块注意力 Top5: {[(f'{self._blocks[s].name}({w:.3f})') for s, w in valid_items[:5]]}")

        self._last_calc_time = time.time()
        return result
    
    def _aggregate_by_block(
        self,
        symbols: np.ndarray,
        returns: np.ndarray,
        volumes: np.ndarray,
        block_ids: Optional[np.ndarray] = None
    ) -> Dict[str, Dict[str, np.ndarray]]:
        """
        按板块聚合数据
        使用预分配数组避免动态扩容

        Args:
            symbols: 股票代码数组
            returns: 涨跌幅数组
            volumes: 成交量数组
            block_ids: 板块ID数组（可选，如果提供将优先使用）
        """
        sector_data = defaultdict(lambda: {
            'returns': [],
            'volumes': []
        })

        use_external_sectors = block_ids is not None and len(block_ids) == len(symbols)
        noise_detector = _get_noise_detector()
        filtered_noise = 0

        for i, symbol in enumerate(symbols):
            symbol_str = str(symbol)

            if use_external_sectors:
                block_id = str(block_ids[i])
                if block_id and block_id != '0':
                    if noise_detector and noise_detector.is_noise(block_id, self._blocks.get(block_id).name if block_id in self._blocks else block_id):
                        filtered_noise += 1
                        continue
                    sector_data[block_id]['returns'].append(returns[i])
                    sector_data[block_id]['volumes'].append(volumes[i])
            else:
                block_id_list = self._symbol_to_blocks.get(symbol_str, [])
                for block_id in block_id_list:
                    if noise_detector and noise_detector.is_noise(block_id, self._blocks.get(block_id).name if block_id in self._blocks else block_id):
                        filtered_noise += 1
                        continue
                    sector_data[block_id]['returns'].append(returns[i])
                    sector_data[block_id]['volumes'].append(volumes[i])

        if filtered_noise > 0 and os.environ.get("NAJA_LAB_DEBUG") == "true":
            log.info(f"[SectorAttention] 噪音板块聚合已过滤: {filtered_noise} 条")

        result = {}
        for block_id, data in sector_data.items():
            result[block_id] = {
                'returns': np.array(data['returns']),
                'volumes': np.array(data['volumes'])
            }

        return result
    
    def _calc_block_attention(
        self,
        returns: np.ndarray,
        volumes: np.ndarray,
        sector: BlockConfig
    ) -> float:
        """
        计算单个板块的注意力分数
        
        维度:
        1. 领涨股比例 (40%)
        2. 成交量集中度 (30%)
        3. 内部相关性 (30%)
        """
        if len(returns) == 0:
            return 0.0
        
        # 1. 领涨股比例
        leader_threshold = np.percentile(np.abs(returns), 80) if len(returns) > 5 else 2.0
        leader_ratio = np.sum(np.abs(returns) >= leader_threshold) / len(returns)
        leader_score = min(leader_ratio * 2, 1.0)  # 归一化
        
        # 2. 成交量集中度 (使用 Gini 系数思想)
        if len(volumes) > 0:
            total_volume = np.sum(volumes)
            if total_volume > 1e-10:  # 避免除零
                sorted_volumes = np.sort(volumes)
                cumsum = np.cumsum(sorted_volumes)
                n = len(volumes)
                if cumsum[-1] > 1e-10:  # 再次检查
                    concentration = (n + 1 - 2 * np.sum(cumsum) / cumsum[-1]) / n
                    volume_score = max(0.0, min(1.0, concentration))
                else:
                    volume_score = 0.0
            else:
                volume_score = 0.0
        else:
            volume_score = 0.0
        
        # 3. 内部相关性 (使用收益率标准差作为代理)
        if len(returns) > 1:
            return_std = np.std(returns)
            # 标准差适中表示有分化但又有联动
            correlation_score = 1.0 - abs(return_std - 3.0) / 3.0
            correlation_score = max(0.0, min(1.0, correlation_score))
        else:
            correlation_score = 0.0
        
        # 加权求和
        score = (
            leader_score * 0.4 +
            volume_score * 0.3 +
            correlation_score * 0.3
        )
        
        return score
    
    def get_active_blocks(self, threshold: Optional[float] = None) -> List[str]:
        """获取活跃的板块列表"""
        threshold = threshold or 0.3

        active = []
        for block_id, idx in self._block_id_to_idx.items():
            score = float(self._attention_scores[idx])
            clamped_score = max(0.0, min(1.0, score))
            if clamped_score >= threshold:
                active.append(block_id)

        active.sort(key=lambda s: max(0.0, min(1.0, float(self._attention_scores[self._block_id_to_idx[s]]))), reverse=True)
        return active
    
    def get_block_attention(self, block_id: str) -> float:
        """获取指定板块的注意力分数"""
        idx = self._block_id_to_idx.get(block_id)
        if idx is None:
            return 0.0
        raw_score = float(self._attention_scores[idx])
        clamped_score = max(0.0, min(1.0, raw_score))
        if abs(raw_score - clamped_score) > 0.01:
            log.warning(f"[SectorAttention] block_id={block_id} 分数异常: {raw_score:.6f} -> 限制到 {clamped_score:.6f}")
        return clamped_score
    
    def get_top_blocks(self, n: int = 5) -> List[Tuple[str, float]]:
        """获取注意力最高的 N 个板块"""
        sectors = []
        for block_id, idx in self._block_id_to_idx.items():
            raw_score = float(self._attention_scores[idx])
            clamped_score = max(0.0, min(1.0, raw_score))
            sectors.append((block_id, clamped_score))
        sectors.sort(key=lambda x: x[1], reverse=True)
        return sectors[:n]
    
    def get_all_weights(self, filter_noise: bool = True) -> Dict[str, float]:
        """获取所有板块的权重

        Args:
            filter_noise: 是否过滤噪音板块
        """
        noise_detector = _get_noise_detector() if filter_noise else None

        weights = {}
        filtered_count = 0
        for block_id, idx in self._block_id_to_idx.items():
            if filter_noise and noise_detector:
                sector_name = self._blocks[idx].name if idx in self._blocks else None
                if noise_detector.is_noise(block_id, sector_name):
                    filtered_count += 1
                    continue
            raw_score = float(self._attention_scores[idx])
            clamped_score = max(0.0, min(1.0, raw_score))
            if abs(raw_score - clamped_score) > 0.01:
                log.warning(f"[SectorAttention] get_all_weights block_id={block_id} 分数异常: {raw_score:.6f} -> 限制到 {clamped_score:.6f}")
            weights[block_id] = clamped_score

        if len(weights) < 5:
            weight_names = [self._blocks[idx].name if idx in self._blocks else k for k, idx in self._block_id_to_idx.items() if k in weights]
            log.info(f"[SectorAttention] get_all_weights: 返回 {len(weights)} 个有效板块 (过滤了 {filtered_count} 个噪音)")
        else:
            log.debug(f"[SectorAttention] get_all_weights: 返回 {len(weights)} 个有效板块 (过滤了 {filtered_count} 个噪音)")
        return weights

    def reset(self):
        """重置引擎状态"""
        self._attention_scores.fill(0.0)
        self._last_update_time.clear()
        self._leader_counts.clear()
        self._volume_concentration.clear()
        self._block_last_activity.clear()

    def _cleanup_stale_blocks(self, current_time: float):
        """清理长期不活跃的板块数据，防止内存泄漏"""
        stale_blocks = [
            block_id for block_id, last_activity in self._block_last_activity.items()
            if current_time - last_activity > self.stale_threshold_seconds
        ]

        for block_id in stale_blocks:
            if block_id in self._leader_counts:
                del self._leader_counts[block_id]
            if block_id in self._volume_concentration:
                del self._volume_concentration[block_id]

        if stale_blocks and len(stale_blocks) > 0:
            log.info(f"[SectorAttention] 清理了 {len(stale_blocks)} 个不活跃板块的状态数据")
