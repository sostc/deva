"""IntradayDeviation——日内偏离度判据（做 T 的"该不该动"闸门）

别名/关键词: 日内偏离、VWAP、振幅、摩擦成本、做T信号、intraday deviation

为什么不用「预测涨跌」来驱动做 T
----------------------------------
前一晚查证过一个活生生的反例（2026-10-13）：

* 流动性传导模型预测「A 股今日下跌」→ **错了**（上证收 +0.10%）。
* 但同一天科创芯片指数低开 -3%、盘中砸到 -4.29%、V 型拉到 +1.56%，
  振幅 5.85%，**做 T 的人白捡 6%**。

结论：**方向预测可以全错，做 T 照样赚钱。** 因为两者赚的不是同一笔钱——
方向预测赚"明天的钱"，做 T 赚"当下偏离均值回归的钱"。
后者的判据不需要预测未来，只需要回答一个当下可验证的问题：

    「此刻的价格，相对今天的成交重心，偏离得够不够多？」

所以本模块**刻意不接入任何方向/传导预测**。输入只有行情本身。

★ 为什么均值回归的锚必须是「昨收」而不是 VWAP
----------------------------------------------
第一版拿 VWAP 当主锚，跑今天（2026-10-13 科创芯片）真实行情，结果是 **0 次触发**。
事后逐层拆闸门，发现是两个独立缺陷叠加，别混为一谈：

**缺陷一：VWAP 会跟着价格漂移（今天实测低估 7.6 倍）**

    price=3208 时：相对昨收 -4.23%，相对 VWAP 只有 -0.56%。

低开低走的日子里 VWAP 一路跟着价格下移，于是"相对成交重心的偏离"始终很小 ——
明明已经跌了 4%，指标却说"挺接近重心"。
**用一个跟着被测对象跑的指标做均值回归的锚，本身就是错的。**
落到净空间上差距更致命：0.41% vs 1.97%，前者几乎擦着 0.35% 的门槛过不去。

**缺陷二：趋势保护判据用错了尺度（这才是那次 0 次触发的直接原因）**

当时写的是"连续 N 根（默认 6）阴线就不低吸"。可在分钟级分时上，
**任何一段像样的下跌都是几十根连续阴线**，等于永久禁止低吸。
正确的做法是反过来：要求连跌**已被打断**（详见 require_stabilize），
即"我已经不再下跌了"，而不是"我跌得太久所以不许买"。

修正后：锚换成外生的昨收，VWAP 降级为方向确认；趋势保护改成右侧确认。
保守起见预期空间也不假设走满全程：``|ret| × reversion_ratio``（默认只算回归一半）。

闸门是三重的
-----------
1. **偏离度**：相对**昨收**的偏离必须够大，且相对 VWAP 方向一致。
2. **振幅**：当日振幅不足说明今天是死水，回归空间撑不起成本。
3. **摩擦成本**：这是最容易被忽略、却最致命的一环。
   场内 ETF 免印花税，但仍要付双边佣金 + 双边滑点。空间小于成本时做 T
   **不是在降成本，是在给券商打工**。

    round_trip_cost = 2 × (commission + slippage) + stamp_duty

   只有 ``|deviation| - round_trip_cost > min_net_edge`` 才发信号。

保守默认：宁可不发
------------------
- 样本不足时不发（VWAP 早期不稳，容易假信号）。
- 连续单边下跌时不发低吸（trend guard —— 防止在下跌趋势里接飞刀）。
- 临近收盘不发新的倒 T（没时间买回，会逼出追高）。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

ACTION_NONE = "NONE"
#: 正 T 的低吸腿（先买），以及对应的了结腿。需要底仓 + 备用资金。
ACTION_BUY_T = "BUY_T"
#: 倒 T 的高抛腿（先卖），以及对应的买回腿。会产生回购义务。
ACTION_SELL_T = "SELL_T"


@dataclass
class IntradayBar:
    """一根分时数据点。"""

    timestamp: float
    price: float
    volume: float = 0.0
    amount: float = 0.0


@dataclass
class RotationThresholds:
    """做 T 触发参数。

    默认值按 **场内 ETF** 标定（免印花税）。若标的是个股，
    请把 ``stamp_duty_pct`` 改成 0.05。
    """

    # --- 摩擦成本 ---
    commission_pct: float = 0.025   # 单边佣金 %（万2.5）
    slippage_pct: float = 0.05      # 单边滑点 %
    stamp_duty_pct: float = 0.0     # 卖出单边印花税 %（ETF=0，股票=0.05）
    min_commission: float = 5.0     # 单笔最低佣金（元），小额定投时占比很高

    # --- 触发闸门 ---
    #: 相对**昨收**的偏离阈值(%)。这是主锚，理由见模块 docstring「为什么锚必须是昨收」
    buy_dev_close: float = 1.5
    sell_dev_close: float = 1.5
    #: 相对 VWAP 也需偏低/偏高才算数(%)。0 表示只要求低于/高于当日重心
    buy_dev_vwap: float = 0.0
    sell_dev_vwap: float = 0.0
    #: 保守假设价格只回归偏离的一半。这是 estimates，不能假设走满全程
    reversion_ratio: float = 0.5
    min_amplitude: float = 1.0      # 当日振幅下限(%)，低于此值视为死水
    min_net_edge: float = 0.35      # 扣除往返成本后仍要求的净空间(%)
    min_samples: int = 15           # VWAP 预热所需样本数

    # --- 风控 ---
    #: 右侧确认：低吸前连跌必须已被打断，高抛前连涨必须已被打断。
    #: **不等极值，等转折**——省下的那一点点收益，远不及接飞刀的代价。
    #: 设为 False 则变成无条件抄最后一根 Turkey tail
    require_stabilize: bool = True
    #: 企稳要**连续几根 bar** 才算数（配合 require_stabilize 使用）。
    #: ❗曾经只要求「最后一根没跌」：轮询默认 30 秒一根，那等于只确认了
    #: **30 秒**没创新低 —— 在真正的下跌里，30 秒的喘息毫无意义，
    #: 这是接飞刀的主敞口。2026-10-14 收紧为 3 根（约 90 秒）。
    stabilize_bars: int = 3
    #: 相对昨收偏离超过此值(%)时不动手。极端偏离通常意味着基本面事件
    #: （停牌、退市风险、政策黑天鹅），均值回归的假设不再成立
    max_dev_close: float = 8.0
    no_new_sell_before_close_min: int = 30  # 收盘前 N 分钟不新开倒 T
    min_bars_between_actions: int = 3       # 两次动作之间的最小间隔（bar 数）

    def round_trip_cost_pct(self) -> float:
        """一次完整做 T（买+卖）的往返摩擦成本百分比。"""
        return (
            2 * (self.commission_pct + self.slippage_pct) + self.stamp_duty_pct
        )

    def validate(self) -> List[str]:
        """返回非法项。坏值要在启动时就暴露，不要等到实盘。"""
        errs = []
        if self.commission_pct < 0:
            errs.append("commission_pct 不能为负")
        if self.slippage_pct < 0:
            errs.append("slippage_pct 不能为负")
        if self.stamp_duty_pct < 0:
            errs.append("stamp_duty_pct 不能为负")
        if self.buy_dev_close <= 0 or self.sell_dev_close <= 0:
            errs.append("相对昨收的偏离阈值必须为正")
        if not 0 < self.reversion_ratio <= 1.0:
            errs.append("reversion_ratio 必须在 (0, 1] 内，1.0 表示假设完全回归")
        if self.min_amplitude < 0:
            errs.append("min_amplitude 不能为负")
        if self.min_net_edge < 0:
            errs.append("min_net_edge 不能为负")
        if self.min_samples < 2:
            errs.append("min_samples 至少为 2")
        if self.stabilize_bars < 1:
            errs.append("stabilize_bars 至少为 1")
        if self.max_dev_close <= max(self.buy_dev_close, self.sell_dev_close):
            errs.append("max_dev_close 必须大于触发阈值，否则永远不会触发")
        if self.round_trip_cost_pct() > 1.0:
            errs.append(
                f"往返成本 {self.round_trip_cost_pct():.2f}% 异常高，参数可能填错"
            )
        return errs


@dataclass
class DeviationSnapshot:
    """某个时刻的日内偏离度视图。"""

    stock_code: str
    last: float = 0.0
    open: float = 0.0
    prev_close: float = 0.0
    high: float = 0.0
    low: float = 0.0
    vwap: float = 0.0
    #: 相对 VWAP 偏离 %
    dev_vwap: float = 0.0
    #: 相对今日开盘偏离 %
    dev_open: float = 0.0
    #: 相对昨收涨跌 %
    ret: float = 0.0
    #: 当日振幅 (high-low)/prev_close %
    amplitude: float = 0.0
    #: 跳空 gap = open/prev_close - 1，%
    gap: float = 0.0
    #: 连续下行 bar 数，用于趋势保护
    consecutive_down: int = 0
    #: 连续上行 bar 数，与 consecutive_down 对称
    consecutive_up: int = 0
    #: ❗自最近一次**创新低**以来经过的 bar 数 —— 低吸的企稳确认口径。
    #: 比 consecutive_up 严格：价格持平也算「没创新低」，一样计入。
    bars_since_low: int = 0
    #: 自最近一次**创新高**以来经过的 bar 数 —— 高抛的回落确认口径
    bars_since_high: int = 0
    samples: int = 0
    timestamp: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "last": self.last,
            "open": self.open,
            "prev_close": self.prev_close,
            "high": self.high,
            "low": self.low,
            "vwap": self.vwap,
            "dev_vwap": self.dev_vwap,
            "dev_open": self.dev_open,
            "ret": self.ret,
            "amplitude": self.amplitude,
            "gap": self.gap,
            "consecutive_down": self.consecutive_down,
            "bars_since_low": self.bars_since_low,
            "bars_since_high": self.bars_since_high,
            "samples": self.samples,
            "timestamp": self.timestamp,
            "extra": dict(self.extra),
        }


@dataclass
class RotationSignal:
    """一次做 T 信号。 action == NONE 表示不动。"""

    stock_code: str
    action: str = ACTION_NONE
    reason: str = ""
    price: float = 0.0
    #: 相对昨收的偏离 % —— 这是主判据所用的锚
    ret: float = 0.0
    dev_vwap: float = 0.0
    amplitude: float = 0.0
    #: 扣除往返成本后的预期净空间 %
    net_edge: float = 0.0
    #: 往返摩擦成本 %
    cost_pct: float = 0.0
    confidence: float = 0.0
    snapshot: Dict[str, Any] = field(default_factory=dict)

    @property
    def actionable(self) -> bool:
        return self.action != ACTION_NONE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "action": self.action,
            "reason": self.reason,
            "price": self.price,
            "ret": self.ret,
            "dev_vwap": self.dev_vwap,
            "amplitude": self.amplitude,
            "net_edge": self.net_edge,
            "cost_pct": self.cost_pct,
            "confidence": self.confidence,
            "actionable": self.actionable,
            "snapshot": dict(self.snapshot),
        }


class IntradayDeviationTracker:
    """维护日内行情序列并给出偏离度画像。

    本类**纯计算、无副作用、不下单**。它是可被人肉复算的：
    给它同一串 bar，输出的 snapshot 必然一致。
    """

    def __init__(self, stock_code: str, max_bars: int = 4000):
        self.stock_code = stock_code
        self._bars: List[IntradayBar] = []
        self._max_bars = max_bars
        self._prev_close: float = 0.0
        self._open: float = 0.0
        self._high: float = 0.0
        self._low: float = 0.0
        self._cum_vol: float = 0.0
        self._cum_amount: float = 0.0
        self._consecutive_down: int = 0
        self._consecutive_up: int = 0
        self._bars_since_low: int = 0
        self._bars_since_high: int = 0

    # ------------------------------------------------------------------
    def set_prev_close(self, prev_close: float):
        """昨收。这是所有百分比的基准，缺失则整个模块无意义，必须显式给。"""
        self._prev_close = float(prev_close or 0.0)

    @property
    def prev_close(self) -> float:
        return self._prev_close

    def update(self, price: float, timestamp: Optional[float] = None,
               volume: float = 0.0, amount: float = 0.0) -> DeviationSnapshot:
        """喂入一个新价格，返回更新后的偏离度快照。"""
        ts = time.time() if timestamp is None else timestamp
        price = float(price)
        bar = IntradayBar(timestamp=ts, price=price, volume=volume, amount=amount)

        if not self._bars:
            self._open = price
            self._high = price
            self._low = price
        else:
            prev_price = self._bars[-1].price
            # ❗必须先判「这一根有没有创新低/新高」再更新 high/low。
            # 顺序反了的话极值会被自己刷新，计数永远是 0，企稳闸形同虚设。
            new_low = price <= self._low
            new_high = price >= self._high
            if price < prev_price:
                self._consecutive_down += 1
                self._consecutive_up = 0
            elif price > prev_price:
                self._consecutive_down = 0
                self._consecutive_up += 1
            self._high = max(self._high, price)
            self._low = min(self._low, price)
            self._bars_since_low = 0 if new_low else self._bars_since_low + 1
            self._bars_since_high = 0 if new_high else self._bars_since_high + 1

        self._bars.append(bar)
        self._cum_vol += volume
        self._cum_amount += amount if amount > 0 else price * volume

        if len(self._bars) > self._max_bars:
            dropped = self._bars[: len(self._bars) - self._max_bars]
            self._bars = self._bars[len(self._bars) - self._max_bars :]
            # 滚动窗口内保持 high/low 正确：重新计算而非只增不减
            self._high = max(b.price for b in self._bars)
            self._low = min(b.price for b in self._bars)

        return self.snapshot()

    # ------------------------------------------------------------------
    @property
    def vwap(self) -> float:
        """成交量加权均价。无成交量数据时退化为算术均价。"""
        if not self._bars:
            return 0.0
        if self._cum_vol > 0:
            return self._cum_amount / self._cum_vol
        return sum(b.price for b in self._bars) / len(self._bars)

    def snapshot(self) -> DeviationSnapshot:
        if not self._bars:
            return DeviationSnapshot(stock_code=self.stock_code)

        last = self._bars[-1].price
        vwap = self.vwap
        prev = self._prev_close

        dev_vwap = (last - vwap) / vwap * 100 if vwap > 0 else 0.0
        dev_open = (last - self._open) / self._open * 100 if self._open > 0 else 0.0
        ret = (last - prev) / prev * 100 if prev > 0 else 0.0
        amplitude = (self._high - self._low) / prev * 100 if prev > 0 else 0.0
        gap = (self._open - prev) / prev * 100 if prev > 0 else 0.0

        return DeviationSnapshot(
            stock_code=self.stock_code,
            last=last,
            open=self._open,
            prev_close=prev,
            high=self._high,
            low=self._low,
            vwap=vwap,
            dev_vwap=dev_vwap,
            dev_open=dev_open,
            ret=ret,
            amplitude=amplitude,
            gap=gap,
            consecutive_down=self._consecutive_down,
            consecutive_up=self._consecutive_up,
            bars_since_low=self._bars_since_low,
            bars_since_high=self._bars_since_high,
            samples=len(self._bars),
            timestamp=self._bars[-1].timestamp,
        )

    def reset_session(self, prev_close: Optional[float] = None):
        """新交易日重置。prev_close 不传则沿用上一次的。"""
        self._bars.clear()
        self._open = 0.0
        self._high = 0.0
        self._low = 0.0
        self._cum_vol = 0.0
        self._cum_amount = 0.0
        self._consecutive_down = 0
        self._consecutive_up = 0
        self._bars_since_low = 0
        self._bars_since_high = 0
        if prev_close is not None:
            self._prev_close = float(prev_close)

    @property
    def bar_count(self) -> int:
        return len(self._bars)


def evaluate_deviation(
    snapshot: DeviationSnapshot,
    thresholds: RotationThresholds,
    now: Optional[float] = None,
    minutes_to_close: Optional[float] = None,
    bars_since_last_action: int = 999,
) -> RotationSignal:
    """把偏离度快照翻译成要不要动手。

    这是整个模块唯一对外输出的判断，所有闸门集中在此，便于逐个对人复算。

    Args:
        snapshot: 当前偏离度画像
        thresholds: 触发参数
        now: 当前时间
        minutes_to_close: 距收盘分钟数。**不知道就传 None**，
            此时临近收盘的倒 T 闸门失效 —— 调用方会被要求显式提供，
            因为"距离收盘还有多久"无法从 bar 里可靠推断。
        bars_since_last_action: 距上次动作的 bar 间隔

    Returns:
        RotationSignal —— action == NONE 时 reason 里写明**为什么不发**，
        空理由的拒绝同样是静默失效。
    """
    base = RotationSignal(
        stock_code=snapshot.stock_code,
        price=snapshot.last,
        ret=snapshot.ret,
        dev_vwap=snapshot.dev_vwap,
        amplitude=snapshot.amplitude,
        cost_pct=thresholds.round_trip_cost_pct(),
        snapshot=snapshot.to_dict(),
    )

    # 闸门 0：数据够不够
    if snapshot.last <= 0:
        base.reason = "无有效价格"
        return base
    if snapshot.prev_close <= 0:
        base.reason = "缺少昨收，无法计算百分比基准"
        return base
    if snapshot.samples < thresholds.min_samples:
        base.reason = (
            f"样本不足({snapshot.samples}/{thresholds.min_samples})，VWAP 未预热"
        )
        return base

    # 闸门 1：今天是不是死水
    if snapshot.amplitude < thresholds.min_amplitude:
        base.reason = (
            f"振幅 {snapshot.amplitude:.2f}% < 下限 {thresholds.min_amplitude:.2f}%，"
            f"回归空间撑不起成本"
        )
        return base

    # 闸门 2：动作太密
    if bars_since_last_action < thresholds.min_bars_between_actions:
        base.reason = f"距上次动作仅 {bars_since_last_action} 根 bar，避免过度交易"
        return base

    cost = thresholds.round_trip_cost_pct()

    # ---- 低吸（正 T 买入腿）----
    if snapshot.ret <= -thresholds.buy_dev_close:
        # 闸门：右侧确认 —— 连跌必须已经被打断，否则就是在接下落的刀
        if thresholds.require_stabilize and (
            snapshot.bars_since_low < thresholds.stabilize_bars
        ):
            base.reason = (
                f"相对昨收 {snapshot.ret:.2f}% 已够低，"
                f"但创新低后仅 {snapshot.bars_since_low} 根 bar"
                f"(需 ≥{thresholds.stabilize_bars})，未企稳，不抄底"
            )
            return base
        # 闸门：极端偏离不参与 —— 多半有基本面事件，均值回归假设失效
        if abs(snapshot.ret) > thresholds.max_dev_close:
            base.reason = (
                f"相对昨收 {snapshot.ret:.2f}% 超出极端阈值 "
                f"±{thresholds.max_dev_close:.2f}%，均值回归假设不再成立"
            )
            return base
        # 确认：相对当日成交重心也偏低（防止确实是全天低位震荡、压根没机会）
        if snapshot.dev_vwap > thresholds.buy_dev_vwap:
            base.reason = (
                f"虽低于昨收 {snapshot.ret:.2f}%，但已站在当日 VWAP 之上"
                f"（{snapshot.dev_vwap:+.2f}%），不算低位"
            )
            return base
        expected = abs(snapshot.ret) * thresholds.reversion_ratio - cost
        if expected < thresholds.min_net_edge:
            base.reason = (
                f"偏离 {snapshot.ret:.2f}% × 回归假设 "
                f"{thresholds.reversion_ratio:.0%} − 成本 {cost:.2f}% = "
                f"{expected:.2f}% < {thresholds.min_net_edge:.2f}%"
            )
            return base
        base.action = ACTION_BUY_T
        base.net_edge = expected
        base.confidence = min(1.0, expected / 3.0)
        base.reason = (
            f"低于昨收 {snapshot.ret:.2f}%（VWAP {snapshot.dev_vwap:+.2f}%），"
            f"已企稳，预期净空间 {expected:.2f}% → 低吸（正 T 买入腿）"
        )
        base.snapshot["leg"] = "正T-低吸"
        return base

    # ---- 高抛（倒 T 卖出腿）----
    if snapshot.ret >= thresholds.sell_dev_close:
        if thresholds.require_stabilize and (
            snapshot.bars_since_high < thresholds.stabilize_bars
        ):
            base.reason = (
                f"相对昨收 {snapshot.ret:.2f}% 已够高，"
                f"但创新高后仅 {snapshot.bars_since_high} 根 bar"
                f"(需 ≥{thresholds.stabilize_bars})，未见回落，不高抛"
            )
            return base
        if abs(snapshot.ret) > thresholds.max_dev_close:
            base.reason = (
                f"相对昨收 {snapshot.ret:.2f}% 超出极端阈值 "
                f"±{thresholds.max_dev_close:.2f}%，可能存在基本面事件"
            )
            return base
        if snapshot.dev_vwap < -thresholds.sell_dev_vwap:
            base.reason = (
                f"虽高于昨收 {snapshot.ret:.2f}%，但仍在当日 VWAP 之下"
                f"（{snapshot.dev_vwap:+.2f}%），不算高位"
            )
            return base
        # 闸门：临近收盘不新开倒 T —— 开出去可能来不及买回，被迫追高
        if minutes_to_close is None:
            base.reason = "未提供距收盘时间，保守起见不开新的倒 T（避免买不回来）"
            return base
        if minutes_to_close < thresholds.no_new_sell_before_close_min:
            base.reason = (
                f"距收盘仅 {minutes_to_close:.0f} 分钟"
                f"(<{thresholds.no_new_sell_before_close_min})，不新开倒 T"
            )
            return base
        expected = snapshot.ret * thresholds.reversion_ratio - cost
        if expected < thresholds.min_net_edge:
            base.reason = (
                f"偏离 {snapshot.ret:.2f}% × 回归假设 "
                f"{thresholds.reversion_ratio:.0%} − 成本 {cost:.2f}% = "
                f"{expected:.2f}% < {thresholds.min_net_edge:.2f}%"
            )
            return base
        base.action = ACTION_SELL_T
        base.net_edge = expected
        base.confidence = min(1.0, expected / 3.0)
        base.reason = (
            f"高于昨收 {snapshot.ret:+.2f}%（VWAP {snapshot.dev_vwap:+.2f}%），"
            f"已见回落，预期净空间 {expected:.2f}% → 高抛（倒 T 卖出腿，须买回）"
        )
        base.snapshot["leg"] = "倒T-高抛"
        return base

    base.reason = (
        f"相对昨收 {snapshot.ret:+.2f}% 落在 ±{thresholds.buy_dev_close:.2f}% 死区内，"
        f"不动"
    )
    return base
