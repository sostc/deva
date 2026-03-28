"""Global Market Configuration - 全球市场配置

定义了全球主要市场的开盘时间、时区、类型等信息。
用于全球流动性传播系统的市场节点初始化。

市场类型:
- equity: 股票市场
- forex: 外汇市场
- commodity: 商品市场
- crypto: 虚拟货币
- volatility: 波动率指数
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import time


@dataclass
class MarketConfig:
    """单个市场配置"""
    market_id: str
    name: str
    market_type: str
    timezone: str
    trading_start: str
    trading_end: str
    is_24h: bool = False
    related_narratives: List[str] = None
    description: str = ""

    def __post_init__(self):
        if self.related_narratives is None:
            self.related_narratives = []


MARKET_CONFIGS: Dict[str, MarketConfig] = {
    # === 股票市场 ===
    "us_equity": MarketConfig(
        market_id="us_equity",
        name="美股",
        market_type="equity",
        timezone="America/New_York",
        trading_start="22:30",
        trading_end="05:00",
        related_narratives=["全球宏观", "流动性紧张", "地缘政治"],
        description="美国股票市场 (NYSE, NASDAQ)",
    ),
    "sp500": MarketConfig(
        market_id="sp500",
        name="标普500",
        market_type="equity",
        timezone="America/New_York",
        trading_start="22:30",
        trading_end="05:00",
        related_narratives=["全球宏观", "流动性紧张", "股票市场"],
        description="标普500指数",
    ),
    "nasdaq": MarketConfig(
        market_id="nasdaq",
        name="纳斯达克",
        market_type="equity",
        timezone="America/New_York",
        trading_start="22:30",
        trading_end="05:00",
        related_narratives=["全球宏观", "流动性紧张", "股票市场"],
        description="纳斯达克综合指数",
    ),
    "dow_jones": MarketConfig(
        market_id="dow_jones",
        name="道琼斯",
        market_type="equity",
        timezone="America/New_York",
        trading_start="22:30",
        trading_end="05:00",
        related_narratives=["全球宏观", "流动性紧张", "股票市场"],
        description="道琼斯工业平均指数",
    ),

    # === 亚洲股票市场 ===
    "a_share": MarketConfig(
        market_id="a_share",
        name="A股",
        market_type="equity",
        timezone="Asia/Shanghai",
        trading_start="09:30",
        trading_end="15:00",
        related_narratives=["全球宏观", "流动性紧张", "股票市场"],
        description="中国A股 (上证、深证)",
    ),
    "hs300": MarketConfig(
        market_id="hs300",
        name="沪深300",
        market_type="equity",
        timezone="Asia/Shanghai",
        trading_start="09:30",
        trading_end="15:00",
        related_narratives=["全球宏观", "流动性紧张", "股票市场"],
        description="沪深300指数",
    ),
    "hk_stock": MarketConfig(
        market_id="hk_stock",
        name="港股",
        market_type="equity",
        timezone="Asia/Hong_Kong",
        trading_start="03:00",
        trading_end="09:00",
        related_narratives=["全球宏观", "流动性紧张", "股票市场"],
        description="香港股票市场",
    ),
    "nikkei": MarketConfig(
        market_id="nikkei",
        name="日经225",
        market_type="equity",
        timezone="Asia/Tokyo",
        trading_start="00:00",
        trading_end="06:00",
        related_narratives=["全球宏观", "流动性紧张", "股票市场"],
        description="日本日经225指数",
    ),

    # === 欧洲股票市场 ===
    "eu_stock": MarketConfig(
        market_id="eu_stock",
        name="欧股",
        market_type="equity",
        timezone="Europe/London",
        trading_start="08:00",
        trading_end="16:30",
        related_narratives=["全球宏观", "流动性紧张", "股票市场"],
        description="欧洲股票市场 (DAX, CAC, FTSE)",
    ),

    # === 商品市场 ===
    "gold": MarketConfig(
        market_id="gold",
        name="黄金",
        market_type="commodity",
        timezone="UTC",
        trading_start="23:00",
        trading_end="22:00",
        is_24h=True,
        related_narratives=["贵金属", "流动性紧张", "全球宏观"],
        description="国际黄金现货/期货",
    ),
    "silver": MarketConfig(
        market_id="silver",
        name="白银",
        market_type="commodity",
        timezone="UTC",
        trading_start="23:00",
        trading_end="22:00",
        is_24h=True,
        related_narratives=["贵金属", "流动性紧张"],
        description="国际白银现货/期货",
    ),
    "crude_oil": MarketConfig(
        market_id="crude_oil",
        name="原油",
        market_type="commodity",
        timezone="UTC",
        trading_start="00:00",
        trading_end="22:30",
        related_narratives=["大宗商品", "全球宏观", "地缘政治"],
        description="WTI/布伦特原油",
    ),
    "natural_gas": MarketConfig(
        market_id="natural_gas",
        name="天然气",
        market_type="commodity",
        timezone="UTC",
        trading_start="00:00",
        trading_end="22:30",
        related_narratives=["大宗商品", "全球宏观", "地缘政治"],
        description="天然气期货",
    ),
    "copper": MarketConfig(
        market_id="copper",
        name="铜",
        market_type="commodity",
        timezone="UTC",
        trading_start="00:00",
        trading_end="22:30",
        related_narratives=["大宗商品", "全球宏观"],
        description="铜期货 (经济晴雨表)",
    ),

    # === 外汇市场 ===
    "usd_index": MarketConfig(
        market_id="usd_index",
        name="美元指数",
        market_type="forex",
        timezone="UTC",
        trading_start="00:00",
        trading_end="00:00",
        is_24h=True,
        related_narratives=["外汇与美元", "流动性紧张", "全球宏观"],
        description="DXY美元指数",
    ),
    "eur_usd": MarketConfig(
        market_id="eur_usd",
        name="欧元/美元",
        market_type="forex",
        timezone="UTC",
        trading_start="00:00",
        trading_end="00:00",
        is_24h=True,
        related_narratives=["外汇与美元", "全球宏观"],
        description="欧元兑美元",
    ),
    "usd_cny": MarketConfig(
        market_id="usd_cny",
        name="美元/人民币",
        market_type="forex",
        timezone="UTC",
        trading_start="00:00",
        trading_end="00:00",
        is_24h=True,
        related_narratives=["外汇与美元", "中美关系", "全球宏观"],
        description="美元兑人民币",
    ),

    # === 虚拟货币 ===
    "btc": MarketConfig(
        market_id="btc",
        name="比特币",
        market_type="crypto",
        timezone="UTC",
        trading_start="00:00",
        trading_end="00:00",
        is_24h=True,
        related_narratives=["流动性紧张", "全球宏观"],
        description="比特币 (BTC)",
    ),
    "eth": MarketConfig(
        market_id="eth",
        name="以太坊",
        market_type="crypto",
        timezone="UTC",
        trading_start="00:00",
        trading_end="00:00",
        is_24h=True,
        related_narratives=["流动性紧张", "全球宏观"],
        description="以太坊 (ETH)",
    ),

    # === 波动率指数 ===
    "vix": MarketConfig(
        market_id="vix",
        name="VIX恐慌指数",
        market_type="volatility",
        timezone="America/New_York",
        trading_start="22:30",
        trading_end="05:00",
        related_narratives=["流动性紧张", "地缘政治", "全球宏观"],
        description="CBOE波动率指数 (恐慌指数)",
    ),

    # === 债券市场 ===
    "us10y_bond": MarketConfig(
        market_id="us10y_bond",
        name="美债10年",
        market_type="bond",
        timezone="America/New_York",
        trading_start="22:30",
        trading_end="05:00",
        related_narratives=["债券市场", "流动性紧张", "全球宏观"],
        description="美国10年期国债收益率",
    ),
    "cn_bond": MarketConfig(
        market_id="cn_bond",
        name="中债",
        market_type="bond",
        timezone="Asia/Shanghai",
        trading_start="09:30",
        trading_end="15:00",
        related_narratives=["债券市场", "流动性紧张", "全球宏观"],
        description="中国债券市场",
    ),
}


INFLUENCE_PATHS: List[Dict] = [
    {"from": "us_equity", "to": "hk_stock", "delay_hours": 6, "strength": 0.9, "reason": "美股收市影响港股开盘"},
    {"from": "us_equity", "to": "a_share", "delay_hours": 16, "strength": 0.7, "reason": "美股影响A股期货"},
    {"from": "us_equity", "to": "nikkei", "delay_hours": 2, "strength": 0.8, "reason": "美股收盘影响日经"},
    {"from": "us_equity", "to": "eu_stock", "delay_hours": 1, "strength": 0.7, "reason": "美股期货影响欧股"},

    {"from": "nikkei", "to": "hk_stock", "delay_hours": 3, "strength": 0.8, "reason": "日经影响港股"},
    {"from": "nikkei", "to": "a_share", "delay_hours": 4, "strength": 0.6, "reason": "日经影响A股"},

    {"from": "eu_stock", "to": "us_equity", "delay_hours": 14, "strength": 0.6, "reason": "欧股收盘后美股开盘"},

    {"from": "gold", "to": "aud_usd", "delay_hours": 1, "strength": 0.7, "reason": "黄金影响澳元"},
    {"from": "gold", "to": "usd_index", "delay_hours": 0, "strength": 0.8, "reason": "黄金与美元负相关"},

    {"from": "crude_oil", "to": "cad_usd", "delay_hours": 2, "strength": 0.7, "reason": "原油影响加元"},
    {"from": "crude_oil", "to": "rub_usd", "delay_hours": 2, "strength": 0.6, "reason": "原油影响卢布"},

    {"from": "vix", "to": "us_equity", "delay_hours": 0, "strength": -0.9, "reason": "VIX飙升预示股市下跌"},
    {"from": "vix", "to": "gold", "delay_hours": 0, "strength": 0.6, "reason": "VIX飙升黄金受益"},
    {"from": "vix", "to": "btc", "delay_hours": 0, "strength": -0.7, "reason": "VIX飙升比特币下跌"},

    {"from": "usd_index", "to": "a_share", "delay_hours": 4, "strength": -0.6, "reason": "美元强势影响A股"},
    {"from": "usd_index", "to": "hk_stock", "delay_hours": 4, "strength": -0.7, "reason": "美元强势影响港股"},

    {"from": "btc", "to": "us_equity", "delay_hours": 0, "strength": 0.5, "reason": "比特币与美股正相关"},
    {"from": "btc", "to": "gold", "delay_hours": 0, "strength": 0.6, "reason": "比特币与黄金正相关"},
]


MARKET_TRADING_ORDER: List[str] = [
    "btc", "eth", "usd_index", "gold", "crude_oil",
    "nikkei",
    "hk_stock",
    "a_share", "hs300",
    "eu_stock",
    "us10y_bond", "us_equity", "sp500", "nasdaq", "dow_jones", "vix",
]


def get_market_config(market_id: str) -> Optional[MarketConfig]:
    """获取市场配置"""
    return MARKET_CONFIGS.get(market_id)


def get_markets_by_type(market_type: str) -> List[MarketConfig]:
    """按类型获取市场列表"""
    return [cfg for cfg in MARKET_CONFIGS.values() if cfg.market_type == market_type]


def get_influence_paths(from_market: str = None, to_market: str = None) -> List[Dict]:
    """获取影响路径"""
    paths = INFLUENCE_PATHS
    if from_market:
        paths = [p for p in paths if p["from"] == from_market]
    if to_market:
        paths = [p for p in paths if p["to"] == to_market]
    return paths


def get_next_markets(market_id: str) -> List[str]:
    """获取某个市场之后应该关注的市场列表（按时间顺序）"""
    paths = get_influence_paths(from_market=market_id)
    return sorted(paths, key=lambda x: x["delay_hours"])
