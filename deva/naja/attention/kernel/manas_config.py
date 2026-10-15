"""
末那识的可调参数（ManasConfig）与滑窗原语（RollingWindow）

================================================================================
为什么要有这个文件
================================================================================

重构前，manas_engine.py 里的策略参数以字面量形式散落在各方法中：

    harmony_strength = timing * 0.4 + risk * 0.35 + confidence * 0.25
    if narrative_risk > 0.6: score *= (1.0 - (narrative_risk - 0.6) * 0.5)
    if harmony_strength > 0.5: ... elif > 0.6: ...

以及 5 处形态一致的滑动窗口：

    self._xxx.append(v)
    if len(self._xxx) > 20:
        self._xxx.pop(0)

结果是：想调一个阈值得先读懂整条链路；想开一份"更保守"的参数做对比实验，
只能复制整个类。现在这些旋钮集中在这里，滑窗逻辑收敛成 RollingWindow。

================================================================================
边界：什么进 config，什么不进
================================================================================

进 config 的是**策略旋钮**——改动它们会改变"系统怎么决策"：
融合权重、行动门槛、调节链系数、纠偏阈值、窗口长度。

不进 config 的是**特征分档字面量**——它们描述"数据长什么样"，
与策略松耦合，且只在子引擎内部出现一次：
    - TimingEngine 的时间压力档位（剩余 <900s → 0.3 等）
    - ConfidenceEngine 的 bandit 交易数分档（<5 / <20 / <50）
    - RiskEngine 的回撤/波动分档（>0.1 / >0.05 / >2.0）
    - 认知事件的平滑系数（旧值 0.7 + 新值 0.3 那一类）

把它们也搬进来只会得到一个 60 字段、没人读得完的 config。
"""
from dataclasses import dataclass, field
from typing import Dict


class RollingWindow:
    """固定长度滑动窗口：append 后自动裁剪到 maxlen

    此前 5 处窗口各自写一遍 append + pop(0)，其中 2 处还是只写不读的死字段
    （RegimeEngine._trend_history / TimingEngine._trade_density_history 等，
    已在本次重构中删除）。
    """

    __slots__ = ("_items", "maxlen")

    def __init__(self, maxlen: int, items=None):
        if maxlen <= 0:
            raise ValueError(f"maxlen 必须为正，收到 {maxlen}")
        self.maxlen = maxlen
        self._items = list(items or [])[-maxlen:]

    def append(self, value):
        """追加一个样本，超出 maxlen 时丢弃最旧的一个"""
        self._items.append(value)
        if len(self._items) > self.maxlen:
            del self._items[0]
        return self

    @property
    def items(self) -> list:
        """当前样本的副本"""
        return list(self._items)

    def tail(self, n: int) -> list:
        """最近 n 个样本（不足则全部）"""
        return self._items[-n:]

    def mean(self, n: int = None) -> float:
        """均值；n 为 None 时取整个窗口。空窗口返回 0.0"""
        xs = self._items[-n:] if n else self._items
        return sum(xs) / len(xs) if xs else 0.0

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __repr__(self):
        return f"RollingWindow({self._items}, maxlen={self.maxlen})"


def _default_awakening_factors() -> Dict[str, float]:
    """觉醒等级 → 分数乘数。未列出的等级为 1.0（不加成）"""
    return {
        "enlightened": 1.15,
        "illuminated": 1.10,
        "awakening": 1.05,
    }


@dataclass(frozen=True)
class ManasConfig:
    """末那识决策层参数（默认值即重构前的线上取值）

    冻结（frozen）是为了避免运行期被某个环节悄悄改掉；
    需要另一套参数时新建一个实例传入 ManasEngine(config=...)。
    """

    # ── 三维融合权重（天时 / 地势 / 人和）────────────────────
    weight_timing: float = 0.4
    weight_risk: float = 0.35
    weight_confidence: float = 0.25
    # 风险温度的反函数分母：T 越大越保守，1 - min(T, span)/span
    risk_temperature_span: float = 1.5

    # ── 行动门槛 ─────────────────────────────────────────────
    # 分数通道：> action_threshold 才行动，> strong_action_threshold 为强档
    action_threshold: float = 0.5
    strong_action_threshold: float = 0.6
    # 共振通道：RESONANCE 且时机分 > 此值 → ACT_FULLY，不看分数
    resonance_timing_threshold: float = 0.7

    # ── 人的意愿 → 门槛放宽（有限、可回滚）────────────────────
    # 背景：`intents.json` 里人下达的意愿强度（confidence）此前只被写进
    # market_state['signal_confidence'] 就再没人读 —— 权重恒 0，写 0.65 与
    # 写 0.10 得到逐字相同的裁定。这里把它接上，但**不是**让它直接加分，
    # 而是允许它在**有限幅度**内下调「分数通道」的门槛，即
    # 「人越想要，环境得有多好才放行」这条线越低。
    #
    # 三条硬边界（都有守卫盯着）：
    #   1. 只削分数通道门槛；strong_action_threshold 与共振通道都不动。
    #   2. 放宽量有**硬顶** intent_relax_max —— 门槛 0.5 最低只降到 0.35，
    #      绝不出现「因为人想买就把门槛砍到近乎为 0」。
    #   3. HarmonyState.RESISTANCE（风险温度 > 1.4 或逆风 regime < -0.5）
    #      时**一律不生效** —— 环境说"不"的时候，意愿穿透不过去。
    # 设计取舍见 docs/naja/ 与 .workbuddy/memory（意愿接线定案）。
    intent_relax_enabled: bool = True
    intent_relax_min: float = 0.5        # 意愿低于此值完全不参与放宽
    intent_relax_full: float = 0.75      # 意愿到此值拿满放宽额度（= clamp_confidence 硬顶）
    intent_relax_max: float = 0.15       # 放宽上限（硬顶）

    # ── 和谐状态判定 ─────────────────────────────────────────
    harmony_resistance_temperature: float = 1.4   # T 高于此值 → RESISTANCE
    harmony_resistance_regime: float = -0.5       # regime 低于此值 → RESISTANCE
    harmony_resonance_temperature: float = 0.8    # 以下三者同时满足 → RESONANCE
    harmony_resonance_timing: float = 0.6
    harmony_resonance_regime: float = 0.2

    # ── 调节链系数 ───────────────────────────────────────────
    # 地势折扣：regime ∈ [-1,1] → [floor, floor+span] 的乘性折扣
    regime_discount_floor: float = 0.7
    regime_discount_span: float = 0.3
    # 叙事风险：超过阈值后按超出量 × slope 打折
    narrative_risk_threshold: float = 0.6
    narrative_risk_slope: float = 0.5
    # AI 算力加成：上升趋势且强度过阈值才生效
    ai_compute_strength_threshold: float = 0.6
    ai_compute_bonus_slope: float = 0.3
    # 天-地共振：强度过阈值后按情绪方向加成/惩罚
    resonance_score_threshold: float = 0.7
    resonance_sentiment_threshold: float = 0.2    # 正向 ≥ +x，负向 ≤ -x
    resonance_bonus_slope: float = 0.2
    resonance_bonus_cap: float = 0.10
    resonance_penalty_cap: float = 0.08
    awakening_factors: Dict[str, float] = field(default_factory=_default_awakening_factors)

    # ── 输出归一 ─────────────────────────────────────────────
    alpha_min: float = 0.3
    alpha_max: float = 1.5
    market_deterioration_temperature: float = 1.3  # T 高于此值 → 市场恶化标记

    # ── 观照层（MetaManas 偏差检测）──────────────────────────
    aggressiveness_window: int = 10       # 激进度样本窗口
    bias_min_samples: int = 5             # 盈亏样本不足此数不判偏差（暖机）
    greed_recent_avg: float = 0.05        # 近 5 笔均盈 > 此值
    greed_overall_avg: float = 0.03       # 且整体均盈 > 此值
    greed_aggressiveness: float = 0.6     # 且平均激进度 > 此值 → 判"贪"
    fear_recent_avg: float = -0.03        # 近 5 笔均盈 < 此值
    fear_losses: int = 3                  # 且近 5 笔中亏损 ≥ 此笔数 → 判"惧"
    neutral_band: float = 0.02            # |近 5 笔均盈| < 此值 → 回归中性
    correction_greed: float = 0.7         # 贪：抑制（乘性折扣）
    correction_fear: float = 0.5          # 惧：首轮促使行动
    correction_fear_steady: float = 0.8   # 惧：稳态

    # ── 滑动窗口长度 ─────────────────────────────────────────
    pnl_window: int = 20                  # 最近盈亏（观照层样本源）
    volatility_window: int = 20           # 波动率历史
    hit_rate_window: int = 10             # 命中率历史
    drawdown_window: int = 10             # 回撤历史
    volatility_sample: int = 5            # 波动率自适应权重取的近期样本数

    # ── 其它 ─────────────────────────────────────────────────
    update_interval: float = 1.0          # compute() 结果缓存秒数
