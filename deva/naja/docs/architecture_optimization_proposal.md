# Naja 架构优化方案报告

> 生成日期: 2026-04-04
> 作者: AI Assistant
> 版本: v1.0

---

## 一、问题概述

经过代码分析，发现当前架构存在以下 4 个核心问题：

| # | 问题 | 严重程度 | 影响 |
|---|------|---------|------|
| 1 | narratives 和 ai_positions 数据流断裂 | 🔴 高 | FirstPrinciplesMind 无法做叙事分析 |
| 2 | Manas 四维引擎与 FirstPrinciplesMind 各自为战 | 🔴 高 | 决策依据不完整 |
| 3 | Bandit 循环和 Manas 循环关系不清 | 🟡 中 | 战术和战略脱节 |
| 4 | 四维引擎权重硬编码 | 🟡 中 | 缺乏市场适应性 |

---

## 二、问题详解与修复方案

---

### 问题 1：narratives 和 ai_positions 数据流断裂

#### 2.1.1 问题分析

在 `center.py` 的 `_get_cognition_context()` 方法中：

```python
def _get_cognition_context(self) -> Dict[str, Any]:
    context = {
        "narratives": [],           # ← 始终为空
        "ai_positions": {},         # ← 始终为空
        "ai_compute_trend": None,  # ← 正常获取
        ...
    }
```

**根本原因**：
- `narratives` 应该从 `NarrativeTracker.get_summary()` 获取，但代码中没有实现
- `ai_positions` 应该从 `VirtualPortfolio` 或 `PortfolioManager` 获取，但代码中没有实现

**影响范围**：
- `FirstPrinciplesMind.think()` 收到的 `narratives` 参数始终为空列表
- AI 持仓盈亏分析功能完全失效

#### 2.1.2 修复方案

**修改文件**: `deva/naja/attention/center.py`

**修改位置**: `_get_cognition_context()` 方法（约 L1577）

**修改内容**:

```python
def _get_cognition_context(self) -> Dict[str, Any]:
    context = {
        "narratives": [],
        "ai_positions": {},
        "ai_compute_trend": None,
        # ... 其他字段
    }

    # ========== NarrativeTracker 获取 narratives ==========
    try:
        from deva.naja.cognition import get_narrative_tracker
        tracker = get_narrative_tracker()
        summary = tracker.get_summary(limit=10)
        if summary:
            # 转换为 FirstPrinciplesMind 需要的格式
            context["narratives"] = [
                {
                    "narrative": s["narrative"],
                    "stage": s.get("stage", "unknown"),
                    "attention_score": s.get("attention_score", 0.5),
                    "trend": s.get("trend", 0),
                    "keywords": s.get("keywords", []),
                }
                for s in summary
            ]
    except Exception as e:
        log.debug(f"[Cognition] 获取 narratives 失败: {e}")

    # ========== 获取 AI 持仓信息 ==========
    try:
        from deva.naja.bandit.portfolio_manager import get_portfolio_manager
        spark = get_portfolio_manager()
        open_positions = spark.get_open_positions()

        ai_related_keywords = ["NVDA", "AMD", "TSLA", "AI", "GPU", "H100", "A100"]

        ai_positions = {}
        for pos in open_positions:
            # 检查是否AI相关股票
            symbol = pos.symbol.upper()
            if any(kw in symbol for kw in ai_related_keywords):
                ai_positions[symbol] = {
                    "return_pct": pos.profit_loss / (pos.entry_price * pos.quantity) * 100,
                    "profit_loss": pos.profit_loss,
                    "weight": pos.market_value / spark.get_summary()["total_market_value"] if spark.get_summary()["total_market_value"] > 0 else 0,
                    "days_held": (time.time() - pos.entry_time) / 86400 if pos.entry_time else 0,
                }

        context["ai_positions"] = ai_positions
    except Exception as e:
        log.debug(f"[Cognition] 获取 AI 持仓失败: {e}")

    return context
```

#### 2.1.3 验证方法

```python
# 在 center.py 中添加调试日志
context = self._get_cognition_context()
log.info(f"[Cognition] narratives count: {len(context.get('narratives', []))}")
log.info(f"[Cognition] ai_positions: {context.get('ai_positions', {})}")
```

---

### 问题 2：Manas 四维引擎与 FirstPrinciplesMind 各自为战

#### 2.2.1 问题分析

**当前架构**:

```
FirstPrinciplesMind.think()
    └── 输出: fp_insights (opportunity/risk + level + confidence)

UnifiedManas.compute()
    └── 输出: timing_score, regime_score, confidence_score, risk_temperature
```

**问题**:
1. 两者的输出**独立计算**，没有交互
2. `FirstPrinciplesInsights` 的 `confidence` 没有被 `Manas` 的 `confidence_score` 校准
3. `FirstPrinciplesInsights` 中的 `opportunity/risk` 没有被 `Manas` 的 `timing/regime` 调整
4. 最终决策时不知道如何融合两者的输出

#### 2.2.2 修复方案：新增决策融合层

**新建文件**: `deva/naja/cognition/decision_fusion.py`

```python
"""
Decision Fusion Layer - 决策融合层

融合 FirstPrinciplesMind 和 Manas 四维引擎的输出，
生成最终的交易决策置信度和仓位建议
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from deva.naja.manas.output import UnifiedManasOutput

@dataclass
class FusionResult:
    """融合结果"""
    final_confidence: float          # 最终置信度 [0, 1]
    position_adjustment: float        # 仓位调整 [-0.3, +0.3]
    action_type: str                 # hold / act_fully / act_carefully / act_minimally
    should_act: bool                 # 是否应该行动
    reasoning: List[str]             # 推理过程
    risk_warnings: List[str]         # 风险警告

class DecisionFusion:
    """
    决策融合器

    融合策略：
    1. FP Mind 的 first_principles 洞察 → 基础置信度 +0.15
    2. FP Mind 的 causal 洞察 → 基础置信度 +0.10
    3. FP Mind 的 pattern 洞察 → 基础置信度 +0.05
    4. Manas timing_score < 0.4 → 降低行动概率
    5. Manas risk_temperature > 1.3 → 降低仓位
    6. Manas bias_state != NEUTRAL → 应用纠偏
    """

    # Manas 分数到置信度的映射
    MANAS_WEIGHT = 0.3
    FP_MIND_WEIGHT = 0.7

    # FP Mind level 到置信度的加成
    LEVEL_BONUS = {
        "first_principles": 0.15,
        "causal": 0.10,
        "pattern": 0.05,
        "surface": 0.0,
    }

    def fuse(
        self,
        fp_insights: List[Dict[str, Any]],
        manas_output: UnifiedManasOutput,
        current_position: float = 0.0,
    ) -> FusionResult:
        """
        融合 FP Mind 和 Manas 的输出

        Args:
            fp_insights: FirstPrinciplesMind 输出的洞察列表
            manas_output: UnifiedManas 输出的决策
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
            by_level = {}
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

            # 如果有 opportunity 和 first_principles 加成
            if "first_principles" in by_level:
                for insight in by_level["first_principles"]:
                    if insight["type"] == "opportunity":
                        fp_confidence += 0.05
                        reasoning.append("opportunity + first_principles: +0.05")

        # ========== 第二步：应用 Manas 四维调整 ==========

        # timing 调整
        timing = manas_output.timing_score
        if timing < 0.4:
            fp_confidence *= 0.7
            reasoning.append(f"Manas时机低({timing:.2f}): ×0.7")
        elif timing > 0.7:
            fp_confidence *= 1.1
            reasoning.append(f"Manas时机高({timing:.2f}): ×1.1")

        # regime 调整
        regime = manas_output.regime_score
        if regime < -0.3:  # 逆风
            fp_confidence *= 0.8
            reasoning.append(f"Manas环境逆风({regime:.2f}): ×0.8")

        # risk_temperature 调整
        risk_t = manas_output.risk_temperature
        position_adjustment = 0.0
        if risk_t > 1.3:
            position_adjustment = -0.15
            risk_warnings.append(f"风险温度高({risk_t:.2f}): 建议减仓")
        elif risk_t > 1.5:
            position_adjustment = -0.25
            risk_warnings.append(f"风险温度很高({risk_t:.2f}): 强烈建议减仓")

        # bias 纠偏
        if manas_output.bias_state.value != "neutral":
            correction = manas_output.bias_correction
            fp_confidence *= correction
            reasoning.append(f"bias纠偏({manas_output.bias_state.value}): ×{correction:.2f}")

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
        if manas_output.action_type.value == "hold":
            position_adjustment = min(position_adjustment, 0)
        elif manas_output.action_type.value == "act_fully":
            position_adjustment = max(position_adjustment, 0.10)

        # 仓位不能为负
        final_position = max(0.0, min(1.0, current_position + position_adjustment))

        return FusionResult(
            final_confidence=round(final_confidence, 3),
            position_adjustment=round(position_adjustment, 3),
            action_type=action_type,
            should_act=should_act,
            reasoning=reasoning,
            risk_warnings=risk_warnings,
        )
```

#### 2.2.3 修改 center.py 使用融合层

**修改文件**: `deva/naja/attention/center.py`

**新增导入**:
```python
from deva.naja.cognition.decision_fusion import DecisionFusion, FusionResult
```

**修改 `_awakened_think()` 方法**（约 L1140）:

```python
def _awakened_think(self, market_state: Dict[str, Any], session_manager=None):
    # ... 现有的 FP Mind 调用 ...

    fp_result = self._first_principles_mind.think(...)
    manas_output = self._unified_manas.compute(
        session_manager=session_manager,
        portfolio_data=portfolio_data,
        scanner=self._scanner,
        bandit_tracker=self._bandit_tracker,
        macro_signal=macro_signal,
        market_state=market_state,
    )

    # ========== 新增：决策融合 ==========
    fusion = DecisionFusion()
    fusion_result = fusion.fuse(
        fp_insights=fp_result.get("insights", []),
        manas_output=manas_output,
        current_position=current_position_pct,
    )

    log.info(f"[Decision] 融合结果: confidence={fusion_result.final_confidence}, "
             f"action={fusion_result.action_type}, adjustment={fusion_result.position_adjustment}")

    return {
        "fp_insights": fp_result,
        "manas_output": manas_output.to_dict(),
        "fusion": {
            "final_confidence": fusion_result.final_confidence,
            "position_adjustment": fusion_result.position_adjustment,
            "action_type": fusion_result.action_type,
            "should_act": fusion_result.should_act,
            "reasoning": fusion_result.reasoning,
            "risk_warnings": fusion_result.risk_warnings,
        }
    }
```

---

### 问题 3：Bandit 循环和 Manas 循环关系不清

#### 2.3.1 问题分析

**当前架构**:

```
Bandit 自适应循环:
SignalListener → VirtualPortfolio → MarketDataObserver → 止盈止损 → 平仓 → Bandit更新 → 策略优化

Manas 四维引擎:
UnifiedManas.compute() → timing_score, regime_score, confidence_score, risk_temperature
```

**问题**:
1. Bandit 的止盈止损是**固定值**（+15% / -8%），不考虑市场环境
2. Bandit 的策略参数调整没有利用 Manas 的风险评估
3. 两者都是独立运行，没有信息交换

#### 2.3.2 修复方案：让 Bandit 使用 Manas 的风险评估

**修改文件**: `deva/naja/bandit/adaptive_cycle.py`

**新增方法**:

```python
class AdaptiveCycle:
    def __init__(self):
        # ... 现有代码 ...
        self._manas_output_cache = None
        self._last_manas_update = 0
        self._manas_update_interval = 60  # 每60秒更新一次 Manas

    def _get_manas_risk_context(self) -> Dict[str, Any]:
        """
        获取 Manas 的风险上下文，用于调整止盈止损

        Returns:
            {
                "risk_temperature": float,
                "timing_score": float,
                "regime_score": float,
                "bias_state": str,
            }
        """
        current_time = time.time()

        # 缓存机制，避免频繁调用
        if (current_time - self._last_manas_update < self._manas_update_interval
                and self._manas_output_cache is not None):
            return self._manas_output_cache

        try:
            from deva.naja.manas.unified_manas import get_unified_manas
            manas = get_unified_manas()

            scanner = getattr(self, '_scanner', None)
            session_manager = getattr(self, '_session_manager', None)

            output = manas.compute(
                session_manager=session_manager,
                portfolio_data=self._get_portfolio_data(),
                scanner=scanner,
                bandit_tracker=self._tracker,
                macro_signal=0.5,
                market_state=None,
            )

            self._manas_output_cache = {
                "risk_temperature": output.risk_temperature,
                "timing_score": output.timing_score,
                "regime_score": output.regime_score,
                "bias_state": output.bias_state.value,
                "confidence_score": output.confidence_score,
            }
            self._last_manas_update = current_time

            return self._manas_output_cache
        except Exception as e:
            log.warning(f"[AdaptiveCycle] 获取 Manas 上下文失败: {e}")
            return {
                "risk_temperature": 1.0,
                "timing_score": 0.5,
                "regime_score": 0.0,
                "bias_state": "neutral",
                "confidence_score": 0.5,
            }

    def _get_adaptive_stop_loss(self, base_return_pct: float) -> tuple[float, float]:
        """
        根据 Manas 风险上下文获取自适应止盈止损

        Args:
            base_return_pct: 持仓当前收益率

        Returns:
            (stop_loss_pct, take_profit_pct)
        """
        manas_context = self._get_manas_risk_context()
        risk_t = manas_context["risk_temperature"]
        timing = manas_context["timing_score"]

        # 基础止盈止损
        base_stop_loss = -8.0
        base_take_profit = 15.0

        # 根据风险温度调整
        if risk_t > 1.3:
            # 高风险环境：更严格的止损，更低的止盈
            stop_loss = base_stop_loss * 0.6  # -4.8%
            take_profit = base_take_profit * 0.8  # 12%
            log.info(f"[AdaptiveCycle] 高风险环境: stop_loss={stop_loss}%, take_profit={take_profit}%")
        elif risk_t > 1.5:
            # 极高风险：保守策略
            stop_loss = base_stop_loss * 0.4  # -3.2%
            take_profit = base_take_profit * 0.6  # 9%
            log.warning(f"[AdaptiveCycle] 极高风险环境: stop_loss={stop_loss}%, take_profit={take_profit}%")
        elif timing < 0.4:
            # 时机不佳：观望
            stop_loss = base_stop_loss * 1.5  # -12%
            take_profit = base_take_profit * 0.7  # 10.5%
            log.info(f"[AdaptiveCycle] 时机不佳: stop_loss={stop_loss}%, take_profit={take_profit}%")
        else:
            # 正常环境
            stop_loss = base_stop_loss
            take_profit = base_take_profit

        # 如果持仓已经盈利，可以适当放宽止损
        if base_return_pct > 5.0:
            stop_loss = max(stop_loss, -10.0)  # 不超过 -10%

        return stop_loss, take_profit

    def _get_portfolio_data(self) -> Dict[str, Any]:
        """获取组合数据用于 Manas 计算"""
        try:
            positions = self._portfolio.get_all_positions(status="OPEN")
            if not positions:
                return {}

            total_value = sum(p.market_value for p in positions)
            total_cost = sum(p.entry_price * p.quantity for p in positions)
            total_return = (total_value - total_cost) / total_cost if total_cost > 0 else 0

            return {
                "held_symbols": [p.stock_code for p in positions],
                "total_return": total_return,
                "profit_loss": total_value - total_cost,
                "cash_ratio": 0.3,  # 假设30%现金
                "concentration": max(p.market_value / total_value for p in positions) if positions else 0,
            }
        except:
            return {}
```

**修改止盈止损检查逻辑**:

```python
# 在检查持仓状态时使用自适应止盈止损
def _check_position_exit(self, position):
    current_return = position.return_pct
    stop_loss, take_profit = self._get_adaptive_stop_loss(current_return)

    # 现有平仓逻辑...

    # 如果触发 Manas 风险警告，优先考虑减仓
    manas_context = self._get_manas_risk_context()
    if manas_context["risk_temperature"] > 1.5 and current_return > 0:
        log.warning(f"[AdaptiveCycle] 高风险环境+盈利，考虑止盈")
        return "take_profit"
```

---

### 问题 4：四维引擎权重硬编码

#### 2.4.1 问题分析

在 `unified_manas.py` 中：

```python
# TimingEngine
timing = time_pressure * 0.4 + volatility * 0.25 + density * 0.2 + structure * 0.15

# RegimeEngine
regime = trend * 0.4 + liquidity * 0.35 + diffusion * 0.25
```

**问题**:
- 这些权重是固定的经验值
- 在高波动市场中，时机比趋势更重要
- 在低波动市场中，趋势和流动性更重要
- 当前没有根据市场状态自适应调整

#### 2.4.2 修复方案：四维引擎权重自适应

**修改文件**: `deva/naja/manas/unified_manas.py`

**新增自适应权重机制**:

```python
class AdaptiveWeights:
    """
    自适应权重计算器

    根据当前市场状态动态调整四维引擎的权重
    """

    def __init__(self):
        self._volatility_history: List[float] = []
        self._trend_history: List[float] = []

    def get_timing_weights(self, scanner=None) -> Dict[str, float]:
        """
        获取 TimingEngine 的自适应权重

        Returns:
            {component_name: weight}
        """
        weights = {
            "time_pressure": 0.4,
            "volatility": 0.25,
            "density": 0.2,
            "structure": 0.15,
        }

        if scanner is None:
            return weights

        try:
            vol = scanner.get_market_volatility()
            if vol:
                self._volatility_history.append(vol)
                if len(self._volatility_history) > 20:
                    self._volatility_history.pop(0)

                if len(self._volatility_history) >= 5:
                    recent_avg = sum(self._volatility_history[-5:]) / 5
                    current_vol = recent_avg[-1]

                    # 高波动环境：更注重时机和结构
                    if current_vol > recent_avg * 1.3:
                        weights = {
                            "time_pressure": 0.35,
                            "volatility": 0.35,  # 提高波动率权重
                            "density": 0.15,
                            "structure": 0.15,
                        }
                    # 低波动环境：更注重交易密度
                    elif current_vol < recent_avg * 0.7:
                        weights = {
                            "time_pressure": 0.3,
                            "volatility": 0.15,
                            "density": 0.35,  # 提高密度权重
                            "structure": 0.2,
                        }
        except:
            pass

        return weights

    def get_regime_weights(self, scanner=None) -> Dict[str, float]:
        """
        获取 RegimeEngine 的自适应权重

        Returns:
            {component_name: weight}
        """
        weights = {
            "trend": 0.4,
            "liquidity": 0.35,
            "diffusion": 0.25,
        }

        if scanner is None:
            return weights

        try:
            summary = scanner.get_market_summary()
            phase = summary.get('us_trading_phase', 'closed')

            # 美股交易时段：更注重趋势
            if phase == 'trading':
                weights = {
                    "trend": 0.5,
                    "liquidity": 0.3,
                    "diffusion": 0.2,
                }
            # 美股盘前/盘后：更注重流动性
            elif phase in ('pre_market', 'after_hours'):
                weights = {
                    "trend": 0.25,
                    "liquidity": 0.5,
                    "diffusion": 0.25,
                }
        except:
            pass

        return weights


class TimingEngine:
    def __init__(self):
        # ... 现有代码 ...
        self._adaptive_weights = AdaptiveWeights()

    def compute(self, session_manager=None, scanner=None) -> float:
        weights = self._adaptive_weights.get_timing_weights(scanner)

        time_pressure = self._get_time_pressure(session_manager)
        volatility = self._get_volatility_regime(scanner)
        density = self._get_trade_density(scanner)
        structure = self._get_structure_break(scanner)

        timing = (
            time_pressure * weights["time_pressure"] +
            volatility * weights["volatility"] +
            density * weights["density"] +
            structure * weights["structure"]
        )

        return max(0.0, min(1.0, timing))


class RegimeEngine:
    def __init__(self):
        # ... 现有代码 ...
        self._adaptive_weights = AdaptiveWeights()

    def compute(self, scanner=None, macro_signal: float = 0.5) -> float:
        weights = self._adaptive_weights.get_regime_weights(scanner)

        trend = self._get_index_trend(scanner)
        liquidity = self._get_liquidity_signal(scanner, macro_signal)
        diffusion = self._get_sector_diffusion(scanner)

        regime = (
            trend * weights["trend"] +
            liquidity * weights["liquidity"] +
            diffusion * weights["diffusion"]
        )

        return regime  # 可以是负值
```

---

## 三、实施计划

### 优先级排序

| 优先级 | 问题 | 预计工作量 | 风险 |
|-------|------|----------|------|
| P0 | 问题1：narratives 数据流 | 2小时 | 低 |
| P0 | 问题2：决策融合层 | 4小时 | 中 |
| P1 | 问题3：Bandit+Manas 整合 | 3小时 | 中 |
| P2 | 问题4：自适应权重 | 2小时 | 低 |

### 实施步骤

#### Phase 1: 修复数据流（P0）
1. 修改 `center.py` 的 `_get_cognition_context()`
2. 添加 NarrativeTracker 集成
3. 添加 PortfolioManager 集成
4. 添加调试日志验证

#### Phase 2: 新增决策融合层（P0）
1. 创建 `decision_fusion.py`
2. 实现 `DecisionFusion` 类
3. 修改 `center.py` 使用融合层
4. 添加单元测试

#### Phase 3: Bandit+Manas 整合（P1）
1. 修改 `adaptive_cycle.py`
2. 添加 `_get_manas_risk_context()` 方法
3. 修改止盈止损逻辑
4. 验证自适应止盈止损

#### Phase 4: 自适应权重（P2）
1. 创建 `AdaptiveWeights` 类
2. 修改 `TimingEngine` 和 `RegimeEngine`
3. 添加市场状态检测
4. 验证权重调整

---

## 四、预期效果

| 指标 | 当前状态 | 优化后预期 |
|------|---------|-----------|
| narratives 接入率 | 0% | 100% |
| AI 持仓盈亏分析 | 失效 | 正常运作 |
| FP Mind + Manas 融合 | 无 | 完全融合 |
| 止盈止损适应性 | 固定值 | 随市场调整 |
| 四维引擎适应性 | 固定权重 | 自适应权重 |

---

## 五、风险与注意事项

1. **决策融合层**的权重系数需要根据实际交易结果调优
2. **自适应止盈止损**可能需要回测验证效果
3. **Manas 调用频率**需要控制，避免性能问题
4. 所有修改应该**向后兼容**，保留现有接口

---

## 六、附录

### A. 相关文件列表

```
deva/naja/attention/center.py           # 主要修改文件
deva/naja/cognition/narrative_tracker.py  # NarrativeTracker
deva/naja/bandit/adaptive_cycle.py       # Bandit 循环
deva/naja/bandit/virtual_portfolio.py    # 虚拟持仓
deva/naja/bandit/portfolio_manager.py    # 实盘持仓
deva/naja/manas/unified_manas.py          # Manas 四维引擎
deva/naja/cognition/decision_fusion.py  # 新建：决策融合层
```

### B. 关键接口

```python
# NarrativeTracker
def get_summary(limit: int = 10) -> List[Dict[str, Any]]

# UnifiedManas
def compute(
    session_manager=None,
    portfolio_data: Optional[Dict[str, Any]] = None,
    scanner=None,
    bandit_tracker=None,
    macro_signal: float = 0.5,
    market_state: Optional[Dict[str, Any]] = None,
) -> UnifiedManasOutput

# VirtualPortfolio
def get_all_positions(status: Optional[str] = None) -> List[VirtualPosition]
```
