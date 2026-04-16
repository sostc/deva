"""
AttentionKernel - 核心注意力中枢

协调 Encoder、MultiHeadAttention 进行注意力计算
价值观驱动注意力计算
支持流动性救援漏斗式处理
支持末那识引擎 ManasEngine（决策中枢）
支持 UnifiedManas 统一末那识

新增（借鉴 Transformer）：
- 支持类 Transformer 的自注意力层
- 事件嵌入表示
- 事件间自注意力建模
"""

import logging
from deva.naja.register import SR

log = logging.getLogger(__name__)


class AttentionKernel:
    """
    核心注意力中枢

    属性:
        encoder: Encoder 实例
        multi_head: MultiHeadAttention 实例
        liquidity_rescue_filter: 流动性救援快速预过滤层
        panic_analyzer: 恐慌指数分析器
        rescue_orchestrator: 流动性救援协调器
        manas_engine: 末那识引擎（可选）
        _enable_manas: 是否启用末那识
        _enable_transformer: 是否启用类 Transformer 自注意力层
    """

    def __init__(self, encoder, multi_head, enable_manas=False, enable_transformer=False, enable_in_context=False):
        """
        初始化注意力中枢

        Args:
            encoder: Encoder 实例
            multi_head: MultiHeadAttention 实例
            enable_manas: 是否启用末那识引擎（默认关闭）
            enable_transformer: 是否启用类 Transformer 自注意力层（默认关闭）
            enable_in_context: 是否启用上下文学习（默认关闭）
        """
        self.encoder = encoder
        self.multi_head = multi_head
        self._value_system = None
        self._liquidity_rescue_filter = None
        self._panic_analyzer = None
        self._rescue_orchestrator = None
        self._narrative_tracker = None
        self._enable_manas = enable_manas
        self._manas_engine = None
        
        # 新增：类 Transformer 相关组件
        self._enable_transformer = enable_transformer
        self._feature_encoder = None
        self._transformer_layer = None
        
        # 新增：上下文学习相关组件
        self._enable_in_context = enable_in_context
        self._in_context_learner = None
        
        if enable_manas:
            self._init_manas_engine()
        if enable_transformer:
            self._init_transformer_components()
        if enable_in_context:
            self._init_in_context_learner()
    
    def _init_transformer_components(self):
        """初始化类 Transformer 组件"""
        from .embedding import MarketFeatureEncoder
        from .self_attention import TransformerLikeAttentionLayer
        
        self._feature_encoder = MarketFeatureEncoder(embedding_dim=128)
        self._transformer_layer = TransformerLikeAttentionLayer(
            d_model=128,
            num_heads=4,
            d_ff=512
        )
        log.info("[AttentionKernel] 已启用类 Transformer 自注意力层")
    
    def set_transformer_enabled(self, enabled: bool):
        """
        设置是否启用类 Transformer 自注意力层

        Args:
            enabled: 是否启用
        """
        if enabled and not self._enable_transformer:
            self._enable_transformer = True
            self._init_transformer_components()
        elif not enabled:
            self._enable_transformer = False
            self._feature_encoder = None
            self._transformer_layer = None
    
    def is_transformer_enabled(self) -> bool:
        """返回是否启用了类 Transformer 自注意力层"""
        return self._enable_transformer
    
    def _init_in_context_learner(self):
        """初始化上下文学习器"""
        from .in_context_learner import get_in_context_learner
        self._in_context_learner = get_in_context_learner()
    
    def set_in_context_enabled(self, enabled: bool):
        """
        设置是否启用上下文学习

        Args:
            enabled: 是否启用
        """
        if enabled and not self._enable_in_context:
            self._enable_in_context = True
            self._init_in_context_learner()
        elif not enabled:
            self._enable_in_context = False
            self._in_context_learner = None
    
    def is_in_context_enabled(self) -> bool:
        """返回是否启用了上下文学习"""
        return self._enable_in_context
    
    def get_in_context_learner(self):
        """获取上下文学习器实例"""
        return self._in_context_learner
    
    def _init_manas_engine(self):
        """初始化末那识引擎"""
        from .manas_engine import ManasEngine
        self._manas_engine = ManasEngine()

    def get_manas_engine(self):
        """获取末那识引擎实例"""
        return self._manas_engine

    def set_manas_enabled(self, enabled: bool):
        """
        设置是否启用末那识引擎

        Args:
            enabled: 是否启用
        """
        if enabled and not self._enable_manas:
            self._enable_manas = True
            self._init_manas_engine()
        elif not enabled:
            self._enable_manas = False
            self._manas_engine = None

    def is_manas_enabled(self) -> bool:
        """返回是否启用了末那识引擎"""
        return self._enable_manas

    def _get_value_system(self):
        """获取价值观系统（延迟加载）"""
        if self._value_system is None:
            self._value_system = SR('value_system')
        return self._value_system

    def _get_session_manager(self):
        """获取交易时段管理器"""
        try:
            return SR('trading_clock')
        except ImportError:
            return None

    def _get_portfolio(self):
        """获取虚拟持仓"""
        try:
            return SR('virtual_portfolio')
        except KeyError:
            return None

    def _get_strategy_manager(self):
        """获取策略管理器"""
        try:
            from deva.naja.market_hotspot.strategies import get_strategy_manager
            return get_strategy_manager()
        except ImportError:
            return None

    def _get_bandit_tracker(self):
        """获取 bandit tracker"""
        try:
            return SR('bandit_tracker')
        except ImportError:
            return None

    def _get_scanner(self):
        """获取市场扫描器"""
        try:
            from deva.naja.radar.global_market_scanner import get_global_market_scanner
            return get_global_market_scanner()
        except ImportError:
            return None

    def _get_narrative_tracker(self):
        """获取叙事追踪器（NarrativeTracker / 地）（延迟加载 + 缓存）"""
        if self._narrative_tracker is None:
            try:
                from deva.naja.cognition import NarrativeTracker
                self._narrative_tracker = NarrativeTracker()
            except ImportError:
                return None
        return self._narrative_tracker

    def _get_liquidity_rescue_filter(self):
        """获取流动性救援快速预过滤层（延迟加载）"""
        if self._liquidity_rescue_filter is None:
            from deva.naja.market_hotspot.filters import LiquidityRescueFilter
            self._liquidity_rescue_filter = LiquidityRescueFilter()
        return self._liquidity_rescue_filter

    def _get_panic_analyzer(self):
        """获取恐慌指数分析器（延迟加载）"""
        if self._panic_analyzer is None:
            from deva.naja.market_hotspot.filters import PanicAnalyzer
            self._panic_analyzer = PanicAnalyzer()
        return self._panic_analyzer

    def _get_rescue_orchestrator(self):
        """获取流动性救援协调器（延迟加载）"""
        if self._rescue_orchestrator is None:
            from deva.naja.market_hotspot.strategies import LiquidityRescueOrchestrator
            self._rescue_orchestrator = LiquidityRescueOrchestrator()
        return self._rescue_orchestrator
    
    def _process_with_transformer(self, Q, events):
        """
        使用类 Transformer 的增强处理流程
        
        1. 事件向量化
        2. 事件间自注意力（让事件互相影响）
        3. 将增强信息回注到事件特征
        """
        import numpy as np
        import time
        from .embedding import EventEmbedding
        
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
                    timestamp=e.timestamp or time.time()
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
            
            log.debug(f"[AttentionKernel] Transformer 自注意力处理完成: {len(events)} 个事件")
            
        except Exception as e:
            log.warning(f"[AttentionKernel] Transformer 处理失败，回退到原始模式: {e}")
        
        return events

    def process(self, Q, raw_events):
        """
        处理事件列表

        Args:
            Q: QueryState
            raw_events: AttentionEvent 列表

        Returns:
            attention 结果 dict
        """
        if not raw_events:
            return {"alpha": 0, "risk": 0, "confidence": 0}

        if self._enable_manas and self._manas_engine is not None:
            return self._process_with_manas(Q, raw_events)
        else:
            return self._process_original(Q, raw_events)

    def _process_original(self, Q, raw_events):
        """
        原有逻辑，不受末那识影响
        
        新增：
        - 支持类 Transformer 的自注意力增强
        - 支持上下文学习调整 Query

        Args:
            Q: QueryState
            raw_events: AttentionEvent 列表

        Returns:
            attention 结果 dict
        """
        vs = self._get_value_system()
        events = []
        for e in raw_events:
            e.key = self.encoder.encode_key(e)
            e.value = self.encoder.encode_value(e)
            events.append(e)

            alignment = vs.calculate_alignment(e.features)
            e.features["_value_alignment"] = alignment
        
        # 新增：类 Transformer 自注意力增强
        events = self._process_with_transformer(Q, events)
        
        # 新增：上下文学习调整 Query
        adjustment_info = {}
        if self._enable_in_context and self._in_context_learner is not None:
            # 提取事件特征用于上下文检索
            event_features_list = [e.features for e in events]
            Q, adjustment_info = self._in_context_learner.adjust_query_with_demos(
                Q, event_features_list
            )

        result = self.multi_head.compute(Q, events)
        
        # 添加上下文学习信息到结果
        if adjustment_info:
            result["_in_context"] = adjustment_info

        for e in events:
            symbol = getattr(e, 'symbol', None) or e.source if hasattr(e, 'source') else "unknown"
            alignment = e.features.get("_value_alignment", 0.5)
            reason = vs.generate_focus_reason(e.features)
            vs.record_attention(symbol, alignment, reason)
            vs.set_last_decision_reason(reason)

        return result

    def _process_with_manas(self, Q, raw_events):
        """
        末那识引擎决策逻辑

        用末那识塑造 Query，应用决策调制到最终结果。

        Args:
            Q: QueryState
            raw_events: AttentionEvent 列表

        Returns:
            attention 结果 dict（含末那识状态）
        """
        macro_signal = 0.5
        if hasattr(Q, 'macro_liquidity_signal'):
            macro_signal = Q.macro_liquidity_signal

        narratives = []
        tracker = self._get_narrative_tracker()
        if tracker:
            try:
                summary = tracker.get_summary()
                narratives = list(summary.get('active_narratives', {}).keys())
            except Exception:
                pass

        manas_output = self._manas_engine.compute(
            session_manager=self._get_session_manager(),
            portfolio=self._get_portfolio(),
            scanner=self._get_scanner(),
            bandit_tracker=self._get_bandit_tracker(),
            macro_signal=macro_signal,
            narratives=narratives
        )

        vs = self._get_value_system()
        events = []
        for e in raw_events:
            e.key = self.encoder.encode_key(e)
            e.value = self.encoder.encode_value(e)
            events.append(e)

            alignment = vs.calculate_alignment(e.features)
            e.features["_value_alignment"] = alignment
        
        # 新增：类 Transformer 自注意力增强
        events = self._process_with_transformer(Q, events)
        
        # 新增：上下文学习调整 Query
        adjustment_info = {}
        if self._enable_in_context and self._in_context_learner is not None:
            # 提取事件特征用于上下文检索
            event_features_list = [e.features for e in events]
            Q, adjustment_info = self._in_context_learner.adjust_query_with_demos(
                Q, event_features_list
            )

        shaped_Q = Q
        if hasattr(Q, 'features'):
            shaped_Q.features = shaped_Q.features.copy() if shaped_Q.features else {}
            shaped_Q.features['attention_focus'] = manas_output.attention_focus
            shaped_Q.features['regime_score'] = manas_output.regime_score
            shaped_Q.features['timing_score'] = manas_output.timing_score

        result = self.multi_head.compute(shaped_Q, events)
        
        # 添加上下文学习信息到结果
        if adjustment_info:
            result["_in_context"] = adjustment_info

        result["alpha"] = result.get("alpha", 0) * manas_output.alpha
        result["_manas_score"] = manas_output.manas_score
        result["_timing_score"] = manas_output.timing_score
        result["_regime_score"] = manas_output.regime_score
        result["_confidence_score"] = manas_output.confidence_score
        result["_risk_temperature"] = manas_output.risk_temperature
        result["_bias_state"] = manas_output.bias_state.value
        result["_bias_correction"] = manas_output.bias_correction
        result["_narrative_risk"] = manas_output.narrative_risk
        result["_supply_chain_risk_level"] = manas_output.supply_chain_risk_level
        result["_hot_narratives"] = manas_output.hot_narratives

        for e in events:
            symbol = getattr(e, 'symbol', None) or e.source if hasattr(e, 'source') else "unknown"
            alignment = e.features.get("_value_alignment", 0.5)
            reason = vs.generate_focus_reason(e.features)
            vs.record_attention(symbol, alignment, reason)
            vs.set_last_decision_reason(reason)

        result["manas"] = manas_output.to_dict()
        result["should_act"] = manas_output.should_act

        return result

    def _get_portfolio_data(self) -> dict:
        """获取持仓数据"""
        portfolio = self._get_portfolio()
        if portfolio is None:
            return {}

        try:
            summary = portfolio.get_summary()
            positions = portfolio.get_all_positions() if hasattr(portfolio, 'get_all_positions') else []

            held_symbols = [p.stock_code for p in positions if hasattr(p, 'stock_code')]
            position_details = []
            block_allocations = {}

            for pos in positions:
                if hasattr(pos, 'to_dict'):
                    position_details.append(pos.to_dict())

            total_return = summary.get('total_return', 0.0)
            available = summary.get('available_capital', 0)
            total = summary.get('total_capital', 1)
            cash_ratio = available / max(total, 1)

            concentration = 0.0
            if held_symbols and total > 0:
                for pos in positions:
                    if hasattr(pos, 'entry_price') and hasattr(pos, 'quantity'):
                        pos_value = pos.entry_price * pos.quantity
                        concentration = max(concentration, pos_value / total)

            return {
                "held_symbols": held_symbols,
                "position_details": position_details,
                "block_allocations": block_allocations,
                "total_return": total_return,
                "cash_ratio": cash_ratio,
                "concentration": concentration,
            }
        except:
            return {}

    def _convert_recalled_to_attention_events(self, recalled_events, unified_output):
        """
        将 RecalledEvent 转换为 AttentionEvent

        召回事件来自 Manas 的事件池（dict 格式），需要转换成
        AttentionEvent 对象才能被 multi_head.compute() 处理。
        召回事件带有 priority 权重，会作为 _recall_priority 注入 features。
        """
        if not recalled_events:
            return []

        from ..kernel.event import AttentionEvent
        import time as _time

        attention_events = []
        for re in recalled_events:
            features = {
                "_recalled": True,
                "_recall_priority": re.priority,
                "_recall_confidence": re.confidence,
                **(re.conditions or {}),
                "price_change": re.conditions.get("return_pct", 0) if re.conditions else 0,
                "sentiment": re.priority,  # 用 priority 作为情感信号
                "volume_spike": re.priority * 0.5,
                "historical_alpha": re.priority * unified_output.manas_score,
            }

            event = AttentionEvent(
                source=f"recalled_{re.event_type}",
                data={"symbol": re.symbol, "content": re.content},
                features=features,
                timestamp=_time.time(),
            )

            attention_events.append(event)

        return attention_events

    def _build_manas_aware_heads(self, unified_output):
        """
        构建 Manas-aware 注意力头

        scorer 同时看 Q（注入了 Manas 信息）和 K（事件特征），
        实现真正的 Q·K 注意力驱动：
        - attention_focus 决定哪个维度占主导
        - portfolio_signal 调整风险敞口
        - regime_score 调整市场/趋势信号权重
        - timing_score 调整行动紧迫度
        """
        from .attention_scorer import AttentionHead
        from .multi_scorer import MultiHeadAttention

        focus = unified_output.attention_focus.value
        portfolio_sig = unified_output.portfolio_signal.value
        regime = unified_output.regime_score
        timing = unified_output.timing_score
        harmony = unified_output.harmony_state.value
        action = unified_output.action_type.value

        # 基础 scorer：根据 attention_focus 调整各维度权重
        def manas_market_scorer(Q, K):
            """市场头 scorer - Q·K 联合打分"""
            base = K.get("price_change", 0) if isinstance(K, dict) else getattr(K, "features", {}).get("price_change", 0)
            recall_boost = K.get("_recall_priority", 0) if isinstance(K, dict) else getattr(K, "features", {}).get("_recall_priority", 0)

            # 从 Q 获取 Manas 信息
            q_features = {}
            if isinstance(Q, dict):
                q_features = Q
            elif hasattr(Q, 'features') and Q.features:
                q_features = Q.features

            q_regime = q_features.get("regime_score", 0)
            q_focus = q_features.get("attention_focus", "watch")

            # 不同 focus 下市场信号权重不同
            focus_weight = 1.0
            if q_focus == "stop_loss":
                focus_weight = 1.5  # 止损时更关注市场波动
            elif q_focus == "accumulate":
                focus_weight = 0.8
            elif q_focus == "watch":
                focus_weight = 1.0

            # 召回事件获得额外加权
            recall_weight = 1.0 + recall_boost * 2.0

            return base * focus_weight * (1.0 + abs(q_regime) * 0.5) * recall_weight

        def manas_news_scorer(Q, K):
            """新闻/情绪头 scorer"""
            base = K.get("sentiment", 0) if isinstance(K, dict) else getattr(K, "features", {}).get("sentiment", 0)
            recall_boost = K.get("_recall_priority", 0) if isinstance(K, dict) else getattr(K, "features", {}).get("_recall_priority", 0)

            q_features = {}
            if isinstance(Q, dict):
                q_features = Q
            elif hasattr(Q, 'features') and Q.features:
                q_features = Q.features

            q_timing = q_features.get("timing_score", 0.5)
            q_harmony = q_features.get("harmony_state", "neutral")

            # 时机越好，新闻信号越重要
            timing_weight = 0.5 + q_timing * 1.0

            # 和谐状态为共振时，情绪信号更可信
            harmony_weight = 1.0
            if q_harmony == "resonance":
                harmony_weight = 1.5
            elif q_harmony == "resistance":
                harmony_weight = 0.6

            recall_weight = 1.0 + recall_boost * 2.0

            return base * timing_weight * harmony_weight * recall_weight

        def manas_flow_scorer(Q, K):
            """资金流头 scorer"""
            base = K.get("volume_spike", 0) if isinstance(K, dict) else getattr(K, "features", {}).get("volume_spike", 0)
            recall_boost = K.get("_recall_priority", 0) if isinstance(K, dict) else getattr(K, "features", {}).get("_recall_priority", 0)

            q_features = {}
            if isinstance(Q, dict):
                q_features = Q
            elif hasattr(Q, 'features') and Q.features:
                q_features = Q.features

            q_portfolio_sig = q_features.get("portfolio_signal", "none")
            q_regime = q_features.get("regime_score", 0)

            # 止损/止盈时资金流信号更重要
            sig_weight = 1.0
            if q_portfolio_sig in ("stop_loss", "take_profit"):
                sig_weight = 1.8
            elif q_portfolio_sig == "rebalance":
                sig_weight = 1.3

            # 顺风环境资金流更可信
            regime_weight = 1.0 + max(q_regime, 0) * 0.5

            recall_weight = 1.0 + recall_boost * 2.0

            return base * sig_weight * regime_weight * recall_weight

        def manas_meta_scorer(Q, K):
            """Meta/Alpha 头 scorer - 由 Manas 历史表现驱动"""
            base = K.get("historical_alpha", 0) if isinstance(K, dict) else getattr(K, "features", {}).get("historical_alpha", 0)
            recall_boost = K.get("_recall_priority", 0) if isinstance(K, dict) else getattr(K, "features", {}).get("_recall_priority", 0)

            q_features = {}
            if isinstance(Q, dict):
                q_features = Q
            elif hasattr(Q, 'features') and Q.features:
                q_features = Q.features

            q_confidence = q_features.get("confidence_score", 0.5)
            q_action = q_features.get("action_type", "hold")

            # Manas 自信度高时，meta 信号权重提升
            confidence_weight = 0.5 + q_confidence * 1.0

            # 行动类型影响 meta 评分
            action_weight = 1.0
            if q_action == "act_fully":
                action_weight = 1.5
            elif q_action == "hold":
                action_weight = 0.7

            recall_weight = 1.0 + recall_boost * 2.0

            return base * confidence_weight * action_weight * recall_weight

        # 根据 attention_focus 动态调整 head 权重（通过 output_mode="merge" 的简单加法实现）
        heads = [
            AttentionHead("market", scorer=manas_market_scorer),
            AttentionHead("news", scorer=manas_news_scorer),
            AttentionHead("flow", scorer=manas_flow_scorer),
            AttentionHead("meta", scorer=manas_meta_scorer),
        ]

        return MultiHeadAttention(heads, output_mode="merge")

    def process_with_feedback(self, Q, raw_events, feedback):
        """
        带反馈的处理流程

        Args:
            Q: QueryState
            raw_events: AttentionEvent 列表
            feedback: 反馈 dict，包含 reward 等

        Returns:
            attention 结果 dict
        """
        result = self.process(Q, raw_events)

        if "reward" in feedback:
            pass

        if self._unified_manas is not None and "pnl_pct" in feedback:
            self._unified_manas.record_pnl(feedback["pnl_pct"])
            self._unified_manas.record_feedback(
                outcome=feedback,
                market_data=feedback.get("market_data", {})
            )
        elif self._manas_engine is not None and "pnl_pct" in feedback:
            self._manas_engine.record_pnl(feedback["pnl_pct"])

        Q.update(feedback)

        return result

    def process_liquidity_rescue(self, Q, raw_events) -> dict:
        """
        流动性救援专用处理流程（漏斗式）

        第一层：快速预过滤（价格/成交量变化）
        第二层：恐慌指数分析
        第三层：深度分析（策略协调器）

        Args:
            Q: QueryState
            raw_events: AttentionEvent 列表

        Returns:
            dict: 包含普通结果 + 流动性救援状态
        """
        if not raw_events:
            return {
                "alpha": 0, "risk": 0, "confidence": 0,
                "liquidity_rescue": {"state": "normal", "action": "watch"}
            }

        vs = self._get_value_system()
        is_liquidity_rescue_mode = vs.get_active_value_type() == "liquidity_rescue"

        if is_liquidity_rescue_mode:
            return self._process_with_rescue_funnel(Q, raw_events)
        else:
            return self.process(Q, raw_events)

    def _process_with_rescue_funnel(self, Q, raw_events) -> dict:
        """使用漏斗式处理流动性救援事件"""
        rescue_filter = self._get_liquidity_rescue_filter()
        panic_analyzer = self._get_panic_analyzer()
        rescue_orchestrator = self._get_rescue_orchestrator()

        passed_events = []
        rescue_state = {"state": "normal", "action": "watch"}

        for e in raw_events:
            e.key = self.encoder.encode_key(e)
            e.value = self.encoder.encode_value(e)

            filter_result = rescue_filter.filter(e)

            if not filter_result.passed:
                continue

            panic_result = panic_analyzer.analyze(e)

            if panic_result.passed:
                features = e.features
                rescue_state = rescue_orchestrator.update(
                    panic_score=panic_result.panic_score,
                    spread=features.get("spread_ratio", 1.0) * 0.05,
                    volume_ratio=features.get("volume_shrink_ratio", 1.0),
                    price_change=features.get("price_change", 0),
                    order_book_depth=features.get("order_book_depth", 1000),
                    sentiment_change=features.get("sentiment_change", 0)
                )

                alignment = vs.calculate_alignment(e.features)
                e.features["_value_alignment"] = alignment
                e.features["_panic_score"] = panic_result.panic_score
                e.features["_liquidity_score"] = panic_result.liquidity_score
                e.features["_rescue_level"] = rescue_state.level

                passed_events.append(e)

        if not passed_events:
            return {
                "alpha": 0, "risk": 0, "confidence": 0,
                "liquidity_rescue": {
                    "state": rescue_state.level,
                    "action": rescue_orchestrator.get_recommended_action(),
                    "panic_score": panic_result.panic_score if 'panic_result' in dir() else 0,
                    "liquidity_score": panic_result.liquidity_score if 'panic_result' in dir() else 1.0
                }
            }

        result = self.multi_head.compute(Q, passed_events)

        for e in passed_events:
            symbol = getattr(e, 'symbol', None) or e.source if hasattr(e, 'source') else "unknown"
            alignment = e.features.get("_value_alignment", 0.5)
            reason = vs.generate_focus_reason(e.features)
            vs.record_attention(symbol, alignment, reason)
            vs.set_last_decision_reason(reason)

        return {
            "alpha": result.get("alpha", 0),
            "risk": result.get("risk", 0),
            "confidence": result.get("confidence", 0),
            "liquidity_rescue": {
                "state": rescue_state.level,
                "action": rescue_orchestrator.get_recommended_action(),
                "panic_score": rescue_state.panic_score,
                "liquidity_score": rescue_state.liquidity_score,
                "passed_events_count": len(passed_events),
                "rescue_opportunity": rescue_state.level in ["peak", "opportunity"]
            }
        }

    def get_liquidity_rescue_stats(self) -> dict:
        """获取流动性救援统计"""
        try:
            orch = self._get_rescue_orchestrator()
            return orch.get_state()
        except:
            return {"error": "orchestrator not initialized"}

    def personalize_event(self, event: dict) -> dict:
        """根据用户关注对事件进行个性化打分

        这是 Attention Kernel 的核心职责之一：
        根据用户画像（Monas、Ananya 等系统）结合用户关注，
        对事件进行个性化的 relevance 评分。

        Args:
            event: 事件字典，需包含 score、signal_type 等字段

        Returns:
            更新后的事件字典，增加了 user_score、scope 等字段
        """
        from typing import Any

        def _clamp(v: float) -> float:
            return max(0.0, min(1.0, v))

        def _safe_float(v: Any, default: float = 0.5) -> float:
            try:
                return float(v)
            except (TypeError, ValueError):
                return default

        score = _safe_float(event.get("score"), 0.5)
        system_attention = _clamp(score)
        confidence = _safe_float(event.get("confidence"), 0.5)
        actionability = _safe_float(event.get("actionability"), 0.4)
        novelty = _safe_float(event.get("novelty"), 0.5)

        payload = event.get("payload") or {}
        signal_type = str(payload.get("signal_type", event.get("signal_type", ""))).upper()
        if signal_type in {"BUY", "SELL"}:
            actionability = 0.9
            confidence = max(confidence, 0.7)

        user_score = (
            0.4 * system_attention
            + 0.2 * confidence
            + 0.2 * actionability
            + 0.2 * novelty
        )

        event["user_score"] = round(_clamp(user_score), 3)
        event["system_attention"] = round(system_attention, 3)
        event["scope"] = self._infer_event_scope(event)
        return event

    def _infer_event_scope(self, event: dict) -> str:
        """推断事件作用域（macro / symbol）"""
        payload = event.get("payload") or {}
        for key in ("stock_code", "symbol", "code", "ticker", "stock_name"):
            if payload.get(key):
                return "symbol"
        symbols = payload.get("symbols")
        if isinstance(symbols, list) and len(symbols) == 1:
            return "symbol"
        return "macro"
