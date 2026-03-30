"""
LiquidityVerificationScheduler - 智能验证时间调度器

根据A股交易时间节奏动态计算预测验证时间

核心逻辑：
1. 预测创建时，根据事件发生时间和目标市场状态计算"理论验证时间"
2. 目标市场开市时，执行验证
3. 目标市场休市时，等待到下一个开市时间
4. 盘中波动剧烈时，提前验证
"""

import time
import logging
from typing import Dict, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, time as dt_time

log = logging.getLogger(__name__)


class MarketSession(Enum):
    """市场状态"""
    PRE_MARKET = "pre_market"      # 盘前
    OPEN = "open"                  # 交易中
    CLOSED = "closed"              # 休市
    LUNCH = "lunch"               # 午休


@dataclass
class VerificationSchedule:
    """验证时间表"""
    verify_at: float              # 验证时间戳
    verify_type: str              # "at_market_open" / "delayed" / "immediate" / "at_next_open"
    reason: str                   # 原因说明
    market_status: MarketSession # 创建时的市场状态


class LiquidityVerificationScheduler:
    """
    智能验证时间调度器

    根据以下因素动态计算验证时间：
    1. 事件发生时间（美股/期货）
    2. A股当前状态（盘前/盘中/休市/尾盘）
    3. 预期传播速度（恐慌时更快）
    4. 距离开盘/闭盘时间
    """

    # A股交易时间（北京时间）
    A_SHARE_PRE_MARKET_START = dt_time(9, 0)
    A_SHARE_PRE_MARKET_END = dt_time(9, 15)
    A_SHARE_OPEN = dt_time(9, 30)
    A_SHARE_LUNCH_START = dt_time(11, 30)
    A_SHARE_LUNCH_END = dt_time(13, 0)
    A_SHARE_CLOSE = dt_time(15, 0)

    # 美股期货换月/交易时间
    US_FUTURES_OPEN = dt_time(6, 0)   # 北京时间
    US_MARKET_CLOSE = dt_time(5, 0)   # 北京时间（次日）

    # 各时段预期传播延迟（分钟）
    PROPAGATION_DELAYS = {
        "pre_market_event": 30,        # 盘前事件
        "open_market_event": 15,        # 盘中事件
        "lunch_event": 20,             # 午休事件
        "us_futures_during_asia_night": 60,  # 亚洲夜间美股期货
        "emergency_event": 5,           # 紧急事件（快速验证）
    }

    def __init__(self):
        self._timezone_offset = 8 * 3600  # 北京时区

    def _is_market_open(self, market: str = "a_share") -> Tuple[bool, MarketSession]:
        """检查市场是否开市"""
        now = datetime.now()
        current_time = now.time()

        if market == "a_share":
            return self._is_a_share_open(current_time, now)
        elif market == "hk_equity":
            return self._is_hk_open(current_time, now)
        elif market == "us_equity":
            return self._is_us_open(current_time, now)

        return False, MarketSession.CLOSED

    def _is_a_share_open(self, current_time, now) -> Tuple[bool, MarketSession]:
        """检查A股是否开市"""
        # 周末
        if now.weekday() >= 5:
            return False, MarketSession.CLOSED

        # 盘前
        if self.A_SHARE_PRE_MARKET_START <= current_time < self.A_SHARE_PRE_MARKET_END:
            return True, MarketSession.PRE_MARKET

        # 上午交易
        if self.A_SHARE_OPEN <= current_time < self.A_SHARE_LUNCH_START:
            return True, MarketSession.OPEN

        # 午休
        if self.A_SHARE_LUNCH_START <= current_time < self.A_SHARE_LUNCH_END:
            return False, MarketSession.LUNCH

        # 下午交易
        if self.A_SHARE_LUNCH_END <= current_time < self.A_SHARE_CLOSE:
            return True, MarketSession.OPEN

        # 盘后
        return False, MarketSession.CLOSED

    def _is_hk_open(self, current_time, now) -> Tuple[bool, MarketSession]:
        """检查港股是否开市"""
        if now.weekday() >= 5:
            return False, MarketSession.CLOSED

        HK_OPEN = dt_time(9, 30)
        HK_CLOSE = dt_time(16, 0)

        if HK_OPEN <= current_time < HK_CLOSE:
            return True, MarketSession.OPEN
        return False, MarketSession.CLOSED

    def _is_us_open(self, current_time, now) -> Tuple[bool, MarketSession]:
        """检查美股是否开市（简化）"""
        if now.weekday() >= 5:
            return False, MarketSession.CLOSED

        # 美股交易时间北京时间 21:30-4:00（次日）
        US_OPEN = dt_time(21, 30)
        US_CLOSE_NEXT = dt_time(4, 0)

        if current_time >= US_OPEN or current_time < US_CLOSE_NEXT:
            return True, MarketSession.OPEN
        return False, MarketSession.CLOSED

    def _get_next_open_time(self, market: str = "a_share") -> float:
        """获取下一个开盘时间戳"""
        now = datetime.now()
        current_time = now.time()

        if market == "a_share":
            return self._get_next_a_share_open(now, current_time)
        elif market == "hk_equity":
            return self._get_next_hk_open(now, current_time)

        return time.time() + 3600  # 默认1小时

    def _get_next_a_share_open(self, now, current_time) -> float:
        """获取A股下一个开盘时间"""
        # 今天是工作日
        if now.weekday() < 5:
            # 现在是盘前(9:00-9:15)
            if current_time < self.A_SHARE_OPEN:
                # 今天9:30开盘
                next_open = now.replace(
                    hour=9, minute=30, second=0, microsecond=0
                )
                return next_open.timestamp()

            # 现在是盘中(9:30-11:30)
            if current_time < self.A_SHARE_LUNCH_START:
                return now.timestamp()  # 已经开盘，立即

            # 现在是午休(11:30-13:00)
            if current_time < self.A_SHARE_LUNCH_END:
                next_open = now.replace(
                    hour=13, minute=0, second=0, microsecond=0
                )
                return next_open.timestamp()

            # 现在是下午盘中(13:00-15:00)
            if current_time < self.A_SHARE_CLOSE:
                return now.timestamp()  # 已经开盘，立即

        # 现在是盘后或周末，需要到下一个工作日
        days_ahead = (7 - now.weekday()) % 7  # 到周一的天数
        if days_ahead == 0:
            days_ahead = 1  # 如果是周日，需要等1天

        next_monday = now.replace(
            hour=9, minute=30, second=0, microsecond=0
        ) + timedelta(days=days_ahead)

        return next_monday.timestamp()

    def _get_next_hk_open(self, now, current_time) -> float:
        """获取港股下一个开盘时间"""
        if now.weekday() < 5:
            HK_OPEN = dt_time(9, 30)
            if current_time < HK_OPEN:
                next_open = now.replace(
                    hour=9, minute=30, second=0, microsecond=0
                )
                return next_open.timestamp()

        days_ahead = (7 - now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 1

        next_open = now.replace(
            hour=9, minute=30, second=0, microsecond=0
        ) + timedelta(days=days_ahead)

        return next_open.timestamp()

    def calculate_verification_time(
        self,
        event_time: float,
        from_market: str,
        to_market: str,
        event_severity: float = 0.5,
        is_emergency: bool = False,
    ) -> VerificationSchedule:
        """
        计算验证时间

        Args:
            event_time: 事件发生时间戳
            from_market: 源市场 (us_equity, us_futures, etc.)
            to_market: 目标市场 (a_share, hk_equity)
            event_severity: 事件严重程度 0-1
            is_emergency: 是否紧急事件

        Returns:
            VerificationSchedule: 包含验证时间和类型
        """
        now = datetime.now()
        current_time = now.time()
        is_open, session = self._is_market_open(to_market)

        if is_emergency:
            return VerificationSchedule(
                verify_at=time.time() + 5 * 60,  # 5分钟后
                verify_type="immediate",
                reason="紧急事件，快速验证",
                market_status=session,
            )

        if to_market == "a_share":
            return self._calculate_for_a_share(
                event_time, from_market, is_open, session, event_severity
            )
        elif to_market == "hk_equity":
            return self._calculate_for_hk(
                event_time, from_market, is_open, session, event_severity
            )

        # 默认30分钟
        return VerificationSchedule(
            verify_at=event_time + 30 * 60,
            verify_type="delayed",
            reason="默认30分钟验证",
            market_status=session,
        )

    def _calculate_for_a_share(
        self,
        event_time: float,
        from_market: str,
        is_open: bool,
        session: MarketSession,
        event_severity: float,
    ) -> VerificationSchedule:
        """为A股计算验证时间"""
        now = datetime.now()
        current_time = now.time()

        # 紧急/重大事件
        if event_severity > 0.8:
            if is_open:
                return VerificationSchedule(
                    verify_at=time.time() + 10 * 60,  # 10分钟后
                    verify_type="immediate",
                    reason="重大事件，盘中介入验证",
                    market_status=session,
                )
            else:
                return VerificationSchedule(
                    verify_at=time.time() + 20 * 60,  # 20分钟后
                    verify_type="at_market_open",
                    reason="重大事件，开盘即验证",
                    market_status=session,
                )

        # 盘前事件（9:00-9:15）
        if session == MarketSession.PRE_MARKET:
            return VerificationSchedule(
                verify_at=time.time() + 15 * 60,  # 9:30开盘后15分钟
                verify_type="at_market_open",
                reason="盘前事件，开盘验证",
                market_status=session,
            )

        # 午休事件
        if session == MarketSession.LUNCH:
            return VerificationSchedule(
                verify_at=time.time() + 30 * 60,  # 13:00开盘后验证
                verify_type="delayed",
                reason="午休事件，午后开盘验证",
                market_status=session,
            )

        # 盘中事件
        if is_open and session == MarketSession.OPEN:
            # 尾盘（14:30后）事件需要更早验证
            if current_time >= dt_time(14, 30):
                return VerificationSchedule(
                    verify_at=time.time() + 10 * 60,  # 10分钟后
                    verify_type="delayed",
                    reason="尾盘事件，提前验证",
                    market_status=session,
                )

            # 盘中正常事件
            base_delay = 20 if event_severity > 0.5 else 30
            return VerificationSchedule(
                verify_at=time.time() + base_delay * 60,
                verify_type="delayed",
                reason=f"盘中事件，{base_delay}分钟后验证",
                market_status=session,
            )

        # 盘后事件 → 下一个开盘验证
        next_open_time = self._get_next_open_time("a_share")
        return VerificationSchedule(
            verify_at=next_open_time + 15 * 60,  # 开盘后15分钟
            verify_type="at_next_open",
            reason="盘后事件，下一开盘验证",
            market_status=session,
        )

    def _calculate_for_hk(
        self,
        event_time: float,
        from_market: str,
        is_open: bool,
        session: MarketSession,
        event_severity: float,
    ) -> VerificationSchedule:
        """为港股计算验证时间"""
        if is_open:
            return VerificationSchedule(
                verify_at=time.time() + 15 * 60,
                verify_type="delayed",
                reason="盘中事件，15分钟后验证",
                market_status=session,
            )

        next_open_time = self._get_next_open_time("hk_equity")
        return VerificationSchedule(
            verify_at=next_open_time + 15 * 60,
            verify_type="at_next_open",
            reason="休市事件，下一开盘验证",
            market_status=session,
        )

    def get_market_status(self, market: str = "a_share") -> Dict[str, Any]:
        """获取市场状态信息"""
        is_open, session = self._is_market_open(market)
        next_open = self._get_next_open_time(market)

        status = {
            "market": market,
            "is_open": is_open,
            "session": session.value,
            "current_time": datetime.now().isoformat(),
            "next_open_timestamp": next_open,
            "next_open_readable": datetime.fromtimestamp(next_open).isoformat(),
        }

        if market == "a_share":
            status["trading_hours"] = "09:30-11:30, 13:00-15:00"
            status["pre_market"] = "09:00-09:15"
        elif market == "hk_equity":
            status["trading_hours"] = "09:30-16:00"

        return status


from datetime import timedelta
