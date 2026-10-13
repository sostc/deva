"""长期底仓标的配置 —— 「我们长期持有什么」的唯一权威。

用户拍板（2026-10-13）
--------------------
    「我们其实还要长期持有一个半导体指数（就是刚才说的芯片指数），
      因为现在是 AI 时代，咱们要长期价值投资持有这个指数。
      不过中间可以做 T，但要利用这种流动性的机会，做完之后一定要买回来，
      保证我们长期持有。」

落地为默认配置项：**科创芯片 ETF（588200）**，规模占总资产 **40%**。

用户的两次话（2026-10-13）
------------------------
    「订单：「你要长期持有一个半导体指数……
      中间可以做 T，但做完之后一定要买回来，保证我们长期持有。」
    二、「我觉得先有 40% 的仓位吧，用来做这个底仓。」

第二条是**授权**：此前 ``ESTABLISH`` 默认关闭的理由是「动用多少资金
由人拍板，代码不替用户决定」——既然数字已经给了，这个前提不再成立，
故自动补足底仓改为默认开启（仍可用环境变量关掉）。

为什么集中在一个文件里
----------------------
底仓标的一旦散落在多处（发起建仓的地方、做 T 的地方、看状态的地方），
就会出现「写着持有芯片指数、实际什么都持有」的静默失效 ——
本仓库已经为这类「UI/配置写好了、链路没接」的毛病付过好几次学费。

从上到下只有一条链路：本文件决定「持有谁」，
``t_rotation_runner`` 负责把它接到行情上并执行。
* ``DEFAULT_CORE_CODE``  —— 默认标的代码
* ``CHIP_ETF_CATALOG``   —— 备查清单（真实名称和代码，均已用新浪行情核对）
* ``load_core_holdings()`` —— 唯一的读取入口（含环境变量覆盖与坏值回退）

代码口径
--------
``code`` 是**归一化代码**（不带 ``sh``/``sz`` 前缀），``bus_code`` 才是
MarketDataBus / 新浪行情要的带前缀格式。两者混用会查不到数据：
bus 内部 ``_normalize_code`` 会剥前缀当 key，
而新浪的返回行是以 ``sh588200`` 为 key 写进 quotes 的。

环境变量
--------
``NAJA_T_ROTATION_SYMBOLS``        逗号分隔的标的代码，默认 ``588200``
``NAJA_T_ROTATION_ALLOC_PCT``      底仓占**总资产**的百分比，默认 ``40``
``NAJA_T_ROTATION_TARGET_SHARES``  目标份额的**显式覆盖**（优先于 alloc_pct）。
                                   写法：``200000``（对所有标的生效）或
                                   ``588200:200000,512480:50000``（逐标的）
``NAJA_T_ROTATION_ENABLED``        ``0`` 关闭整个做 T 运行器
``NAJA_T_ROTATION_ESTABLISH``      ``1`` 允许自动补足未达标的底仓（默认 **开**，
                                   依据：用户已明确给出 40% 的仓位规模）
``NAJA_T_ROTATION_POLL_SECONDS``   行情轮询秒数，默认 30

份额从哪来
----------
``target_shares`` 默认是 **0**，意思是「没显式指定」——
此时份额由 ``总资产 × alloc_pct / 当前价`` 算出。

为什么不直接写死一个份额数字：同样的 40%，
价格 1.0 时是 40 万份、价格 2.0 时就该是 20 万份。
写死份额等于把「占多少仓位」这个决定偷换成「买多少份」，
价格一变，仓位比例就悄悄漂走了。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from .intraday_deviation import RotationThresholds

log = logging.getLogger(__name__)

#: 默认核心底仓 —— 科创芯片 ETF（嘉实，跟踪上证科创板芯片指数）
DEFAULT_CORE_CODE = "588200"

#: 底仓默认占总资产的百分比。用户拍板（2026-10-13）：「先有 40% 的仓位吧」。
#:
#: 为什么是比例而不是份额：见模块 docstring「份额从哪来」。
#: 40% 的依据是「留出 60% 做机动」—— 正 T 需要备用资金、
#: 突发机会也需要现金，把全部资金押在一个标的上就没有做 T 的空间了。
DEFAULT_ALLOC_PCT = 40.0

#: 显式覆盖目标份额时的默认值。**0 表示「未指定」**，
#: 走 alloc_pct × 总资产 / 现价 的路径（见 :meth:`CoreHoldingSpec.resolve_target_shares`）。
DEFAULT_TARGET_SHARES = 0.0

#: ETF 场内最小交易单位
DEFAULT_ROUND_LOT = 100.0


# ---------------------------------------------------------------- 市场档位


@dataclass(frozen=True)
class MarketProfile:
    """一个市场的做 T 参数档。

    为什么要分市场
    --------------
    判据参数**不是**可以跨市场共用的常数。它们是按「标的的日內波动尺度」
    标出来的，而三个市场的尺度差了一个数量级（2026-10-14 实测当日振幅）：

        A 股 588200 **6.02%** ｜ 港股 00700 **1.36%** ｜ 美股 QQQ **0.72%**

    拿 A 股那套（``min_amplitude=1.0`` / ``dev_close=1.5``）去套 QQQ，
    QQQ 连"死水"闸门都过不去 —— **永不触发**，而且不报错、不告警，
    看上去就是"今天没机会"。这是最典型的静默失效。

    ⚠️ 以下费率是**按各市场常见零售费率粗标的**，目的是让
    ``min_net_edge`` 与成本处在同一量级，不是精算结果。
    真实费率以券商为准，实盘前需重新标定。
    """

    market: str
    #: 本币代码。用户拍板（2026-10-14）：**各市场独立本币记账，不做汇率换算**。
    #: 所以 ``max_round_amount`` 的单位就是这里的币种。
    currency: str
    round_lot: float
    max_round_amount: float
    thresholds: RotationThresholds = field(default_factory=RotationThresholds)
    note: str = ""


MARKET_PROFILES: Dict[str, MarketProfile] = {
    "CN": MarketProfile(
        market="CN", currency="CNY", round_lot=100.0, max_round_amount=200000.0,
        # 场内 ETF：免印花税。振幅大（~6%），闸门可以放宽
        thresholds=RotationThresholds(
            commission_pct=0.025, slippage_pct=0.05, stamp_duty_pct=0.0,
            min_commission=5.0,
            buy_dev_close=1.5, sell_dev_close=1.5,
            min_amplitude=1.0, min_net_edge=0.35, max_dev_close=8.0,
        ),
        note="A股场内ETF：免印花税，日内振幅大（实测 6%）",
    ),
    "HK": MarketProfile(
        market="HK", currency="HKD", round_lot=100.0, max_round_amount=200000.0,
        # 港股：印花税 0.1% 单边，佣金也高于 A 股 → 往返成本约 0.30%
        thresholds=RotationThresholds(
            commission_pct=0.05, slippage_pct=0.05, stamp_duty_pct=0.1,
            min_commission=20.0,
            buy_dev_close=0.8, sell_dev_close=0.8,
            min_amplitude=0.6, min_net_edge=0.10, max_dev_close=5.0,
        ),
        note="港股：含 0.1% 印花税，往返成本约 0.30%，振幅中等（实测 1.4%）",
    ),
    "US": MarketProfile(
        market="US", currency="USD", round_lot=1.0, max_round_amount=30000.0,
        # 美股：无印花税、可 1 股起。ETF 振幅小（~0.7%），闸门必须放低，
        # 否则按 A 股那套永远不会触发
        thresholds=RotationThresholds(
            commission_pct=0.03, slippage_pct=0.03, stamp_duty_pct=0.0,
            min_commission=1.0,
            buy_dev_close=0.5, sell_dev_close=0.5,
            min_amplitude=0.35, min_net_edge=0.10, max_dev_close=4.0,
        ),
        note="美股：1 股起、无印花税，但振幅小（实测 0.72%），闸门须放低",
    ),
}


def market_profile(market: str) -> MarketProfile:
    """取市场档位。认不出的市场**回落到 A 股档**（保守：闸门更严）。"""
    return MARKET_PROFILES.get(str(market or "").strip().upper(), MARKET_PROFILES["CN"])


def _floor_lot(value: float, lot: float) -> float:
    """向下取整到交易单位的整数倍。宁可少买，不可超出预算或买成零股。"""
    if lot <= 0 or value <= 0:
        return 0.0
    return float(int(value / lot)) * lot


@dataclass(frozen=True)
class CoreHoldingSpec:
    """一份「长期持有」承诺。target 以内的份额不参与任何卖出。"""

    code: str            # 归一化代码，如 "588200"
    bus_code: str        # 行情总线代码，如 "sh588200"
    name: str            # 中文名
    market: str          # CN / HK / US —— 决定时段、每手、判据参数、币种
    target_shares: float  # 显式指定的目标份额；0 = 未指定，按 alloc_pct 折算
    round_lot: float = DEFAULT_ROUND_LOT
    alloc_pct: float = DEFAULT_ALLOC_PCT  # 占总资产百分比
    enabled: bool = True
    note: str = ""

    # ---- 口径换算 -------------------------------------------------
    @property
    def explicit(self) -> bool:
        """是否显式指定了份额（人的手填数字优先于按比例折算）。"""
        return self.target_shares > 0

    @property
    def profile(self) -> MarketProfile:
        """该标的所在市场的参数档。"""
        return market_profile(self.market)

    @property
    def currency(self) -> str:
        return self.profile.currency

    def target_budget(self, total_assets: float) -> float:
        """这份底仓对应多少钱。"""
        return max(0.0, total_assets) * max(0.0, self.alloc_pct) / 100.0

    def resolve_target_shares(self, total_assets: float, price: float) -> float:
        """折算成份额。**调用方必须负责"每天只算一次"**（见 runner 的锁定逻辑）。

        这里按调用瞬间的价格折算——价格会动，若每个 tick 都重算，
        计划份额就会跟着漂，份额守恒的基准也跟着漂。
        """
        if self.explicit:
            return _floor_lot(self.target_shares, self.round_lot)
        if price <= 0 or total_assets <= 0:
            return 0.0
        return _floor_lot(self.target_budget(total_assets) / price, self.round_lot)

    def to_dict(self) -> Dict:
        return {
            "code": self.code,
            "bus_code": self.bus_code,
            "name": self.name,
            "market": self.market,
            "currency": self.currency,
            "target_shares": self.target_shares,
            "round_lot": self.round_lot,
            "alloc_pct": self.alloc_pct,
            "enabled": self.enabled,
            "note": self.note,
        }


#: 已登记的底仓标的清单（名称与代码均用富途行情逐个核对过）。
#:
#: ★ 用户的三个仓（2026-10-14 拍板）：
#:     A 股 588200 科创芯片ETF —— 长期持有的指数底仓
#:     美股 QQQ   纳指100ETF  —— 指数底仓
#:     港股 00700 腾讯控股    —— **选它做 T 而非指数**，理由是日内振幅
#:
#: ❗「持有指数」与「持续做 T」之间有张力：做 T 吃的是日内波动，
#:   而指数波动天然小于个股。同一时刻实测振幅：
#:     588200 **6.02%** ｜ 00700 **1.36%** ｜ QQQ **0.72%**
#:   拿指数做 T，扣掉往返摩擦后剩下的空间很薄；用户点名腾讯做 T 是对的直觉。
#:   指数更适合「底仓 + 偶尔倒 T」，不适合高频做 T。
#:
#: 三者的 target_shares 一律为 0 —— 走 alloc_pct 折算，不写死份额。
CORE_CATALOG: Dict[str, CoreHoldingSpec] = {
    "588200": CoreHoldingSpec(
        code="588200", bus_code="sh588200", name="科创芯片ETF嘉实", market="CN",
        target_shares=DEFAULT_TARGET_SHARES, round_lot=100.0,
        note="A股底仓：跟踪上证科创板芯片指数，成分股全是半导体",
    ),
    "512480": CoreHoldingSpec(
        code="512480", bus_code="sh512480", name="半导体ETF国联安", market="CN",
        target_shares=DEFAULT_TARGET_SHARES, round_lot=100.0,
        note="备选：覆盖沪深两市半导体，含部分非科创板标的",
    ),
    "159995": CoreHoldingSpec(
        code="159995", bus_code="sz159995", name="芯片ETF", market="CN",
        target_shares=DEFAULT_TARGET_SHARES, round_lot=100.0,
        note="备选：国证芯片指数，与 588200 高度重叠",
    ),
    "QQQ": CoreHoldingSpec(
        code="QQQ", bus_code="gb_qqq", name="纳指100ETF", market="US",
        target_shares=DEFAULT_TARGET_SHARES, round_lot=1.0,
        note="美股底仓：每手 1 股，日内振幅小（实测 0.72%），判据已按美股档放宽",
    ),
    "00700": CoreHoldingSpec(
        code="00700", bus_code="hk00700", name="腾讯控股", market="HK",
        target_shares=DEFAULT_TARGET_SHARES, round_lot=100.0,
        note="港股做T标的：振幅中等（实测 1.36%），含 0.1% 印花税",
    ),
}

#: 兼容旧名（既有代码与文档里用的是 CHIP_ETF_CATALOG）
CHIP_ETF_CATALOG = CORE_CATALOG


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def env_flag(name: str, default: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    log.warning(f"[CoreHoldings] {name}={raw!r} 无法识别，回退为 {default}")
    return default


def env_float(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        log.warning(f"[CoreHoldings] {name}={raw!r} 不是数字，回退为 {default}")
        return default


def _bus_code_for(code: str) -> str:
    """归一化代码 → 行情总线代码。

    交易所号段判断统一委托给 :func:`market_data_bus.format_exchange_code`
    （那里踩过「588200 被编成 sz」的坑），这里刻意不再自己写一份规则。
    延迟 import：配置模块不该把总线及其 NB 依赖拖进导入路径。
    """
    if code.startswith(("sh", "sz", "bj", "gb_")):
        return code
    try:
        from .market_data_bus import format_exchange_code

        return format_exchange_code(code)
    except Exception as e:  # pragma: no cover - 基础设施不可用时
        log.error(f"[CoreHoldings] 无法推断 {code} 的交易所前缀: {e}")
        return code


def _parse_targets(raw: str, codes: List[str]) -> Dict[str, float]:
    """解析目标份额覆盖。坏值一律回退到默认值并告警，不静默吞掉。"""
    out: Dict[str, float] = {}
    if not raw:
        return out

    # 写法一：纯数字 —— 对所有标的生效
    try:
        val = float(raw)
        return {c: val for c in codes}
    except ValueError:
        pass

    # 写法二：code:shares,code:shares
    for chunk in raw.split(","):
        piece = chunk.strip()
        if not piece:
            continue
        if ":" not in piece:
            log.warning(f"[CoreHoldings] 目标份额片段 {piece!r} 缺少 code:shares 形式，忽略")
            continue
        cod, val = piece.split(":", 1)
        cod = cod.strip()
        try:
            out[cod] = float(val.strip())
        except ValueError:
            log.warning(f"[CoreHoldings] 目标份额 {val.strip()!r} 不是数字，忽略 {cod}")
    return out


def _parse_symbols(raw: str) -> List[Tuple[Optional[str], str]]:
    """解析 ``NAJA_T_ROTATION_SYMBOLS``。

    两种写法：**裸代码**（``588200``，市场按代码形态推断）与
    **显式市场**（``US:QQQ`` / ``HK:00700``）。

    为什么要支持显式写法：``qqq`` 是裸字母，代码形态**说不出它属于哪个市场**
    （5 位数字=港股、6 位数字=A 股，字母只有查注册表才认得）。让用户在配置里
    直接说清楚，比依赖一份可能漏登记的代码宇宙可靠得多。
    """
    out: List[Tuple[Optional[str], str]] = []
    for chunk in (raw or "").split(","):
        piece = chunk.strip()
        if not piece:
            continue
        if ":" in piece:
            mkt, cod = piece.split(":", 1)
            mkt, cod = mkt.strip().upper(), cod.strip()
            if not cod:
                log.warning(f"[CoreHoldings] 标的片段 {piece!r} 缺代码，忽略")
                continue
            out.append((mkt, cod))
        else:
            out.append((None, piece))
    return out


def _infer_market(code: str) -> str:
    """按代码形态猜市场。猜不出**回落到 CN**（保守：A 股档闸门最严）。"""
    try:
        from .execution import infer_market

        mkt, _note = infer_market(code)
        if mkt:
            return mkt
    except Exception as e:  # pragma: no cover
        log.debug(f"[CoreHoldings] 推断 {code} 的市场失败: {e}")

    text = str(code or "").strip()
    if text.isdigit():
        return "HK" if len(text) == 5 else "CN"
    return "CN"


def load_core_holdings() -> List[CoreHoldingSpec]:
    """读取启用中的底仓标的。这是调用方唯一该用的入口。"""
    raw_codes = _env("NAJA_T_ROTATION_SYMBOLS")
    pairs = _parse_symbols(raw_codes) if raw_codes else [(None, DEFAULT_CORE_CODE)]
    codes = [c for _, c in pairs]

    overrides = _parse_targets(_env("NAJA_T_ROTATION_TARGET_SHARES"), codes)
    alloc_pct = env_float("NAJA_T_ROTATION_ALLOC_PCT", DEFAULT_ALLOC_PCT)
    if alloc_pct <= 0:
        log.warning(
            f"[CoreHoldings] NAJA_T_ROTATION_ALLOC_PCT={alloc_pct} 不是正数，"
            f"回退为 {DEFAULT_ALLOC_PCT}"
        )
        alloc_pct = DEFAULT_ALLOC_PCT
    elif alloc_pct > 100:
        log.warning(
            f"[CoreHoldings] NAJA_T_ROTATION_ALLOC_PCT={alloc_pct} 超过 100%，"
            f"回退为 {DEFAULT_ALLOC_PCT}（底仓不能吃掉全部资金）"
        )
        alloc_pct = DEFAULT_ALLOC_PCT

    specs: List[CoreHoldingSpec] = []
    for declared_market, code in pairs:
        # 清单查找按**大写**归一：用户写 qqq 也要能命中 QQQ
        base = CORE_CATALOG.get(code) or CORE_CATALOG.get(code.upper())
        if base is None:
            mkt = declared_market or _infer_market(code)
            prof = market_profile(mkt)
            # 不在清单里（比如用户想拿某只票做 T）也放行，
            # 但名字只能退化成代码本身 —— 宁可显示难看，也不假装知道它叫什么。
            base = CoreHoldingSpec(
                code=code,
                bus_code=_bus_code_for(code),
                name=code,
                market=mkt,
                target_shares=overrides.get(code, DEFAULT_TARGET_SHARES),
                round_lot=prof.round_lot,
                alloc_pct=alloc_pct,
                note=f"未登记的标的：按 {mkt} 档参数处理（{prof.note}）",
            )
            log.warning(
                f"[CoreHoldings] {code} 不在底仓清单中，按 {mkt} 档处理"
                f"（每手 {prof.round_lot:g}，币种 {prof.currency}）"
            )
        else:
            base = replace(base, alloc_pct=alloc_pct)
            # 显式声明的市场压过清单里的：用户写在配置里的更可信
            if declared_market and declared_market != base.market:
                log.warning(
                    f"[CoreHoldings] {code} 配置声明 {declared_market}，"
                    f"覆盖清单里的 {base.market}"
                )
                base = replace(base, market=declared_market)
        if code in overrides:
            base = replace(base, target_shares=overrides[code])
        if base.explicit and base.target_shares <= 0:
            log.warning(f"[CoreHoldings] {code} 目标份额 <=0，本次跳过")
            continue
        # 每手必须与所在市场档一致，否则会出现「美股按 100 股一手买 QQQ」
        prof = base.profile
        if base.round_lot != prof.round_lot:
            log.warning(
                f"[CoreHoldings] {code} 每手 {base.round_lot:g} 与 {base.market} 档"
                f"({prof.round_lot:g}) 不一致，以市场档为准"
            )
            base = replace(base, round_lot=prof.round_lot)
        specs.append(base)
    return specs


def core_summary() -> Dict:
    """给状态页/日志用的摘要。"""
    return {
        "enabled": env_flag("NAJA_T_ROTATION_ENABLED", True),
        "establish_enabled": env_flag("NAJA_T_ROTATION_ESTABLISH", True),
        "poll_seconds": env_float("NAJA_T_ROTATION_POLL_SECONDS", 30.0),
        "alloc_pct": env_float("NAJA_T_ROTATION_ALLOC_PCT", DEFAULT_ALLOC_PCT),
        "holdings": [s.to_dict() for s in load_core_holdings()],
        "default_code": DEFAULT_CORE_CODE,
    }


__all__ = [
    "DEFAULT_CORE_CODE",
    "DEFAULT_TARGET_SHARES",
    "DEFAULT_ALLOC_PCT",
    "DEFAULT_ROUND_LOT",
    "CHIP_ETF_CATALOG",
    "CORE_CATALOG",
    "MARKET_PROFILES",
    "MarketProfile",
    "market_profile",
    "CoreHoldingSpec",
    "load_core_holdings",
    "core_summary",
    "env_flag",
    "env_float",
]
