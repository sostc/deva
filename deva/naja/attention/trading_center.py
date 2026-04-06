"""
TradingCenter - 交易中枢

定位：Naja系统的协调中枢，协调各层模块完成交易决策

架构：
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TradingCenter (交易中枢)                               │
│                                                                             │
│  职责：                                                                     │
│    • 数据协调 - 接收市场数据，分发给各模块                                    │
│    • 快速决策 - 通过 AttentionOS.kernel.make_decision()                      │
│    • 慢思考融合 - 调用 FirstPrinciplesMind.think()                           │
│    • 模式匹配 - 调用 AwakenedAlaya.illuminate()                              │
│    • 决策融合 - 融合各模块输出生成最终决策                                    │
│    • 策略协调 - 协调策略执行                                                 │
│                                                                             │
│  内部模块：                                                                 │
│    • AttentionOS - 注意力计算和快速决策                                      │
│    • FirstPrinciplesMind - 因果推理                                           │
│    • AwakenedAlaya - 模式匹配/顿悟                                          │
└─────────────────────────────────────────────────────────────────────────────┘

使用方式：
    center = TradingCenter()
    decision = center.process_market_data(data)
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import threading

from .attention_os import AttentionOS, get_attention_os

log = logging.getLogger(__name__)


@dataclass
class FusionResult:
    """决策融合结果（提案完整版）"""
    final_confidence: float = 0.5
    position_adjustment: float = 0.0
    final_position: float = 0.0  # 当前仓位+调整后的最终仓位
    action_type: str = "hold"
    should_act: bool = False
    reasoning: List[str] = field(default_factory=list)
    risk_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_confidence": self.final_confidence,
            "position_adjustment": self.position_adjustment,
            "final_position": self.final_position,
            "action_type": self.action_type,
            "should_act": self.should_act,
            "reasoning": self.reasoning,
            "risk_warnings": self.risk_warnings,
        }


@dataclass
class FusionOutput:
    """融合输出"""
    should_act: bool = False
    action_type: str = "hold"
    harmony_strength: float = 0.5
    fused_confidence: float = 0.5
    insight_confidence: float = 0.5
    awakening_level: str = "dormant"

    fp_insights: List[Dict] = field(default_factory=list)
    recalled_patterns: List[Dict] = field(default_factory=list)

    manas_score: float = 0.5
    timing_score: float = 0.5
    regime_score: float = 0.0
    confidence_score: float = 0.5

    bias_state: str = "neutral"
    bias_correction: float = 1.0

    final_decision: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "should_act": self.should_act,
            "action_type": self.action_type,
            "harmony_strength": self.harmony_strength,
            "fused_confidence": self.fused_confidence,
            "insight_confidence": self.insight_confidence,
            "awakening_level": self.awakening_level,
            "fp_insights": self.fp_insights,
            "recalled_patterns": self.recalled_patterns,
            "manas_score": self.manas_score,
            "timing_score": self.timing_score,
            "regime_score": self.regime_score,
            "confidence_score": self.confidence_score,
            "bias_state": self.bias_state,
            "bias_correction": self.bias_correction,
            "final_decision": self.final_decision,
        }


class DecisionFusion:
    """
    决策融合层（提案完整版）

    融合 FirstPrinciplesMind 和 Manas 的输出，生成最终决策

    融合逻辑（提案2.2.2）：
    1. FP Mind 基础置信度 + level 加成
    2. Manas 四维调整（timing / regime / risk_temperature / bias）
    3. 最终置信度计算
    4. 行动类型确定
    5. 仓位调整
    """

    # FP Mind level 加成表
    LEVEL_BONUS = {
        "first_principles": 0.15,
        "causal": 0.08,
        "surface": 0.0,
    }

    def fuse(
        self,
        fp_insights: List[Dict],
        kernel_output,
        current_position: float = 0.0,
    ) -> FusionResult:
        """
        融合 FP Mind 和 Manas 的输出

        Args:
            fp_insights: FirstPrinciplesMind 输出的洞察列表
            kernel_output: AttentionOS Kernel 输出的 Manas 结果
            current_position: 当前仓位 [0, 1]

        Returns:
            FusionResult: 融合后的决策
        """
        reasoning = []
        risk_warnings = []

        # ========== 第一步：计算 FP Mind 基础置信度 ==========
        fp_confidence = 0.5  # 基础值

        if fp_insights:
            # 按 level 分组
            by_level: Dict[str, list] = {}
            for insight in fp_insights:
                level = insight.get("level", "surface")
                insight_type = insight.get("type", "unknown")
                confidence = insight.get("confidence", 0.5)

                if level not in by_level:
                    by_level[level] = []
                by_level[level].append({
                    "type": insight_type,
                    "confidence": confidence,
                    "content": insight.get("content", ""),
                })

            # 应用 level 加成
            for level, bonus in self.LEVEL_BONUS.items():
                if level in by_level and by_level[level]:
                    fp_confidence += bonus
                    reasoning.append(f"FP洞察({level}): +{bonus}")

            # 如果有 opportunity + first_principles 加成
            if "first_principles" in by_level:
                for insight in by_level["first_principles"]:
                    if insight["type"] == "opportunity":
                        fp_confidence += 0.05
                        reasoning.append("opportunity + first_principles: +0.05")

        # ========== 第二步：应用 Manas 四维调整 ==========

        # timing 调整
        timing = kernel_output.timing_score
        if timing < 0.4:
            fp_confidence *= 0.7
            reasoning.append(f"Manas时机低({timing:.2f}): ×0.7")
        elif timing > 0.7:
            fp_confidence *= 1.1
            reasoning.append(f"Manas时机高({timing:.2f}): ×1.1")

        # regime 调整
        regime = kernel_output.regime_score
        if regime < -0.3:  # 逆风
            fp_confidence *= 0.8
            reasoning.append(f"Manas环境逆风({regime:.2f}): ×0.8")

        # risk_temperature 调整
        risk_t = getattr(kernel_output, 'risk_temperature', 1.0)
        position_adjustment = 0.0
        if risk_t > 1.3:
            position_adjustment = -0.15
            risk_warnings.append(f"风险温度高({risk_t:.2f}): 建议减仓")
        elif risk_t > 1.5:
            position_adjustment = -0.25
            risk_warnings.append(f"风险温度很高({risk_t:.2f}): 强烈建议减仓")

        # bias 纠偏
        bias_state = getattr(kernel_output, 'bias_state', 'neutral')
        bias_correction = getattr(kernel_output, 'bias_correction', 1.0)
        if bias_state != "neutral":
            fp_confidence *= bias_correction
            reasoning.append(f"bias纠偏({bias_state}): ×{bias_correction:.2f}")

        # ========== 第三步：计算最终置信度 ==========
        final_confidence = max(0.0, min(1.0, fp_confidence))

        # ========== 第四步：确定行动类型 ==========
        if final_confidence < 0.3:
            action_type = "hold"
            should_act = False
            reasoning.append("置信度<0.3: 观望")
        elif final_confidence < 0.5:
            action_type = "act_minimally"
            should_act = True
            reasoning.append("置信度0.3-0.5: 轻仓试探")
        elif final_confidence < 0.7:
            action_type = "act_carefully"
            should_act = True
            reasoning.append("置信度0.5-0.7: 谨慎行动")
        else:
            action_type = "act_fully"
            should_act = True
            reasoning.append("置信度>0.7: 全力行动")

        # ========== 第五步：仓位调整 ==========
        # 基于 FP Mind 的洞察类型调整仓位
        if fp_insights:
            for insight in fp_insights:
                if insight.get("type") == "opportunity" and insight.get("level") == "first_principles":
                    position_adjustment += 0.20
                    reasoning.append("opportunity+first_principles: 仓位+20%")
                elif insight.get("type") == "opportunity" and insight.get("level") == "causal":
                    position_adjustment += 0.10
                    reasoning.append("opportunity+causal: 仓位+10%")
                elif insight.get("type") == "risk" and insight.get("level") == "first_principles":
                    position_adjustment -= 0.30
                    risk_warnings.append("risk+first_principles: 仓位-30%")

        # Manas 的 action_type 也影响仓位
        action_type_attr = getattr(kernel_output, 'action_type', 'hold')
        if action_type_attr == "hold":
            position_adjustment = min(position_adjustment, 0)
        elif action_type_attr == "act_fully":
            position_adjustment = max(position_adjustment, 0.10)

        # 仓位不能为负
        final_position = max(0.0, min(1.0, current_position + position_adjustment))

        return FusionResult(
            final_confidence=round(final_confidence, 3),
            position_adjustment=round(position_adjustment, 3),
            final_position=round(final_position, 3),
            action_type=action_type,
            should_act=should_act,
            reasoning=reasoning,
            risk_warnings=risk_warnings,
        )


class TradingCenter:
    """
    交易中枢

    协调 AttentionOS、FirstPrinciplesMind、AwakenedAlaya 完成交易决策
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.attention_os = get_attention_os()

        self._first_principles_mind = None
        self._awakened_alaya = None

        # 感知系统模块（从 AwakeningController 迁移）
        self._volatility_surface = None
        self._pre_taste = None
        self._prophet_sense = None
        self._realtime_taste = None

        self._awakened_state: Dict[str, Any] = {
            "fused_confidence": 0.5,
            "adaptive_decisions": 0,
            "fusion_note": "",
            "pre_taste_count": 0,
            "prophet_signals": 0,
            "taste_signals": 0,
            "volatility_signals": 0,
        }

        self._initialized = True
        log.info("[TradingCenter] 初始化完成")

    def _get_first_principles_mind(self):
        """获取 FirstPrinciplesMind"""
        if self._first_principles_mind is None:
            try:
                from deva.naja.cognition.first_principles_mind import FirstPrinciplesMind
                self._first_principles_mind = FirstPrinciplesMind()
            except ImportError as e:
                log.warning(f"[TradingCenter] 无法导入 FirstPrinciplesMind: {e}")
        return self._first_principles_mind

    def _get_awakened_alaya(self):
        """获取 AwakenedAlaya"""
        if self._awakened_alaya is None:
            try:
                from deva.naja.alaya.awakened_alaya import AwakenedAlaya
                self._awakened_alaya = AwakenedAlaya()
            except ImportError as e:
                log.warning(f"[TradingCenter] 无法导入 AwakenedAlaya: {e}")
        return self._awakened_alaya

    def _get_volatility_surface(self):
        """获取波动率曲面感知"""
        if self._volatility_surface is None:
            try:
                from deva.naja.senses import VolatilitySurfaceSense
                self._volatility_surface = VolatilitySurfaceSense()
            except ImportError as e:
                log.warning(f"[TradingCenter] 无法导入 VolatilitySurfaceSense: {e}")
        return self._volatility_surface

    def _get_pre_taste(self):
        """获取预尝味感知"""
        if self._pre_taste is None:
            try:
                from deva.naja.senses import PreTasteSense
                self._pre_taste = PreTasteSense()
            except ImportError as e:
                log.warning(f"[TradingCenter] 无法导入 PreTasteSense: {e}")
        return self._pre_taste

    def _get_prophet_sense(self):
        """获取先知感知"""
        if self._prophet_sense is None:
            try:
                from deva.naja.senses import ProphetSense
                self._prophet_sense = ProphetSense()
            except ImportError as e:
                log.warning(f"[TradingCenter] 无法导入 ProphetSense: {e}")
        return self._prophet_sense

    def _get_realtime_taste(self):
        """获取实时尝味感知"""
        if self._realtime_taste is None:
            try:
                from deva.naja.senses import RealtimeTaste
                self._realtime_taste = RealtimeTaste()
            except ImportError as e:
                log.warning(f"[TradingCenter] 无法导入 RealtimeTaste: {e}")
        return self._realtime_taste

    def _get_current_narratives(self) -> List[str]:
        """获取当前活跃的叙事列表"""
        try:
            from deva.naja.cognition.narrative import NarrativeTracker
            tracker = NarrativeTracker()
            summary = tracker.get_summary(limit=10)
            return [item["narrative"] for item in summary]
        except Exception:
            pass
        return []

    def _get_volatility_surface_state(self) -> Dict[str, Any]:
        """获取波动率曲面状态"""
        try:
            from deva.naja.senses import VolatilitySurfaceSense
            surface = VolatilitySurfaceSense()
            if surface:
                return {
                    "regime": surface.get_regime(),
                    "volatility": surface.get_volatility(),
                }
        except Exception as e:
            log.debug(f"[TradingCenter] 获取波动率曲面状态失败: {e}")
        return {"regime": "normal", "volatility": 0.5}

    def _get_awakening_level(self) -> str:
        """获取觉醒级别"""
        return self._awakened_state.get("awakening_level", "dormant")

    def _check_contradiction(self) -> Dict[str, Any]:
        """检查矛盾"""
        return {
            "has_contradiction": False,
            "description": "",
            "severity": 0.0,
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "awakening": self._awakened_state,
            "volatility_surface": self._get_volatility_surface_state(),
        }

    def get_attention_context(self) -> Dict[str, Any]:
        """获取注意力上下文"""
        return {
            "awakening_level": self._get_awakening_level(),
            "volatility_surface": self._get_volatility_surface_state(),
            "contradiction": self._check_contradiction(),
        }

    def _build_awakened_market_state(self, market_state: Dict, snapshot: Dict) -> Dict[str, Any]:
        """构建觉醒市场状态"""
        import pandas as pd
        positions = {}
        if snapshot:
            positions = snapshot.get("positions", {})

        awakened_state = {
            "timestamp": market_state.get("timestamp", 0),
            "positions": positions,
            "global_attention": market_state.get("global_attention", 0.5),
        }

        if snapshot and hasattr(snapshot, 'get') and snapshot.get('top_symbols'):
            awakened_state["top_symbols"] = snapshot.get('top_symbols', [])

        return awakened_state

    def _process_sensation_modules(self, market_state: Dict, snapshot: Dict) -> Dict:
        """
        处理感知系统模块

        从 AwakeningController 迁移，整合感知系统到决策流程
        """
        awakened_market_state = self._build_awakened_market_state(market_state, snapshot)

        # 波动率曲面
        vol_surface = self._get_volatility_surface()
        if vol_surface:
            try:
                vol_surface.process(awakened_market_state)
                self._awakened_state["volatility_signals"] += 1
            except Exception as e:
                log.debug(f"[TradingCenter] 处理波动率曲面失败: {e}")

        # 先知感知
        prophet = self._get_prophet_sense()
        if prophet:
            try:
                prophet.process(awakened_market_state)
                self._awakened_state["prophet_signals"] += 1
            except Exception as e:
                log.debug(f"[TradingCenter] 处理先知感知失败: {e}")

        # 预尝味
        pre_taste = self._get_pre_taste()
        if pre_taste:
            try:
                pre_taste.process(awakened_market_state)
                self._awakened_state["pre_taste_count"] += 1
            except Exception as e:
                log.debug(f"[TradingCenter] 处理预尝味失败: {e}")

        # 实时尝味
        realtime_taste = self._get_realtime_taste()
        if realtime_taste:
            try:
                realtime_taste.process(awakened_market_state)
                self._awakened_state["taste_signals"] += 1
            except Exception as e:
                log.debug(f"[TradingCenter] 处理实时尝味失败: {e}")

        return market_state

    def _get_volatility_surface_state(self) -> Dict[str, Any]:
        """获取波动率曲面状态"""
        vol_surface = self._get_volatility_surface()
        if vol_surface:
            try:
                return {
                    "regime": getattr(vol_surface, 'regime', 'normal'),
                    "volatility": getattr(vol_surface, 'volatility', 0.5),
                }
            except Exception:
                pass
        return {"regime": "normal", "volatility": 0.5}

    def _check_contradiction(self) -> Dict[str, Any]:
        """检查矛盾信号"""
        return {
            "has_contradiction": False,
            "description": "",
            "severity": 0.0,
        }

    def apply_pre_taste_filter(self, signals: List, data) -> List:
        """应用预尝味过滤到信号"""
        if not signals:
            return signals

        pre_taste = self._get_pre_taste()
        if pre_taste:
            try:
                for signal in signals:
                    symbol = getattr(signal, 'symbol', None) or getattr(signal, 'stock_code', None)
                    if symbol:
                        taste_result = pre_taste.judge(symbol, data)
                        if taste_result and hasattr(signal, 'metadata'):
                            signal.metadata['pre_taste'] = taste_result
            except Exception as e:
                log.debug(f"[TradingCenter] 应用预尝味过滤失败: {e}")

        return signals

    def process_market_data(
        self,
        data: Dict[str, Any],
        symbols: Optional[List[str]] = None
    ) -> FusionOutput:
        """
        处理市场数据，生成交易决策

        Args:
            data: 市场数据
            symbols: 关注的股票列表

        Returns:
            FusionOutput: 融合后的决策
        """
        market_state = data.get("market_state", {})
        snapshot = data.get("snapshot", {})

        narratives = self._get_current_narratives()
        if narratives:
            market_state["narratives"] = narratives

        # ========== 感知系统处理 ==========
        market_state = self._process_sensation_modules(market_state, snapshot)
        # =================================

        kernel_output = self.attention_os.make_decision(market_state)

        fp_mind = self._get_first_principles_mind()
        fp_insights = []
        if fp_mind and market_state:
            try:
                fp_result = fp_mind.think(market_state, snapshot)
                fp_insights = fp_result.get("insights", []) if fp_result else []
            except Exception as e:
                log.warning(f"[TradingCenter] FirstPrinciplesMind.think 失败: {e}")

        alaya = self._get_awakened_alaya()
        awakening_level = "dormant"
        recalled_patterns = []
        if alaya and market_state:
            try:
                manas_output_dict = kernel_output.to_dict() if hasattr(kernel_output, 'to_dict') else {
                    "timing_score": kernel_output.timing_score,
                    "regime_score": kernel_output.regime_score,
                    "confidence_score": kernel_output.confidence_score,
                    "risk_temperature": kernel_output.risk_temperature,
                    "portfolio_loss_pct": getattr(kernel_output, 'portfolio_loss_pct', 0.0),
                    "market_deterioration": getattr(kernel_output, 'market_deterioration', False),
                }
                alaya_result = alaya.illuminate(
                    market_data=snapshot,
                    unified_manas_output=manas_output_dict,
                    fp_insights=fp_insights
                )
                awakening_level = alaya_result.get("awakening_level", "dormant")
                recalled_patterns = alaya_result.get("recalled_patterns", [])
            except Exception as e:
                log.warning(f"[TradingCenter] AwakenedAlaya.illuminate 失败: {e}")

        fusion = self._fuse_decisions(kernel_output, fp_insights, awakening_level)
        fusion.recalled_patterns = recalled_patterns

        return fusion

    def _fuse_decisions(
        self,
        kernel_output,
        fp_insights: List[Dict],
        awakening_level: str
    ) -> FusionOutput:
        """
        融合各模块输出（使用提案完整版 DecisionFusion）

        融合流程：
        1. FP Mind 基础置信度 + level 加成
        2. Manas 四维调整（timing / regime / risk_temperature / bias）
        3. 觉醒等级加成
        4. 最终置信度 & 仓位调整
        """
        fusion = DecisionFusion()
        fusion_result = fusion.fuse(
            fp_insights=fp_insights,
            kernel_output=kernel_output,
            current_position=0.0,  # TradingCenter 不直接持有仓位，仓位由外部传入
        )

        # 觉醒等级加成
        if awakening_level == "enlightened":
            fusion_result.final_confidence *= 1.1
            fusion_result.reasoning.append(f"觉醒加成(enlightened): ×1.1")
        elif awakening_level == "illuminated":
            fusion_result.final_confidence *= 1.05
            fusion_result.reasoning.append(f"觉醒加成(illuminated): ×1.05")

        fusion_result.final_confidence = max(0.0, min(1.0, fusion_result.final_confidence))

        log.info(f"[DecisionFusion] {fusion_result.reasoning[-3:] if fusion_result.reasoning else 'no reasoning'}")

        return FusionOutput(
            should_act=fusion_result.should_act,
            action_type=fusion_result.action_type,
            harmony_strength=kernel_output.harmony_strength,
            fused_confidence=fusion_result.final_confidence,
            insight_confidence=0.5,  # 简化，DecisionFusion 已合并到 final_confidence
            awakening_level=awakening_level,
            fp_insights=fp_insights,
            manas_score=kernel_output.manas_score,
            timing_score=kernel_output.timing_score,
            regime_score=kernel_output.regime_score,
            confidence_score=kernel_output.confidence_score,
            bias_state=getattr(kernel_output, 'bias_state', 'neutral'),
            bias_correction=getattr(kernel_output, 'bias_correction', 1.0),
            final_decision=fusion_result.to_dict(),
        )

    def make_decision(
        self,
        market_state: Optional[Dict[str, Any]] = None,
        portfolio: Optional[Any] = None
    ) -> FusionOutput:
        """
        快速决策（不经过完整流程）

        用于简单决策场景
        """
        kernel_output = self.attention_os.make_decision(market_state, portfolio)

        return FusionOutput(
            should_act=kernel_output.should_act,
            action_type=kernel_output.action_type,
            harmony_strength=kernel_output.harmony_strength,
            fused_confidence=kernel_output.confidence,
            manas_score=kernel_output.manas_score,
            timing_score=kernel_output.timing_score,
            regime_score=kernel_output.regime_score,
            confidence_score=kernel_output.confidence_score,
            bias_state=kernel_output.bias_state,
            bias_correction=kernel_output.bias_correction,
        )

    def get_harmony(self) -> Dict[str, Any]:
        """获取当前和谐状态"""
        return self.attention_os.get_harmony()

    def get_attention_os(self) -> AttentionOS:
        """获取 AttentionOS"""
        return self.attention_os

    def process_datasource_data(self, datasource_id: str, data: Any) -> None:
        """
        处理数据源数据（兼容旧接口）

        Args:
            datasource_id: 数据源ID
            data: 数据
        """
        try:
            if isinstance(data, dict):
                self.attention_os.market_scheduler.schedule(data)
        except Exception as e:
            log.warning(f"[TradingCenter] process_datasource_data 失败: {e}")

    def register_datasource(self, datasource_id: str) -> None:
        """注册数据源（兼容旧接口）"""
        pass

    def unregister_datasource(self, datasource_id: str) -> None:
        """注销数据源（兼容旧接口）"""
        pass

    def get_cached_market_time(self) -> str:
        """获取缓存的市场时间（兼容旧接口）"""
        try:
            from deva.naja.radar.trading_clock import get_trading_clock
            clock = get_trading_clock()
            if clock:
                return clock.get_formatted_time()
        except Exception:
            pass
        return ""


_trading_center: Optional[TradingCenter] = None


def get_trading_center() -> TradingCenter:
    """获取 TradingCenter 单例"""
    global _trading_center
    if _trading_center is None:
        _trading_center = TradingCenter()
    return _trading_center
