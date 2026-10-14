"""目标（Objective）—— 声明「要达成什么状态」，不写怎么做。

和「指令」的区别
================
指令是「买 5900 股 588200」；目标是「588200 占到总资产 40%」。
中间那一步「现在该买多少」留给决策中心，不由目标层拍板。

❗为什么必须显式带结算点
========================
一个没有结算点的目标，和一条已经死掉的线程**长得一模一样** ——
两者都表现为「日志里什么都不再出现」。这是本仓库头号病理（静默失效家族）的
标准形态。所以这里在**构造时就强制**：没有 ``max_wait_seconds`` 直接报错，
而不是等到运行时用默认值兜过去。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

__all__ = [
    "MissingSettlementPoint",
    "Objective",
    "WatchContext",
    "OBJECTIVE_KINDS",
]


class MissingSettlementPoint(ValueError):
    """目标缺少结算点 —— 不允许存在「可以无限期等下去」的守望。"""


#: 目前支持的目标类型。扩展时往这里加，并在消费方实现解析。
OBJECTIVE_KINDS = (
    "establish_core",   # 建立 / 补足底仓到目标占比
    "reduce_position",  # 减仓 / 止盈 / 止损
    "rotate_cost",      # 做 T：把持仓成本降下来
)


@dataclass
class Objective:
    """一个待达成的状态。

    :param max_wait_seconds: **必填**。守望最长可以等多久，到点必须结算。
        到期未达成就是 ``expired``，会把这件事明确记下来，而不是继续沉默地等。
    :param params: 与 :attr:`kind` 相关的参数。取值一律走 :meth:`param` /
        :meth:`require`，缺键要**报错**而不是悄悄拿默认值 ——
        幽灵配置正是从这里长出来的。
    """

    id: str
    kind: str
    subject: str
    market: str = ""
    max_wait_seconds: Optional[float] = None
    params: Dict[str, Any] = field(default_factory=dict)
    note: str = ""
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not str(self.id or "").strip():
            raise ValueError("Objective.id 不能为空")
        if self.max_wait_seconds is None or float(self.max_wait_seconds) <= 0:
            # ❗结构性强制：不存在「无限期守望」
            raise MissingSettlementPoint(
                f"目标 {self.id!r} 没有结算点（max_wait_seconds 必须为正数）—— "
                "不允许存在可以无限期等下去的守望"
            )

    # ------------------------------------------------------------------
    def param(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)

    def require(self, *keys: str) -> Dict[str, Any]:
        """取出必需参数，缺一个就报错（**不用默认值糊过去**）。"""
        missing = [k for k in keys if k not in self.params or self.params[k] is None]
        if missing:
            raise KeyError(f"目标 {self.id} 缺少必需参数：{missing}")
        return {k: self.params[k] for k in keys}

    def describe(self) -> str:
        return self.note or f"{self.kind}@{self.subject}"


@dataclass(frozen=True)
class WatchContext:
    """一次守望轮询的观测面。**只读**，守望不修改任何东西。

    所有字段都可以是 ``None`` —— ``None`` 的语义是「这一路没取到」，
    ❗绝不等价于「取到了空值/零值」。判据必须据此返回三态中的 ``unknown``。
    """

    #: 本轮轮询时刻（epoch 秒）
    now: float
    #: 现价；``None`` = 行情没取到
    price: Optional[float] = None
    #: 外生锚（如昨收）；``None`` = 锚没算出来
    anchor: Optional[float] = None
    #: 距收盘/结算的分钟数；``None`` = 休市或未知
    minutes_to_close: Optional[float] = None
    #: 决策中心当前档位；``None`` = 没问到
    action_type: Optional[str] = None
    #: 各类判据可能需要的额外观测，按名字取
    extras: Dict[str, Any] = field(default_factory=dict)

    def value(self, name: str, default: Any = None) -> Any:
        """取额外观测。缺失返回 default —— 调用方有责任把「缺」变成 unknown。"""
        return self.extras.get(name, default)

    @property
    def readable(self) -> bool:
        """有没有最基本的观测（价格）。没有的话多数判据只能给 unknown。"""
        return self.price is not None


def make_context(now: Optional[float] = None, **kwargs: Any) -> WatchContext:
    """便捷构造。``extras`` 之外的键直接落到同名字段上。"""
    return WatchContext(now=now if now is not None else time.time(), **kwargs)
