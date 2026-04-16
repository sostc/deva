"""
In-Context Attention Learner - 上下文学习器

借鉴大模型的 Few-Shot Learning 思想

让系统从历史案例中学习，而不是从零开始决策
"""

import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

log = logging.getLogger(__name__)


@dataclass
class Demonstration:
    """示范样本 - 用于上下文学习"""
    events: List[Dict[str, Any]]  # 输入事件序列
    decision: Dict[str, Any]       # 对应的决策
    outcome: float              # 结果（盈亏等）
    timestamp: float            # 时间戳
    metadata: Dict[str, Any] = None  # 额外元数据


class InContextAttentionLearner:
    """
    上下文学习器 - 借鉴大模型的 Few-Shot Learning
    
    思想：给模型看几个"示例"，让它学会如何处理当前情况
    """
    
    def __init__(self, max_demonstrations: int = 20, embedding_dim: int = 128):
        self.demonstrations: List[Demonstration] = []
        self.max_demonstrations = max_demonstrations
        self.embedding_dim = embedding_dim
        
        # 简单的事件特征哈希嵌入
        self._feature_weights = np.random.randn(10, 10) * 0.01  # 10个板块，每个板块10维特征
    
    def _hash_features(self, features: Dict[str, Any]) -> np.ndarray:
        """简单的特征哈希到向量的映射"""
        vec = np.zeros(self.embedding_dim)
        
        # 价格变化
        price_change = features.get("price_change", 0)
        vec[0] = price_change
        
        # 成交量
        volume = features.get("volume_spike", 0)
        vec[1] = volume
        
        # 情绪
        sentiment = features.get("sentiment", 0)
        vec[2] = sentiment
        
        # 板块哈希
        block = str(features.get("block", "default"))
        block_hash = hash(block) % 10
        vec[3:13] = self._feature_weights[block_hash]
        
        # Alpha/Risk/Confidence
        vec[13] = features.get("alpha", 0)
        vec[14] = features.get("risk", 0)
        vec[15] = features.get("confidence", 0)
        
        return vec
    
    def _embed_events_similarity(self, events_a: List[Dict[str, Any]], events_b: List[Dict[str, Any]]) -> float:
        """计算两个事件序列的相似度"""
        if not events_a or not events_b:
            return 0.0
        
        # 简单实现：比较符号重叠 + 特征相似度
        symbols_a = set(e.get("symbol", "") for e in events_a)
        symbols_b = set(e.get("symbol", "") for e in events_b)
        symbol_overlap = len(symbols_a & symbols_b) / max(len(symbols_a | symbols_b), 1e-6)
        
        # 特征相似度
        vec_a = np.mean([self._hash_features(e) for e in events_a], axis=0)
        vec_b = np.mean([self._hash_features(e) for e in events_b], axis=0)
        
        feature_sim = float(np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b) + 1e-6))

        return 0.5 * symbol_overlap + 0.5 * feature_sim
    
    def add_demonstration(
        self,
        events: List[Dict[str, Any]],
        decision: Dict[str, Any],
        outcome: float,
        metadata: Dict[str, Any] = None
    ):
        """添加一个示范样本"""
        import time
        demo = Demonstration(
            events=events,
            decision=decision,
            outcome=outcome,
            timestamp=time.time(),
            metadata=metadata or {}
        )
        self.demonstrations.append(demo)
        
        # 保留最成功的样本，同时保持时间新鲜度
        if len(self.demonstrations) > self.max_demonstrations:
            # 综合排序：结果好坏 * 时间衰减因子
            def demo_score(d):
                time_decay = 0.99 ** ((time.time() - d.timestamp) / 86400)  # 每天衰减1%
                return d.outcome * time_decay
            
            self.demonstrations.sort(key=demo_score, reverse=True)
            self.demonstrations = self.demonstrations[:self.max_demonstrations]
        
        log.debug(f"[InContextLearner] 添加示范样本，当前总数: {len(self.demonstrations)}")
    
    def retrieve_relevant_demos(
        self,
        current_events: List[Dict[str, Any]],
        k: int = 5,
        min_similarity: float = 0.1
    ) -> List[Demonstration]:
        """
        检索相关的示范样本
        
        借鉴 RAG（检索增强生成）的思想
        """
        if not self.demonstrations:
            return []
        
        # 计算相似度
        scored_demos = []
        for demo in self.demonstrations:
            sim = self._embed_events_similarity(current_events, demo.events)
            if sim >= min_similarity:
                # 综合分数 = 相似度 * (1 + max(0, demo.outcome))  # 好结果加权
                scored_demos.append((sim * (1 + max(0, demo.outcome)), demo))
        
        # 排序返回 top-k
        scored_demos.sort(key=lambda x: x[0], reverse=True)
        return [demo for _, demo in scored_demos[:k]]
    
    def adjust_query_with_demos(
        self,
        Q,
        current_events: List[Dict[str, Any]]
    ):
        """
        使用相关示范调整 Query
        
        让决策参考历史上类似的成功/失败案例
        """
        relevant_demos = self.retrieve_relevant_demos(current_events, k=3)
        
        if not relevant_demos:
            return Q, {}
        
        # 计算示范的平均决策
        demo_decisions = [d.decision for d in relevant_demos]
        avg_alpha = np.mean([d.get("alpha", 0.5) for d in demo_decisions])
        avg_risk = np.mean([d.get("risk", 0.5) for d in demo_decisions])
        avg_confidence = np.mean([d.get("confidence", 0.5) for d in demo_decisions])
        avg_outcome = np.mean([d.outcome for d in relevant_demos])
        
        # 调整 Query（这是一个简化的例子）
        adjustment_info = {
            "num_demos": len(relevant_demos),
            "avg_alpha_bias": float(avg_alpha - 0.5),
            "avg_risk_bias": float(avg_risk - 0.5),
            "avg_confidence_bias": float(avg_confidence - 0.5),
            "historical_success": float(max(0, avg_outcome)),
            "best_outcome": float(max(d.outcome for d in relevant_demos)),
            "worst_outcome": float(min(d.outcome for d in relevant_demos)),
        }
        
        if hasattr(Q, 'features'):
            if Q.features is None:
                Q.features = {}
            else:
                Q.features = Q.features.copy()
            
            Q.features["_demo_alpha_bias"] = adjustment_info["avg_alpha_bias"]
            Q.features["_demo_risk_bias"] = adjustment_info["avg_risk_bias"]
            Q.features["_demo_confidence_bias"] = adjustment_info["avg_confidence_bias"]
            Q.features["_historical_success"] = adjustment_info["historical_success"]
            Q.features["_num_relevant_demos"] = adjustment_info["num_demos"]
        
        log.debug(f"[InContextLearner] 使用 {len(relevant_demos)} 个相关示范调整 Query")
        
        return Q, adjustment_info
    
    def get_demo_statistics(self) -> Dict[str, Any]:
        """获取示范样本统计信息"""
        if not self.demonstrations:
            return {
                "total": 0,
                "successful": 0,
                "avg_outcome": 0.0,
                "best_outcome": 0.0,
                "worst_outcome": 0.0,
            }
        
        outcomes = [d.outcome for d in self.demonstrations]
        successful = sum(1 for o in outcomes if o > 0)
        
        return {
            "total": len(self.demonstrations),
            "successful": successful,
            "avg_outcome": float(np.mean(outcomes)),
            "best_outcome": float(max(outcomes)),
            "worst_outcome": float(min(outcomes)),
        }


# 全局单例
_in_context_learner: Optional[InContextAttentionLearner] = None


def get_in_context_learner() -> InContextAttentionLearner:
    """获取上下文学习器单例"""
    global _in_context_learner
    if _in_context_learner is None:
        _in_context_learner = InContextAttentionLearner()
    return _in_context_learner


def setup_in_context_learner(max_demonstrations: int = 20):
    """设置上下文学习器"""
    global _in_context_learner
    _in_context_learner = InContextAttentionLearner(max_demonstrations=max_demonstrations)
    log.info(f"[InContextLearner] 已初始化上下文学习器，最大样本数: {max_demonstrations}")
