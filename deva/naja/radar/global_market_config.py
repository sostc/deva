"""
GlobalMarketConfig - 全球市场交易时间配置

定义全球各市场的交易时间、时区和扫描优先级

TODO (2026-03-29): 当开始做美股交易时，需要将这里的市场配置接入 TradingClock
参考: AGENTS.md 中的 "TradingClock 与 GlobalMarketConfig 集成"
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple
import pytz
import threading
from deva.naja.register import SR


class MarketType(Enum):
    """市场类型"""
    FUTURES_24H = "futures_24h"      # 24小时期货（黄金、原油等）
    FUTURES_EXTENDED = "futures_extended"  # 延长时间期货（股指期货）
    US_STOCK = "us_stock"            # 美股
    HK_STOCK = "hk_stock"            # 港股
    CN_STOCK = "cn_stock"            # A股
    FOREX = "forex"                 # 外汇
    CRYPTO = "crypto"                # 加密货币


class MarketStatus(Enum):
    """市场状态"""
    OPEN = "open"                    # 交易中
    PRE_MARKET = "pre_market"        # 盘前
    POST_MARKET = "post_market"      # 盘后
    CLOSED = "closed"                # 收盘
    BREAK = "break"                  # 休市（午休等）
    NA = "na"                        # 不可用


@dataclass
class MarketSession:
    """交易时段"""
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int
    status: MarketStatus


@dataclass
class MarketInfo:
    """市场信息"""
    market_id: str
    name: str
    market_type: MarketType
    timezone: str
    sessions: List[MarketSession]
    pre_market_enabled: bool = False
    post_market_enabled: bool = False

    def get_current_status(self, now: datetime = None) -> MarketStatus:
        """获取当前状态"""
        if now is None:
            now = datetime.now(pytz.timezone(self.timezone))

        current_time = now.time()

        for session in self.sessions:
            start = time(session.start_hour, session.start_minute)
            end = time(session.end_hour, session.end_minute)

            if start <= current_time < end:
                return session.status

        return MarketStatus.CLOSED


GLOBAL_MARKET_CONFIGS: Dict[str, MarketInfo] = {
    # === 24小时期货市场 ===
    "nasdaq100": MarketInfo(
        market_id="nasdaq100",
        name="纳斯达克100指数期货",
        market_type=MarketType.FUTURES_EXTENDED,
        timezone="America/New_York",
        sessions=[
            MarketSession(0, 0, 23, 59, MarketStatus.OPEN),  # 几乎24小时
        ],
    ),
    "sp500": MarketInfo(
        market_id="sp500",
        name="标普500指数期货",
        market_type=MarketType.FUTURES_EXTENDED,
        timezone="America/New_York",
        sessions=[
            MarketSession(0, 0, 23, 59, MarketStatus.OPEN),
        ],
    ),
    "dowjones": MarketInfo(
        market_id="dowjones",
        name="道琼斯指数期货",
        market_type=MarketType.FUTURES_EXTENDED,
        timezone="America/New_York",
        sessions=[
            MarketSession(0, 0, 23, 59, MarketStatus.OPEN),
        ],
    ),
    "gold": MarketInfo(
        market_id="gold",
        name="纽约黄金",
        market_type=MarketType.FUTURES_24H,
        timezone="America/New_York",
        sessions=[
            MarketSession(0, 0, 23, 59, MarketStatus.OPEN),
        ],
    ),
    "silver": MarketInfo(
        market_id="silver",
        name="纽约白银",
        market_type=MarketType.FUTURES_24H,
        timezone="America/New_York",
        sessions=[
            MarketSession(0, 0, 23, 59, MarketStatus.OPEN),
        ],
    ),
    "crude_oil": MarketInfo(
        market_id="crude_oil",
        name="WTI原油",
        market_type=MarketType.FUTURES_24H,
        timezone="America/New_York",
        sessions=[
            MarketSession(0, 0, 23, 59, MarketStatus.OPEN),
        ],
    ),
    "natural_gas": MarketInfo(
        market_id="natural_gas",
        name="天然气",
        market_type=MarketType.FUTURES_24H,
        timezone="America/New_York",
        sessions=[
            MarketSession(0, 0, 23, 59, MarketStatus.OPEN),
        ],
    ),

    # === 美股个股 ===
    "nvda": MarketInfo(
        market_id="nvda",
        name="英伟达",
        market_type=MarketType.US_STOCK,
        timezone="America/New_York",
        sessions=[
            MarketSession(4, 0, 9, 30, MarketStatus.PRE_MARKET),   # 盘前 20:00-01:30
            MarketSession(9, 30, 16, 0, MarketStatus.OPEN),         # 交易 01:30-08:00
            MarketSession(16, 0, 20, 0, MarketStatus.POST_MARKET),  # 盘后 08:00-12:00
        ],
        pre_market_enabled=True,
        post_market_enabled=True,
    ),
    "aapl": MarketInfo(
        market_id="aapl",
        name="苹果",
        market_type=MarketType.US_STOCK,
        timezone="America/New_York",
        sessions=[
            MarketSession(4, 0, 9, 30, MarketStatus.PRE_MARKET),
            MarketSession(9, 30, 16, 0, MarketStatus.OPEN),
            MarketSession(16, 0, 20, 0, MarketStatus.POST_MARKET),
        ],
        pre_market_enabled=True,
        post_market_enabled=True,
    ),
    "tsla": MarketInfo(
        market_id="tsla",
        name="特斯拉",
        market_type=MarketType.US_STOCK,
        timezone="America/New_York",
        sessions=[
            MarketSession(4, 0, 9, 30, MarketStatus.PRE_MARKET),
            MarketSession(9, 30, 16, 0, MarketStatus.OPEN),
            MarketSession(16, 0, 20, 0, MarketStatus.POST_MARKET),
        ],
        pre_market_enabled=True,
        post_market_enabled=True,
    ),
    "msft": MarketInfo(
        market_id="msft",
        name="微软",
        market_type=MarketType.US_STOCK,
        timezone="America/New_York",
        sessions=[
            MarketSession(4, 0, 9, 30, MarketStatus.PRE_MARKET),
            MarketSession(9, 30, 16, 0, MarketStatus.OPEN),
            MarketSession(16, 0, 20, 0, MarketStatus.POST_MARKET),
        ],
        pre_market_enabled=True,
        post_market_enabled=True,
    ),
    "googl": MarketInfo(
        market_id="googl",
        name="谷歌",
        market_type=MarketType.US_STOCK,
        timezone="America/New_York",
        sessions=[
            MarketSession(4, 0, 9, 30, MarketStatus.PRE_MARKET),
            MarketSession(9, 30, 16, 0, MarketStatus.OPEN),
            MarketSession(16, 0, 20, 0, MarketStatus.POST_MARKET),
        ],
        pre_market_enabled=True,
        post_market_enabled=True,
    ),
    "amzn": MarketInfo(
        market_id="amzn",
        name="亚马逊",
        market_type=MarketType.US_STOCK,
        timezone="America/New_York",
        sessions=[
            MarketSession(4, 0, 9, 30, MarketStatus.PRE_MARKET),
            MarketSession(9, 30, 16, 0, MarketStatus.OPEN),
            MarketSession(16, 0, 20, 0, MarketStatus.POST_MARKET),
        ],
        pre_market_enabled=True,
        post_market_enabled=True,
    ),
    "meta": MarketInfo(
        market_id="meta",
        name="Meta",
        market_type=MarketType.US_STOCK,
        timezone="America/New_York",
        sessions=[
            MarketSession(4, 0, 9, 30, MarketStatus.PRE_MARKET),
            MarketSession(9, 30, 16, 0, MarketStatus.OPEN),
            MarketSession(16, 0, 20, 0, MarketStatus.POST_MARKET),
        ],
        pre_market_enabled=True,
        post_market_enabled=True,
    ),
    "amd": MarketInfo(
        market_id="amd",
        name="AMD",
        market_type=MarketType.US_STOCK,
        timezone="America/New_York",
        sessions=[
            MarketSession(4, 0, 9, 30, MarketStatus.PRE_MARKET),
            MarketSession(9, 30, 16, 0, MarketStatus.OPEN),
            MarketSession(16, 0, 20, 0, MarketStatus.POST_MARKET),
        ],
        pre_market_enabled=True,
        post_market_enabled=True,
    ),
    "intc": MarketInfo(
        market_id="intc",
        name="英特尔",
        market_type=MarketType.US_STOCK,
        timezone="America/New_York",
        sessions=[
            MarketSession(4, 0, 9, 30, MarketStatus.PRE_MARKET),
            MarketSession(9, 30, 16, 0, MarketStatus.OPEN),
            MarketSession(16, 0, 20, 0, MarketStatus.POST_MARKET),
        ],
        pre_market_enabled=True,
        post_market_enabled=True,
    ),
    "nke": MarketInfo(
        market_id="nke",
        name="耐克",
        market_type=MarketType.US_STOCK,
        timezone="America/New_York",
        sessions=[
            MarketSession(4, 0, 9, 30, MarketStatus.PRE_MARKET),
            MarketSession(9, 30, 16, 0, MarketStatus.OPEN),
            MarketSession(16, 0, 20, 0, MarketStatus.POST_MARKET),
        ],
        pre_market_enabled=True,
        post_market_enabled=True,
    ),
    "dis": MarketInfo(
        market_id="dis",
        name="迪士尼",
        market_type=MarketType.US_STOCK,
        timezone="America/New_York",
        sessions=[
            MarketSession(4, 0, 9, 30, MarketStatus.PRE_MARKET),
            MarketSession(9, 30, 16, 0, MarketStatus.OPEN),
            MarketSession(16, 0, 20, 0, MarketStatus.POST_MARKET),
        ],
        pre_market_enabled=True,
        post_market_enabled=True,
    ),
    "pypl": MarketInfo(
        market_id="pypl",
        name="PayPal",
        market_type=MarketType.US_STOCK,
        timezone="America/New_York",
        sessions=[
            MarketSession(4, 0, 9, 30, MarketStatus.PRE_MARKET),
            MarketSession(9, 30, 16, 0, MarketStatus.OPEN),
            MarketSession(16, 0, 20, 0, MarketStatus.POST_MARKET),
        ],
        pre_market_enabled=True,
        post_market_enabled=True,
    ),
}


class MarketSessionManager:
    """市场会话管理器"""

    def __init__(self):
        self._configs = GLOBAL_MARKET_CONFIGS
        self._us_eastern = pytz.timezone("America/New_York")
        self._cn = pytz.timezone("Asia/Shanghai")

    def get_market_status(self, market_id: str, when: datetime = None) -> MarketStatus:
        """获取市场状态"""
        config = self._configs.get(market_id)
        if not config:
            return MarketStatus.NA
        return config.get_current_status(when)

    def get_all_status(self, when: datetime = None) -> Dict[str, MarketStatus]:
        """获取所有市场状态"""
        return {
            market_id: config.get_current_status(when)
            for market_id, config in self._configs.items()
        }

    def get_markets_by_status(self, status: MarketStatus, when: datetime = None) -> List[str]:
        """获取特定状态的市场"""
        return [
            market_id for market_id, s in self.get_all_status(when).items()
            if s == status
        ]

    def get_open_markets(self, when: datetime = None) -> List[str]:
        """获取正在交易的市场"""
        return self.get_markets_by_status(MarketStatus.OPEN, when)

    def get_market_type(self, market_id: str) -> MarketType:
        """获取市场类型"""
        config = self._configs.get(market_id)
        return config.market_type if config else MarketType.US_STOCK

    def get_market_info(self, market_id: str) -> Optional[MarketInfo]:
        """获取市场信息"""
        return self._configs.get(market_id)

    def get_markets_by_type(self, market_type: MarketType) -> List[str]:
        """获取特定类型的所有市场"""
        return [
            market_id for market_id, config in self._configs.items()
            if config.market_type == market_type
        ]

    def get_market_timezone(self, market_id: str) -> Optional[pytz.BaseTzInfo]:
        """获取市场的时区"""
        config = self._configs.get(market_id)
        if not config:
            return None
        return pytz.timezone(config.timezone)

    def get_session_remaining_seconds(self, market_id: str, when: datetime = None) -> Optional[float]:
        """
        获取当前交易时段剩余秒数
        - 如果市场未开盘，返回距离开盘的秒数（等待中）
        - 如果市场已收盘，返回 None
        - 如果市场正在交易，返回距当前时段结束的秒数
        """
        config = self._configs.get(market_id)
        if not config:
            return None

        if when is None:
            when = datetime.now(pytz.timezone(config.timezone))

        current_time = when.time()
        now_dt = when

        for session in config.sessions:
            start = time(session.start_hour, session.start_minute)
            end = time(session.end_hour, session.end_minute)

            if session.status == MarketStatus.OPEN:
                if start <= current_time < end:
                    end_dt = when.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
                    if end_dt <= now_dt:
                        end_dt += timedelta(days=1)
                    remaining = (end_dt - now_dt).total_seconds()
                    return max(0, remaining)
            elif session.status in (MarketStatus.PRE_MARKET, MarketStatus.POST_MARKET, MarketStatus.BREAK):
                if start <= current_time < end:
                    end_dt = when.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
                    if end_dt <= now_dt:
                        end_dt += timedelta(days=1)
                    remaining = (end_dt - now_dt).total_seconds()
                    return max(0, remaining)

        return None

    def get_market_trading_duration_seconds(self, market_id: str) -> Optional[float]:
        """获取市场完整交易时段总秒数（如 A 股 4 小时 = 14400）"""
        config = self._configs.get(market_id)
        if not config:
            return None
        total = 0
        for session in config.sessions:
            if session.status == MarketStatus.OPEN:
                total += (session.end_hour * 3600 + session.end_minute * 60) - (session.start_hour * 3600 + session.start_minute * 60)
        return total if total > 0 else None

    def get_us_trading_phase(self, when: datetime = None) -> str:
        """获取美股当前交易阶段"""
        if when is None:
            when = datetime.now(self._us_eastern)

        current_time = when.time()

        if time(4, 0) <= current_time < time(9, 30):
            return "pre_market"
        elif time(9, 30) <= current_time < time(16, 0):
            return "trading"
        elif time(16, 0) <= current_time < time(20, 0):
            return "post_market"
        else:
            return "closed"


def get_market_config(market_id: str) -> Optional[MarketInfo]:
    """获取市场配置"""
    return GLOBAL_MARKET_CONFIGS.get(market_id)


def get_all_market_ids() -> List[str]:
    """获取所有市场ID"""
    return list(GLOBAL_MARKET_CONFIGS.keys())
