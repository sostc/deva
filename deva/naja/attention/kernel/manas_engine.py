"""
ManasEngine - 末那识引擎

🧠 定位：天-地-人框架中的「人」
    - 「人」= 决策中枢
    - 回答：「我该怎么做？」
    - 感知天（时机）和地（题材）的变化后做出决策

一个持续输出"是否行动"的内在决策中枢

核心职责：
    • 要不要看（注意力方向 Q）
    • 要不要信（置信度 α）
    • 要不要上（仓位 T）
    • 要不要停（风险）

================================================================================
🌌 天-地-人 框架
================================================================================

ManasEngine（人）
    │
    ├── 感知「天」（TimingNarrative）
    │       时机成熟度 → timing_score
    │       现在是不是该动的时候？
    │
    ├── 感知「地」（BlockNarrative）
    │       题材状态 → spatial_score
    │       我关心的主题现在怎么样了？
    │
    └── 综合判断 → manas_score → 交易决策

================================================================================
内部架构（4引擎 + 1观照层）
================================================================================

ManasEngine
    ├── TimingEngine（时机节律）  ← 天时
    │       判断"现在能不能动"
    │       视角：微观时机
    │
    ├── RegimeEngine（环境感）  ← 地利
    │       判断"最近大方向顺不顺"
    │       视角：宏观环境
    │
    ├── ConfidenceEngine（自信）  ← 自知
    │       判断"我的策略还管用吗"
    │       视角：策略适配度
    │
    ├── RiskEngine（风险）  ← 生存本能
    │       判断"还能承受多少波动"
    │       视角：客观风险（市场杀的）
    │
    ├── MetaManas（观照层）  ← 觉知偏差
    │       判断"我自己会不会犯错"
    │       视角：主观偏差（自己作的）

各引擎视角总结：
┌──────────────────┬────────────────┬─────────────────┐
│ 引擎             │ 看的角度        │ 简单理解         │
├──────────────────┼────────────────┼─────────────────┤
│ TimingEngine     │ 微观时机        │ 现在能动手吗？   │
│ RegimeEngine     │ 宏观环境        │ 大方向顺吗？     │
│ ConfidenceEngine │ 策略适配度      │ 策略还管用吗？   │
│ RiskEngine       │ 客观风险        │ 市场能杀我多少？ │
│ MetaManas        │ 主观偏差        │ 我自己会作死吗？ │
└──────────────────┴────────────────┴─────────────────┘

================================================================================
公式
================================================================================

【核心指标】harmony_strength
    compute() 组装输出时的 manas_score 字段就是 harmony_strength（同一数值）。

（下列所有数值都是 ManasConfig 的默认值，实际取值以传入的 config 为准）

1) 基础融合（加权和）
    harmony_strength = weight_timing     * timing
                     + weight_risk       * risk_safety
                     + weight_confidence * confidence

      timing      = TimingEngine.compute()                 ∈ [0,1]
      risk_safety = 1 - min(risk_temperature, 1.5) / 1.5   ← RiskEngine 温度的「反函数」
      confidence  = ConfidenceEngine.compute()             ∈ [0,1]

    当前权重 = 0.4 / 0.35 / 0.25
    ⚠️ 第三项是 risk（风险温度的反函数），**不是** regime；
       regime 在下一步以乘性折扣的方式参与。

2) 乘性调节（按 compute() 中的先后顺序依次作用，每步后 clamp 到 [0,1]）
    • regime      harmony *= 0.7 + ((regime + 1) / 2) * 0.3        # 折扣区间 [0.7, 1.0]
    • narrative   narrative_risk > 0.6 → harmony *= 1 - (risk - 0.6) * 0.5
    • ai_compute  trend == "up" 且 strength > 0.6 →
                  harmony *= 1 + (strength - 0.6) * 0.3            # 最多 +12%
    • resonance   score >= 0.7 时按 sentiment 定向：
                  >= 0.2 → 加成（最多 +10%）；<= -0.2 → 惩罚（最多 -8%）
    • awakening   enlightened ×1.15 / illuminated ×1.10 / awakening ×1.05
    • bias        harmony *= MetaManas 的 bias_correction
                  （贪 0.7 / 惧 首次 0.5、稳态 0.8 / 中性 1.0）

3) 派生量
    • Action Gate : action_type = _determine_action_type(...)
                    should_act  = (action_type != ActionType.HOLD)
                    ⚠️ 分数门槛不是唯一通道：共振 + 强时机可直接判 ACT_FULLY
                       （即 should_act 为真时，分数仍可能低于 ACTION_THRESHOLD）
    • α = clamp(confidence * harmony_strength, alpha_min, alpha_max)
                    ⚠️ bias_correction 已在第 2 步作用于 harmony_strength，
                       这里**不再**重复相乘（否则纠偏系数被平方）
    • T = RiskEngine.compute() 独立算出：
              base_T = 1.0 + (1 - cash_ratio) * 0.5
              回撤   > 0.1 → ×1.3 ；> 0.05 → ×1.1
              波动率 > 2.0 → ×1.2 ；> 1.5  → ×1.1
              最终 clamp 到 [0.5, 2.0]
      ⚠️ T 只由现金比/回撤/波动率决定，与 harmony_strength(manas_score) **无关**。
         不要按 "T = base_T / (1 + manas_score)" 理解——那是早期设计，从未实现。

偏差纠偏（MetaManas）：
    • 连赢 → bias_correction 降到 0.7 → α 随之下降 → 防贪
    • 连亏 → bias_correction 降到 0.5（稳态 0.8）→ 防惧
    ⚠️ MetaManas 只返回 bias_correction 乘子，不改写 T；
       "increase T / moderate T" 是设计意图，当前实现未落地。

================================================================================
事件驱动（新架构）
================================================================================

ManasEngine 订阅 NajaEventBus，感知认知层变化：
    - BLOCK_NARRATIVE_UPDATE（地）：我们关注的题材更新了
    - RESONANCE_DETECTED（共振）：天-地共振事件
    - TIMING_NARRATIVE_UPDATE（天）：时机状态变化了

收到事件后 → _invalidate_cache() → 下次 compute() 会重新计算
"""

import time
import logging
from typing import Callable, Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

from deva.naja.attention.kernel.manas_config import ManasConfig, RollingWindow

log = logging.getLogger(__name__)

# 事件级常量：原先在 _update_cognitive_state 中每次事件重建，提到模块级复用。
_RISK_LEVEL_SCORES = {
    "HIGH": 0.8,
    "MEDIUM": 0.5,
    "LOW": 0.2,
}

# AI 算力相关关键词（预先 lower，避免每个事件对每个关键词重复 .lower()）
_AI_COMPUTE_KEYWORDS_LOWER = tuple(
    kw.lower()
    for kw in (
        "AI", "算力", "芯片", "GPU", "数据中心", "大模型", "模型训练",
        "H100", "B100", "GB200", "Blackwell", "算力需求", "AI服务器",
    )
)


class AttentionFocus(Enum):
    """注意力聚焦类型"""
    WATCH = "watch"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    REBALANCE = "rebalance"
    ACCUMULATE = "accumulate"


class HarmonyState(Enum):
    """和谐状态"""
    RESONANCE = "resonance"
    NEUTRAL = "neutral"
    RESISTANCE = "resistance"


class BiasState(Enum):
    """偏差状态"""
    NEUTRAL = "neutral"
    GREED = "greed"
    FEAR = "fear"


class ActionType(Enum):
    """行动类型"""
    HOLD = "hold"
    ACT_FULLY = "act_fully"
    ACT_CAREFULLY = "act_carefully"
    ACT_MINIMALLY = "act_minimally"


class PortfolioSignal(Enum):
    """持仓信号"""
    NONE = "none"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    REBALANCE = "rebalance"
    ACCUMULATE = "accumulate"


# ManasOutput 的字段语义分组。
#
# 23 个字段原本平铺在一层里，既看不出归属，UI 也只能按硬编码顺序取。
# 这里把分组声明成数据，UI / 诊断按组取用；字段名本身一律不变，
# `out.manas_score` 这种既有写法继续有效。
MANAS_OUTPUT_GROUPS: Dict[str, Tuple[str, ...]] = {
    # 各路原始分数与最终融合分
    'scores': (
        'manas_score', 'timing_score', 'regime_score',
        'confidence_score', 'risk_temperature',
    ),
    # 天地人是否合拍
    'harmony': ('harmony_state', 'harmony_strength'),
    # 行动门：要不要动、怎么动、为什么
    'gate': ('should_act', 'action_type', 'action_gate_reason'),
    # 观照层纠偏
    'bias': ('bias_state', 'bias_correction'),
    # 注意力
    'attention': ('alpha', 'attention_focus'),
    # 认知层快照（对应 CognitiveState 的四个子状态）
    'cognition': (
        'narrative_risk', 'hot_narratives', 'supply_chain_risk_level',
        'ai_compute_direction', 'awakening_level',
    ),
    # 组合与风控
    'portfolio': (
        'portfolio_loss_pct', 'market_deterioration', 'portfolio_signal',
    ),
    # 注意力焦点枚举
    'focus': ('focus_enum',),
}


def _jsonable(value: Any) -> Any:
    """把 ManasOutput 的字段值转成可直接 json.dumps 的形态。

    枚举取 .value（与 to_dict() 一致）；tuple / list / dict 递归降一遍，
    其中 tuple 会变成 list —— json 虽然能序列化 tuple，但 list 才是
    JSON 的规范形态，避免下游按 list 解包时踩类型差异。
    其余类型原样返回（float / str / bool 本身就是 JSON 原语）。
    """
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


@dataclass
class ManasOutput:
    """末那识输出"""
    manas_score: float = 0.5
    timing_score: float = 0.5
    regime_score: float = 0.0
    confidence_score: float = 0.5
    risk_temperature: float = 1.0

    should_act: bool = False
    action_gate_reason: str = ""

    bias_state: BiasState = BiasState.NEUTRAL
    bias_correction: float = 1.0

    alpha: float = 1.0
    attention_focus: float = 1.0

    narrative_risk: float = 0.5
    hot_narratives: List[Tuple[str, float]] = field(default_factory=list)
    supply_chain_risk_level: str = "unknown"

    ai_compute_direction: str = "unknown"
    awakening_level: str = "dormant"

    harmony_state: HarmonyState = HarmonyState.NEUTRAL
    harmony_strength: float = 0.5
    action_type: ActionType = ActionType.HOLD

    portfolio_loss_pct: float = 0.0
    market_deterioration: bool = False

    focus_enum: AttentionFocus = AttentionFocus.WATCH
    portfolio_signal: PortfolioSignal = PortfolioSignal.NONE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manas_score": self.manas_score,
            "timing_score": self.timing_score,
            "regime_score": self.regime_score,
            "confidence_score": self.confidence_score,
            "risk_temperature": self.risk_temperature,
            "should_act": self.should_act,
            "action_gate_reason": self.action_gate_reason,
            "bias_state": self.bias_state.value,
            "bias_correction": self.bias_correction,
            "alpha": self.alpha,
            "attention_focus": self.attention_focus,
            "narrative_risk": self.narrative_risk,
            "hot_narratives": self.hot_narratives,
            "supply_chain_risk_level": self.supply_chain_risk_level,
            "ai_compute_direction": self.ai_compute_direction,
            "awakening_level": self.awakening_level,
            "harmony_state": self.harmony_state.value,
            "harmony_strength": self.harmony_strength,
            "action_type": self.action_type.value,
            "portfolio_loss_pct": self.portfolio_loss_pct,
            "market_deterioration": self.market_deterioration,
            "focus_enum": self.focus_enum.value,
            "portfolio_signal": self.portfolio_signal.value,
        }

    def group(self, name: str) -> Dict[str, Any]:
        """返回某一语义分组的字段子集（枚举取 .value，容器递归成 list）。

        组名见模块级 MANAS_OUTPUT_GROUPS。未知组名抛 KeyError —— 拼错组名
        应当立刻炸，而不是静默返回一个空 dict 让 UI 少渲染一块。
        """
        fields = MANAS_OUTPUT_GROUPS[name]
        return {f: _jsonable(getattr(self, f)) for f in fields}

    def to_grouped_dict(self) -> Dict[str, Dict[str, Any]]:
        """嵌套视图：{组名: {字段: 值}}。

        to_dict() 保持扁平以兼容既有消费者（os_kernel 构造 KernelOutput、
        kernel.py 状态导出、UI 表格）；这个嵌套版本给新代码 / 按组渲染的面板用。
        """
        return {g: self.group(g) for g in MANAS_OUTPUT_GROUPS}


@dataclass
class NarrativeState:
    """叙事维度：风险分数 + 热点叙事（来自 BLOCK_NARRATIVE_UPDATE / SUPPLY_CHAIN_RISK 等事件）"""
    risk: float = 0.5
    level: str = "LOW"
    # [(叙事, 重要性)]，按重要性降序，最多 5 条
    hot_narratives: List[Tuple[str, float]] = field(default_factory=list)


@dataclass
class AiComputeState:
    """AI 算力趋势：从事件叙事的关键词命中情况推断"""
    trend: str = "neutral"   # up / down / neutral
    strength: float = 0.5    # 0-1


@dataclass
class WatchlistState:
    """自选股注意力加成"""
    codes: List[str] = field(default_factory=list)
    bonus: float = 1.0       # 命中自选股时放大注意力，上限 1.5


@dataclass
class ResonanceState:
    """天-地共振状态（来自 CrossSignalAnalyzer 的 RESONANCE_DETECTED 事件）"""
    score: float = 0.0
    sentiment: float = 0.0
    blocks: List[str] = field(default_factory=list)
    updated: float = 0.0


@dataclass
class CognitiveState:
    """认知层状态（事件驱动演化）

    原先是一个 13 字段的混合 dict `_supply_chain_state`：读靠 `.get(k, 默认值)`、
    写靠整块重建（重建时漏掉未列出的字段，曾把 focus_themes 清空）。
    改为嵌套 dataclass 后：
        • 字段有类型与默认值，读写不再需要 .get 兜底；
        • 更新只能逐字段赋值，结构上无法再整块覆盖掉未提及的字段；
        • 四组关注点各自成类，新增字段只需改对应类。
    """
    narrative: NarrativeState = field(default_factory=NarrativeState)
    ai_compute: AiComputeState = field(default_factory=AiComputeState)
    watchlist: WatchlistState = field(default_factory=WatchlistState)
    resonance: ResonanceState = field(default_factory=ResonanceState)
    # 我们关心的叙事主题（"地"维度只追踪这些主题），见 _get_default_focus_themes
    focus_themes: List[Dict[str, Any]] = field(default_factory=list)
    last_update: float = 0.0


class TimingEngine:
    """
    时机引擎 - 判断市场"能不能动"

    视角：微观时机 - 现在是不是动手的好时机？

    分析四个维度：
        • 时间压力 (time_pressure) - 今天是开盘/盘中/收盘？
        • 波动率状态 (volatility) - 市场是否稳定到可以操作？
        • 成交密度 (trade_density) - 有足够流动性吗？
        • 结构断裂 (structure_break) - 趋势是否被破坏？

    注意：与 RegimeEngine 的区别
        - TimingEngine 看「现在能不能动」→ 微观层面的择时
        - RegimeEngine 看「现在是顺风还是逆风」→ 宏观层面的方向

    简单理解：
        TimingEngine = 今天/现在适不适合动手（微观）
        RegimeEngine = 最近一段时间大方向顺不顺（宏观）

    输出 timing_score ∈ [0, 1]
        0 = 不宜动（时机不对）
        1 = 可以出手（时机成熟）

    支持自适应权重：高波动环境自动调整各因子权重
    """

    def __init__(self, session_manager=None, config: ManasConfig = None):
        self.config = config or ManasConfig()
        self._last_volatility = 0.0
        self._volatility_history = RollingWindow(self.config.volatility_window)
        self._session_manager = session_manager
        # 最近一次 compute 的四个分量，供 UI / 诊断读取。
        # 此前 attention/ui/dashboard.py 用 getattr(te, '_time_pressure', 0) 这类
        # 读法，而这些属性**从未存在** → 时序面板的四个分量恒为 0（死面板）。
        self._last_components: Dict[str, Any] = {}

    def get_last_components(self) -> Dict[str, Any]:
        """最近一次 compute 的分量（含 timing_score 与自适应权重）。"""
        return dict(self._last_components)

    def set_session_manager(self, session_manager):
        """设置 session_manager 依赖"""
        self._session_manager = session_manager

    def compute(self, session_manager=None, scanner=None) -> float:
        """
        计算时机分数

        Args:
            session_manager: TradingClock/MarketSessionManager
            scanner: GlobalMarketScanner

        Returns:
            timing_score ∈ [0, 1]
        """
        time_pressure = self._get_time_pressure(session_manager)
        volatility = self._get_volatility_regime(scanner)
        density = self._get_trade_density(scanner)
        structure = self._get_structure_break(scanner)

        weights = self._get_adaptive_weights(scanner, volatility)

        timing = (
            time_pressure * weights["time_pressure"] +
            volatility * weights["volatility"] +
            density * weights["density"] +
            structure * weights["structure"]
        )
        timing = max(0.0, min(1.0, timing))

        self._last_volatility = volatility
        self._last_components = {
            "time_pressure": time_pressure,
            "volatility": volatility,
            "density": density,
            "structure": structure,
            "timing_score": timing,
            "weights": dict(weights),
        }
        return timing

    def _get_adaptive_weights(self, scanner, current_volatility: float) -> Dict[str, float]:
        """
        根据当前波动率环境自适应调整权重

        高波动：降低波动率权重，提高时间压力和结构断裂权重
        低波动：提高波动率权重，降低成交密度权重
        """
        sample = self.config.volatility_sample
        if len(self._volatility_history) >= sample:
            recent_avg = self._volatility_history.mean(sample)
            if current_volatility > recent_avg * 1.3:
                return {
                    "time_pressure": 0.35,
                    "volatility": 0.35,
                    "density": 0.15,
                    "structure": 0.15,
                }
            elif current_volatility < recent_avg * 0.7:
                return {
                    "time_pressure": 0.3,
                    "volatility": 0.15,
                    "density": 0.35,
                    "structure": 0.2,
                }

        return {
            "time_pressure": 0.4,
            "volatility": 0.25,
            "density": 0.2,
            "structure": 0.15,
        }

    def _get_time_pressure(self, session_manager) -> float:
        """获取时间压力"""
        if session_manager is None:
            session_manager = self._session_manager

        if session_manager is None:
            return 0.5

        try:
            if hasattr(session_manager, 'get_market_status'):
                status = session_manager.get_market_status("china_a")
                is_open = (status.value == "open") if hasattr(status, 'value') else False
                if not is_open:
                    return 0.2
            if hasattr(session_manager, 'get_session_remaining_seconds'):
                remaining = session_manager.get_session_remaining_seconds("china_a") or 0
                if remaining < 900:
                    return 0.3
                elif remaining < 1800:
                    return 0.7
                return 0.8
        except Exception as e:
            log.debug("manas: 抑制异常并回退默认值: %s", e)
            pass
        return 0.5

    def _get_volatility_regime(self, scanner) -> float:
        """获取波动率状态"""
        if scanner is None:
            return 0.5

        try:
            vol = scanner.get_market_volatility()
            if vol is None:
                return 0.5

            self._volatility_history.append(vol)

            sample = self.config.volatility_sample
            if len(self._volatility_history) < sample:
                return 0.5

            recent = self._volatility_history.tail(sample)
            avg_vol = sum(recent) / len(recent)
            current_vol = recent[-1]

            if current_vol < avg_vol * 0.7:
                return 0.8
            elif current_vol > avg_vol * 1.3:
                return 0.3
            return 0.5
        except Exception as e:
            log.debug("manas: 抑制异常并回退默认值: %s", e)
            return 0.5

    def _get_trade_density(self, scanner) -> float:
        """获取成交密度"""
        if scanner is None:
            return 0.5

        try:
            market_data = scanner.get_last_data()
            if not market_data:
                return 0.5

            total_change = 0.0
            count = 0
            for code, md in market_data.items():
                if hasattr(md, 'change_pct') and md.change_pct != 0:
                    total_change += abs(md.change_pct)
                    count += 1

            if count == 0:
                return 0.5

            avg_change = total_change / count

            if avg_change < 0.5:
                return 0.4
            elif avg_change < 1.0:
                return 0.6
            elif avg_change < 2.0:
                return 0.8
            return 0.9
        except Exception as e:
            log.debug("manas: 抑制异常并回退默认值: %s", e)
            return 0.5

    def _get_structure_break(self, scanner) -> float:
        """检测结构断裂"""
        if scanner is None:
            return 0.5

        try:
            summary = scanner.get_market_summary()
            phase = summary.get('us_trading_phase', 'closed')

            if phase == 'trading':
                return 0.8
            elif phase in ('pre_market', 'after_hours'):
                return 0.5
            return 0.3
        except Exception as e:
            log.debug("manas: 抑制异常并回退默认值: %s", e)
            return 0.5


class RegimeEngine:
    """
    环境引擎 - 判断当前是"顺风"还是"逆风"

    视角：宏观环境 - 最近一段时间大方向顺不顺？

    分析三个维度：
        • 指数趋势 (index_trend) - 大盘是在上涨还是下跌？
        • 流动性信号 (liquidity) - 资金是在流入还是流出？
        • 题材扩散 (block_diffusion) - 是普涨还是分化？

    注意：与 TimingEngine 的区别
        - RegimeEngine 看「最近宏观方向」→ 大方向顺不顺
        - TimingEngine 看「现在微观时机」→ 现在能不能动

    简单理解：
        RegimeEngine = 最近一段时间大方向顺不顺（顺风/逆风）
        TimingEngine = 今天/现在适不适合动手（时机）

    输出 regime_score ∈ [-1, 1]
        -1 = 强逆风（市场整体下跌）
         0 = 中性（横盘）
        +1 = 强顺风（市场整体上涨）
    """

    def __init__(self, config: ManasConfig = None):
        # _trend_history 原先只 append/trim，从无读取点（写入后即弃），已删除
        self.config = config or ManasConfig()
        # 最近一次 compute 的分量（供 UI / 诊断；此前 dashboard 读的
        # _trend / _liquidity / _diffusion 从未存在，面板恒 0）
        self._last_components: Dict[str, Any] = {}

    def get_last_components(self) -> Dict[str, Any]:
        """最近一次 compute 的分量（含 regime_score 与自适应权重）。"""
        return dict(self._last_components)

    def compute(self, scanner=None, macro_signal: float = 0.5) -> float:
        """
        计算宏观环境分数

        Args:
            scanner: GlobalMarketScanner
            macro_signal: 宏观流动性信号

        Returns:
            regime_score ∈ [-1, 1]
        """
        trend = self._get_index_trend(scanner)
        liquidity = self._get_liquidity_signal(scanner, macro_signal)
        diffusion = self._get_block_diffusion(scanner)

        weights = self._get_adaptive_regime_weights(scanner)

        regime = (
            trend * weights["trend"] +
            liquidity * weights["liquidity"] +
            diffusion * weights["diffusion"]
        )
        regime = max(-1.0, min(1.0, regime))

        self._last_components = {
            "trend": trend,
            "liquidity": liquidity,
            "diffusion": diffusion,
            "regime_score": regime,
            "weights": dict(weights),
        }
        return regime

    def _get_adaptive_regime_weights(self, scanner) -> Dict[str, float]:
        """
        根据当前市场状态自适应调整 RegimeEngine 权重

        提案 2.4.2：美股交易时段更注重趋势，盘前盘后更注重流动性
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
        except Exception as e:
            log.debug("manas: 抑制异常并回退默认值: %s", e)
            pass

        return weights

    def _get_index_trend(self, scanner) -> float:
        """获取指数趋势"""
        if scanner is None:
            return 0.0

        try:
            market_data = scanner.get_last_data()
            if not market_data:
                return 0.0

            total_change = 0.0
            count = 0
            for code, md in market_data.items():
                if hasattr(md, 'change_pct') and md.change_pct != 0:
                    total_change += md.change_pct
                    count += 1

            if count == 0:
                return 0.0

            avg_change = total_change / count

            if avg_change > 1.0:
                return 1.0
            elif avg_change < -1.0:
                return -1.0
            return avg_change
        except Exception as e:
            log.debug("manas: 抑制异常并回退默认值: %s", e)
            return 0.0

    def _get_liquidity_signal(self, scanner, macro_signal: float) -> float:
        """获取流动性信号"""
        if scanner is not None:
            try:
                adj = scanner.get_liquidity_adjustment("CHINA_A")
                if adj:
                    return adj.get("adjusted_signal", macro_signal) * 2 - 1
            except Exception as e:
                log.debug("manas: 抑制异常并回退默认值: %s", e)
                pass

        return macro_signal * 2 - 1

    def _get_block_diffusion(self, scanner) -> float:
        """获取题材扩散程度"""
        if scanner is None:
            return 0.0

        try:
            market_data = scanner.get_last_data()
            if not market_data:
                return 0.0

            advancing = 0
            declining = 0
            for code, md in market_data.items():
                if hasattr(md, 'change_pct'):
                    if md.change_pct > 0:
                        advancing += 1
                    elif md.change_pct < 0:
                        declining += 1

            total = advancing + declining
            if total == 0:
                return 0.0

            diffusion = (advancing - declining) / total
            return max(-1.0, min(1.0, diffusion))
        except Exception as e:
            log.debug("manas: 抑制异常并回退默认值: %s", e)
            return 0.0


class ConfidenceEngine:
    """
    自信引擎 - 判断"策略是否适配当前市场"

    视角：策略自检 - 我的策略现在还管用吗？

    分析三个维度：
        • 命中率 (hit_rate) - 最近策略命中率如何？
        • 滚动盈亏 (rolling_pnl) - 最近是在赚钱还是亏钱？
        • Bandit置信度 (bandit_conf) - 多臂老虎机对策略的信心

    简单理解：
        这个引擎回答「我这套方法现在还能用吗？」
        如果最近一直在亏，可能是策略不适应现在市场了。

    与其他引擎的区别：
        - RiskEngine：看「市场有多危险」（外部）
        - MetaManas：看「我有没有心理偏差」（内部）
        - ConfidenceEngine：看「我的策略现在还管用吗」（策略本身）

    输出 confidence ∈ [0, 1.5]
        < 0.5 = 策略失灵，需要重新审视
        0.5-1.0 = 正常范围
        > 1.0 = 策略非常适配（注意是否过度自信）
    """

    def __init__(self, bandit_tracker=None, config: ManasConfig = None):
        self.config = config or ManasConfig()
        # _rolling_pnl_history 原先声明后从未使用（rolling pnl 直接取自 tracker），已删除
        self._hit_rate_history = RollingWindow(self.config.hit_rate_window)
        self._bandit_tracker = bandit_tracker
        # 最近一次 compute 的分量（供 UI / 诊断）
        self._last_components: Dict[str, Any] = {}

    def get_last_components(self) -> Dict[str, Any]:
        """最近一次 compute 的分量（hit_rate / rolling_pnl / bandit 置信 / 合成值）。"""
        return dict(self._last_components)

    def set_bandit_tracker(self, bandit_tracker):
        """设置 bandit_tracker 依赖"""
        self._bandit_tracker = bandit_tracker

    def compute(self, bandit_tracker=None) -> float:
        """
        计算策略自信度

        Args:
            bandit_tracker: BanditPositionTracker

        Returns:
            confidence ∈ [0, 1.5]
        """
        hit_rate = self._get_hit_rate(bandit_tracker)
        rolling_pnl = self._get_rolling_pnl(bandit_tracker)
        bandit_conf = self._get_bandit_confidence(bandit_tracker)

        confidence = (
            hit_rate * 0.4 +
            min(max(rolling_pnl / 10, 0), 1.0) * 0.3 +
            bandit_conf * 0.3
        )
        confidence = max(0.0, min(1.5, confidence))

        self._last_components = {
            "hit_rate": hit_rate,
            "rolling_pnl": rolling_pnl,
            "bandit_confidence": bandit_conf,
            "confidence_score": confidence,
        }
        return confidence

    def _get_hit_rate(self, tracker) -> float:
        """获取近期命中率"""
        if tracker is None:
            tracker = self._bandit_tracker
        
        if tracker is None:
            return 0.5

        try:
            history = tracker.get_position_history(limit=20)
            if not history:
                return 0.5

            wins = sum(1 for r in history if r.get('return_pct', 0) > 0)
            hit_rate = wins / len(history)

            self._hit_rate_history.append(hit_rate)
            return self._hit_rate_history.mean()
        except Exception as e:
            log.debug("manas: 抑制异常并回退默认值: %s", e)
            return 0.5

    def _get_rolling_pnl(self, tracker) -> float:
        """获取 rolling 盈亏"""
        if tracker is None:
            return 0.0

        try:
            history = tracker.get_position_history(limit=10)
            if not history:
                return 0.0

            total_pnl = sum(r.get('return_pct', 0) for r in history)
            return total_pnl
        except Exception as e:
            log.debug("manas: 抑制异常并回退默认值: %s", e)
            return 0.0

    def _get_bandit_confidence(self, tracker) -> float:
        """获取 bandit 置信度"""
        if tracker is None:
            return 0.5

        try:
            stats = tracker.get_strategy_summary("default")
            total_trades = stats.get('total_trades', 0)

            if total_trades < 5:
                return 0.3
            elif total_trades < 20:
                return 0.5
            elif total_trades < 50:
                return 0.7
            return 0.9
        except Exception as e:
            log.debug("manas: 抑制异常并回退默认值: %s", e)
            return 0.5


class RiskEngine:
    """
    风险引擎 - 判断"还能承受多少波动"

    视角：外部风险 - 市场能杀我多少？

    分析三个维度：
        • 现金比例 (cash_ratio) - 我还有多少子弹？
        • 当前回撤 (drawdown) - 我已经亏了多少？
        • 市场波动率 (volatility) - 市场有多疯狂？

    注意：与 MetaManas 的区别
        - RiskEngine 看「绝对亏损量」→ 市场造成的客观损失
        - MetaManas 看「连续盈亏方向」→ 我自己的心理偏差

    输出 temperature ∈ (0, 2]
        T 大 = 更保守（市场太危险，少动）
        T 小 = 更激进（还有子弹，可以干）
    """

    def __init__(self, portfolio=None, config: ManasConfig = None):
        self.config = config or ManasConfig()
        self._drawdown_history = RollingWindow(self.config.drawdown_window)
        self._portfolio = portfolio
        # 最近一次 compute 的分量（供 UI / 诊断）
        self._last_components: Dict[str, Any] = {}

    def get_last_components(self) -> Dict[str, Any]:
        """最近一次 compute 的分量（cash_ratio / drawdown / volatility / T）。"""
        return dict(self._last_components)

    def set_portfolio(self, portfolio):
        """设置 portfolio 依赖"""
        self._portfolio = portfolio

    def compute(self, portfolio=None, scanner=None, summary=None) -> float:
        """
        计算风险温度

        Args:
            portfolio: VirtualPortfolio
            scanner: GlobalMarketScanner
            summary: 可选的持仓汇总（portfolio.get_summary() 的结果）。
                     传入可避免在现金比例/回撤两处重复获取。

        Returns:
            temperature ∈ (0, 2]
        """
        cash_ratio = self._get_cash_ratio(portfolio, summary=summary)
        drawdown = self._get_drawdown(portfolio, summary=summary)
        volatility = self._get_current_volatility(scanner)

        base_T = 1.0 + (1.0 - cash_ratio) * 0.5

        if drawdown > 0.1:
            base_T *= 1.3
        elif drawdown > 0.05:
            base_T *= 1.1

        if volatility > 2.0:
            base_T *= 1.2
        elif volatility > 1.5:
            base_T *= 1.1

        temperature = max(0.5, min(2.0, base_T))
        self._last_components = {
            "cash_ratio": cash_ratio,
            "drawdown": drawdown,
            "volatility": volatility,
            "base_T": base_T,
            "risk_temperature": temperature,
        }
        return temperature

    def _get_cash_ratio(self, portfolio, summary=None) -> float:
        """获取现金比例 available / total ∈ [0, 1]

        历史上是 `available / max(summary.get('total_capital', 1), 1)`：
        分母缺失时兜底成 1，于是「键不存在」与「总资金真的是 1 元」不可区分，
        比值直接变成可用资金的数值本身（如 590000），base_T 随之变成大负数、
        撞上 0.5 下限——看起来像「市场极度安全」，实际是分母没接上。
        现在补两条兜底（available+used 复原 / total_value），并夹到 [0,1]。
        """
        if portfolio is None:
            portfolio = self._portfolio

        if portfolio is None:
            return 0.5

        try:
            if summary is None:
                summary = portfolio.get_summary()
            available = summary.get('available_capital', 0) or 0
            total = summary.get('total_capital')
            if not total:
                total = available + (summary.get('used_capital', 0) or 0)
            if not total:
                total = summary.get('total_value', 0) or 0
            if not total:
                return 0.5
            return max(0.0, min(1.0, available / total))
        except Exception as e:
            log.debug("manas: 抑制异常并回退默认值: %s", e)
            return 0.5

    def _get_drawdown(self, portfolio, summary=None) -> float:
        """获取当前回撤（小数口径：0.06 = 6%）

        入参 `total_return` 为**百分数**（生产实现 VirtualPortfolio 及其 UI、
        attention/kernel/state.py 都是百分数口径），而本方法的加档阈值是
        0.1 / 0.05（小数）—— 此前直接把百分数当小数比，于是任何非零收益
        （哪怕是 +3.5% 的**盈利**，因为取了 abs）都会命中 `> 0.1` 这一档，
        base_T 恒乘 1.3。这里在入口处统一归一到小数。
        """
        if portfolio is None:
            return 0.0

        try:
            if summary is None:
                summary = portfolio.get_summary()
            return_pct = abs(summary.get('total_return', 0) or 0) / 100.0
            self._drawdown_history.append(return_pct)
            return self._drawdown_history.mean()
        except Exception as e:
            log.debug("manas: 抑制异常并回退默认值: %s", e)
            return 0.0

    def _get_current_volatility(self, scanner) -> float:
        """获取当前市场波动率"""
        if scanner is None:
            return 1.0

        try:
            vol = scanner.get_market_volatility()
            return vol if vol else 1.0
        except Exception as e:
            log.debug("manas: 抑制异常并回退默认值: %s", e)
            return 1.0


class MetaManas:
    """
    观照层 - 觉知末那识正在"执"

    视角：内部偏差 - 我自己会怎么犯错？

    检测两种心理偏差：
        • 连赢 → 越来越激进 → 标记"贪"（贪心让我过度自信）
        • 连亏 → 完全不动 → 标记"惧"（恐惧让我错过机会）

    纠偏机制：
        • 贪时 → reduce α（别太信自己）, increase T（仓位别太重）
        • 恐时 → keep α（策略没问题）, moderate T（保持合理仓位）

    注意：与 RiskEngine 的区别
        - MetaManas 看「连续盈亏方向」→ 我自己的心理偏差（主观）
        - RiskEngine 看「绝对亏损量」→ 市场造成的客观损失（客观）

    简单理解：
        RiskEngine = 客观风险（市场杀的）
        MetaManas = 主观偏差（自己作的）
    """

    def __init__(self, config: ManasConfig = None):
        self.config = config or ManasConfig()
        self.bias_state = BiasState.NEUTRAL
        self._decision_aggressiveness = RollingWindow(self.config.aggressiveness_window)

    def detect_and_correct(
        self,
        recent_pnl: List[float],
        decision_aggressiveness: float
    ) -> tuple[BiasState, float]:
        """
        检测偏差并纠偏

        Args:
            recent_pnl: 最近 N 笔交易的盈亏列表。
                调用方（ManasEngine._recent_pnl）已维护好滑动窗口，上限 20 笔
            decision_aggressiveness: 本次决策的激进程度，量纲与判贪阈值
                （avg_aggressiveness > 0.6）一致，勿当作分数误改

        Returns:
            tuple: (bias_state, bias_correction)
        """
        # 样本窗口只应有一份权威来源，即调用方传入的 recent_pnl。
        # 此前这里用 self._pnl_trend.extend(recent_pnl)，每轮把整个窗口再追加一遍，
        # 使 len < 5 的暖机判断被重复计数绕过：实测仅 2 笔真实交易即可触发纠偏。
        cfg = self.config
        pnl_trend = list(recent_pnl or [])

        self._decision_aggressiveness.append(decision_aggressiveness)

        if len(pnl_trend) < cfg.bias_min_samples:
            return BiasState.NEUTRAL, 1.0

        recent = pnl_trend[-cfg.bias_min_samples:]
        recent_avg = sum(recent) / len(recent)
        overall_avg = sum(pnl_trend) / len(pnl_trend)
        avg_aggressiveness = self._decision_aggressiveness.mean()

        greed_detected = (
            recent_avg > cfg.greed_recent_avg and
            overall_avg > cfg.greed_overall_avg and
            avg_aggressiveness > cfg.greed_aggressiveness
        )

        fear_detected = (
            recent_avg < cfg.fear_recent_avg and
            len([p for p in recent if p < 0]) >= cfg.fear_losses
        )

        if greed_detected and self.bias_state != BiasState.GREED:
            self.bias_state = BiasState.GREED
            log.warning("[MetaManas] 检测到贪bias，开始纠偏")
            return BiasState.GREED, cfg.correction_greed

        if fear_detected and self.bias_state != BiasState.FEAR:
            self.bias_state = BiasState.FEAR
            log.warning("[MetaManas] 检测到惧bias，开始纠偏")
            return BiasState.FEAR, cfg.correction_fear

        if abs(recent_avg) < cfg.neutral_band and self.bias_state != BiasState.NEUTRAL:
            self.bias_state = BiasState.NEUTRAL
            return BiasState.NEUTRAL, 1.0

        if self.bias_state == BiasState.GREED:
            return BiasState.GREED, cfg.correction_greed
        elif self.bias_state == BiasState.FEAR:
            return BiasState.FEAR, cfg.correction_fear_steady

        return BiasState.NEUTRAL, 1.0

    def get_state(self) -> Dict[str, Any]:
        """获取观照层状态（供 UI 展示与排查）

        此前本类没有 get_state，而 attention/ui/dashboard.py 用
        `mm.get_state() if hasattr(mm, 'get_state') else {}` 取值，
        hasattr 恒为 False → 末那识面板永远显示 bias_state=neutral、
        bias_direction=none，等于一个死面板。
        """
        aggressiveness = self._decision_aggressiveness
        return {
            "bias_state": self.bias_state.value,
            # 纠偏方向（不是偏差方向，后者已由 bias_state 表达）：
            # 贪 → 抑制激进；惧 → 促使行动；无偏差 → none
            "bias_direction": (
                "restrain" if self.bias_state == BiasState.GREED
                else "encourage" if self.bias_state == BiasState.FEAR
                else "none"
            ),
            # 给**人**看的教练语。同一份检测，对内是打分乘子，对外是提醒：
            # 「你最近连赢之后仓位在放大」。这是 P2.1 想补的那一环——
            # 检测早就有了，缺的是把它接到人看得见的地方。
            "bias_message": self.bias_message(),
            # 诊断用：判贪条件之一是 avg_aggressiveness > greed_aggressiveness，
            # 面板上能看到当前处于什么水平
            "aggressiveness_samples": len(aggressiveness),
            "avg_aggressiveness": round(aggressiveness.mean(), 3),
        }

    def bias_message(self) -> str:
        """把偏差状态翻译成一句可读的教练语（无偏差时返回中性说明）。"""
        aggr = self._decision_aggressiveness
        if self.bias_state == BiasState.GREED:
            return (
                "检测到贪：连续盈利后决策激进度升到 {:.2f}，已下调 α 并抬高仓位温度。"
                "建议主动复核是否在放大仓位，而不是继续踩油门。".format(aggr.mean())
            )
        if self.bias_state == BiasState.FEAR:
            return (
                "检测到惧：连续亏损后决策趋于保守，已适度放宽。"
                "建议核对策略本身是否仍然有效——该停手的是坏策略，不是所有动作。"
            )
        return "无显著行为偏差，α 未被纠偏。"


class ManasEngine:
    """
    末那识引擎 - 核心决策中枢

    统一四个引擎的输出，生成最终的 manas_score

    使用方式：
        manas = ManasEngine()
        output = manas.compute(
            session_manager=session_mgr,
            portfolio=portfolio,
            scanner=scanner,
            bandit_tracker=bandit_tracker
        )

        # output.manas_score: 综合分数
        # output.should_act: 是否行动
        # output.alpha: 置信度因子
        # output.risk_temperature: 风险温度
    """

    # 策略参数（融合权重 / 行动门槛 / 调节系数 / 窗口长度）全部收敛到
    # ManasConfig，见 manas_config.py。改行为请改 config，不要在这里加常量。

    def __init__(self, session_manager=None, portfolio=None, bandit_tracker=None,
                 config: ManasConfig = None):
        self.config = config or ManasConfig()
        self.timing_engine = TimingEngine(session_manager, config=self.config)
        self.regime_engine = RegimeEngine(config=self.config)
        self.confidence_engine = ConfidenceEngine(bandit_tracker, config=self.config)
        self.risk_engine = RiskEngine(portfolio, config=self.config)
        self.meta_manas = MetaManas(config=self.config)
        self._session_manager = session_manager
        self._portfolio = portfolio
        self._bandit_tracker = bandit_tracker

        self._last_output: Optional[ManasOutput] = None
        self._last_update = 0.0
        self._update_interval = self.config.update_interval
        self._current_narratives: List[str] = []
        self._recent_pnl = RollingWindow(self.config.pnl_window)

        # 🚀 和谐状态
        self._harmony_state = HarmonyState.NEUTRAL
        self._harmony_strength = 0.5

        # 🚀 认知层状态（事件驱动，收到认知事件后演化，见 _update_cognitive_state）
        self._cognitive_state = CognitiveState(
            focus_themes=self._get_default_focus_themes(),
        )

        self._awakening_level: str = "dormant"
        # 觉醒等级的注入点（见 set_awakening_level_provider）。
        # 本仓无输入侧生产者 → 默认 None → 调节链 awakening 环节恒 ×1.0。
        self._awakening_level_provider: Optional[Callable[[], str]] = None

        # 🚀 事件订阅已迁移到 EventSubscriberRegistrar（应用层）
        # 构造期不再自动订阅：本引擎常为懒创建（首次访问 UI 才建立），
        # 且历史上所有实例共用固定订阅者名 "ManasEngine"，多实例会重复挂载。
        # 由装配方（Registrar / ManasManager）调用 subscribe_cognitive_events()。
        self._event_bus = None
        self._cognitive_subscribed = False
        self._cognitive_subscriber_name = f"ManasEngine#{id(self)}"

    def set_session_manager(self, session_manager):
        """设置 session_manager 依赖"""
        self._session_manager = session_manager
        self.timing_engine.set_session_manager(session_manager)
    
    def set_portfolio(self, portfolio):
        """设置 portfolio 依赖"""
        self._portfolio = portfolio
        self.risk_engine.set_portfolio(portfolio)
    
    def set_bandit_tracker(self, bandit_tracker):
        """设置 bandit_tracker 依赖"""
        self._bandit_tracker = bandit_tracker
        self.confidence_engine.set_bandit_tracker(bandit_tracker)

    def _get_default_focus_themes(self) -> List[Dict[str, Any]]:
        """
        🚀 获取默认的关注主题列表

        这是我们"地"维度关心的话题，来自 keyword_registry 的预设关键词。
        BlockNarrative（地）只追踪这些主题，而不是所有市场主题。

        返回格式：[{"id": "AI", "name": "AI", "keywords": [...]}, ...]

        跨域复用说明：keyword_registry 属于 cognition 包，把 ManasEngine 搬出
        交易/认知域时它可能不存在。此时返回空列表而不是抛异常——「没有预设主题」
        是可接受的中性初值，只影响叙事主题追踪，不影响天/地/人/风险四维打分。
        与其它兜底一致：**降级要留痕**（记一条 info），不做静默。
        """
        try:
            from deva.naja.cognition.semantic.keyword_registry import (
                DEFAULT_NARRATIVE_KEYWORDS,
            )
        except ImportError as e:
            log.info(
                "[ManasEngine] 认知层 keyword_registry 不可用（%s），focus_themes 置空；"
                "四维打分不受影响，仅叙事主题追踪退化为空。",
                e,
            )
            return []

        return [
            {
                "id": theme_id,
                "name": theme_id,
                "keywords": keywords,
            }
            for theme_id, keywords in DEFAULT_NARRATIVE_KEYWORDS.items()
        ]

    def get_focus_themes(self) -> List[Dict[str, Any]]:
        """
        🚀 获取当前关注的叙事主题列表

        这是 Manas 关心的话题（地），BlockNarrative 应该只追踪这些主题。
        """
        return self._cognitive_state.focus_themes

    def set_focus_themes(self, themes: List[Dict[str, Any]]):
        """
        🚀 设置关注的叙事主题列表

        可以动态更新我们关心的话题。
        """
        self._cognitive_state.focus_themes = themes
        log.info(f"[ManasEngine] 关注主题已更新: {len(themes)} 个主题")
        self._publish_manas_state_change({"focus_themes": themes})

    def _publish_manas_state_change(self, partial_state: Dict[str, Any] = None):
        """
        🚀 发布 Manas 状态变化事件

        通知订阅者（如 Cognition 层）Manas 状态已更新。
        Cognition 层应订阅 CognitiveEventType.MANAS_STATE_CHANGED 事件。
        """
        try:
            from deva.naja.events import get_event_bus, CognitiveEventType

            bus = get_event_bus()
            state_data = {
                "focus_themes": self._cognitive_state.focus_themes,
                "harmony_strength": self._harmony_strength,
                "harmony_state": self._harmony_state.value if hasattr(self._harmony_state, 'value') else str(self._harmony_state),
            }
            if partial_state:
                state_data.update(partial_state)

            bus.publish_cognitive_event(
                source="ManasEngine",
                event_type=CognitiveEventType.MANAS_STATE_CHANGED,
                data=state_data,
                importance=0.6,
            )
            log.debug(f"[ManasEngine] 发布 MANAS_STATE_CHANGED 事件")
        except Exception as e:
            log.debug(f"[ManasEngine] 发布状态变化事件失败: {e}")

    def subscribe_cognitive_events(self, event_bus=None) -> bool:
        """
        🚀 订阅 NajaEventBus，感知认知层的重要更新

        当 NarrativeTracker / MarketNarrative / SupplyChainLinker 有重要更新时，
        ManasEngine 会收到通知并清缓存，确保决策反映最新认知状态。

        由 EventSubscriberRegistrar（应用层）或 ManasManager 装配点调用，
        遵循架构基准 §6.3「事件订阅集中管理」。幂等：已订阅则直接返回 True。

        Args:
            event_bus: 事件总线；None 时取全局默认总线

        Returns:
            是否订阅成功
        """
        if self._cognitive_subscribed:
            return True

        try:
            from deva.naja.events import (
                get_event_bus,
                CognitiveEventType,
            )

            if event_bus is None:
                event_bus = get_event_bus()

            event_bus.subscribe(
                self._cognitive_subscriber_name,
                self._on_cognitive_event,
                event_types=[
                    CognitiveEventType.BLOCK_NARRATIVE_UPDATE,
                    CognitiveEventType.NARRATIVE_BOOST,
                    CognitiveEventType.TIMING_NARRATIVE_UPDATE,
                    CognitiveEventType.NARRATIVE_SUPPLY_LINK,
                    CognitiveEventType.SUPPLY_CHAIN_RISK,
                    CognitiveEventType.RESONANCE_DETECTED,
                ],
                min_importance=0.5,  # 只关心重要事件
            )
            self._event_bus = event_bus
            self._cognitive_subscribed = True
            log.info(f"[ManasEngine] 已订阅 NajaEventBus（{self._cognitive_subscriber_name}）")
            return True
        except ImportError:
            log.debug("[ManasEngine] NajaEventBus 未安装，跳过订阅")
            return False
        except Exception as e:
            log.warning(f"[ManasEngine] 订阅 NajaEventBus 失败: {e}")
            return False

    def unsubscribe_cognitive_events(self) -> bool:
        """
        🚀 取消认知事件订阅

        供装配方在重建/销毁引擎时调用，避免残留订阅持续回调已弃用实例。
        """
        if not self._cognitive_subscribed or self._event_bus is None:
            return False
        try:
            ok = self._event_bus.unsubscribe(self._cognitive_subscriber_name)
            self._cognitive_subscribed = False
            self._event_bus = None
            return bool(ok)
        except Exception as e:
            log.warning(f"[ManasEngine] 取消 NajaEventBus 订阅失败: {e}")
            return False

    def _on_cognitive_event(self, event):
        """
        🚀 处理认知事件，感知认知层状态变化

        当收到认知事件时，更新供应链状态，清缓存
        """
        log.info(
            f"[ManasEngine] 收到认知事件: {event.source} -> {event.event_type.value} "
            f"(importance={event.importance:.2f}, narratives={event.narratives[:2]})"
        )

        # 🚀 更新认知层状态
        self._update_cognitive_state(event)

        # 清缓存，触发重新计算
        self._invalidate_cache()

    def _update_cognitive_state(self, event):
        """
        🚀 根据认知事件演化认知层状态

        事件驱动更新：不再主动拉取，由事件携带状态

        处理四个维度（对应 CognitiveState 的四个子状态）：
        1. 叙事风险 + 热点叙事  → NarrativeState
        2. AI算力趋势（从叙事中判断） → AiComputeState
        3. 自选股注意力加成 → WatchlistState
        4. 天-地共振（CrossSignalAnalyzer） → ResonanceState

        只做逐字段赋值：状态是"基于旧值演化"，没有任何字段需要被整体清空。
        """
        st = self._cognitive_state
        importance = float(getattr(event, "importance", 0.0) or 0.0)

        # ── 1. 叙事风险 + 热点叙事 ─────────────────────────────
        risk_level = event.risk_level if hasattr(event, 'risk_level') and event.risk_level else "LOW"
        # 旧风险占 7 成，事件风险按重要性占 3 成
        st.narrative.risk = max(0.0, min(1.0,
            st.narrative.risk * 0.7 + _RISK_LEVEL_SCORES.get(risk_level, 0.5) * importance * 0.3
        ))

        # 与已有叙事合并去重（同名保留更高的重要性），按重要性取前 5
        hot = dict(st.narrative.hot_narratives)
        for narrative in event.narratives[:5]:
            hot[narrative] = max(hot.get(narrative, importance), importance)
        st.narrative.hot_narratives = sorted(hot.items(), key=lambda x: x[1], reverse=True)[:5]

        # 风险等级只在事件足够重要时才刷新，避免低重要性事件来回拉扯
        if importance > 0.7:
            st.narrative.level = risk_level

        # ── 2. AI算力趋势：从叙事关键词命中数判断 ──────────────
        narratives_lower = [n.lower() for n in event.narratives]
        ai_hits = sum(1 for kw in _AI_COMPUTE_KEYWORDS_LOWER if any(kw in n for n in narratives_lower))

        if ai_hits >= 3:
            # 多个AI关键词命中 → 趋势转为增强
            st.ai_compute.trend = "up"
            st.ai_compute.strength = min(1.0, st.ai_compute.strength * 0.8 + importance * 0.2)
        elif ai_hits >= 1 and importance > 0.7:
            # 有AI关键词且重要 → 轻微增强
            st.ai_compute.strength = min(1.0, st.ai_compute.strength * 0.9 + importance * 0.1)
        else:
            # 自然衰减
            st.ai_compute.strength = max(0.3, st.ai_compute.strength * 0.98)

        # ── 3. 自选股注意力加成 ────────────────────────────────
        event_stocks_upper = [s.upper() for s in (getattr(event, 'stock_codes', []) or [])]
        watchlist_upper = [s.upper() for s in st.watchlist.codes]

        if event_stocks_upper and any(s in watchlist_upper for s in event_stocks_upper):
            # 命中自选股 → 增加注意力
            st.watchlist.bonus = min(1.5, st.watchlist.bonus * 1.2)
        else:
            # 自然衰减
            st.watchlist.bonus = max(1.0, st.watchlist.bonus * 0.99)

        # ── 4. 天-地共振 ───────────────────────────────────────
        # 只比字符串值：枚举的 .value 就是 "resonance_detected"，无需再 import 枚举类。
        # 旧写法在 import 失败时会用到未绑定的 CognitiveEventType → NameError。
        if str(getattr(event.event_type, "value", event.event_type)) == "resonance_detected":
            meta = getattr(event, "metadata", {}) or {}
            st.resonance.score = max(st.resonance.score, importance)
            st.resonance.sentiment = float(meta.get("sentiment", st.resonance.sentiment) or 0.0)

            block_id = meta.get("block_id") or meta.get("block_name") or ""
            if block_id and block_id not in st.resonance.blocks:
                st.resonance.blocks = (st.resonance.blocks + [block_id])[-5:]
            st.resonance.updated = time.time()

            # 共振情绪为负时，轻微增加风险；为正时，轻微降低风险
            if st.resonance.sentiment < -0.2 and st.resonance.score > 0.7:
                st.narrative.risk = min(1.0, st.narrative.risk + 0.05)
            elif st.resonance.sentiment > 0.2 and st.resonance.score > 0.7:
                st.narrative.risk = max(0.0, st.narrative.risk - 0.03)

        st.last_update = time.time()

        log.debug(
            f"[ManasEngine] 认知状态已更新: risk={st.narrative.risk:.2f}, "
            f"ai_trend={st.ai_compute.trend}({st.ai_compute.strength:.2f}), "
            f"watchlist_bonus={st.watchlist.bonus:.2f}"
        )

    def _invalidate_cache(self):
        """
        🚀 清除缓存，强制下次计算时重新获取认知数据

        这样可以确保决策反映最新的叙事/供应链状态
        """
        # 清除上次输出，下次 compute 会强制重新计算
        self._last_output = None
        self._last_update = 0.0

        log.debug("[ManasEngine] 缓存已失效，下次计算将重新获取认知数据")

    def refresh_watchlist(self, watchlist: List[str] = None):
        """
        🚀 刷新自选股列表

        可以手动传入，也可以从持仓系统自动获取

        Args:
            watchlist: 自选股代码列表，如 ["NVDA", "AMD", "TSLA"]
        """
        if watchlist is None:
            # 从持仓系统自动获取
            watchlist = self._get_watchlist_from_portfolio()

        self._cognitive_state.watchlist.codes = watchlist
        log.info(f"[ManasEngine] 自选股列表已更新: {len(watchlist)} 只股票")

    def _get_watchlist_from_portfolio(self) -> List[str]:
        """
        🚀 从 NB 数据表读取自选股

        数据来源：naja_watchlist 表的 ai_stocks 字段
        """
        try:
            from deva.naja.tables import get_table_data
            import json

            watchlist_data = get_table_data("naja_watchlist")
            if watchlist_data is None:
                return []

            others = watchlist_data.get("others", [])
            ai_stocks = next((item for item in others if item[0] == "ai_stocks"), None)
            if ai_stocks is None or len(ai_stocks) < 2:
                return []

            stocks_dict = ai_stocks[1]
            if isinstance(stocks_dict, str):
                try:
                    stocks_dict = json.loads(stocks_dict)
                except Exception as e:
                    log.debug("manas: 抑制异常并回退默认值: %s", e)
                    pass

            stocks = stocks_dict.get("stocks", []) if isinstance(stocks_dict, dict) else []
            watchlist_codes = [s["code"] for s in stocks if isinstance(s, dict) and "code" in s]

            return watchlist_codes
        except Exception as e:
            log.debug(f"[ManasEngine] 获取自选股失败: {e}")
            return []

    def _determine_harmony_state(self, risk_temperature: float, timing_score: float, regime_score: float) -> HarmonyState:
        """确定和谐状态"""
        cfg = self.config
        if risk_temperature > cfg.harmony_resistance_temperature or regime_score < cfg.harmony_resistance_regime:
            return HarmonyState.RESISTANCE
        elif (risk_temperature < cfg.harmony_resonance_temperature
              and timing_score > cfg.harmony_resonance_timing
              and regime_score > cfg.harmony_resonance_regime):
            return HarmonyState.RESONANCE
        return HarmonyState.NEUTRAL

    def _determine_action_type(
        self,
        harmony_state: HarmonyState,
        harmony_strength: float,
        timing_score: float
    ) -> ActionType:
        """确定行动类型

        两条通道：
        1) 共振通道：RESISTANCE 直接 HOLD；RESONANCE 且强时机 → ACT_FULLY。
           此通道不看 harmony_strength，可以绕过 action_threshold。
        2) 分数通道：先过 action_threshold，再按 strong_action_threshold 分强弱两档。
        """
        should_act = harmony_strength > self.config.action_threshold

        if harmony_state == HarmonyState.RESISTANCE:
            return ActionType.HOLD
        if harmony_state == HarmonyState.RESONANCE and timing_score > self.config.resonance_timing_threshold:
            return ActionType.ACT_FULLY
        if should_act:
            # should_act 已保证 > action_threshold，这里只需再区分强弱两档
            if harmony_strength > self.config.strong_action_threshold:
                return ActionType.ACT_CAREFULLY
            return ActionType.ACT_MINIMALLY
        return ActionType.HOLD

    def _determine_attention_focus(
        self,
        action_type: ActionType,
        portfolio_loss: float
    ) -> Tuple[float, AttentionFocus, PortfolioSignal]:
        """确定注意力聚焦因子及分类"""
        base = 1.0
        if action_type == ActionType.HOLD:
            if portfolio_loss < -0.05:
                focus_float = 0.7
            else:
                focus_float = 1.0
        elif action_type == ActionType.ACT_FULLY:
            focus_float = 1.3
        elif action_type == ActionType.ACT_CAREFULLY:
            focus_float = 1.1
        else:
            focus_float = 1.0

        # AttentionFocus 映射
        if action_type == ActionType.ACT_FULLY:
            focus_enum = AttentionFocus.ACCUMULATE
        elif portfolio_loss < -0.1:
            focus_enum = AttentionFocus.STOP_LOSS
        elif portfolio_loss > 0.15:
            focus_enum = AttentionFocus.TAKE_PROFIT
        elif action_type == ActionType.ACT_CAREFULLY:
            focus_enum = AttentionFocus.REBALANCE
        else:
            focus_enum = AttentionFocus.WATCH

        # PortfolioSignal 映射
        if portfolio_loss < -0.05:
            portfolio_signal = PortfolioSignal.STOP_LOSS
        elif portfolio_loss > 0.1:
            portfolio_signal = PortfolioSignal.TAKE_PROFIT
        elif -0.05 <= portfolio_loss < -0.02:
            portfolio_signal = PortfolioSignal.REBALANCE
        elif action_type == ActionType.ACT_FULLY and portfolio_loss >= -0.02:
            portfolio_signal = PortfolioSignal.ACCUMULATE
        else:
            portfolio_signal = PortfolioSignal.NONE

        return focus_float, focus_enum, portfolio_signal

    def _get_awakening_level(self) -> str:
        """获取觉醒等级（调节链里 awakening 环节的输入）

        来源优先级：注入的 provider（见 set_awakening_level_provider）
                    > set_awakening_level() 推入的值 > 内置默认 "dormant"。

        背景（一次典型的静默失效，修于 P3）：
            旧实现是 `from deva.naja.attention import get_awakening_controller`，
            但 **该函数全仓不存在**——ImportError 被 `except Exception: pass` 吞掉，
            于是恒返回 self._awakening_level（默认 "dormant"）。
            表面上"有取数逻辑"，实际是一段永不生效的死代码。

        关于"本仓到底有没有生产者"（P3 事实核查，勿再记错）：
            **有**。`knowledge/alaya/awakened_alaya.py` 的 `AwakeningEngine`
            提供 `get_awakening_level()`，返回四个档位
            （dormant / awakening / illuminated / enlightened）——与
            `ManasConfig.awakening_factors` 是同一套词汇，说明本意就是要接的。
            但当前**三重断点**导致它实际从不生效，任一未解，硬接上去也只是
            又一个恒 DORMANT 的静默 no-op：
              1. manas 从未接线（旧代码指向不存在的函数；本方法即为此加的注入点）；
              2. `TradingCenter._get_awakening_level()` 读的是 `_awakened_state`
                 （另一个从未写入的字典），而不是它自己缓存的
                 `AwakenedAlaya.awakening_engine`；
              3. 所有可达的 `AwakenedAlaya.illuminate()` 调用点都不喂弱信号
                 （`cognition/bridge.py` 新建临时实例、`decision/orchestrator.py`
                 不传 signals），而等级只能靠累积弱信号才会升上去。

            因此 manas 默认 dormant（调节因子 1.0 中性）是**当前事实**，
            但成因是"未接线 + 无信号喂入"，**不是**"没有生产者"。
            接线前须先解决实例生命周期与信号喂入，否则等于加了个常数。

        跨域复用/接入真实觉醒源时，用 set_awakening_level_provider() 补上。
        """
        provider = getattr(self, "_awakening_level_provider", None)
        if provider is not None:
            try:
                level = provider()
                if level:
                    return str(level)
            except Exception as e:  # noqa: BLE001
                log.debug("[ManasEngine] 觉醒等级 provider 失败，回退内置值: %s", e)
        # 兜底也要确保不因属性缺失而把决策路径带崩（本方法在 compute 热路径上，
        # 外面没有 try 包裹）。正常实例两者都在 __init__ 里赋过值。
        return getattr(self, "_awakening_level", "dormant")

    def set_awakening_level(self, level: str):
        """设置觉醒等级（由外部推入，作为 provider 缺失时的回退）"""
        self._awakening_level = level

    def set_awakening_level_provider(self, provider) -> None:
        """注入「觉醒等级」的来源。

        宿主若已有觉醒源（返回等级字符串），在此挂上即可让调节链的 awakening
        环节真正生效；未注入时该环节恒为中性 ×1.0。

            engine.set_awakening_level_provider(lambda: state["awakening_level"])

        provider 抛异常时回退到 set_awakening_level() 推入的值，不影响打分。
        """
        self._awakening_level_provider = provider

    def set_narratives(self, narratives: List[str]):
        """
        设置当前关注的叙事主题

        Args:
            narratives: 叙事主题列表
        """
        self._current_narratives = narratives

    # --- 分数调节链 -------------------------------------------------------
    # compute() 的核心是一条线性乘性管道：
    #   base → regime → narrative_risk → ai_compute → resonance
    #        → awakening → bias → clamp
    # 抽成链是为了让「有哪些调节、按什么顺序」显式可读，而不是埋在长方法里。
    #
    # 环节签名为 f(score, ctx) -> score：返回**新分数**而非乘数。
    # 原因是 regime 环节带一次 min(1.0) 截断，而它的位置是语义的一部分——
    # 「先截到 1.0 再乘后续惩罚因子」与「先乘惩罚因子再截断」结果不同。
    # 若统一挪到链尾做 clamp，快照基线会立刻抓到差异。

    def _build_score_context(self, regime_score: float) -> Dict[str, Any]:
        """构造调节链所需的只读上下文

        bias_state / bias_correction 由 bias 环节回填（该环节有两个输出）。
        """
        state = self._cognitive_state
        return {
            "regime_score": regime_score,
            "narrative_risk": state.narrative.risk,
            "ai_compute_trend": state.ai_compute.trend,
            "ai_compute_strength": state.ai_compute.strength,
            "resonance_score": state.resonance.score,
            "resonance_sentiment": state.resonance.sentiment,
            "awakening_level": self._get_awakening_level(),
            "bias_state": BiasState.NEUTRAL,
            "bias_correction": 1.0,
        }

    def _score_modifier_chain(self):
        """按施加顺序返回 (名称, 调节函数) 序列"""
        return (
            ("regime", self._modifier_regime),
            ("narrative_risk", self._modifier_narrative_risk),
            ("ai_compute", self._modifier_ai_compute),
            ("resonance", self._modifier_resonance),
            ("awakening", self._modifier_awakening),
            ("bias", self._modifier_bias),
        )

    def _modifier_regime(self, score, ctx):
        """地势折扣：regime [-1,1] 映射为 [0.7,1.0] 的乘性折扣，随后截断到 1.0

        注意这里的 min(1.0) 是**中间截断**，不是链尾 clamp，位置不可挪动。
        """
        cfg = self.config
        regime_factor = (ctx["regime_score"] + 1) / 2
        return min(1.0, score * (cfg.regime_discount_floor + regime_factor * cfg.regime_discount_span))

    def _modifier_narrative_risk(self, score, ctx):
        """叙事风险折扣：超过阈值后按超出量线性打折"""
        cfg = self.config
        narrative_risk = ctx["narrative_risk"]
        if narrative_risk > cfg.narrative_risk_threshold:
            return score * (1.0 - (narrative_risk - cfg.narrative_risk_threshold) * cfg.narrative_risk_slope)
        return score

    def _modifier_ai_compute(self, score, ctx):
        """AI 算力加成：仅上升趋势且强度过阈值时加成"""
        cfg = self.config
        trend = ctx["ai_compute_trend"]
        strength = ctx["ai_compute_strength"]
        if trend == "up" and strength > cfg.ai_compute_strength_threshold:
            bonus = 1.0 + (strength - cfg.ai_compute_strength_threshold) * cfg.ai_compute_bonus_slope
            log.debug(
                f"[ManasEngine] AI算力加成: trend={trend}, "
                f"strength={strength:.2f}, bonus={bonus:.2f}"
            )
            return score * bonus
        return score

    def _modifier_resonance(self, score, ctx):
        """共振加成/惩罚：强度过阈值才生效，方向由情绪决定"""
        cfg = self.config
        r_score = ctx["resonance_score"]
        sentiment = ctx["resonance_sentiment"]
        if r_score >= cfg.resonance_score_threshold:
            if sentiment >= cfg.resonance_sentiment_threshold:
                bonus = 1.0 + min(
                    cfg.resonance_bonus_cap,
                    (r_score - cfg.resonance_score_threshold) * cfg.resonance_bonus_slope,
                )
                log.debug(
                    f"[ManasEngine] 共振正向加成: score={r_score:.2f}, bonus={bonus:.2f}"
                )
                return score * bonus
            elif sentiment <= -cfg.resonance_sentiment_threshold:
                penalty = 1.0 - min(
                    cfg.resonance_penalty_cap,
                    (r_score - cfg.resonance_score_threshold) * cfg.resonance_bonus_slope,
                )
                log.debug(
                    f"[ManasEngine] 共振负向惩罚: score={r_score:.2f}, penalty={penalty:.2f}"
                )
                return score * penalty
        return score

    def _modifier_awakening(self, score, ctx):
        """觉醒加成（档位见 ManasConfig.awakening_factors）"""
        factor = self.config.awakening_factors.get(ctx["awakening_level"], 1.0)
        return score * factor

    def _modifier_bias(self, score, ctx):
        """偏差纠偏，并把 (bias_state, bias_correction) 回填到 ctx

        激进度样本传 score（链上前序环节的结果）是**有意设计**：
        它代表「本次决策有多激进」，而不是原始 manas 分数。
        """
        bias_state, correction = self.meta_manas.detect_and_correct(
            self._recent_pnl, score
        )
        ctx["bias_state"] = bias_state
        ctx["bias_correction"] = correction
        return score * correction

    def compute(
        self,
        session_manager=None,
        portfolio=None,
        scanner=None,
        bandit_tracker=None,
        macro_signal: float = 0.5,
        narratives: List[str] = None,
    ) -> ManasOutput:
        """
        计算末那识输出

        使用三维融合逻辑：
        1. 天时 (timing) + 地势 (risk) + 人和 (confidence)
        2. 结合环境状态 (regime)
        3. 叙事风险折扣
        4. AI算力影响
        5. 觉醒加成
        6. 偏差纠偏

        Args:
            session_manager: TradingClock/MarketSessionManager
            portfolio: VirtualPortfolio
            scanner: GlobalMarketScanner
            bandit_tracker: BanditPositionTracker
            macro_signal: 宏观流动性信号
            narratives: 当前叙事主题列表（从 NarrativeTracker 获取）

        Returns:
            ManasOutput: 末那识决策输出
        """
        current_time = time.time()
        if current_time - self._last_update < self._update_interval and self._last_output is not None:
            return self._last_output

        if narratives is not None:
            self._current_narratives = narratives

        # 每轮只取一次持仓汇总，供风险引擎与后续仓位损失计算复用
        portfolio_summary = None
        if portfolio is not None and hasattr(portfolio, 'get_summary'):
            try:
                portfolio_summary = portfolio.get_summary()
            except Exception:
                portfolio_summary = None

        timing_score = self.timing_engine.compute(session_manager, scanner)
        regime_score = self.regime_engine.compute(scanner, macro_signal)
        confidence_score = self.confidence_engine.compute(bandit_tracker)
        risk_temperature = self.risk_engine.compute(portfolio, scanner, summary=portfolio_summary)

        harmony_state = self._determine_harmony_state(risk_temperature, timing_score, regime_score)

        ctx = self._build_score_context(regime_score)

        # 基础分：天时 + 地势（风险温度的反函数）+ 人和
        cfg = self.config
        harmony_strength = (
            timing_score * cfg.weight_timing +
            (1.0 - min(risk_temperature, cfg.risk_temperature_span) / cfg.risk_temperature_span)
            * cfg.weight_risk +
            confidence_score * cfg.weight_confidence
        )

        # 依次施加调节环节：地势 / 叙事风险 / AI算力 / 共振 / 觉醒 / 偏差
        # （认知层状态为事件驱动更新，见 _update_cognitive_state）
        for _name, modifier in self._score_modifier_chain():
            harmony_strength = modifier(harmony_strength, ctx)

        harmony_strength = max(0.0, min(1.0, harmony_strength))

        narrative_risk = ctx["narrative_risk"]
        hot_narratives = self._cognitive_state.narrative.hot_narratives
        awakening_level = ctx["awakening_level"]
        bias_state = ctx["bias_state"]
        bias_correction = ctx["bias_correction"]

        action_type = self._determine_action_type(harmony_state, harmony_strength, timing_score)
        should_act = action_type != ActionType.HOLD

        # bias_correction 已在上方作用于 harmony_strength，这里不再重复相乘。
        # 原写法 alpha = ... * harmony_strength * bias_correction 等于对纠偏系数
        # 取平方（惧首轮 0.5 → 0.25，直接撞 clamp 下限 0.3），与 docstring
        # 「贪时 reduce α」的单次语义不符。
        alpha = confidence_score * harmony_strength
        alpha = max(cfg.alpha_min, min(cfg.alpha_max, alpha))

        portfolio_loss = 0.0
        if portfolio:
            try:
                if hasattr(portfolio, 'get_summary'):
                    summary = portfolio_summary if portfolio_summary is not None else portfolio.get_summary()
                    raw_return = summary.get('total_return', 0.0) or 0.0
                elif isinstance(portfolio, dict):
                    raw_return = portfolio.get('total_return', 0.0) or 0.0
                else:
                    raw_return = 0.0
                # PortfolioView 契约的 total_return 是**百分数**（生产实现
                # VirtualPortfolio 及其 UI、state.py 都是百分数口径），
                # 而 _determine_attention_focus 的阈值是小数
                # （-0.05 / -0.1 / 0.15）。这里统一归一到小数。
                portfolio_loss = raw_return / 100.0
            except Exception as e:
                log.debug("manas: 抑制异常并回退默认值: %s", e)
                pass

        market_deterioration = risk_temperature > cfg.market_deterioration_temperature

        attention_focus, focus_enum, portfolio_signal = self._determine_attention_focus(action_type, portfolio_loss)

        # 🚀 自选股注意力加成
        watchlist_bonus = self._cognitive_state.watchlist.bonus
        if watchlist_bonus > 1.0:
            attention_focus *= watchlist_bonus
            log.debug(f"[ManasEngine] 自选股注意力加成: bonus={watchlist_bonus:.2f}")

        reason = self._get_gate_reason(harmony_strength, timing_score, regime_score, confidence_score, bias_state, harmony_state, action_type)

        supply_chain_risk = self._cognitive_state.narrative.level

        # AI 算力方向取认知层推断出的 trend（up / down / neutral）。
        # 原先 compute() 压根没给这个字段赋值，to_dict() 又漏了它，
        # 两处叠加导致下游 KernelOutput.ai_compute_direction 恒为 "unknown"。
        ai_compute_direction = self._cognitive_state.ai_compute.trend

        output = ManasOutput(
            manas_score=harmony_strength,
            timing_score=timing_score,
            regime_score=regime_score,
            confidence_score=confidence_score,
            risk_temperature=risk_temperature,
            should_act=should_act,
            action_gate_reason=reason,
            bias_state=bias_state,
            bias_correction=bias_correction,
            alpha=alpha,
            attention_focus=attention_focus,
            narrative_risk=narrative_risk,
            hot_narratives=hot_narratives,
            supply_chain_risk_level=supply_chain_risk,
            ai_compute_direction=ai_compute_direction,
            awakening_level=awakening_level,
            harmony_state=harmony_state,
            harmony_strength=harmony_strength,
            action_type=action_type,
            portfolio_loss_pct=max(-1.0, min(1.0, portfolio_loss)),
            market_deterioration=market_deterioration,
            focus_enum=focus_enum,
            portfolio_signal=portfolio_signal,
        )

        self._last_output = output
        self._last_update = current_time

        # 行动门留痕（旁路：失败只降级为「少一条记录」，绝不影响决策）
        self._record_gate_audit(output)

        return output

    def _record_gate_audit(self, output: "ManasOutput") -> None:
        """把本次判定留给行动门审计，见 manas_gate_audit.py。

        `action_gate_reason` 是每次 compute 都会生成的一句「为什么不让你动」，
        在风控语境里就是天然的可解释留痕。此前它随 UI 输出即逝。
        """
        try:
            from .manas_gate_audit import get_gate_audit_log
            get_gate_audit_log().record(output)
        except Exception as e:  # noqa: BLE001
            log.debug("[ManasEngine] 行动门留痕失败: %s", e)

    def _get_gate_reason(
        self,
        manas_score: float,
        timing: float,
        regime: float,
        confidence: float,
        bias: BiasState,
        harmony_state: HarmonyState,
        action_type: ActionType
    ) -> str:
        """生成行动门原因"""
        reasons = []

        if harmony_state == HarmonyState.RESISTANCE:
            reasons.append("环境阻力")
        elif harmony_state == HarmonyState.RESONANCE:
            reasons.append("和谐共振")

        if timing < 0.3:
            reasons.append("时机不佳")
        elif timing > 0.7:
            reasons.append("时机成熟")

        if regime < -0.3:
            reasons.append("逆风环境")
        elif regime > 0.3:
            reasons.append("顺风环境")

        if confidence > 0.8:
            reasons.append("策略自信")
        elif confidence < 0.4:
            reasons.append("策略不自信")

        if bias == BiasState.GREED:
            reasons.append("⚠️检测到贪")
        elif bias == BiasState.FEAR:
            reasons.append("⚠️检测到惧")

        reasons.append(f"行动:{action_type.value}")

        # 与 compute() 中 should_act 的判定保持一致：_determine_action_type 的共振通道
        # 可绕过分数门槛，若这里仍只比分数就会出现「should_act=True 但理由显示✗未通过」。
        gate_passed = action_type != ActionType.HOLD
        if gate_passed:
            reasons.append("✓通过")
            if manas_score <= self.config.action_threshold:
                reasons.append(
                    f"(分数{manas_score:.2f}≤{self.config.action_threshold}，由共振/强时机豁免)"
                )
        else:
            reasons.append("✗未通过")

        return " | ".join(reasons)

    def record_pnl(self, pnl_pct: float):
        """记录盈亏（用于 MetaManas 偏差检测）"""
        self._recent_pnl.append(pnl_pct)

    def get_state(self) -> Dict[str, Any]:
        """获取末那识状态"""
        if self._last_output is None:
            return {"status": "not_initialized"}

        return self._last_output.to_dict()

    def reset_bias(self):
        """重置偏差状态"""
        self.meta_manas.bias_state = BiasState.NEUTRAL
        log.info("[ManasEngine] 偏差状态已重置")
