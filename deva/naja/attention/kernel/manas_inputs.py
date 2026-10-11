"""
ManasEngine 外部输入契约（Protocol）

================================================================================
为什么要有这个文件
================================================================================

ManasEngine 的四个子引擎各自从外部对象取数，接口全靠鸭子类型 + try/except 兜底：

    session_manager.get_market_status("china_a")        # TimingEngine
    scanner.get_market_volatility()                     # TimingEngine / RiskEngine
    portfolio.get_summary()['available_capital']        # RiskEngine
    tracker.get_position_history(limit=20)              # ConfidenceEngine
    tracker.get_strategy_summary("default")             # ConfidenceEngine

鸭子类型本身没问题，问题在于**回退是静默的**：
「对象根本没有这个方法」与「数据正常、但恰好等于默认值」在外部完全无法区分
——唯一的痕迹是一行 log.debug，生产日志级别下看不见。

本文件把这些方法声明成显式契约，并写明**缺失时引擎会退化成什么值**，
使「接错线」从不可观测的静默行为变成可检测的违约。

校验入口：scripts/verify/verify_manas_input_contract.py

================================================================================
契约方法与静默回退对照表（改契约前先看这张表）
================================================================================

    契约方法                                  缺失 / 返回 None 时的退化结果
    --------------------------------------------------------------------------
    ClockView.get_market_status                time_pressure 恒 0.5
    ClockView.get_session_remaining_seconds    time_pressure 恒 0.5
    MarketView.get_market_volatility           Timing 波动率维恒 0.5 / Risk 恒 1.0
    MarketView.get_last_data                   成交密度、指数趋势、题材扩散 恒 0
    MarketView.get_market_summary              结构断裂恒 0.5；regime 自适应权重失效
    MarketView.get_liquidity_adjustment        退化为 macro_signal * 2 - 1
    PortfolioView.get_summary                  cash_ratio 恒 0.5、drawdown 恒 0 → T 恒 1.25
    StrategyView.get_position_history          hit_rate 恒 0.5、rolling_pnl 恒 0
    StrategyView.get_strategy_summary          bandit_conf 恒 0.5 → confidence 恒 0.35

注意这些数值不是「安全兜底」，而是**把对应维度整体摘掉**：
TimingEngine 四个维度里有两个会变成常数，RiskEngine 三个输入里有两个是常数。

================================================================================
附带的跨域种子：DictBackedInputs
================================================================================

DictBackedInputs 用纯 dict / 基本类型实现上述全部四个契约，同一个实例可以同时
充当 session_manager、scanner、portfolio、bandit_tracker。它有两个用处：

    • 单测：构造 ManasEngine 不需要任何交易对象；
    • 复用：把 ManasEngine 搬出交易域时，这就是最薄的适配层样板。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


__all__ = [
    "ClockView",
    "MarketView",
    "PortfolioView",
    "StrategyView",
    "INPUT_CONTRACTS",
    "missing_methods",
    "check_contract",
    "SimpleTick",
    "SimpleStatus",
    "DictBackedInputs",
]


# =============================================================================
# 四个输入契约
# =============================================================================

@runtime_checkable
class ClockView(Protocol):
    """交易时钟：TimingEngine 用它算「时间压力」。

    生产实现：MarketSessionManager（radar/global_market_config.py）。
    注意 TradingClock 不满足本契约——它只有 cn_phase / us_phase / get_global_status，
    把 TradingClock 当 session_manager 传进来，时间压力维会恒为 0.5。
    """

    def get_market_status(self, market_id: str) -> Any:
        """返回带 .value 的状态对象，.value == "open" 表示开市。"""
        ...

    def get_session_remaining_seconds(self, market_id: str) -> Optional[float]:
        """距本时段收盘的剩余秒数；非交易时段可为 None。"""
        ...


@runtime_checkable
class MarketView(Protocol):
    """市场视图：TimingEngine 与 RegimeEngine 的共用数据源。

    生产实现：GlobalMarketScanner（radar/global_market_scanner.py）。
    """

    def get_market_volatility(self) -> Optional[float]:
        """当前市场波动率（标准差量纲，>1.5 / >2.0 会触发保守档）。"""
        ...

    def get_last_data(self) -> Dict[str, Any]:
        """{标的代码: 行情对象}，行情对象需带 float 型 .change_pct。"""
        ...

    def get_market_summary(self) -> Dict[str, Any]:
        """市场汇总，需含 'us_trading_phase'（trading / pre_market / after_hours / closed）。"""
        ...

    def get_liquidity_adjustment(self, target_market: str) -> Optional[Dict[str, Any]]:
        """流动性调整结果，需含 'adjusted_signal'（0~1）。"""
        ...


@runtime_checkable
class PortfolioView(Protocol):
    """持仓视图：RiskEngine 用它算风险温度 T。

    生产实现：VirtualPortfolio（bandit/virtual_portfolio.py）。
    """

    def get_summary(self) -> Dict[str, Any]:
        """需含 available_capital / total_capital / total_return 三个键。

        单位口径（踩过坑，务必对齐）：
          · available_capital / total_capital：绝对金额。total_capital 是
            cash_ratio = available / total 的**分母**——缺了它，调用方一律
            兜底成 1，比值会退化成「可用资金的数值本身」，T 随之撞下限。
          · total_return：**百分数**（3.5 表示 +3.5%），与生产实现
            VirtualPortfolio、其 UI 以及 attention/kernel/state.py 的阈值
            （-5 / -2 / 10）一致。而 manas 的加档阈值是小数口径
            （0.05 / 0.1），因此 manas 在消费时会自行 /100 归一。
        """
        ...


@runtime_checkable
class StrategyView(Protocol):
    """策略表现视图：ConfidenceEngine 用它算自信度。

    生产实现：BanditPositionTracker（bandit/tracker.py）。
    """

    def get_position_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """最近的平仓记录，每条需含 float 型 'return_pct'。"""
        ...

    def get_strategy_summary(self, strategy_id: str) -> Dict[str, Any]:
        """按策略 id 的汇总，需含 int 型 'total_trades'。"""
        ...


# =============================================================================
# 契约检查工具
# =============================================================================

#: 契约名 → (Protocol, 必需方法名元组)。供校验脚本与测试共用。
INPUT_CONTRACTS: Dict[str, Any] = {
    "ClockView": (ClockView, ("get_market_status", "get_session_remaining_seconds")),
    "MarketView": (
        MarketView,
        ("get_market_volatility", "get_last_data", "get_market_summary", "get_liquidity_adjustment"),
    ),
    "PortfolioView": (PortfolioView, ("get_summary",)),
    "StrategyView": (StrategyView, ("get_position_history", "get_strategy_summary")),
}


def missing_methods(obj: Any, methods) -> List[str]:
    """返回 obj 上缺失（或不可调用）的方法名列表。

    对类传入时按类属性检查，不需要实例化——校验脚本因此可以直接喂类对象。
    """
    return [name for name in methods if not callable(getattr(obj, name, None))]


def check_contract(obj: Any, contract_name: str) -> List[str]:
    """检查 obj 是否满足指定契约，返回缺失的方法名（空列表 = 满足）。

    契约名拼错时抛 KeyError——拼错的检查应当立刻炸，而不是静默「通过」。
    """
    _protocol, methods = INPUT_CONTRACTS[contract_name]
    return missing_methods(obj, methods)


# =============================================================================
# 纯 dict 适配器（跨域复用 / 单测种子）
# =============================================================================

@dataclass
class SimpleTick:
    """最小行情对象：只会被读 .change_pct。"""

    change_pct: float = 0.0


@dataclass
class SimpleStatus:
    """最小市场状态对象：只会被读 .value。"""

    value: str = "closed"


@dataclass
class DictBackedInputs:
    """用纯 dict / 基本类型实现四个契约的适配器。

    一个实例可以同时作为 session_manager、scanner、portfolio、bandit_tracker
    传给 ManasEngine.compute()，从而在完全没有交易对象的情况下跑出真实分数：

        src = DictBackedInputs(
            market_status="open", remaining_seconds=3600,
            market_volatility=1.8, ticks={"600000": 1.2, "000001": -0.4},
            us_trading_phase="trading",
            available_capital=30.0, total_capital=100.0, total_return=-4.0,
            position_returns=[0.02, -0.01, 0.03], total_trades=12,
        )
        out = ManasEngine().compute(
            session_manager=src, scanner=src, portfolio=src, bandit_tracker=src
        )

    字段语义与真实对象一致；None 表示「该维度没有数据」，此时引擎按契约表退化。
    total_return 为**百分数**（-4.0 表示 -4%），见 PortfolioView.get_summary。
    """

    # —— ClockView / MarketView 的时段信息 ——
    market_status: str = "closed"
    remaining_seconds: Optional[float] = None

    # —— MarketView ——
    market_volatility: Optional[float] = 1.0
    ticks: Dict[str, float] = field(default_factory=dict)
    us_trading_phase: str = "closed"
    liquidity_signal: Optional[float] = None

    # —— PortfolioView ——
    available_capital: float = 50.0
    total_capital: float = 100.0
    total_return: float = 0.0        # 百分数（-4.0 表示 -4%）

    # —— StrategyView ——
    position_returns: List[float] = field(default_factory=list)
    total_trades: int = 0

    # --- ClockView ---

    def get_market_status(self, market_id: str = "china_a") -> SimpleStatus:
        return SimpleStatus(self.market_status)

    def get_session_remaining_seconds(self, market_id: str = "china_a") -> Optional[float]:
        return self.remaining_seconds

    # --- MarketView ---

    def get_market_volatility(self) -> Optional[float]:
        return self.market_volatility

    def get_last_data(self) -> Dict[str, Any]:
        return {code: SimpleTick(change_pct) for code, change_pct in self.ticks.items()}

    def get_market_summary(self) -> Dict[str, Any]:
        return {"us_trading_phase": self.us_trading_phase}

    def get_liquidity_adjustment(self, target_market: str = "CHINA_A") -> Optional[Dict[str, Any]]:
        if self.liquidity_signal is None:
            return None
        return {"adjusted_signal": self.liquidity_signal}

    # --- PortfolioView ---

    def get_summary(self) -> Dict[str, Any]:
        return {
            "available_capital": self.available_capital,
            "total_capital": self.total_capital,
            "total_return": self.total_return,
        }

    # --- StrategyView ---

    def get_position_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        return [{"return_pct": r} for r in self.position_returns[-limit:]]

    def get_strategy_summary(self, strategy_id: str = "default") -> Dict[str, Any]:
        return {"total_trades": self.total_trades}
