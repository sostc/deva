"""底仓补仓闸门 —— 「现在这一笔该不该下」交给决策中心裁定。

为什么要有这个模块
==================
用户 2026-10-14 问过一句话：「买的时候不考虑大环境背景吗，行情不好还在下跌什么的，
manas 或者决策中心有没起作用」。核查结论是三条：

1. ``TRotationRunner._maybe_establish_core`` **完全不过决策中心**。
   它只算四件事 —— 目标份额、缺口、可用资金、每手股数 —— 然后直接
   ``pf.open_position()``。整个做 T 包里连 ``manas`` 这个词都没有。
2. ``adaptive_cycle`` 里那份 manas 上下文是**假接**：它调用
   ``manas_engine.compute(scanner=None, portfolio={硬编码})``，而
   ``RegimeEngine._get_index_trend`` / ``_get_block_diffusion`` 在
   ``scanner is None`` 时都直接 ``return 0.0`` → regime 恒为中性。
3. **方向与直觉相反**。目标份额的定义是

       target = 总资产 × alloc_pct ÷ **现价**

   分母是现价，所以**每跌一截，目标份额就变大**，系统会 pinch 再买一点补回来。
   实测（昨收 0.996、总资产 100 万、alloc 40%）：

       0%    → target 401,600 份
       -1%   → 404,000（再补 2,400）
       -2%   → 406,500（再补 2,500）
       -5%   → 414,100（再补 5,600）
       -12%  → 433,800（再补 11,500）

   也就是说：**逆风本身就是买入触发器**，整条链上没有任何一环问过
   「现在适不适合建仓」。同一分钟里，决策中心正在以「Manas 闸门未放行
   （档位=hold, manas=0.301）」否决 4 个题材信号，而建仓路径照买不误。

闸门语义（四条硬规则）
==================
1. **硬闸门**：Manas 档位 = ``hold`` → 本轮**不买**。这是「等待时机」的落实。
2. **收盘兜底**：距收盘不足 ``NAJA_T_ESTABLISH_DEADLINE_MIN``（默认 30 分钟）
   时不再等，按最小档（``act_minimally`` 的乘子）补齐。
   ❗为什么必须兜底：资产配置与择时冲突时，优先级用户已经拍过 —— 40% 是要占住的
   仓位。若永不兜底，Manas 连续 hold 时底仓停在 0，做 T 引擎没有可卖的传承底仓，
   整套策略会长期空转 —— 这正是记忆里「闸门接好但从没放行」的死锁形态。
   ❗兜底**不是绕过闸门**：不改变档位判断，只是承认 deadline 后有权按最小量执行，
   并在 ``source="deadline"`` 里把这件事写进日志，事后查得到。
3. **定量而非全买**：非 hold 档位按 ``DecisionPlan.size_hint``
   （``decision.sizing`` 单一口径）折算本轮额度 —— 逆风少买、顺风到位，
   而不是一次性把缺口全部打满。
4. **看不见就别动**：决策中心不可用 / 异常 / 返回不是 dict → 本轮不买并**明确告警**。
   ❗刻意选保守：闸门挂掉时不下单，而不是退回无闸门状态。代价是把可用性绑给了
   上游,所以这条必须**可见**（连续失败会记 ``fail_streak`` 并在日志里报数），
   绝不能退化成静默跳过 —— 「合法的静默」是本仓库头号病理。

为什么用公开的 ``TradingCenter.process_strategy_signal``
======================================================
而不是 ``_full_decision_pipeline``：前者是公开入口，自带 ``DecisionPlan``
留痕（写穿日志），事后能查到「这笔当时为什么放行/否决」。后者既非公开，也绕过留痕。

``signal_confidence`` 刻意给中性 0.5：这是一次**配置补仓**，不是策略喊单，
不能替它在融合层刷分。
"""

from __future__ import annotations

import logging
import time
from time import monotonic as _monotonic
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from .core_holdings import CoreHoldingSpec, env_flag, env_float

log = logging.getLogger(__name__)

#: ``act_minimally`` 的仓位乘子（与 decision.sizing.ACTION_FACTORS 对齐）。
#: 收盘兜底时用这个量补，既「到位」又保留了「逆风少买」的分寸。
MIN_TOP_UP_HINT = 0.25


class VerdictUnavailable(Exception):
    """决策中心拿不到结论。注意：这不是「否决」，而是「看不清」——两者必须分开。"""


def _num(raw: Dict[str, Any], key: str) -> Optional[float]:
    """取值；键不存在时返回 ``None``，**不要**用 0.0 兜底。

    TradingCenter 的否决分支不带 manas/regime/timing，读出来会是 None。
    塞 0.0 会让「上游没给」看起来像「Manas 打了 0 分」，日志因此失去自证能力。
    """
    if key not in raw:
        return None
    try:
        return float(raw[key])
    except (TypeError, ValueError):
        return None


def _fmt(value: Optional[float], spec: str = "%.2f") -> str:
    """把数值格式化成日志片段；``None`` 显示为 ``--`` 而不是 0.00。"""
    if value is None:
        return "--"
    return spec % value


@dataclass
class EstablishmentVerdict:
    """一次补仓请求的裁定结果。

    ❗``allowed=False`` 有两个完全不同的来源，靠 :attr:`source` 区分：
    ``"decision_center"`` 是**真否决**（Manas 没放行，符合预期）；
    ``"unavailable"`` 是**看不清**（链路故障，需要人来看）——
    混为一谈会让闸门故障伪装成「行情不好所以没买」，这正是要防的静默失效。
    """

    allowed: bool
    reason: str = ""
    source: str = ""
    action_type: str = "hold"
    size_hint: float = 0.0
    #: ❗下面几个是 ``Optional[float]`` 而不是默认 0.0：TradingCenter 在
    #: **否决分支**的返回 dict 里根本不带这几个键，读出来就只能是 0.0 ——
    #: 那会把「没有数据」伪装成「Manas 打 0 分」，排查时必被带偏。
    #: 区分不开就用 ``None`` 表示「上游没给」。
    manas_score: Optional[float] = None
    regime_score: Optional[float] = None
    timing_score: Optional[float] = None
    fused_confidence: Optional[float] = None
    gate_reason: str = ""
    #: True = 本次裁定不是「问过决策中心」得来的（不可用 / 兜底 / 闸门关闭）。
    degraded: bool = False


def ask_decision_center(spec: CoreHoldingSpec, price: float) -> Dict[str, Any]:
    """向 TradingCenter 请教「现在能不能买这一笔」。

    返回 ``process_strategy_signal`` 的决策 dict；任何环节拿不到结论都抛
    :class:`VerdictUnavailable`，由调用方决定怎么降级 —— 这里绝不自己替它拍板。
    """
    try:
        from deva.naja.attention.orchestration.trading_center import (
            get_trading_center,
        )
    except Exception as e:  # pragma: no cover - import 失败等同链路不通
        raise VerdictUnavailable(f"TradingCenter 不可导入: {e}") from e

    tc = get_trading_center()
    if tc is None:
        raise VerdictUnavailable("TradingCenter 未初始化")

    # ❗stock_code 用 bus_code（sh588200 / hk00700 / usqqq 形态）：
    # 决策中心一路把 code 当带前缀的标准化代码处理，喂裸码会被当成另一个标的。
    signal = {
        "strategy_id": f"core_establish:{spec.code}",
        "stock_code": spec.bus_code,
        "stock_name": spec.name,
        "signal_type": "BUY",
        "price": float(price),
        "confidence": 0.5,
        "timestamp": time.time(),
    }
    try:
        result = tc.process_strategy_signal(signal)
    except Exception as e:
        raise VerdictUnavailable(f"决策中心异常: {e}") from e

    if not isinstance(result, dict):
        raise VerdictUnavailable(f"决策中心未返回决策结果（{result!r}）")
    return result


class CoreEstablishGate:
    """底仓补仓的节奏闸门。

    做成类而不是函数的原因只有一个：**要缓存**。轮询 30 秒一次，而完整决策管线
    会连着 FP 洞察与 Alaya 一起跑，每轮都问一遍既不经济也会把 ``DecisionPlan``
    日志灌满。 ``NAJA_T_ESTABLISH_GATE_TTL``（默认 300 秒）内的结论直接复用。

    :param provider: 裁定来源，签名为 ``(spec, price) -> dict``。
        刻意留出这个注入点：守卫脚本必须能在**没有 TradingCenter 的环境**里
        离线验证闸门逻辑（否则「问不到 → 不买」会淹没掉所有正向用例）。
    """

    ENV_ENABLED = "NAJA_T_ESTABLISH_GATE"
    ENV_TTL = "NAJA_T_ESTABLISH_GATE_TTL"
    ENV_DEADLINE = "NAJA_T_ESTABLISH_DEADLINE_MIN"

    #: 裁定耗时超过这个秒数就告警：它在轮询线程里同步跑，慢了会拖垮行情节拍
    SLOW_CONSULT_SECONDS = 3.0

    def __init__(
        self,
        provider: Optional[Callable[[CoreHoldingSpec, float], Dict[str, Any]]] = None,
        *,
        enabled: Optional[bool] = None,
        ttl: Optional[float] = None,
        deadline_min: Optional[float] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._provider = provider or ask_decision_center
        self._enabled = (
            env_flag(self.ENV_ENABLED, True) if enabled is None else bool(enabled)
        )
        self._ttl = float(
            ttl if ttl is not None else env_float(self.ENV_TTL, 300.0)
        )
        self._deadline_min = float(
            deadline_min if deadline_min is not None
            else env_float(self.ENV_DEADLINE, 30.0)
        )
        self._clock: Callable[[], float] = clock or time.time
        #: code -> (取数时刻, 决策 dict)。否决也算结论，同样进缓存，
        #: 否则每 30 秒就把整个管线重跑一次。
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        #: 连续看不清的次数。用来把「闸门链路坏了」这件事喊出来。
        self.fail_streak: int = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------
    def last_action_type(self, code: str) -> Optional[str]:
        """从**缓存**里读上一次的档位，**不触发任何管线**（亚毫秒）。

        守望需要一个廉价的环境信号来决定「值不值得去问一次」，而跑完整决策管线
        本身就是要省的东西 —— 所以这里只读缓存。

        :return: ``None`` 表示**不知道**。三种情况都归到这里：从没问过、
            缓存已过期、上游压根没给这个字段。
            ❗过期缓存**不返回陈货**：那会让守望拿着十分钟前的档位做判断，
            这正是记忆里「假新鲜比异常更毒」那种错。
        """
        hit = self._cache.get(code)
        if hit is None:
            return None
        taken_at, raw = hit
        if (self._clock() - taken_at) >= self._ttl:
            return None
        plan = raw.get("plan") or {}
        action = str(
            raw.get("action_type") or plan.get("action_type") or ""
        ).strip()
        return action or None

    # ------------------------------------------------------------------
    def evaluate(
        self,
        spec: CoreHoldingSpec,
        price: float,
        minutes_to_close: Optional[float],
    ) -> EstablishmentVerdict:
        """裁定「本轮是否补这笔」。

        :param minutes_to_close: 距收盘分钟数；``None`` 表示休市/未知 ——
            未知时**不触发**收盘兜底，宁可继续等。
        """
        if not self._enabled:
            return EstablishmentVerdict(
                allowed=True, source="disabled", degraded=True,
                size_hint=1.0, action_type="act_fully",
                reason="闸门已关闭（NAJA_T_ESTABLISH_GATE=0），维持无闸门行为",
            )

        now = self._clock()
        try:
            raw, cached = self._consult(spec, price, now)
        except VerdictUnavailable as e:
            self.fail_streak += 1
            reason = f"决策中心不可用，本轮不建仓（{e}；连续第 {self.fail_streak} 次）"
            # ❗必须 WARNING：这条情况是「链路故障伪装成行情不好」的唯一出口。
            log.warning(f"[CoreEstablishGate] {spec.code} {reason}")
            return EstablishmentVerdict(
                allowed=False, source="unavailable", degraded=True, reason=reason,
            )

        self.fail_streak = 0
        plan = raw.get("plan") or {}
        action_type = str(raw.get("action_type") or plan.get("action_type") or "hold")
        size_hint = float(plan.get("size_hint") or 0.0)
        should_act = bool(raw.get("approved"))
        gate_reason = str(plan.get("gate_reason") or "")

        common = dict(
            action_type=action_type,
            manas_score=_num(raw, "manas_score"),
            regime_score=_num(raw, "regime_score"),
            timing_score=_num(raw, "timing_score"),
            fused_confidence=_num(raw, "final_confidence"),
            gate_reason=gate_reason,
        )
        tail = "" if not cached else "（缓存）"
        detail = (
            f"档位={action_type} manas={_fmt(common['manas_score'])} "
            f"regime={_fmt(common['regime_score'])} "
            f"timing={_fmt(common['timing_score'])}{tail}"
        )

        if should_act and size_hint > 0:
            return EstablishmentVerdict(
                allowed=True, source="decision_center", size_hint=size_hint,
                reason=f"决策中心放行 {detail}", **common,
            )

        # Manas 没放行 —— 硬闸门。只有收盘兜底能开这道门。
        hold_detail = gate_reason or f"Manas 闸门未放行 {detail}"
        if minutes_to_close is not None and 0 <= minutes_to_close <= self._deadline_min:
            log.warning(
                f"[CoreEstablishGate] {spec.name}({spec.code}) 距收盘 "
                f"{minutes_to_close:.0f} 分钟仍在 hold，收盘兜底按最小档补仓 —— "
                f"{hold_detail}。若不该兜底，把 "
                f"NAJA_T_ESTABLISH_DEADLINE_MIN 设成 0"
            )
            return EstablishmentVerdict(
                allowed=True, source="deadline", degraded=True,
                size_hint=max(size_hint, MIN_TOP_UP_HINT),
                reason=f"收盘兜底（≤{self._deadline_min:.0f}分钟）{hold_detail}",
                **common,
            )

        return EstablishmentVerdict(
            allowed=False, source="decision_center", size_hint=size_hint,
            reason=hold_detail, **common,
        )

    # ------------------------------------------------------------------
    def _consult(
        self, spec: CoreHoldingSpec, price: float, now: float
    ) -> Tuple[Dict[str, Any], bool]:
        """取一次裁定，命中 TTL 就复用。返回 ``(决策 dict, 是否命中缓存)``。"""
        hit = self._cache.get(spec.code)
        if hit is not None and (now - hit[0]) < self._ttl:
            return hit[1], True
        # ❗``evaluate`` 是在做 T 轮询线程里**同步**调用的。实测这条管线目前
        # 是亚毫秒级（Naja 这条链路里不调 LLM），但若哪天 FP 洞察改成走真模型，
        # 每 5 分钟卡几十秒会把行情节拍拖垮、还不报错。这里量一下并喊人。
        started = _monotonic()
        raw = self._provider(spec, price)
        elapsed = _monotonic() - started
        if elapsed > self.SLOW_CONSULT_SECONDS:
            log.warning(
                f"[CoreEstablishGate] 决策中心裁定耗时 {elapsed:.1f}s，"
                f"同步阻塞了做 T 轮询线程 —— 请调大 "
                f"NAJA_T_ESTABLISH_GATE_TTL（当前 {self._ttl:.0f}s）"
            )
        if not isinstance(raw, dict):
            raise VerdictUnavailable(f"裁定来源返回的不是 dict（{type(raw).__name__}）")
        self._cache[spec.code] = (now, raw)
        return raw, False

    def invalidate(self, code: Optional[str] = None) -> None:
        """清掉缓存。下单成交后应调用，避免拿几分钟前的旧档位继续放行。"""
        if code is None:
            self._cache.clear()
        else:
            self._cache.pop(code, None)
