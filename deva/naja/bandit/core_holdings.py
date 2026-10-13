"""长期底仓标的配置 —— 「我们长期持有什么」的唯一权威。

用户拍板（2026-10-13）
--------------------
    「我们其实还要长期持有一个半导体指数（就是刚才说的芯片指数），
      因为现在是 AI 时代，咱们要长期价值投资持有这个指数。
      不过中间可以做 T，但要利用这种流动性的机会，做完之后一定要买回来，
      保证我们长期持有。」

落地为默认配置项：**科创芯片 ETF（588200）**。

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
``NAJA_T_ROTATION_TARGET_SHARES``  目标份额。支持两种写法：
                                   ``100000``（对所有标的生效）或
                                   ``588200:100000,512480:50000``（逐标的）
``NAJA_T_ROTATION_ENABLED``        ``0`` 关闭整个做 T 运行器
``NAJA_T_ROTATION_ESTABLISH``      ``1`` 允许自动补足未达标的底仓（默认 **关**）
``NAJA_T_ROTATION_POLL_SECONDS``   行情轮询秒数，默认 30
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, replace
from typing import Dict, List, Tuple

log = logging.getLogger(__name__)

#: 默认核心底仓 —— 科创芯片 ETF（嘉实，跟踪上证科创板芯片指数）
DEFAULT_CORE_CODE = "588200"

#: 默认目标份额（约合 10 万元，按 2026-10-13 的 1.0 元/份估算）。
#: 这是「随时能做 T 的权利」的规模，不是一次性投入的上限。
DEFAULT_TARGET_SHARES = 100_000.0

#: ETF 场内最小交易单位
DEFAULT_ROUND_LOT = 100.0


@dataclass(frozen=True)
class CoreHoldingSpec:
    """一份「长期持有」承诺。target 以内的份额不参与任何卖出。"""

    code: str            # 归一化代码，如 "588200"
    bus_code: str        # 行情总线代码，如 "sh588200"
    name: str            # 中文名
    target_shares: float  # 长期目标份额（底仓规模）
    round_lot: float = DEFAULT_ROUND_LOT
    enabled: bool = True
    note: str = ""

    def to_dict(self) -> Dict:
        return {
            "code": self.code,
            "bus_code": self.bus_code,
            "name": self.name,
            "target_shares": self.target_shares,
            "round_lot": self.round_lot,
            "enabled": self.enabled,
            "note": self.note,
        }


#: 备选清单（名称与代码均于 2026-10-13 用新浪行情逐个核对过）。
#: 当前只启用 588200 —— 用户点名科创芯片 ETF；其余保留供切换/对比。
#:
#: 当日真实特征（同一天同一时刻取数，可见三者振幅接近）：
#:   588200 昨收 0.996  振幅 (1.013-0.953)/0.996 = 6.02%
#:   512480 昨收 0.888  振幅 (0.899-0.848)/0.888 = 5.74%
#:   159995 昨收 0.973  振幅 (0.987-0.933)/0.973 = 5.55%
CHIP_ETF_CATALOG: Dict[str, CoreHoldingSpec] = {
    "588200": CoreHoldingSpec(
        code="588200", bus_code="sh588200", name="科创芯片ETF嘉实",
        target_shares=DEFAULT_TARGET_SHARES,
        note="默认底仓：跟踪上证科创板芯片指数，成分股全是半导体",
    ),
    "512480": CoreHoldingSpec(
        code="512480", bus_code="sh512480", name="半导体ETF国联安",
        target_shares=DEFAULT_TARGET_SHARES,
        note="备选：覆盖沪深两市半导体，含部分非科创板标的",
    ),
    "159995": CoreHoldingSpec(
        code="159995", bus_code="sz159995", name="芯片ETF",
        target_shares=DEFAULT_TARGET_SHARES,
        note="备选：国证芯片指数，与 588200 高度重叠",
    ),
}


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


def load_core_holdings() -> List[CoreHoldingSpec]:
    """读取启用中的底仓标的。这是调用方唯一该用的入口。"""
    raw_codes = _env("NAJA_T_ROTATION_SYMBOLS")
    codes = [c.strip() for c in raw_codes.split(",") if c.strip()] if raw_codes else [DEFAULT_CORE_CODE]

    overrides = _parse_targets(_env("NAJA_T_ROTATION_TARGET_SHARES"), codes)

    specs: List[CoreHoldingSpec] = []
    for code in codes:
        base = CHIP_ETF_CATALOG.get(code)
        if base is None:
            # 不在备选清单里（比如用户想拿某只票做 T）也放行，
            # 但名字只能退化成代码本身 —— 宁可显示难看，也不假装知道它叫什么。
            base = CoreHoldingSpec(
                code=code,
                bus_code=_bus_code_for(code),
                name=code,
                target_shares=overrides.get(code, DEFAULT_TARGET_SHARES),
                note="未登记的标的：请自行确认其为 ETF（否则摩擦成本参数不适用）",
            )
            log.warning(
                f"[CoreHoldings] {code} 不在备选 ETF 清单中，"
                f"按默认精度/交易单位处理"
            )
        if code in overrides:
            base = replace(base, target_shares=overrides[code])
        if base.target_shares <= 0:
            log.warning(f"[CoreHoldings] {code} 目标份额 <=0，本次跳过")
            continue
        specs.append(base)
    return specs


def core_summary() -> Dict:
    """给状态页/日志用的摘要。"""
    return {
        "enabled": env_flag("NAJA_T_ROTATION_ENABLED", True),
        "establish_enabled": env_flag("NAJA_T_ROTATION_ESTABLISH", False),
        "poll_seconds": env_float("NAJA_T_ROTATION_POLL_SECONDS", 30.0),
        "holdings": [s.to_dict() for s in load_core_holdings()],
        "default_code": DEFAULT_CORE_CODE,
    }


__all__ = [
    "DEFAULT_CORE_CODE",
    "DEFAULT_TARGET_SHARES",
    "CHIP_ETF_CATALOG",
    "CoreHoldingSpec",
    "load_core_holdings",
    "core_summary",
    "env_flag",
    "env_float",
]
