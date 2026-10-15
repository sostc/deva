"""宏观流动性信号的**唯一读取口径**。

为什么要有这个模块
==================

``QueryState.macro_liquidity_signal``（0~1，中性值 0.5）是「大环境」进决策链的
**唯一**环境输入，它经 ::

    ManasEngine.compute(macro_signal=)
      → RegimeEngine._get_liquidity_signal: liquidity = macro*2 - 1
      → regime_score = trend*0.4 + liquidity*0.35 + diffusion*0.25
      → 折扣 0.85 + 0.15*regime → harmony_strength → 行动门槛

影响**每一次**裁定。但系统里有两条互不相交的投喂路径：

    ① 决策路径  ``trading_center.process_strategy_signal``
                → ``market_state['macro_liquidity_signal']`` → ``os_kernel`` → Manas
    ② 展示路径  ``ManasManager.compute()``（UI / 守望台 / 状态接口）
                → ``ManasEngine.compute(macro_signal=)`` → Manas

两条路若各写各的读法，**必然漂移**。事实上 ② 曾经硬编码 ``return 0.5``：同一个
引擎在同一时刻，对「环境是顺风还是逆风」可以给出两种答案；更糟的是行动门审计
（``ManasEngine.compute()`` 每次都留痕）被 ② 的高频调用刷满，线上表现为
``regime_score`` 恒 0.0 / 折扣恒 0.85 —— 让人误以为「环境一直中性」，而真相是
这条线压根没接上。

所以取值这件事**只在这里做一次**，两条路都调它。

语义（务必与「真值恰好是 0.5」区分）
====================================

返回 ``None`` 表示**这次拿不到真值**（链路问题），调用方必须把它翻译成
「不传该参数 / 不放该键」，让 Manas 沿用默认 0.5；**不是**写个 0.5 进去冒充
数据。拿不到数据 ≠ 环境中性 —— 前者要告警，后者是合法读数。

本模块**永不抛异常**：读环境是决策的输入，读不到只是「中性」，不是「崩溃」。
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

log = logging.getLogger(__name__)

#: ``QueryState`` 上的属性名，同时也是 ``market_state`` 里的键名。
MACRO_LIQUIDITY_KEY = "macro_liquidity_signal"

#: 拿不到真值时 Manas 侧沿用的中性默认值（与
#: ``ManasEngine.compute`` / ``RegimeEngine.compute`` 的形参默认保持一致）。
NEUTRAL_MACRO_SIGNAL = 0.5

#: 各调用方的「拿不到」计数（用于节流告警，避免心跳刷屏）。
_miss_counts: Dict[str, int] = {}


def read_macro_liquidity_signal() -> Tuple[Optional[float], str]:
    """读当前宏观流动性信号（来自 QueryState，口径 0~1）。

    Returns:
        ``(值, 说明)`` —— 拿到时 ``(float, "")``；拿不到时 ``(None, 原因)``。
        原因字符串直接进告警，因此要说清是**哪一环**断的（容器 / 属性 / 类型）。
    """
    try:
        from deva.naja.application import get_app_container
    except Exception as e:  # noqa: BLE001 - 读不到只是中性，不是崩溃
        return None, f"application 层不可导入: {e}"

    try:
        container = get_app_container()
    except Exception as e:  # noqa: BLE001
        return None, f"取容器失败: {e}"

    if container is None:
        return None, "容器未装配"

    query_state = getattr(container, "query_state", None)
    if query_state is None:
        return None, "QueryState 未装配"

    value = getattr(query_state, MACRO_LIQUIDITY_KEY, None)
    if value is None:
        # ❗注意这里与「真值恰好是 0.5」是两回事：属性缺失 / 值为 None 都算
        #   「拿不到」，必须让调用方告警，不许静默当成中性。
        return None, f"QueryState 无 {MACRO_LIQUIDITY_KEY}"

    try:
        return float(value), ""
    except (TypeError, ValueError) as e:
        return None, f"{MACRO_LIQUIDITY_KEY} 不是数值（{value!r}）: {e}"


def warn_missing(tag: str, why: str, every: int = 50) -> None:
    """拿不到宏观流动性时的节流告警（按 ``tag`` 各记一份计数）。

    Args:
        tag: 调用方名字（进日志，便于区分是哪条路取不到）。
        why: :func:`read_macro_liquidity_signal` 给出的原因。
        every: 每 N 次重复告警一次；第 1 次必告警（避免问题被节流吞掉）。
    """
    count = _miss_counts.get(tag, 0) + 1
    _miss_counts[tag] = count
    if count == 1 or count % max(1, every) == 0:
        log.warning(
            "[%s] 宏观流动性不可用（%s），本次按中性 %s 处理（累计 %d 次）",
            tag, why, NEUTRAL_MACRO_SIGNAL, count,
        )


__all__ = [
    "MACRO_LIQUIDITY_KEY",
    "NEUTRAL_MACRO_SIGNAL",
    "read_macro_liquidity_signal",
    "warn_missing",
]
