"""manas —— 可脱离交易系统单独使用的决策中枢（公共门面）。

为什么有这个包
--------------
manas 的能力（「要不要动 / 多确信 / 多危险 / 动多大」）早已**不依赖交易对象**：
`ManasEngine()` 无参可构造，喂一组 `DictBackedInputs` 就能出真实分数。
但它此前只以 `deva.naja.attention.kernel.manas_engine` 这种**内部路径**存在，
且 `import` 会被上层包入口拖着加载整个交易 / 认知域
（实测 3.4s / 3158 个模块，见 `attention/__init__.py` 的惰性导出注释）。

本包提供**稳定的公共入口**：外部应用只认 `deva.naja.manas`；
内部结构（manas_engine / manas_config / manas_inputs 怎么拆）再怎么变，
使用方不受影响。本包**只做 re-export，不重写任何逻辑**——保证
「一份实现、多处使用」，而不是造出第二份会分叉的副本。

最小用法
--------
::

    from deva.naja.manas import ManasEngine, DictBackedInputs

    src = DictBackedInputs(
        market_status="open", remaining_seconds=3600, market_volatility=1.8,
        ticks={"600000": 1.2, "000001": -0.4}, us_trading_phase="trading",
        available_capital=30.0, total_capital=100.0, total_return=-4.0,
        position_returns=[0.02, -0.01, 0.03], total_trades=12,
    )
    out = ManasEngine().compute(
        session_manager=src, scanner=src, portfolio=src, bandit_tracker=src
    )
    print(out.manas_score, out.action_type, out.alpha, out.risk_temperature)

或者用便利封装（引擎 + 输入源一起管，省去每次传四遍）::

    from deva.naja.manas import create_engine

    session = create_engine(market_status="open", remaining_seconds=3600)
    out = session.compute()

⚠️ 节流（复用时的头号坑）
------------------------
`ManasEngine.compute()` 默认**缓存结果 1 秒**（`ManasConfig.update_interval`）。
同一秒内改了输入再算，拿到的是上一次的输出——不是 bug，是设计。
需要每次立即重算，构造时传 `throttle=False`（本门面把 `update_interval` 置 0）。

详细复用指南：`docs/naja/manas_reuse_guide.md`
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── 核心引擎与输出（叶子模块，不经重包）────────────────────────────────────
from deva.naja.attention.kernel.manas_config import ManasConfig, RollingWindow
from deva.naja.attention.kernel.manas_engine import (
    MANAS_OUTPUT_GROUPS,
    ActionType,
    AttentionFocus,
    BiasState,
    CognitiveState,
    ConfidenceEngine,
    HarmonyState,
    ManasEngine,
    ManasOutput,
    MetaManas,
    PortfolioSignal,
    RegimeEngine,
    RiskEngine,
    TimingEngine,
)

# ── 输入契约与最薄适配器 ────────────────────────────────────────────────────
from deva.naja.attention.kernel.manas_inputs import (
    INPUT_CONTRACTS,
    ClockView,
    DictBackedInputs,
    MarketView,
    PortfolioView,
    SimpleStatus,
    SimpleTick,
    StrategyView,
    check_contract,
    missing_methods,
)

__all__ = [
    # 引擎与子引擎
    "ManasEngine",
    "TimingEngine",
    "RegimeEngine",
    "ConfidenceEngine",
    "RiskEngine",
    "MetaManas",
    # 配置与输出
    "ManasConfig",
    "RollingWindow",
    "ManasOutput",
    "CognitiveState",
    "MANAS_OUTPUT_GROUPS",
    # 词汇表（枚举）
    "ActionType",
    "HarmonyState",
    "BiasState",
    "AttentionFocus",
    "PortfolioSignal",
    # 输入契约
    "ClockView",
    "MarketView",
    "PortfolioView",
    "StrategyView",
    "INPUT_CONTRACTS",
    "check_contract",
    "missing_methods",
    # 最薄适配器
    "DictBackedInputs",
    "SimpleTick",
    "SimpleStatus",
    # 便利封装
    "ManasSession",
    "create_engine",
]


class ManasSession:
    """引擎 + 一个可变输入源的轻组合（**不含任何决策逻辑**）。

    解决「每次 `compute` 都要把同一个 src 传四遍」的啰嗦。`inputs` 是普通
    `DictBackedInputs`，改它的字段就是改输入::

        session = ManasSession(market_volatility=2.0, throttle=False)
        session.inputs.market_volatility = 0.8      # 改输入
        out = session.compute()                     # 立即重算

    纯转发，不缓存、不改写引擎输出。
    """

    def __init__(
        self,
        config: Optional[ManasConfig] = None,
        *,
        awakening_level_provider: Optional[Callable[[], str]] = None,
        throttle: bool = True,
        **inputs: Any,
    ):
        cfg = config or ManasConfig()
        self.throttle = bool(throttle)
        if not throttle:
            # update_interval 是 frozen config 的字段，用 replace 造一份不节流的
            cfg = replace(cfg, update_interval=0.0)
        self.engine = ManasEngine(config=cfg)
        if awakening_level_provider is not None:
            self.engine.set_awakening_level_provider(awakening_level_provider)
        self.inputs = DictBackedInputs(**inputs)

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<ManasSession throttle={self.throttle}>"

    def update(self, **inputs: Any) -> "ManasSession":
        """批量改输入字段，返回自身以便链式调用。"""
        for key, value in inputs.items():
            setattr(self.inputs, key, value)
        return self

    def compute(
        self,
        macro_signal: float = 0.5,
        narratives: Optional[List[str]] = None,
    ) -> ManasOutput:
        """用当前 `inputs` 跑一次，返回 `ManasOutput`。"""
        src = self.inputs
        return self.engine.compute(
            session_manager=src,
            scanner=src,
            portfolio=src,
            bandit_tracker=src,
            macro_signal=macro_signal,
            narratives=narratives,
        )


def create_engine(
    config: Optional[ManasConfig] = None,
    *,
    awakening_level_provider: Optional[Callable[[], str]] = None,
    throttle: bool = True,
    **inputs: Any,
) -> ManasSession:
    """一步拿到「引擎 + 输入源」（`ManasSession`）。

    Args:
        config: 引擎配置；缺省用 `ManasConfig()` 的默认策略。
        awakening_level_provider: 觉醒等级提供函数（`() -> str`，取值
            dormant / awakening / illuminated / enlightened）。缺省不注入，
            调节链的觉醒环节恒 ×1.0——这是**本仓外使用时的正常状态**。
        throttle: `False` 则关闭 compute 的 1 秒结果缓存（见模块 docstring）。
        **inputs: 直接透传给 `DictBackedInputs` 的字段
            （market_status / market_volatility / ticks / available_capital …）。
    """
    return ManasSession(
        config=config,
        awakening_level_provider=awakening_level_provider,
        throttle=throttle,
        **inputs,
    )
