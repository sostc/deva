"""
PositionSizer - 仓位管理器

觉醒系统的仓位管理层，根据多种因素计算最优仓位

核心能力：
1. KellySizer: Kelly公式仓位
2. VolatilitySizer: 波动率调整仓位
3. ConfidenceSizer: 置信度调整仓位
4. RiskParitySizer: 风险平价仓位
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger(__name__)


class SizingMethod(Enum):
    """仓位计算方法"""
    KELLY = "kelly"                 # Kelly公式
    VOLATILITY = "volatility"       # 波动率调整
    CONFIDENCE = "confidence"        # 置信度调整
    RISK_PARITY = "risk_parity"     # 风险平价
    FIXED = "fixed"                 # 固定比例


@dataclass
class PositionSize:
    """仓位建议"""
    symbol: str
    method: SizingMethod
    size_ratio: float              # 仓位比例
    quantity: int                  # 交易数量
    confidence: float              # 置信度
    reasoning: List[str]           # 计算理由


class KellySizer:
    """
    Kelly公式仓位计算器

    f* = (bp - q) / b
    其中：
    f* = 仓位比例
    b = 赔率（盈亏比）
    p = 胜率
    q = 1 - p
    """

    def __init__(self, max_kelly_ratio: float = 0.25):
        self.max_kelly_ratio = max_kelly_ratio

    def calculate(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        total_capital: float
    ) -> PositionSize:
        """
        计算Kelly仓位

        Args:
            win_rate: 胜率 (0-1)
            avg_win: 平均盈利
            avg_loss: 平均亏损
            total_capital: 总资金

        Returns:
            仓位建议
        """
        if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
            return PositionSize(
                symbol="",
                method=SizingMethod.KELLY,
                size_ratio=0,
                quantity=0,
                confidence=0,
                reasoning=["参数无效"]
            )

        b = avg_win / avg_loss
        p = win_rate
        q = 1 - p

        kelly_ratio = (b * p - q) / b

        if kelly_ratio <= 0:
            reasoning = ["期望收益为负，不建议持仓"]
            return PositionSize(
                symbol="",
                method=SizingMethod.KELLY,
                size_ratio=0,
                quantity=0,
                confidence=0,
                reasoning=reasoning
            )

        adjusted_ratio = min(kelly_ratio, self.max_kelly_ratio)
        confidence = min(1.0, kelly_ratio / self.max_kelly_ratio)

        reasoning = [
            f"Kelly公式: f* = ({b:.2f} × {p:.1%} - {q:.1%}) / {b:.2f} = {kelly_ratio:.1%}",
            f"原始建议仓位: {kelly_ratio:.1%}",
            f"上限调整后: {adjusted_ratio:.1%}"
        ]

        return PositionSize(
            symbol="",
            method=SizingMethod.KELLY,
            size_ratio=adjusted_ratio,
            quantity=int(total_capital * adjusted_ratio / avg_loss / 100) * 100,
            confidence=confidence,
            reasoning=reasoning
        )


class VolatilitySizer:
    """
    波动率调整仓位计算器

    目标：根据市场波动率调整仓位，保持风险恒定
    size = target_volatility / current_volatility
    """

    def __init__(self, target_volatility: float = 0.15):
        self.target_volatility = target_volatility

    def calculate(
        self,
        symbol: str,
        current_volatility: float,
        price: float,
        total_capital: float
    ) -> PositionSize:
        """
        计算波动率调整仓位

        Args:
            symbol: 股票代码
            current_volatility: 当前波动率 (年化)
            price: 当前价格
            total_capital: 总资金

        Returns:
            仓位建议
        """
        if current_volatility <= 0:
            reasoning = ["波动率无效，设置为默认值"]
            return PositionSize(
                symbol=symbol,
                method=SizingMethod.VOLATILITY,
                size_ratio=0.1,
                quantity=int(total_capital * 0.1 / price / 100) * 100,
                confidence=0.5,
                reasoning=reasoning
            )

        vol_ratio = self.target_volatility / current_volatility
        size_ratio = min(1.0, max(0.05, vol_ratio))

        confidence = 1.0 - min(1.0, abs(vol_ratio - 1.0))

        reasoning = [
            f"目标波动率: {self.target_volatility:.1%}",
            f"当前波动率: {current_volatility:.1%}",
            f"波动率比: {vol_ratio:.2f}",
            f"调整后仓位: {size_ratio:.1%}"
        ]

        return PositionSize(
            symbol=symbol,
            method=SizingMethod.VOLATILITY,
            size_ratio=size_ratio,
            quantity=int(total_capital * size_ratio / price / 100) * 100,
            confidence=confidence,
            reasoning=reasoning
        )


class ConfidenceSizer:
    """
    置信度调整仓位计算器

    根据信号的置信度调整仓位
    """

    def __init__(self, base_size: float = 0.1):
        self.base_size = base_size

    def calculate(
        self,
        symbol: str,
        signal_confidence: float,
        price: float,
        total_capital: float
    ) -> PositionSize:
        """
        计算置信度调整仓位

        Args:
            symbol: 股票代码
            signal_confidence: 信号置信度 (0-1)
            price: 当前价格
            total_capital: 总资金

        Returns:
            仓位建议
        """
        size_ratio = self.base_size * signal_confidence
        size_ratio = max(0.01, min(0.3, size_ratio))

        reasoning = [
            f"基础仓位: {self.base_size:.1%}",
            f"信号置信度: {signal_confidence:.1%}",
            f"调整后仓位: {size_ratio:.1%}"
        ]

        return PositionSize(
            symbol=symbol,
            method=SizingMethod.CONFIDENCE,
            size_ratio=size_ratio,
            quantity=int(total_capital * size_ratio / price / 100) * 100,
            confidence=signal_confidence,
            reasoning=reasoning
        )


class RiskParitySizer:
    """
    风险平价仓位计算器

    各资产对组合风险的贡献相等
    """

    def __init__(self, target_risk: float = 0.1):
        self.target_risk = target_risk

    def calculate_for_portfolio(
        self,
        positions: Dict[str, Dict],
        volatilities: Dict[str, float],
        total_capital: float
    ) -> List[PositionSize]:
        """
        计算风险平价仓位

        Args:
            positions: 持仓字典
            volatilities: 各资产波动率
            total_capital: 总资金

        Returns:
            各资产仓位建议列表
        """
        if not positions:
            return []

        total_vol_adjusted_risk = sum(
            volatilities.get(symbol, 0.2) * pos.get("quantity", 0) * pos.get("price", 0)
            for symbol, pos in positions.items()
        )

        if total_vol_adjusted_risk <= 0:
            equal_size = 1.0 / len(positions)
            return [
                PositionSize(
                    symbol=symbol,
                    method=SizingMethod.RISK_PARITY,
                    size_ratio=equal_size,
                    quantity=int(total_capital * equal_size / pos.get("price", 10) / 100) * 100,
                    confidence=0.5,
                    reasoning=["总风险无效，等权分配"]
                )
                for symbol, pos in positions.items()
            ]

        position_sizes = []

        for symbol, pos in positions.items():
            vol = volatilities.get(symbol, 0.2)
            price = pos.get("price", 10)
            quantity = pos.get("quantity", 0)

            current_risk_contribution = vol * quantity * price
            risk_weight = current_risk_contribution / total_vol_adjusted_risk

            target_value = self.target_risk * total_capital
            adjusted_quantity = target_value / price / vol if vol > 0 else target_value / price
            adjusted_size_ratio = (adjusted_quantity * price) / total_capital

            adjusted_size_ratio = max(0.01, min(0.4, adjusted_size_ratio))

            reasoning = [
                f"当前风险贡献: {risk_weight:.1%}",
                f"目标风险: {self.target_risk:.1%}",
                f"调整后仓位: {adjusted_size_ratio:.1%}"
            ]

            position_sizes.append(PositionSize(
                symbol=symbol,
                method=SizingMethod.RISK_PARITY,
                size_ratio=adjusted_size_ratio,
                quantity=int(adjusted_quantity / 100) * 100,
                confidence=0.6,
                reasoning=reasoning
            ))

        return position_sizes


class PositionSizer:
    """
    仓位管理器（综合多种方法）

    根据不同场景选择最优仓位计算方法
    """

    def __init__(self):
        self.kelly_sizer = KellySizer()
        self.volatility_sizer = VolatilitySizer()
        self.confidence_sizer = ConfidenceSizer()
        self.risk_parity_sizer = RiskParitySizer()

    def calculate_size(
        self,
        symbol: str,
        price: float,
        total_capital: float,
        method: SizingMethod,
        **kwargs
    ) -> PositionSize:
        """
        计算仓位

        Args:
            symbol: 股票代码
            price: 当前价格
            total_capital: 总资金
            method: 计算方法
            **kwargs: 其他参数（根据方法不同而不同）

        Returns:
            仓位建议
        """
        if method == SizingMethod.KELLY:
            return self.kelly_sizer.calculate(
                win_rate=kwargs.get("win_rate", 0.5),
                avg_win=kwargs.get("avg_win", 1000),
                avg_loss=kwargs.get("avg_loss", 500),
                total_capital=total_capital
            )

        elif method == SizingMethod.VOLATILITY:
            return self.volatility_sizer.calculate(
                symbol=symbol,
                current_volatility=kwargs.get("current_volatility", 0.3),
                price=price,
                total_capital=total_capital
            )

        elif method == SizingMethod.CONFIDENCE:
            return self.confidence_sizer.calculate(
                symbol=symbol,
                signal_confidence=kwargs.get("signal_confidence", 0.5),
                price=price,
                total_capital=total_capital
            )

        else:
            fixed_ratio = kwargs.get("fixed_ratio", 0.1)
            return PositionSize(
                symbol=symbol,
                method=SizingMethod.FIXED,
                size_ratio=fixed_ratio,
                quantity=int(total_capital * fixed_ratio / price / 100) * 100,
                confidence=0.5,
                reasoning=[f"固定仓位: {fixed_ratio:.1%}"]
            )

    def calculate_optimal_size(
        self,
        symbol: str,
        price: float,
        total_capital: float,
        signal_confidence: float = 0.5,
        win_rate: Optional[float] = None,
        avg_win: float = 1000,
        avg_loss: float = 500,
        volatility: float = 0.3
    ) -> PositionSize:
        """
        计算综合最优仓位

        综合 Kelly、波动率、置信度三种方法
        """
        kelly_size = self.kelly_sizer.calculate(
            win_rate=win_rate if win_rate else signal_confidence,
            avg_win=avg_win,
            avg_loss=avg_loss,
            total_capital=total_capital
        )

        vol_size = self.volatility_sizer.calculate(
            symbol=symbol,
            current_volatility=volatility,
            price=price,
            total_capital=total_capital
        )

        conf_size = self.confidence_sizer.calculate(
            symbol=symbol,
            signal_confidence=signal_confidence,
            price=price,
            total_capital=total_capital
        )

        final_ratio = (
            kelly_size.size_ratio * 0.4 +
            vol_size.size_ratio * 0.3 +
            conf_size.size_ratio * 0.3
        )

        final_ratio = max(0.01, min(0.3, final_ratio))

        reasoning = [
            f"Kelly建议: {kelly_size.size_ratio:.1%}",
            f"波动率建议: {vol_size.size_ratio:.1%}",
            f"置信度建议: {conf_size.size_ratio:.1%}",
            f"综合仓位: {final_ratio:.1%}"
        ]

        return PositionSize(
            symbol=symbol,
            method=SizingMethod.KELLY,
            size_ratio=final_ratio,
            quantity=int(total_capital * final_ratio / price / 100) * 100,
            confidence=signal_confidence,
            reasoning=reasoning
        )