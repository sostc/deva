"""
AttentionKernel - 核心注意力中枢

协调 Encoder、MultiHeadAttention 和 AttentionMemory
价值观驱动注意力计算
支持流动性救援漏斗式处理
支持末那识引擎 ManasEngine（决策中枢）
支持 UnifiedManas 统一末那识
"""


class AttentionKernel:
    """
    核心注意力中枢

    属性:
        encoder: Encoder 实例
        multi_head: MultiHeadAttention 实例
        memory: AttentionMemory 实例
        liquidity_rescue_filter: 流动性救援快速预过滤层
        panic_analyzer: 恐慌指数分析器
        rescue_orchestrator: 流动性救援协调器
        manas_engine: 末那识引擎（可选）
        unified_manas: 统一末那识（可选）
        _enable_manas: 是否启用末那识
        _use_unified: 是否使用统一末那识
    """

    def __init__(self, encoder, multi_head, memory, enable_manas=False):
        """
        初始化注意力中枢

        Args:
            encoder: Encoder 实例
            multi_head: MultiHeadAttention 实例
            memory: AttentionMemory 实例
            enable_manas: 是否启用末那识引擎（默认关闭）
        """
        self.encoder = encoder
        self.multi_head = multi_head
        self.memory = memory
        self._value_system = None
        self._liquidity_rescue_filter = None
        self._panic_analyzer = None
        self._rescue_orchestrator = None
        self._enable_manas = enable_manas
        self._use_unified = False
        self._manas_engine = None
        self._unified_manas = None
        if enable_manas:
            self._init_manas_engine()

    def _init_manas_engine(self):
        """初始化末那识引擎"""
        from .manas_engine import ManasEngine
        self._manas_engine = ManasEngine()

    def _init_unified_manas(self):
        """初始化统一末那识"""
        from deva.naja.manas import UnifiedManas
        self._unified_manas = UnifiedManas()
        self._use_unified = True

    def get_manas_engine(self):
        """获取末那识引擎实例"""
        return self._manas_engine

    def get_unified_manas(self):
        """获取统一末那识实例"""
        return self._unified_manas

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

    def set_unified_manas_enabled(self, enabled: bool):
        """
        设置是否启用统一末那识

        Args:
            enabled: 是否启用
        """
        if enabled and not self._use_unified:
            self._use_unified = True
            self._init_unified_manas()
        elif not enabled:
            self._use_unified = False
            self._unified_manas = None

    def is_manas_enabled(self) -> bool:
        """返回是否启用了末那识引擎"""
        return self._enable_manas

    def is_unified_manas_enabled(self) -> bool:
        """返回是否启用了统一末那识"""
        return self._use_unified

    def _get_value_system(self):
        """获取价值观系统（延迟加载）"""
        if self._value_system is None:
            from deva.naja.attention.values import get_value_system
            self._value_system = get_value_system()
        return self._value_system

    def _get_session_manager(self):
        """获取交易时段管理器"""
        try:
            from deva.naja.radar.trading_clock import get_trading_clock
            return get_trading_clock()
        except ImportError:
            return None

    def _get_portfolio(self):
        """获取虚拟持仓"""
        try:
            from deva.naja.bandit import get_virtual_portfolio
            return get_virtual_portfolio()
        except ImportError:
            return None

    def _get_strategy_manager(self):
        """获取策略管理器"""
        try:
            from deva.naja.attention.strategies import get_strategy_manager
            return get_strategy_manager()
        except ImportError:
            return None

    def _get_bandit_tracker(self):
        """获取 bandit tracker"""
        try:
            from deva.naja.bandit import get_bandit_tracker
            return get_bandit_tracker()
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
        """获取叙事追踪器"""
        try:
            from deva.naja.cognition import NarrativeTracker
            return NarrativeTracker.get_instance()
        except ImportError:
            return None

    def _get_liquidity_rescue_filter(self):
        """获取流动性救援快速预过滤层（延迟加载）"""
        if self._liquidity_rescue_filter is None:
            from deva.naja.attention.filters import LiquidityRescueFilter
            self._liquidity_rescue_filter = LiquidityRescueFilter()
        return self._liquidity_rescue_filter

    def _get_panic_analyzer(self):
        """获取恐慌指数分析器（延迟加载）"""
        if self._panic_analyzer is None:
            from deva.naja.attention.filters import PanicAnalyzer
            self._panic_analyzer = PanicAnalyzer()
        return self._panic_analyzer

    def _get_rescue_orchestrator(self):
        """获取流动性救援协调器（延迟加载）"""
        if self._rescue_orchestrator is None:
            from deva.naja.attention.strategies import LiquidityRescueOrchestrator
            self._rescue_orchestrator = LiquidityRescueOrchestrator()
        return self._rescue_orchestrator

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

        if self._use_unified and self._unified_manas is not None:
            return self._process_with_unified_manas(Q, raw_events)
        elif self._enable_manas and self._manas_engine is not None:
            return self._process_with_manas(Q, raw_events)
        else:
            return self._process_original(Q, raw_events)

    def _process_original(self, Q, raw_events):
        """
        原有逻辑，不受末那识影响

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

        result = self.multi_head.compute(Q, events)

        for e in events:
            symbol = getattr(e, 'symbol', None) or e.source if hasattr(e, 'source') else "unknown"
            alignment = e.features.get("_value_alignment", 0.5)
            reason = vs.generate_focus_reason(e.features)
            vs.record_attention(symbol, alignment, reason)
            vs.set_last_decision_reason(reason)

            self.memory.update(e, result["confidence"])

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

        shaped_Q = Q
        if hasattr(Q, 'features'):
            shaped_Q.features = shaped_Q.features.copy() if shaped_Q.features else {}
            shaped_Q.features['attention_focus'] = manas_output.attention_focus
            shaped_Q.features['regime_score'] = manas_output.regime_score
            shaped_Q.features['timing_score'] = manas_output.timing_score

        result = self.multi_head.compute(shaped_Q, events)

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

            self.memory.update(e, result["confidence"])

        result["manas"] = manas_output.to_dict()
        result["should_act"] = manas_output.should_act

        return result

    def _process_with_unified_manas(self, Q, raw_events):
        """
        统一末那识决策逻辑

        用 UnifiedManas 塑造 Query，应用持仓驱动的注意力召回和决策。

        Args:
            Q: QueryState
            raw_events: AttentionEvent 列表

        Returns:
            attention 结果 dict（含统一末那识状态）
        """
        macro_signal = 0.5
        if hasattr(Q, 'macro_liquidity_signal'):
            macro_signal = Q.macro_liquidity_signal

        market_state = {}
        if hasattr(Q, 'features') and Q.features:
            market_state = Q.features.copy()

        portfolio_data = self._get_portfolio_data()

        unified_output = self._unified_manas.compute(
            session_manager=self._get_session_manager(),
            portfolio_data=portfolio_data,
            scanner=self._get_scanner(),
            bandit_tracker=self._get_bandit_tracker(),
            macro_signal=macro_signal,
            market_state=market_state
        )

        recalled_events = self._unified_manas.recall_events(
            portfolio_data=portfolio_data,
            market_data=market_state
        )

        vs = self._get_value_system()
        events = []
        for e in raw_events:
            e.key = self.encoder.encode_key(e)
            e.value = self.encoder.encode_value(e)
            events.append(e)

            alignment = vs.calculate_alignment(e.features)
            e.features["_value_alignment"] = alignment

            e.features["_attention_focus"] = unified_output.attention_focus.value
            e.features["_portfolio_signal"] = unified_output.portfolio_signal.value

        shaped_Q = Q
        if hasattr(Q, 'features'):
            shaped_Q.features = shaped_Q.features.copy() if shaped_Q.features else {}
            shaped_Q.features['attention_focus'] = unified_output.attention_focus.value
            shaped_Q.features['regime_score'] = unified_output.regime_score
            shaped_Q.features['timing_score'] = unified_output.timing_score
            shaped_Q.features['harmony_state'] = unified_output.harmony_state.value
            shaped_Q.features['portfolio_signal'] = unified_output.portfolio_signal.value

        result = self.multi_head.compute(shaped_Q, events)

        result["alpha"] = result.get("alpha", 0) * unified_output.alpha
        result["_manas_score"] = unified_output.manas_score
        result["_timing_score"] = unified_output.timing_score
        result["_regime_score"] = unified_output.regime_score
        result["_confidence_score"] = unified_output.confidence_score
        result["_risk_temperature"] = unified_output.risk_temperature
        result["_bias_state"] = unified_output.bias_state.value
        result["_bias_correction"] = unified_output.bias_correction
        result["_harmony_state"] = unified_output.harmony_state.value
        result["_harmony_strength"] = unified_output.harmony_strength
        result["_action_type"] = unified_output.action_type.value
        result["_portfolio_signal"] = unified_output.portfolio_signal.value
        result["_attention_focus"] = unified_output.attention_focus.value
        result["_recalled_event_count"] = len(recalled_events)

        for e in events:
            symbol = getattr(e, 'symbol', None) or e.source if hasattr(e, 'source') else "unknown"
            alignment = e.features.get("_value_alignment", 0.5)
            reason = vs.generate_focus_reason(e.features)
            vs.record_attention(symbol, alignment, reason)
            vs.set_last_decision_reason(reason)

            self.memory.update(e, result["confidence"])

        result["unified_manas"] = unified_output.to_dict()
        result["should_act"] = unified_output.should_act
        result["attention_focus"] = unified_output.attention_focus.value

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
            sector_allocations = {}

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
                "sector_allocations": sector_allocations,
                "total_return": total_return,
                "cash_ratio": cash_ratio,
                "concentration": concentration,
            }
        except:
            return {}

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
            for e in raw_events:
                self.memory.reinforce(e, feedback["reward"])

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
            self.memory.update(e, result["confidence"])

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
