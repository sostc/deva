"""
AttentionKernel - 核心注意力中枢

协调 Encoder、MultiHeadAttention 和 AttentionMemory
价值观驱动注意力计算
支持流动性救援漏斗式处理
支持四维决策框架（可选）
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
        four_dimensions: 四维决策框架（可选）
        _enable_four_dimensions: 是否启用四维
    """

    def __init__(self, encoder, multi_head, memory, enable_four_dimensions=False):
        """
        初始化注意力中枢

        Args:
            encoder: Encoder 实例
            multi_head: MultiHeadAttention 实例
            memory: AttentionMemory 实例
            enable_four_dimensions: 是否启用四维决策框架（默认关闭）
        """
        self.encoder = encoder
        self.multi_head = multi_head
        self.memory = memory
        self._value_system = None
        self._liquidity_rescue_filter = None
        self._panic_analyzer = None
        self._rescue_orchestrator = None
        self._enable_four_dimensions = enable_four_dimensions
        self._four_dimensions = None
        if enable_four_dimensions:
            self._init_four_dimensions()

    def _init_four_dimensions(self):
        """初始化四维决策框架"""
        from .four_dimensions import FourDimensions
        self._four_dimensions = FourDimensions()

    def set_four_dimensions_enabled(self, enabled: bool):
        """
        设置是否启用四维决策框架

        Args:
            enabled: 是否启用
        """
        if enabled and not self._enable_four_dimensions:
            self._enable_four_dimensions = True
            self._init_four_dimensions()
        elif not enabled:
            self._enable_four_dimensions = False

    def is_four_dimensions_enabled(self) -> bool:
        """返回是否启用了四维决策框架"""
        return self._enable_four_dimensions

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

    def _get_scanner(self):
        """获取市场扫描器"""
        try:
            from deva.naja.radar.global_market_scanner import get_global_market_scanner
            return get_global_market_scanner()
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

        if self._enable_four_dimensions and self._four_dimensions is not None:
            return self._process_with_four_dimensions(Q, raw_events)
        else:
            return self._process_original(Q, raw_events)

    def _process_original(self, Q, raw_events):
        """
        原有逻辑，不受四维影响

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

    def _process_with_four_dimensions(self, Q, raw_events):
        """
        四维决策框架逻辑

        用四维塑造 Query，应用四维门控到最终结果。

        Args:
            Q: QueryState
            raw_events: AttentionEvent 列表

        Returns:
            attention 结果 dict（含四维状态）
        """
        macro_signal = 0.5
        if hasattr(Q, 'macro_liquidity_signal'):
            macro_signal = Q.macro_liquidity_signal

        self._four_dimensions.update(
            session_manager=self._get_session_manager(),
            portfolio=self._get_portfolio(),
            strategy_manager=self._get_strategy_manager(),
            scanner=self._get_scanner(),
            macro_signal=macro_signal
        )

        shaped_Q = self._four_dimensions.shape_query(Q)

        vs = self._get_value_system()
        events = []
        for e in raw_events:
            e.key = self.encoder.encode_key(e)
            e.value = self.encoder.encode_value(e)
            events.append(e)

            alignment = vs.calculate_alignment(e.features)
            e.features["_value_alignment"] = alignment

        result = self.multi_head.compute(shaped_Q, events)

        result = self._four_dimensions.apply_gates(result)

        for e in events:
            symbol = getattr(e, 'symbol', None) or e.source if hasattr(e, 'source') else "unknown"
            alignment = e.features.get("_value_alignment", 0.5)
            reason = vs.generate_focus_reason(e.features)
            vs.record_attention(symbol, alignment, reason)
            vs.set_last_decision_reason(reason)

            self.memory.update(e, result["confidence"])

        result["four_dimensions"] = self._four_dimensions.get_state()
        result["should_act"] = self._four_dimensions.should_act()

        return result

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