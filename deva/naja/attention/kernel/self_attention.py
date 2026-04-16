"""
Event Self-Attention - 事件自注意力层

借鉴 Transformer 的自注意力机制，让事件之间能够"互相看"
"""

import numpy as np
from typing import List, Dict, Any
from .embedding import EventEmbedding


class FeedForwardNetwork:
    """
    前馈网络层 - 借鉴 Transformer 的 FFN
    
    让模型学习更复杂的特征组合
    """
    
    def __init__(self, d_model: int = 128, d_ff: int = 512):
        self.d_model = d_model
        self.d_ff = d_ff
        
        self.W1 = np.random.randn(d_model, d_ff) * 0.01
        self.b1 = np.zeros(d_ff)
        self.W2 = np.random.randn(d_ff, d_model) * 0.01
        self.b2 = np.zeros(d_model)
    
    def _gelu(self, x: np.ndarray) -> np.ndarray:
        """GELU 激活函数 - 大模型常用"""
        return x * (1.0 + np.tanh(np.sqrt(2 / np.pi) * (x + 0.044715 * x**3))) / 2.0
    
    def forward(self, x: np.ndarray) -> np.ndarray:
        """前向传播"""
        hidden = self._gelu(np.matmul(x, self.W1) + self.b1)
        output = np.matmul(hidden, self.W2) + self.b2
        return output


class EventSelfAttention:
    """
    事件自注意力层 - 让事件之间能够"互相看"
    
    借鉴 Transformer 的自注意力机制，但针对金融事件序列
    """
    
    def __init__(self, d_model: int = 128, num_heads: int = 4):
        self.d_model = d_model
        self.num_heads = num_heads
        self.d_k = d_model // num_heads
        
        # 投影矩阵
        self.W_q = np.random.randn(d_model, d_model) * 0.01
        self.W_k = np.random.randn(d_model, d_model) * 0.01
        self.W_v = np.random.randn(d_model, d_model) * 0.01
        self.W_o = np.random.randn(d_model, d_model) * 0.01
    
    def _split_heads(self, x: np.ndarray) -> np.ndarray:
        """将向量分割成多头"""
        batch_size, seq_len, d_model = x.shape
        return x.reshape(batch_size, seq_len, self.num_heads, self.d_k).transpose(0, 2, 1, 3)
    
    def _scaled_dot_product_attention(self, Q: np.ndarray, K: np.ndarray, V: np.ndarray) -> tuple:
        """
        缩放点积注意力 - Transformer 的核心
        
        这样可以让一个事件"关注"其他相关事件
        例如："AI 板块上涨"事件会增加"英伟达上涨"事件的权重
        """
        # 简单实现：直接计算注意力分数
        batch_size, num_heads, seq_len, d_k = Q.shape
        
        # 计算注意力分数
        scores = np.zeros((batch_size, num_heads, seq_len, seq_len))
        for b in range(batch_size):
            for h in range(num_heads):
                for i in range(seq_len):
                    for j in range(seq_len):
                        scores[b, h, i, j] = np.dot(Q[b, h, i], K[b, h, j]) / np.sqrt(d_k)
        
        attention_weights = self._softmax(scores)
        
        # 计算输出
        output = np.zeros_like(Q)
        for b in range(batch_size):
            for h in range(num_heads):
                for i in range(seq_len):
                    output[b, h, i] = np.sum(attention_weights[b, h, i, j] * V[b, h, j] for j in range(seq_len))
        
        return output, attention_weights
    
    def _softmax(self, x: np.ndarray) -> np.ndarray:
        """数值稳定的 softmax"""
        exp_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
        return exp_x / np.sum(exp_x, axis=-1, keepdims=True)
    
    def forward(self, event_embeddings: List[EventEmbedding]) -> tuple:
        """
        前向传播
        
        Args:
            event_embeddings: 事件嵌入列表
            
        Returns:
            (更新后的事件嵌入, 注意力权重矩阵)
        """
        # 构建序列矩阵
        seq_len = len(event_embeddings)
        if seq_len == 0:
            return [], np.array([])
        
        X = np.array([e.vector for e in event_embeddings])[np.newaxis, :, :]  # (1, seq_len, d_model)
        
        # 投影
        Q = np.matmul(X, self.W_q)
        K = np.matmul(X, self.W_k)
        V = np.matmul(X, self.W_v)
        
        # 分头
        Q = self._split_heads(Q)
        K = self._split_heads(K)
        V = self._split_heads(V)
        
        # 自注意力计算
        attn_output, attn_weights = self._scaled_dot_product_attention(Q, K, V)
        
        # 合并头
        attn_output = attn_output.transpose(0, 2, 1, 3).reshape(1, seq_len, self.d_model)
        output = np.matmul(attn_output, self.W_o)
        
        # 创建更新后的嵌入
        updated_embeddings = []
        for i, emb in enumerate(event_embeddings):
            updated_emb = EventEmbedding(
                vector=output[0, i],
                features=emb.features,
                timestamp=emb.timestamp
            )
            updated_embeddings.append(updated_emb)
        
        return updated_embeddings, attn_weights


class TransformerLikeAttentionLayer:
    """
    类 Transformer 注意力层 - 完整的一个 Encoder Layer
    
    包含：自注意力 + 残差连接 + 层归一化 + FFN
    """
    
    def __init__(self, d_model: int = 128, num_heads: int = 4, d_ff: int = 512):
        self.self_attn = EventSelfAttention(d_model, num_heads)
        self.ffn = FeedForwardNetwork(d_model, d_ff)
        self.d_model = d_model
    
    def _layer_norm(self, x: np.ndarray, eps: float = 1e-6) -> np.ndarray:
        """层归一化"""
        mean = np.mean(x, axis=-1, keepdims=True)
        var = np.var(x, axis=-1, keepdims=True)
        return (x - mean) / np.sqrt(var + eps)
    
    def forward(self, event_embeddings: List[EventEmbedding]) -> tuple:
        """前向传播"""
        # 第一步：自注意力 + 残差 + 归一化
        attn_embeddings, attn_weights = self.self_attn.forward(event_embeddings)
        
        # 残差连接
        residual_embeddings = []
        for orig, attn in zip(event_embeddings, attn_embeddings):
            residual_vec = orig.vector + attn.vector
            normalized_vec = self._layer_norm(residual_vec)
            residual_embeddings.append(EventEmbedding(
                vector=normalized_vec,
                features=orig.features,
                timestamp=orig.timestamp
            ))
        
        # 第二步：FFN + 残差 + 归一化
        ffn_input = np.array([e.vector for e in residual_embeddings])
        ffn_output = self.ffn.forward(ffn_input)
        
        final_embeddings = []
        for resid, ffn_out in zip(residual_embeddings, ffn_output):
            final_vec = resid.vector + ffn_out
            final_vec = self._layer_norm(final_vec)
            final_embeddings.append(EventEmbedding(
                vector=final_vec,
                features=resid.features,
                timestamp=resid.timestamp
            ))
        
        return final_embeddings, attn_weights
