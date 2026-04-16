"""
Block Hotspot Module - 题材热点计算

功能:
- 每个题材独立计算热点
- 反映题材内部"变化是否扩散"
- 支持多题材并行
- 支持半衰期衰减
- 集成噪音题材过滤

性能优化:
- 使用预分配 numpy 数组避免动态扩容
- 增量更新，避免全量 groupby
- O(num_blocks) 复杂度
"""

import numpy as np
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import time
import logging
import os
from deva.naja.attention.kernel.embedding import MarketFeatureEncoder, EventEmbedding
from deva.naja.attention.kernel.self_attention import EventSelfAttention
from deva.naja.market_hotspot.intelligence.transformer_enhancer import TransformerEnhancer

log = logging.getLogger(__name__)


def _get_noise_detector():
    """延迟导入避免循环依赖"""
    try:
        from deva.naja.infra.registry.singleton_registry import SR
        detector = SR('block_noise_detector')
        return detector
    except Exception:
        pass
    
    try:
        from deva.naja.market_hotspot.processing.block_noise_detector import BlockNoiseDetector
        return BlockNoiseDetector.get_instance()
    except ImportError:
        return None


@dataclass
class BlockConfig:
    """题材配置"""
    block_id: str
    name: str
    symbols: Set[str] = field(default_factory=set)
    decay_half_life: float = 300.0  # 半衰期(秒)，默认5分钟
    activation_threshold: float = 0.3  # 激活阈值


class BlockHotspotEngine:
    """
    题材热点引擎

    计算逻辑:
    1. 题材内领涨股数量比例
    2. 题材内成交量集中度
    3. 题材内相关性变化
    4. 半衰期衰减

    修复内容:
    - 添加不活跃题材的清理机制
    """

    def __init__(
        self,
        blocks: Optional[List[BlockConfig]] = None,
        max_blocks: int = 5000,
        update_threshold: float = 0.05,
        stale_threshold_seconds: float = 1800.0
    ):
        self.max_blocks = max_blocks
        self.update_threshold = update_threshold
        self.stale_threshold_seconds = stale_threshold_seconds

        # 题材配置
        self._blocks: Dict[str, BlockConfig] = {}
        self._symbol_to_blocks: Dict[str, List[str]] = defaultdict(list)

        # 预分配热点分数数组
        self._block_hotspot_scores = np.zeros(max_blocks)
        self._block_id_to_idx: Dict[str, int] = {}
        self._idx_to_block_id: Dict[int, str] = {}

        # 历史状态 (用于增量计算)
        self._last_update_time: Dict[str, float] = {}
        self._leader_counts: Dict[str, int] = {}
        self._volume_concentration: Dict[str, float] = {}
        self._block_last_activity: Dict[str, float] = {}  # 跟踪题材最后活跃时间

        # 日志节流
        self._last_summary_log_time: float = 0.0
        self._summary_log_interval: float = 60.0

        # 嵌入技术增强
        self.feature_encoder = MarketFeatureEncoder(embedding_dim=128)
        self.self_attention = EventSelfAttention(d_model=128, num_heads=4)
        self.block_embeddings = {}  # 存储题材嵌入向量
        self.embedding_history = defaultdict(list)  # 存储历史嵌入
        
        # Transformer 增强器
        self.transformer_enhancer = TransformerEnhancer(d_model=128, num_heads=4, d_ff=512)

        # 初始化题材
        if blocks:
            for block in blocks:
                self.register_block(block)

        self._last_calc_time = 0.0
    
    def register_block(self, config: BlockConfig) -> bool:
        """注册题材"""
        if len(self._blocks) >= self.max_blocks:
            return False
        
        block_id = config.block_id
        idx = len(self._blocks)
        
        self._blocks[block_id] = config
        self._block_id_to_idx[block_id] = idx
        self._idx_to_block_id[idx] = block_id
        
        # 建立 symbol -> blocks 映射
        for symbol in config.symbols:
            self._symbol_to_blocks[symbol].append(block_id)

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
        更新题材热点分数

        Args:
            symbols: 股票代码数组
            returns: 涨跌幅数组
            volumes: 成交量数组
            timestamp: 当前时间戳
            block_ids: 题材热点字典

        Returns:
            block_hotspot: 题材热点字典
        """
        start_time = time.time()

        returns = np.nan_to_num(returns, nan=0.0, posinf=50.0, neginf=-50.0)
        returns = np.clip(returns, -50.0, 50.0)
        volumes = np.nan_to_num(volumes, nan=0.0, posinf=1e15, neginf=0.0)
        volumes = np.clip(volumes, 0, 1e15)

        try:
            block_data = self._aggregate_by_block(symbols, returns, volumes, block_ids)

            if not block_data:
                log.warning(f"[BlockHotspot] 警告: block_data为空! symbols数量={len(symbols)}")
                # 调试：检查 symbols 和 block_ids 的内容
                if os.environ.get("NAJA_LAB_DEBUG") == "true":
                    log.info(f"[Lab-Debug] symbols[:5]={symbols[:5]}, returns[:5]={returns[:5]}")
            elif all(len(d.get('returns', [])) == 0 for d in block_data.values()):
                log.warning(f"[BlockHotspot] 警告: 所有题材的returns为空! block_data keys={list(block_data.keys())[:5]}")
            else:
                blocks_with_data = [k for k, v in block_data.items() if len(v.get('returns', [])) > 0]
                if len(blocks_with_data) > 0:
                    current_time = time.time()
                    if current_time - self._last_summary_log_time >= self._summary_log_interval:
                        sample_names = [self._blocks[k].name if k in self._blocks else k for k in blocks_with_data[:3]]
                        log.info(f"[BlockHotspot] 有数据的题材数: {len(blocks_with_data)}, 样本: {sample_names}")
                        self._last_summary_log_time = current_time

            noise_detector = _get_noise_detector()
            active_blocks = set()
            use_external_blocks = block_ids is not None and len(block_ids) == len(symbols)
            
            # 存储题材嵌入向量
            block_embeddings = []
            active_block_ids = []
            
            for block_id, data in block_data.items():
                if noise_detector and noise_detector.is_noise(block_id, self._blocks.get(block_id).name if block_id in self._blocks else block_id):
                    continue
                if block_id not in self._blocks:
                    if use_external_blocks and block_id and block_id != '0':
                        config = BlockConfig(
                            block_id=block_id,
                            name=block_id,
                            symbols=set(),
                            decay_half_life=300.0
                        )
                        result = self.register_block(config)
                        log.info(f"[BlockHotspot] 自动注册外部题材: {block_id}, result={result}, current count={len(self._blocks)}")
                        if block_id not in self._blocks:
                            log.warning(f"[BlockHotspot] 注册后仍然不在 _blocks 中!")
                            continue
                    else:
                        continue

                active_blocks.add(block_id)
                if block_id not in self._blocks:
                    continue
                block = self._blocks[block_id]
                idx = self._block_id_to_idx[block_id]

                # 编码题材特征
                if len(data['returns']) > 0:
                    features = {
                        "price_change": np.mean(data['returns']),
                        "volume_spike": np.mean(data['volumes']) if len(data['volumes']) > 0 else 0,
                        "volatility": np.std(data['returns']) if len(data['returns']) > 1 else 0,
                        "block": block_id
                    }
                else:
                    features = {
                        "price_change": 0,
                        "volume_spike": 0,
                        "volatility": 0,
                        "block": block_id
                    }
                
                embedding = self.feature_encoder.encode(features, time_position=int(timestamp % 100))
                self.block_embeddings[block_id] = embedding
                self.embedding_history[block_id].append((timestamp, embedding))
                
                # 保持历史嵌入长度
                if len(self.embedding_history[block_id]) > 10:
                    self.embedding_history[block_id] = self.embedding_history[block_id][-10:]
                
                block_embeddings.append(embedding)
                active_block_ids.append(block_id)

                new_score = self._calc_block_hotspot(
                    data['returns'],
                    data['volumes'],
                    block
                )

                if len(block_data) <= 5:
                    log.info(f"[BlockHotspot] block={block.name}, new_score={new_score:.3f}, data_returns={list(data['returns'][:3]) if len(data['returns']) > 0 else 'empty'}")

                last_time = self._last_update_time.get(block_id, timestamp)
                time_delta = timestamp - last_time
                max_time_delta = block.decay_half_life * 10
                time_delta = min(time_delta, max_time_delta)
                try:
                    decay_factor = 0.5 ** (time_delta / block.decay_half_life)
                except OverflowError:
                    decay_factor = 0.0

                old_score = float(self._block_hotspot_scores[idx])
                if old_score > 1e10 or old_score < -1e10:
                    log.warning(f"[BlockHotspot] block_id={block_id} old_score 异常={old_score:.2f}, 重置")
                    old_score = 0.0

                new_score_capped = max(0.0, min(1.0, new_score))
                blended_score = max(new_score_capped, old_score * decay_factor)
                blended_score = max(0.0, min(1.0, blended_score))

                if abs(blended_score - old_score) > self.update_threshold:
                    self._block_hotspot_scores[idx] = blended_score
                    self._last_update_time[block_id] = timestamp

                self._block_last_activity[block_id] = timestamp

            # 应用自注意力机制分析题材间关系
            if len(block_embeddings) > 1:
                # 将numpy数组转换为EventEmbedding对象列表
                event_embeddings = []
                for i, embedding in enumerate(block_embeddings):
                    event_emb = EventEmbedding(
                        vector=embedding,
                        features={"block_id": active_block_ids[i]},
                        timestamp=timestamp
                    )
                    event_embeddings.append(event_emb)
                
                # 调用自注意力前向传播
                updated_embeddings, attn_weights = self.self_attention.forward(event_embeddings)
                
                # 利用注意力输出增强热点计算
                for i, block_id in enumerate(active_block_ids):
                    if block_id in self._blocks:
                        idx = self._block_id_to_idx[block_id]
                        # 计算注意力分数（取平均注意力权重）
                        if attn_weights.size > 0:
                            attention_score = np.mean(attn_weights[0, :, i, :])  # 取所有头的平均
                            current_score = float(self._block_hotspot_scores[idx])
                            enhanced_score = current_score * (1 + attention_score * 0.1)
                            self._block_hotspot_scores[idx] = min(1.0, enhanced_score)
            
            # 应用Transformer增强器
            if active_block_ids:
                # 准备Transformer输入数据
                blocks_data = []
                for block_id in active_block_ids:
                    if block_id in block_data:
                        data = block_data[block_id]
                        blocks_data.append({
                            'block_id': block_id,
                            'name': self._blocks.get(block_id).name if block_id in self._blocks else block_id,
                            'returns': data['returns'],
                            'volumes': data['volumes']
                        })
                
                if blocks_data:
                    market_data = {
                        'blocks': blocks_data,
                        'timestamp': timestamp
                    }
                    enhancer_result = self.transformer_enhancer.enhance_market_analysis(market_data)
                    
                    # 利用Transformer预测结果调整题材热点分数
                    if enhancer_result['predictions']:
                        for prediction in enhancer_result['predictions']:
                            block_id = prediction['block_id']
                            if block_id in self._blocks:
                                idx = self._block_id_to_idx[block_id]
                                current_score = float(self._block_hotspot_scores[idx])
                                # 根据预测趋势调整分数
                                if prediction['trend'] == 'up':
                                    enhanced_score = current_score * (1 + prediction['confidence'] * 0.1)
                                else:
                                    enhanced_score = current_score * (1 - prediction['confidence'] * 0.05)
                                self._block_hotspot_scores[idx] = min(1.0, max(0.0, enhanced_score))

            self._cleanup_stale_blocks(timestamp)
        except Exception as e:
            import traceback
            log.error(f"BlockHotspot 计算失败: {e}")
            log.error(traceback.format_exc())

        # 构建返回字典（使用限制后的值）
        result = {}
        for block_id, idx in self._block_id_to_idx.items():
            raw_score = float(self._block_hotspot_scores[idx])
            result[block_id] = max(0.0, min(1.0, raw_score))

        # 调试日志（过滤噪音题材）
        import os
        if os.environ.get("NAJA_LAB_DEBUG") == "true":
            noise_detector = _get_noise_detector()
            all_items = [(s, float(self._block_hotspot_scores[idx])) for s, idx in self._block_id_to_idx.items() if hasattr(self._blocks.get(s), 'name') and self._blocks.get(s).name]
            if noise_detector:
                valid_items = [(s, w) for s, w in all_items if not noise_detector.is_noise(s, self._blocks[s].name)]
            else:
                valid_items = all_items
            valid_items.sort(key=lambda x: x[1], reverse=True)
            if valid_items:
                log.info(f"[Lab-Debug] 题材热点 Top5: {[(f'{self._blocks[s].name}({w:.3f})') for s, w in valid_items[:5]]}")

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
        按题材聚合数据
        使用预分配数组避免动态扩容

        Args:
            symbols: 股票代码数组
            returns: 涨跌幅数组
            volumes: 成交量数组
            block_ids: 题材ID数组（可选，如果提供将优先使用）
        """
        block_data = defaultdict(lambda: {
            'returns': [],
            'volumes': []
        })

        use_external_blocks = block_ids is not None and len(block_ids) == len(symbols)
        noise_detector = _get_noise_detector()
        filtered_noise = 0

        for i, symbol in enumerate(symbols):
            symbol_str = str(symbol)

            if use_external_blocks:
                block_id = str(block_ids[i])
                if block_id and block_id != '0':
                    if noise_detector and noise_detector.is_noise(block_id, self._blocks.get(block_id).name if block_id in self._blocks else block_id):
                        filtered_noise += 1
                        continue
                    block_data[block_id]['returns'].append(returns[i])
                    block_data[block_id]['volumes'].append(volumes[i])
            else:
                block_id_list = self._symbol_to_blocks.get(symbol_str, [])
                for block_id in block_id_list:
                    if noise_detector and noise_detector.is_noise(block_id, self._blocks.get(block_id).name if block_id in self._blocks else block_id):
                        filtered_noise += 1
                        continue
                    block_data[block_id]['returns'].append(returns[i])
                    block_data[block_id]['volumes'].append(volumes[i])

        if filtered_noise > 0 and os.environ.get("NAJA_LAB_DEBUG") == "true":
            log.info(f"[BlockHotspot] 噪音题材聚合已过滤: {filtered_noise} 条")

        result = {}
        for block_id, data in block_data.items():
            result[block_id] = {
                'returns': np.array(data['returns']),
                'volumes': np.array(data['volumes'])
            }

        return result
    
    def _calc_block_hotspot(
        self,
        returns: np.ndarray,
        volumes: np.ndarray,
        block: BlockConfig
    ) -> float:
        """
        计算单个题材的热点分数
        
        维度:
        1. 领涨股比例 (30%)
        2. 成交量集中度 (25%)
        3. 内部相关性 (25%)
        4. 嵌入向量相似度 (20%) - 新增
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
        
        # 4. 嵌入向量相似度 - 新增
        embedding_score = 0.0
        if block.block_id in self.block_embeddings:
            current_embedding = self.block_embeddings[block.block_id]
            # 计算与历史嵌入的相似度
            if block.block_id in self.embedding_history and len(self.embedding_history[block.block_id]) > 1:
                # 获取最近的历史嵌入
                recent_embeddings = [emb for _, emb in self.embedding_history[block.block_id][-5:]]
                if recent_embeddings:
                    # 计算平均相似度
                    similarities = []
                    for hist_emb in recent_embeddings:
                        # 余弦相似度
                        sim = np.dot(current_embedding, hist_emb) / (
                            np.linalg.norm(current_embedding) * np.linalg.norm(hist_emb) + 1e-10
                        )
                        similarities.append(sim)
                    embedding_score = np.mean(similarities)
                    embedding_score = max(0.0, min(1.0, embedding_score))
        
        # 加权求和
        score = (
            leader_score * 0.3 +
            volume_score * 0.25 +
            correlation_score * 0.25 +
            embedding_score * 0.2  # 新增嵌入分数权重
        )
        
        return score
    
    def get_active_blocks(self, threshold: Optional[float] = None) -> List[str]:
        """获取活跃的题材列表"""
        threshold = threshold or 0.3

        active = []
        for block_id, idx in self._block_id_to_idx.items():
            score = float(self._block_hotspot_scores[idx])
            clamped_score = max(0.0, min(1.0, score))
            if clamped_score >= threshold:
                active.append(block_id)

        active.sort(key=lambda s: max(0.0, min(1.0, float(self._block_hotspot_scores[self._block_id_to_idx[s]]))), reverse=True)
        return active
    
    def get_block_hotspot(self, block_id: str) -> float:
        """获取指定题材的热点分数"""
        idx = self._block_id_to_idx.get(block_id)
        if idx is None:
            return 0.0
        raw_score = float(self._block_hotspot_scores[idx])
        clamped_score = max(0.0, min(1.0, raw_score))
        if abs(raw_score - clamped_score) > 0.01:
            log.warning(f"[BlockHotspot] block_id={block_id} 分数异常: {raw_score:.6f} -> 限制到 {clamped_score:.6f}")
        return clamped_score
    
    def get_top_blocks(self, n: int = 5) -> List[Tuple[str, float]]:
        """获取热点最高的 N 个题材"""
        blocks = []
        for block_id, idx in self._block_id_to_idx.items():
            raw_score = float(self._block_hotspot_scores[idx])
            clamped_score = max(0.0, min(1.0, raw_score))
            blocks.append((block_id, clamped_score))
        blocks.sort(key=lambda x: x[1], reverse=True)
        return blocks[:n]
    
    def get_all_weights(self, filter_noise: bool = True) -> Dict[str, float]:
        """获取所有题材的权重

        Args:
            filter_noise: 是否过滤噪音题材
        """
        noise_detector = _get_noise_detector() if filter_noise else None

        weights = {}
        filtered_count = 0
        for block_id, idx in self._block_id_to_idx.items():
            if filter_noise and noise_detector:
                block_name = self._blocks[idx].name if idx in self._blocks else None
                if noise_detector.is_noise(block_id, block_name):
                    filtered_count += 1
                    continue
            raw_score = float(self._block_hotspot_scores[idx])
            clamped_score = max(0.0, min(1.0, raw_score))
            if abs(raw_score - clamped_score) > 0.01:
                log.warning(f"[BlockHotspot] get_all_weights block_id={block_id} 分数异常: {raw_score:.6f} -> 限制到 {clamped_score:.6f}")
            weights[block_id] = clamped_score

        if len(weights) < 5:
            weight_names = [self._blocks[idx].name if idx in self._blocks else k for k, idx in self._block_id_to_idx.items() if k in weights]
            log.info(f"[BlockHotspot] get_all_weights: 返回 {len(weights)} 个有效题材 (过滤了 {filtered_count} 个噪音)")
        else:
            log.debug(f"[BlockHotspot] get_all_weights: 返回 {len(weights)} 个有效题材 (过滤了 {filtered_count} 个噪音)")
        return weights

    def save_state(self) -> Dict:
        """保存引擎状态用于持久化"""
        return {
            'blocks': {
                block_id: {
                    'block_id': config.block_id,
                    'name': config.name,
                    'symbols': list(config.symbols),
                    'decay_half_life': config.decay_half_life,
                    'activation_threshold': config.activation_threshold,
                }
                for block_id, config in self._blocks.items()
            },
            'symbol_to_blocks': dict(self._symbol_to_blocks),
            'block_hotspot_scores': self._block_hotspot_scores[:len(self._blocks)].tolist(),
            'block_id_to_idx': self._block_id_to_idx,
            'idx_to_block_id': {int(k): v for k, v in self._idx_to_block_id.items()},
            'last_update_time': self._last_update_time,
            'leader_counts': self._leader_counts,
            'volume_concentration': self._volume_concentration,
            'block_last_activity': self._block_last_activity,
        }

    def load_state(self, state: Dict) -> bool:
        """从持久化状态恢复"""
        try:
            if not state:
                return False

            self._blocks.clear()
            self._symbol_to_blocks.clear()
            self._symbol_to_blocks = defaultdict(list)

            for block_id, config_data in state.get('blocks', {}).items():
                config = BlockConfig(
                    block_id=config_data['block_id'],
                    name=config_data['name'],
                    symbols=set(config_data.get('symbols', [])),
                    decay_half_life=config_data.get('decay_half_life', 300.0),
                    activation_threshold=config_data.get('activation_threshold', 0.3),
                )
                self._blocks[block_id] = config

                for symbol in config.symbols:
                    self._symbol_to_blocks[symbol].append(block_id)

            self._block_id_to_idx = state.get('block_id_to_idx', {})
            self._idx_to_block_id = {int(k): v for k, v in state.get('idx_to_block_id', {}).items()}

            block_hotspot_scores = state.get('block_hotspot_scores', [])
            for i, score in enumerate(block_hotspot_scores):
                if i < len(self._block_hotspot_scores):
                    self._block_hotspot_scores[i] = score

            self._last_update_time = state.get('last_update_time', {})
            self._leader_counts = state.get('leader_counts', {})
            self._volume_concentration = state.get('volume_concentration', {})
            self._block_last_activity = state.get('block_last_activity', {})

            return True
        except Exception as e:
            log.warning(f"[BlockHotspotEngine] load_state 失败: {e}")
            return False

    def reset(self):
        """重置引擎状态"""
        self._block_hotspot_scores.fill(0.0)
        self._last_update_time.clear()
        self._leader_counts.clear()
        self._volume_concentration.clear()
        self._block_last_activity.clear()
        self.block_embeddings.clear()
        self.embedding_history.clear()
        self.transformer_enhancer.reset()

    def _cleanup_stale_blocks(self, current_time: float):
        """清理长期不活跃的题材数据，防止内存泄漏"""
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
            log.info(f"[BlockHotspot] 清理了 {len(stale_blocks)} 个不活跃题材的状态数据")
