from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from .fusion import DecisionFusion, FusionOutput


class DecisionOrchestrator:
    """Application-layer decision workflow extracted from TradingCenter."""

    def __init__(
        self,
        *,
        attention_os,
        awakened_state: Dict[str, Any],
        get_first_principles_mind: Callable[[], Any],
        get_awakened_alaya: Callable[[], Any],
        get_in_context_learner: Callable[[], Any],
        get_volatility_surface: Callable[[], Any],
        get_pre_taste: Callable[[], Any],
        get_prophet_sense: Callable[[], Any],
        get_realtime_taste: Callable[[], Any],
        logger: Optional[logging.Logger] = None,
    ):
        self.attention_os = attention_os
        self.awakened_state = awakened_state
        self.get_first_principles_mind = get_first_principles_mind
        self.get_awakened_alaya = get_awakened_alaya
        self.get_in_context_learner = get_in_context_learner
        self.get_volatility_surface = get_volatility_surface
        self.get_pre_taste = get_pre_taste
        self.get_prophet_sense = get_prophet_sense
        self.get_realtime_taste = get_realtime_taste
        self.log = logger or logging.getLogger(__name__)

    def run_full_pipeline(
        self,
        market_state: Dict[str, Any],
        snapshot: Optional[Dict] = None,
    ) -> FusionOutput:
        market_state = self._process_sensation_modules(market_state, snapshot)
        kernel_output = self.attention_os.make_decision(market_state)

        fp_mind = self.get_first_principles_mind()
        fp_insights = []
        if fp_mind and market_state:
            try:
                fp_result = fp_mind.think(market_state, snapshot)
                fp_insights = fp_result.get("insights", []) if fp_result else []
            except Exception as e:
                self.log.warning(f"[DecisionOrchestrator] FirstPrinciplesMind.think 失败: {e}")

        alaya = self.get_awakened_alaya()
        awakening_level = "dormant"
        recalled_patterns = []
        if alaya and market_state:
            try:
                manas_output_dict = kernel_output.to_dict() if hasattr(kernel_output, "to_dict") else {
                    "timing_score": kernel_output.timing_score,
                    "regime_score": kernel_output.regime_score,
                    "confidence_score": kernel_output.confidence_score,
                    "risk_temperature": kernel_output.risk_temperature,
                    "portfolio_loss_pct": getattr(kernel_output, "portfolio_loss_pct", 0.0),
                    "market_deterioration": getattr(kernel_output, "market_deterioration", False),
                }
                alaya_result = alaya.illuminate(
                    market_data=snapshot or {},
                    unified_manas_output=manas_output_dict,
                    fp_insights=fp_insights,
                )
                awakening_level = alaya_result.get("awakening_level", "dormant")
                recalled_patterns = alaya_result.get("recalled_patterns", [])
            except Exception as e:
                self.log.warning(f"[DecisionOrchestrator] AwakenedAlaya.illuminate 失败: {e}")

        fusion = self.fuse_decisions(
            kernel_output=kernel_output,
            fp_insights=fp_insights,
            awakening_level=awakening_level,
        )
        fusion.recalled_patterns = recalled_patterns
        return fusion

    def fuse_decisions(self, kernel_output, fp_insights: List[Dict], awakening_level: str) -> FusionOutput:
        fusion = DecisionFusion()
        fusion_result = fusion.fuse(
            fp_insights=fp_insights,
            kernel_output=kernel_output,
            current_position=0.0,
        )

        if awakening_level == "enlightened":
            fusion_result.final_confidence *= 1.1
            fusion_result.reasoning.append("觉醒加成(enlightened): ×1.1")
        elif awakening_level == "illuminated":
            fusion_result.final_confidence *= 1.05
            fusion_result.reasoning.append("觉醒加成(illuminated): ×1.05")

        try:
            learner = self.get_in_context_learner()
            if learner:
                market_features = []
                if hasattr(kernel_output, "attention_weights"):
                    for symbol, weight in kernel_output.attention_weights.items():
                        market_features.append({"symbol": symbol, "weight": weight})

                class MockQueryState:
                    def __init__(self):
                        self.features = {}

                _, adjustment_info = learner.adjust_query_with_demos(MockQueryState(), market_features)
                if adjustment_info:
                    historical_success = adjustment_info.get("historical_success", 0)
                    if historical_success > 0.1:
                        factor = 1.0 + historical_success * 0.1
                        fusion_result.final_confidence *= factor
                        fusion_result.reasoning.append(f"上下文学习加成(历史成功): ×{factor:.2f}")
                    if adjustment_info.get("num_demos", 0) > 1:
                        fusion_result.final_confidence *= 1.05
                        fusion_result.reasoning.append("上下文学习加成(多示范): ×1.05")
        except Exception as e:
            self.log.debug(f"[DecisionOrchestrator] 应用上下文学习失败: {e}")

        fusion_result.final_confidence = max(0.0, min(1.0, fusion_result.final_confidence))
        self.log.info(f"[DecisionFusion] {fusion_result.reasoning[-3:] if fusion_result.reasoning else 'no reasoning'}")

        return FusionOutput(
            should_act=fusion_result.should_act,
            action_type=fusion_result.action_type,
            harmony_strength=kernel_output.harmony_strength,
            fused_confidence=fusion_result.final_confidence,
            insight_confidence=0.5,
            awakening_level=awakening_level,
            fp_insights=fp_insights,
            manas_score=kernel_output.manas_score,
            timing_score=kernel_output.timing_score,
            regime_score=kernel_output.regime_score,
            confidence_score=kernel_output.confidence_score,
            bias_state=getattr(kernel_output, "bias_state", "neutral"),
            bias_correction=getattr(kernel_output, "bias_correction", 1.0),
            final_decision=fusion_result.to_dict(),
        )

    def _build_awakened_market_state(self, market_state: Dict, snapshot: Dict) -> Dict[str, Any]:
        positions = {}
        if snapshot:
            positions = snapshot.get("positions", {})

        awakened_state = {
            "timestamp": market_state.get("timestamp", 0),
            "positions": positions,
            "global_attention": market_state.get("global_attention", 0.5),
        }
        if snapshot and hasattr(snapshot, "get") and snapshot.get("top_symbols"):
            awakened_state["top_symbols"] = snapshot.get("top_symbols", [])
        return awakened_state

    def _process_sensation_modules(self, market_state: Dict, snapshot: Dict) -> Dict:
        awakened_market_state = self._build_awakened_market_state(market_state, snapshot)
        snapshot_symbol = snapshot.get("symbol") if snapshot else None

        volatility_surface = self.get_volatility_surface()
        if volatility_surface:
            try:
                volatility_surface.sense(awakened_market_state)
                self.awakened_state["volatility_signals"] += 1
            except Exception as e:
                self.log.debug(f"[DecisionOrchestrator] 处理波动率曲面失败: {e}")

        prophet_sense = self.get_prophet_sense()
        if prophet_sense:
            try:
                prophet_sense.sense(
                    market_data=awakened_market_state,
                    flow_data=None,
                    options_data=None,
                    narrative_data={"narratives": market_state.get("narratives", [])}
                )
                self.awakened_state["prophet_signals"] += 1
            except Exception as e:
                self.log.debug(f"[DecisionOrchestrator] 处理先知感知失败: {e}")

        pre_taste = self.get_pre_taste()
        if pre_taste and snapshot_symbol:
            try:
                pre_taste.pre_taste(snapshot_symbol, awakened_market_state)
                self.awakened_state["pre_taste_count"] += 1
            except Exception as e:
                self.log.debug(f"[DecisionOrchestrator] 处理预尝味失败: {e}")

        realtime_taste = self.get_realtime_taste()
        if realtime_taste and snapshot_symbol:
            try:
                current_price = snapshot.get("price") if snapshot else None
                if current_price:
                    realtime_taste.taste_position(snapshot_symbol, current_price)
                self.awakened_state["taste_signals"] += 1
            except Exception as e:
                self.log.debug(f"[DecisionOrchestrator] 处理实时尝味失败: {e}")

        return market_state
