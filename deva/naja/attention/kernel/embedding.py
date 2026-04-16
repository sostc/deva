"""
Market Feature Encoder - 市场特征编码器

借鉴 Transformer 的 Token Embedding 思想，将市场事件特征映射到统一的向量空间
"""

import numpy as np
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class EventEmbedding:
    """事件嵌入表示"""
    vector: np.ndarray  # d 维向量
    features: Dict[str, Any]  # 原始特征
    timestamp: float


class MarketFeatureEncoder:
    """
    市场特征编码器 - 将市场事件特征映射到统一的向量空间
    
    借鉴 Transformer 的 Token Embedding 思想，但针对金融市场特征
    """
    
    def __init__(self, embedding_dim: int = 128):
        self.embedding_dim = embedding_dim
        
        # 特征类型投影矩阵
        self.price_proj = np.random.randn(1, embedding_dim) * 0.01
        self.volume_proj = np.random.randn(1, embedding_dim) * 0.01
        self.sentiment_proj = np.random.randn(1, embedding_dim) * 0.01
        self.block_proj = np.random.randn(10, embedding_dim) * 0.01  # 假设有10个板块
        
        # 可学习的位置编码（用于时间序列）
        self.position_encoding = self._create_position_encoding(100, embedding_dim)
    
    def _create_position_encoding(self, max_len: int, d_model: int) -> np.ndarray:
        """
        借鉴 Transformer 的位置编码
        让模型理解事件的时间顺序
        """
        pe = np.zeros((max_len, d_model))
        position = np.arange(0, max_len, dtype=np.float32)[:, np.newaxis]
        div_term = np.exp(np.arange(0, d_model, 2) * (-np.log(10000.0) / d_model))
        
        pe[:, 0::2] = np.sin(position * div_term)
        pe[:, 1::2] = np.cos(position * div_term)
        return pe
    
    def encode(self, features: Dict[str, Any], time_position: int = 0) -> np.ndarray:
        """
        将特征字典编码为向量
        
        Args:
            features: 事件特征字典
            time_position: 事件在时间序列中的位置
        """
        # 各维度特征投影
        price_emb = np.array([[features.get("price_change", 0)]]) @ self.price_proj
        volume_emb = np.array([[features.get("volume_spike", 0)]]) @ self.volume_proj
        sentiment_emb = np.array([[features.get("sentiment", 0)]]) @ self.sentiment_proj
        
        # 板块嵌入（简化版）
        block_idx = hash(str(features.get("block", "default"))) % 10
        block_emb = self.block_proj[block_idx:block_idx+1]
        
        # 拼接 + 位置编码
        embedding = price_emb + volume_emb + sentiment_emb + block_emb
        if time_position < len(self.position_encoding):
            embedding += self.position_encoding[time_position:time_position+1]
        
        return embedding.flatten()
