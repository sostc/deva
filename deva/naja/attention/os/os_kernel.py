"""
OSAttentionKernel - AttentionOS 专用注意力内核

与 kernel/kernel.py 中的通用 AttentionKernel 不同，
OSAttentionKernel 是 AttentionOS 层面的简化内核，
固定使用 ManasEngine，专注于 OS 级别的注意力计算和决策。

原名 AttentionKernel（位于 attention_os.py），
为避免与 kernel/kernel.py 的 AttentionKernel 冲突而重命名。
"""

import time
import logging
from typing import Dict, Any, Optional, List

from ..kernel.event_encoder import Encoder
from ..kernel.multi_scorer import MultiHeadAttention
from ..kernel.manas_engine import ManasEngine
from ..kernel import get_default_heads
from ..values.system import ValueSystem
from ..models.output import AttentionFusionOutput, AttentionKernelOutput
from ..attention_fusion import get_attention_fusion
from deva.naja.register import SR

log = logging.getLogger(__name__)


class OSAttentionKernel:
    """
    AttentionOS 专用注意力内核

    核心组件：
    - Encoder: 事件编码
    - MultiHeadAttention: QKV 注意力计算
    - ManasEngine: 决策中枢
    - ValueSystem: 价值观驱动
    """

    def __init__(self):
        self.encoder = Encoder()
        heads = get_default_heads()
        self.multi_head = MultiHeadAttention(heads)
        self.manas_engine = ManasEngine()
        self._value_system = None

        # 新增：类 Transformer 相关组件
        self._enable_transformer = True  # 默认启用
        self._feature_encoder = None
        self._transformer_layer = None
        
        # 新增：上下文学习相关组件
        self._enable_in_context = True  # 默认启用
        self._in_context_learner = None
        
        # 初始化 Transformer 和上下文学习组件
        self._init_transformer_components()
        self._init_in_context_learner()

        self._last_output: Optional[AttentionKernelOutput] = None
        self._update_interval = 1.0
        self._last_update = 0.0

    def _get_value_system(self) -> ValueSystem:
        if self._value_system is None:
            self._value_system = SR('value_system')
        return self._value_system
    
    def _init_transformer_components(self):
        """初始化类 Transformer 组件"""
        from ..kernel.embedding import MarketFeatureEncoder
        from ..kernel.self_attention import TransformerLikeAttentionLayer
        
        self._feature_encoder = MarketFeatureEncoder(embedding_dim=128)
        self._transformer_layer = TransformerLikeAttentionLayer(
            d_model=128,
            num_heads=4,
            d_ff=512
        )
        log.info("[OSAttentionKernel] 已启用类 Transformer 自注意力层")
    
    def _init_in_context_learner(self):
        """初始化上下文学习器"""
        from ..kernel.in_context_learner import get_in_context_learner
        self._in_context_learner = get_in_context_learner()
    
    def _process_with_transformer(self, events):
        """
        使用类 Transformer 的增强处理流程
        
        1. 事件向量化
        2. 事件间自注意力（让事件互相影响）
        3. 将增强信息回注到事件特征
        """
        import numpy as np
        import time
        from ..kernel.embedding import EventEmbedding
        
        if not self._enable_transformer or len(events) <= 1:
            return events
        
        try:
            # 将事件转换为嵌入
            event_embeddings = []
            for i, e in enumerate(events):
                vec = self._feature_encoder.encode(e.features, time_position=i)
                event_embeddings.append(EventEmbedding(
                    vector=vec,
                    features=e.features,
                    timestamp=getattr(e, 'timestamp', None) or time.time()
                ))
            
            # 通过自注意力层
            enhanced_embeddings, attn_matrix = self._transformer_layer.forward(event_embeddings)
            
            # 将增强后的信息回注到事件特征中
            for i, (e, emb) in enumerate(zip(events, enhanced_embeddings)):
                # 计算事件重要性分数
                event_importance = float(np.linalg.norm(emb.vector))
                e.features["_transformer_importance"] = event_importance
                
                # 根据注意力矩阵调整事件权重
                if len(attn_matrix.shape) >= 3 and i < attn_matrix.shape[2]:
                    # 这个事件被其他事件关注的程度
                    self_attn_score = float(attn_matrix[0, :, i, :].mean())
                    e.features["_cross_attention"] = self_attn_score
            
            log.debug(f"[OSAttentionKernel] Transformer 自注意力处理完成: {len(events)} 个事件")
            
        except Exception as e:
            log.warning(f"[OSAttentionKernel] Transformer 处理失败，回退到原始模式: {e}")
        
        return events

    def compute(
        self,
        events: List[Any],
        market_state: Optional[Dict[str, Any]] = None,
        query_state: Optional[Any] = None
    ) -> AttentionKernelOutput:
        """
        计算注意力输出

        Args:
            events: 事件列表
            market_state: 市场状态
            query_state: 查询状态

        Returns:
            AttentionKernelOutput
        """
        current_time = time.time()
        if current_time - self._last_update < self._update_interval and self._last_output is not None:
            return self._last_output

        vs = self._get_value_system()

        encoded_events = []
        for e in events:
            e.key = self.encoder.encode_key(e)
            e.value = self.encoder.encode_value(e)
            encoded_events.append(e)

            alignment = vs.calculate_alignment(e.features)
            e.features["_value_alignment"] = alignment

        # 新增：类 Transformer 自注意力增强
        encoded_events = self._process_with_transformer(encoded_events)
        
        # 新增：上下文学习调整 Query
        adjustment_info = {}
        if self._enable_in_context and self._in_context_learner is not None:
            # 提取事件特征用于上下文检索
            event_features_list = [e.features for e in encoded_events]
            query_state, adjustment_info = self._in_context_learner.adjust_query_with_demos(
                query_state, event_features_list
            )

        attention_result = self.multi_head.compute(query_state, encoded_events)
        
        # 添加上下文学习信息到结果
        if adjustment_info:
            attention_result["_in_context"] = adjustment_info

        alpha = attention_result.get("alpha", 1.0)
        attention_weights = attention_result.get("attention_weights", {})

        focus_symbols = []
        if attention_weights:
            sorted_weights = sorted(attention_weights.items(), key=lambda x: x[1], reverse=True)
            focus_symbols = [s for s, _ in sorted_weights[:10]]

        manas_output = self.manas_engine.compute(
            session_manager=self._get_session_manager(),
            portfolio=self._get_portfolio(),
            scanner=self._get_scanner(),
            bandit_tracker=self._get_bandit_tracker(),
            macro_signal=market_state.get("macro_liquidity_signal", 0.5) if market_state else 0.5,
            narratives=market_state.get("narratives", []) if market_state else []
        )

        alpha *= manas_output.alpha
        alpha = max(0.3, min(1.5, alpha))

        fusion_output = self._compute_fusion(attention_weights)

        for e in encoded_events:
            symbol = getattr(e, 'symbol', None) or e.source if hasattr(e, 'source') else "unknown"
            alignment = e.features.get("_value_alignment", 0.5)
            reason = vs.generate_focus_reason(e.features)
            vs.record_attention(symbol, alignment, reason)
            vs.set_last_decision_reason(reason)

        output = AttentionKernelOutput(
            alpha=alpha,
            confidence=attention_result.get("confidence", 0.5),
            attention_weights=attention_weights,
            focus_symbols=focus_symbols,
            manas_score=manas_output.manas_score,
            timing_score=manas_output.timing_score,
            regime_score=manas_output.regime_score,
            confidence_score=manas_output.confidence_score,
            risk_temperature=manas_output.risk_temperature,
            should_act=manas_output.should_act,
            action_type=manas_output.action_type.value if hasattr(manas_output.action_type, 'value') else str(manas_output.action_type),
            harmony_state=manas_output.harmony_state.value if hasattr(manas_output.harmony_state, 'value') else str(manas_output.harmony_state),
            harmony_strength=manas_output.harmony_strength,
            bias_state=manas_output.bias_state.value if hasattr(manas_output.bias_state, 'value') else str(manas_output.bias_state),
            bias_correction=manas_output.bias_correction,
            narrative_risk=manas_output.narrative_risk,
            ai_compute_direction=manas_output.ai_compute_direction,
            awakening_level=manas_output.awakening_level,
            fusion_output=fusion_output,
        )

        self._last_output = output
        self._last_update = current_time

        return output

    def _compute_fusion(self, attention_weights: Dict[str, float]) -> Optional[AttentionFusionOutput]:
        """计算融合层输出"""
        fusion_warnings: List[str] = []
        try:
            fusion = get_attention_fusion()
            if attention_weights:
                fusion_result = fusion.fuse(
                    market_attention=attention_weights,
                    portfolio_summary=None,
                    world_narrative=None,
                )
                if fusion_result:
                    fusion_signals = [
                        {"block_id": s.block_id, "score": s.fused_score,
                         "action": s.action_recommendation, "should_act": s.should_act}
                        for s in fusion_result.signals[:10]
                    ]
                    consensus_blocks = [b for b, _ in fusion_result.consensus_blocks[:5]]
                    divergence_blocks = [b for b, _ in fusion_result.divergence_blocks[:5]]
                    blind_spots = [b for b, _ in fusion_result.blind_spots[:5]]
                    new_hot_blocks = [b for b, _ in fusion_result.new_hot_blocks[:5]]

                    blind_spot_investigations = self._investigate_blind_spots(blind_spots, fusion_result, fusion_warnings)

                    return AttentionFusionOutput(
                        conviction_score=fusion_result.conviction_score,
                        fusion_signals=fusion_signals,
                        consensus_blocks=consensus_blocks,
                        divergence_blocks=divergence_blocks,
                        blind_spots=blind_spots,
                        new_hot_blocks=new_hot_blocks,
                        fusion_timing_signal=fusion_result.timing_signal,
                        blind_spot_investigations=blind_spot_investigations,
                        value_score=fusion_result.value_score,
                        market_narrative_score=fusion_result.market_narrative_score,
                        value_signals=fusion_result.value_signals,
                        market_narrative_signals=fusion_result.market_narrative_signals,
                        fusion_warnings=fusion_warnings,
                        fusion_success=True,
                    )
                else:
                    return AttentionFusionOutput(
                        fusion_warnings=["fusion_returned_none"],
                        fusion_success=False,
                    )
            else:
                return AttentionFusionOutput(
                    fusion_warnings=["no_attention_weights"],
                    fusion_success=True,
                )
        except Exception as e:
            log.warning(f"[OSAttentionKernel] AttentionFusion 调用失败: {e}")
            return AttentionFusionOutput(
                fusion_warnings=[f"fusion_exception: {e}"],
                fusion_success=False,
            )

    def _investigate_blind_spots(
        self,
        blind_spots: List[str],
        fusion_result,
        fusion_warnings: List[str]
    ) -> List[Dict]:
        """调查盲区"""
        try:
            from deva.naja.attention.discovery import get_blind_spot_investigator
            investigator = get_blind_spot_investigator()
            blind_spot_with_scores = [
                (b, fusion_result.blind_spots[i][1])
                for i, b in enumerate(blind_spots)
            ]
            if blind_spot_with_scores:
                investigation_result = investigator.investigate_all(blind_spot_with_scores)
                if investigation_result:
                    return [
                        {
                            "block_id": r.block_id,
                            "root_cause": r.root_cause,
                            "resolvers": r.resolvers,
                            "auto_followed": r.auto_followed_stocks,
                            "confidence": r.investigation_confidence,
                        }
                        for r in investigation_result.investigations
                        if r.is_actionable
                    ]
        except Exception as e:
            fusion_warnings.append(f"blind_spot_investigation_failed: {e}")
        return []

    def make_decision(
        self,
        market_state: Optional[Dict[str, Any]] = None,
        portfolio: Optional[Any] = None
    ) -> AttentionKernelOutput:
        """
        独立做决策（不经过 QKV）

        用于不需要事件输入的决策场景
        """
        current_time = time.time()
        if current_time - self._last_update < self._update_interval and self._last_output is not None:
            return self._last_output

        manas_output = self.manas_engine.compute(
            session_manager=self._get_session_manager(),
            portfolio=portfolio,
            scanner=self._get_scanner(),
            bandit_tracker=self._get_bandit_tracker(),
            macro_signal=market_state.get("macro_liquidity_signal", 0.5) if market_state else 0.5,
            narratives=market_state.get("narratives", []) if market_state else []
        )

        output = AttentionKernelOutput(
            alpha=manas_output.alpha,
            confidence=manas_output.confidence_score,
            manas_score=manas_output.manas_score,
            timing_score=manas_output.timing_score,
            regime_score=manas_output.regime_score,
            confidence_score=manas_output.confidence_score,
            risk_temperature=manas_output.risk_temperature,
            should_act=manas_output.should_act,
            action_type=manas_output.action_type.value if hasattr(manas_output.action_type, 'value') else str(manas_output.action_type),
            harmony_state=manas_output.harmony_state.value if hasattr(manas_output.harmony_state, 'value') else str(manas_output.harmony_state),
            harmony_strength=manas_output.harmony_strength,
            bias_state=manas_output.bias_state.value if hasattr(manas_output.bias_state, 'value') else str(manas_output.bias_state),
            bias_correction=manas_output.bias_correction,
            narrative_risk=manas_output.narrative_risk,
            ai_compute_direction=manas_output.ai_compute_direction,
            awakening_level=manas_output.awakening_level,
        )

        self._last_output = output
        self._last_update = current_time

        return output

    def get_harmony(self) -> Dict[str, Any]:
        """获取和谐状态"""
        if self._last_output is None:
            return {"harmony_strength": 0.5, "harmony_state": "neutral"}
        return {
            "harmony_strength": self._last_output.harmony_strength,
            "harmony_state": self._last_output.harmony_state,
            "should_act": self._last_output.should_act,
            "action_type": self._last_output.action_type,
        }

    def get_manas_engine(self) -> ManasEngine:
        """获取 ManasEngine 实例"""
        return self.manas_engine

    def get_focus_weights(self) -> Dict[str, float]:
        """获取焦点权重（兼容 BanditOptimizer）"""
        if self._last_output is None:
            return {}
        return self._last_output.attention_weights

    def get_latest_output(self) -> Optional["AttentionKernelOutput"]:
        """获取最新的内核输出（兼容 BanditOptimizer）"""
        return self._last_output

    def _get_session_manager(self):
        try:
            return SR('trading_clock')
        except ImportError:
            return None

    def _get_portfolio(self):
        try:
            return SR('virtual_portfolio')
        except ImportError:
            return None

    def _get_scanner(self):
        try:
            from deva.naja.radar import get_global_market_scanner
            return get_global_market_scanner()
        except ImportError:
            return None

    def _get_bandit_tracker(self):
        try:
            return SR('bandit_tracker')
        except ImportError:
            return None


# 向后兼容别名
AttentionKernel = OSAttentionKernel
