#!/usr/bin/env python3
"""
Transformer Enhancer - 市场热点系统的 Transformer 增强模块

集成多头自注意力和前馈网络，实现热点预测功能
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from deva.naja.attention.kernel.embedding import MarketFeatureEncoder, EventEmbedding
from deva.naja.attention.kernel.self_attention import EventSelfAttention, FeedForwardNetwork
import time
import logging

log = logging.getLogger(__name__)


class TransformerEnhancer:
    """
    Transformer 增强模块
    
    功能:
    1. 多头自注意力分析
    2. 前馈网络特征提取
    3. 热点预测
    4. 题材关系分析
    """
    
    def __init__(self, d_model: int = 128, num_heads: int = 4, d_ff: int = 512):
        """
        初始化 Transformer 增强器
        
        Args:
            d_model: 模型维度
            num_heads: 注意力头数
            d_ff: 前馈网络隐藏层维度
        """
        self.d_model = d_model
        self.num_heads = num_heads
        self.d_ff = d_ff
        
        # 初始化组件
        self.feature_encoder = MarketFeatureEncoder(embedding_dim=d_model)
        self.self_attention = EventSelfAttention(d_model=d_model, num_heads=num_heads)
        self.feed_forward = FeedForwardNetwork(d_model=d_model, d_ff=d_ff)
        
        # 历史数据
        self.history = []
        self.max_history = 20
    
    def enhance_market_analysis(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        增强市场分析
        
        Args:
            market_data: 市场数据
            {
                'blocks': [
                    {
                        'block_id': str,
                        'name': str,
                        'returns': np.ndarray,
                        'volumes': np.ndarray
                    },
                    ...
                ],
                'timestamp': float
            }
        
        Returns:
            增强后的市场分析结果
        """
        try:
            timestamp = market_data.get('timestamp', time.time())
            blocks = market_data.get('blocks', [])
            
            if not blocks:
                return {
                    'enhanced_analysis': {},
                    'predictions': [],
                    'relationships': []
                }
            
            # 1. 编码题材特征
            event_embeddings = []
            for block in blocks:
                block_id = block.get('block_id')
                name = block.get('name')
                returns = block.get('returns', np.array([]))
                volumes = block.get('volumes', np.array([]))
                
                # 计算题材特征
                if len(returns) > 0:
                    features = {
                        "price_change": np.mean(returns),
                        "volume_spike": np.mean(volumes) if len(volumes) > 0 else 0,
                        "volatility": np.std(returns) if len(returns) > 1 else 0,
                        "block": block_id
                    }
                else:
                    features = {
                        "price_change": 0,
                        "volume_spike": 0,
                        "volatility": 0,
                        "block": block_id
                    }
                
                # 生成嵌入向量
                embedding = self.feature_encoder.encode(features, time_position=int(timestamp % 100))
                event_emb = EventEmbedding(
                    vector=embedding,
                    features=features,
                    timestamp=timestamp
                )
                event_embeddings.append(event_emb)
            
            # 2. 应用自注意力
            updated_embeddings, attn_weights = self.self_attention.forward(event_embeddings)
            
            # 3. 应用前馈网络
            ffn_input = np.array([e.vector for e in updated_embeddings])
            ffn_output = self.feed_forward.forward(ffn_input)
            
            # 4. 生成预测
            predictions = self._predict_hotspot_evolution(blocks, updated_embeddings, ffn_output)
            
            # 5. 分析题材关系
            relationships = self._analyze_block_relationships(blocks, attn_weights)
            
            # 6. 存储历史数据
            self._store_history(blocks, updated_embeddings, timestamp)
            
            return {
                'enhanced_analysis': {
                    'timestamp': timestamp,
                    'block_count': len(blocks)
                },
                'predictions': predictions,
                'relationships': relationships
            }
        except Exception as e:
            log.error(f"TransformerEnhancer 增强失败: {e}")
            return {
                'enhanced_analysis': {},
                'predictions': [],
                'relationships': []
            }
    
    def _predict_hotspot_evolution(self, blocks: List[Dict[str, Any]], 
                                 updated_embeddings: List[EventEmbedding],
                                 ffn_output: np.ndarray) -> List[Dict[str, Any]]:
        """
        预测热点演变
        
        Args:
            blocks: 题材列表
            updated_embeddings: 更新后的嵌入向量
            ffn_output: 前馈网络输出
        
        Returns:
            热点预测列表
        """
        predictions = []
        
        for i, block in enumerate(blocks):
            block_id = block.get('block_id')
            name = block.get('name')
            
            # 计算预测分数
            embedding = updated_embeddings[i].vector
            ffn_out = ffn_output[i]
            
            # 综合预测分数
            prediction_score = np.mean(ffn_out) - np.mean(embedding)
            trend = "up" if prediction_score > 0 else "down"
            confidence = min(1.0, abs(prediction_score))
            
            predictions.append({
                'block_id': block_id,
                'name': name,
                'trend': trend,
                'confidence': confidence,
                'prediction_score': prediction_score
            })
        
        # 按预测分数排序
        predictions.sort(key=lambda x: abs(x['prediction_score']), reverse=True)
        
        return predictions
    
    def _analyze_block_relationships(self, blocks: List[Dict[str, Any]], 
                                   attn_weights: np.ndarray) -> List[Dict[str, Any]]:
        """
        分析题材关系
        
        Args:
            blocks: 题材列表
            attn_weights: 注意力权重矩阵
        
        Returns:
            题材关系列表
        """
        relationships = []
        
        if attn_weights.size == 0 or len(blocks) < 2:
            return relationships
        
        # 计算平均注意力权重
        avg_attn = np.mean(attn_weights, axis=(0, 1))  # 平均所有头
        
        for i, block_i in enumerate(blocks):
            for j, block_j in enumerate(blocks):
                if i != j:
                    attention = float(avg_attn[i, j])
                    if attention > 0.1:  # 只保留注意力大于阈值的关系
                        relationships.append({
                            'source_block': block_i.get('block_id'),
                            'source_name': block_i.get('name'),
                            'target_block': block_j.get('block_id'),
                            'target_name': block_j.get('name'),
                            'attention': attention
                        })
        
        # 按注意力权重排序
        relationships.sort(key=lambda x: x['attention'], reverse=True)
        
        return relationships
    
    def _store_history(self, blocks: List[Dict[str, Any]], 
                      embeddings: List[EventEmbedding],
                      timestamp: float):
        """
        存储历史数据
        
        Args:
            blocks: 题材列表
            embeddings: 嵌入向量列表
            timestamp: 时间戳
        """
        history_item = {
            'timestamp': timestamp,
            'blocks': blocks,
            'embeddings': embeddings
        }
        
        self.history.append(history_item)
        
        # 保持历史长度
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
    
    def get_history(self) -> List[Dict[str, Any]]:
        """
        获取历史数据
        
        Returns:
            历史数据列表
        """
        return self.history
    
    def reset(self):
        """
        重置增强器状态
        """
        self.history.clear()
