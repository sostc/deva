"""Narrative to Sector Mapping - 叙事主题到板块的映射配置

职责:
- 定义叙事主题到市场板块的映射关系
- 支持多对多映射（一个叙事主题可以关联多个板块）
- 提供配置开关来控制联动功能

使用场景:
- NarrativeTracker 识别叙事主题后，映射到实际的 sector_id
- CrossSignalAnalyzer 实现"舆情 → 板块轮动"的联动
- 行业叙事 → 板块（AI→半导体）
- 宏观叙事 → 大盘指数（流动性紧张→纳斯达克）
"""

from typing import Dict, List

NARRATIVE_TO_SECTOR_LINK: Dict[str, List[str]] = {
    "AI": ["semiconductor", "software", "internet"],
    "芯片": ["semiconductor", "hardware"],
    "新能源": ["new_energy", "auto", "power_equipment"],
    "医药": ["pharma", "medical_device", "healthcare"],
    "华为": ["semiconductor", "consumer_electronics", "software"],
    "中美关系": ["macro", "export", "import"],
    "地缘政治": ["macro", "defense", "energy"],
    "贵金属": ["precious_metal", "commodity", "macro"],
    "外汇与美元": ["forex", "usd", "macro"],
    "全球宏观": ["macro", "bond", "equity"],
    "流动性紧张": ["macro", "liquidity", "credit"],
    "债券市场": ["bond", "fixed_income", "macro"],
    "股票市场": ["equity", "stock", "macro"],
    "大宗商品": ["commodity", "energy", "industrial_metal"],
    "现金与货币": ["money", "liquidity", "central_bank"],
}

NARRATIVE_TO_MARKET_LINK: Dict[str, List[str]] = {
    "贵金属": ["gold", "silver"],
    "外汇与美元": ["usd_index", "dxy"],
    "全球宏观": ["sp500", "nasdaq", "dow_jones", "hang_seng", "nikkei"],
    "流动性紧张": ["sp500", "nasdaq", "bond", "fed_funds"],
    "债券市场": ["bond", "treasury", "us10y", "us02y"],
    "股票市场": ["sp500", "nasdaq", "dow_jones", "a_share", "hs300"],
    "大宗商品": ["crude_oil", "nat_gas", "copper", "commodity_index"],
    "现金与货币": ["fed_funds", "libor", "money_market"],
    "地缘政治": ["sp500", "nasdaq", "oil", "gold", "vix"],
}

MARKET_TO_NARRATIVE_LINK: Dict[str, List[str]] = {
    "sp500": ["全球宏观", "流动性紧张", "股票市场", "地缘政治"],
    "nasdaq": ["全球宏观", "流动性紧张", "股票市场", "地缘政治"],
    "dow_jones": ["全球宏观", "股票市场"],
    "gold": ["贵金属", "地缘政治"],
    "silver": ["贵金属"],
    "crude_oil": ["大宗商品", "地缘政治"],
    "vix": ["流动性紧张", "地缘政治"],
    "usd_index": ["外汇与美元"],
    "bond": ["流动性紧张", "债券市场"],
}

MARKET_INDEX_CONFIG: Dict[str, Dict[str, str]] = {
    "sp500": {"name": "标普500", "region": "US", "type": "equity"},
    "nasdaq": {"name": "纳斯达克", "region": "US", "type": "equity"},
    "dow_jones": {"name": "道琼斯", "region": "US", "type": "equity"},
    "a_share": {"name": "上证指数", "region": "CN", "type": "equity"},
    "hs300": {"name": "沪深300", "region": "CN", "type": "equity"},
    "hang_seng": {"name": "恒生指数", "region": "HK", "type": "equity"},
    "nikkei": {"name": "日经225", "region": "JP", "type": "equity"},
    "gold": {"name": "黄金", "region": "GLOBAL", "type": "precious_metal"},
    "silver": {"name": "白银", "region": "GLOBAL", "type": "precious_metal"},
    "crude_oil": {"name": "原油", "region": "GLOBAL", "type": "energy"},
    "nat_gas": {"name": "天然气", "region": "GLOBAL", "type": "energy"},
    "copper": {"name": "铜", "region": "GLOBAL", "type": "industrial_metal"},
    "bond": {"name": "债券指数", "region": "GLOBAL", "type": "bond"},
    "treasury": {"name": "国债", "region": "US", "type": "bond"},
    "us10y": {"name": "美债10年", "region": "US", "type": "bond"},
    "us02y": {"name": "美债2年", "region": "US", "type": "bond"},
    "usd_index": {"name": "美元指数", "region": "US", "type": "forex"},
    "dxy": {"name": "DXY", "region": "US", "type": "forex"},
    "fed_funds": {"name": "联邦基金利率", "region": "US", "type": "interest_rate"},
    "libor": {"name": "Libor", "region": "GLOBAL", "type": "interest_rate"},
    "money_market": {"name": "货币市场", "region": "GLOBAL", "type": "money"},
    "commodity_index": {"name": "商品指数", "region": "GLOBAL", "type": "commodity"},
    "vix": {"name": "VIX恐慌指数", "region": "US", "type": "volatility"},
}

NARRATIVE_CATEGORY: Dict[str, str] = {
    "AI": "industry",
    "芯片": "industry",
    "新能源": "industry",
    "医药": "industry",
    "华为": "industry",
    "中美关系": "macro",
    "地缘政治": "macro",
    "贵金属": "macro",
    "外汇与美元": "macro",
    "全球宏观": "macro",
    "流动性紧张": "macro",
    "债券市场": "macro",
    "股票市场": "macro",
    "大宗商品": "macro",
    "现金与货币": "macro",
}

SECTOR_TO_NARRATIVE_REVERSE: Dict[str, List[str]] = {
    "semiconductor": ["AI", "芯片", "华为"],
    "software": ["AI", "华为"],
    "internet": ["AI"],
    "hardware": ["芯片"],
    "new_energy": ["新能源"],
    "auto": ["新能源"],
    "power_equipment": ["新能源"],
    "pharma": ["医药"],
    "medical_device": ["医药"],
    "healthcare": ["医药"],
    "consumer_electronics": ["华为"],
    "macro": ["中美关系", "地缘政治", "贵金属", "外汇与美元", "全球宏观", "流动性紧张", "债券市场", "股票市场", "大宗商品", "现金与货币"],
    "defense": ["地缘政治"],
    "energy": ["地缘政治", "大宗商品"],
    "export": ["中美关系"],
    "import": ["中美关系"],
    "precious_metal": ["贵金属"],
    "commodity": ["贵金属", "大宗商品"],
    "forex": ["外汇与美元"],
    "usd": ["外汇与美元"],
    "bond": ["全球宏观", "债券市场"],
    "equity": ["全球宏观", "股票市场"],
    "liquidity": ["流动性紧张", "现金与货币"],
    "credit": ["流动性紧张"],
    "fixed_income": ["债券市场"],
    "stock": ["股票市场"],
    "money": ["现金与货币"],
    "central_bank": ["现金与货币"],
    "industrial_metal": ["大宗商品"],
}

NARRATIVE_SECTOR_LINKING_ENABLED: bool = True


def get_linked_sectors(narrative: str) -> List[str]:
    """获取叙事主题关联的板块列表"""
    if not NARRATIVE_SECTOR_LINKING_ENABLED:
        return []
    return NARRATIVE_TO_SECTOR_LINK.get(narrative, [])


def get_linked_narratives(sector: str) -> List[str]:
    """获取板块关联的叙事主题列表"""
    if not NARRATIVE_SECTOR_LINKING_ENABLED:
        return []
    return SECTOR_TO_NARRATIVE_REVERSE.get(sector, [])


def get_linked_markets(narrative: str) -> List[str]:
    """获取宏观叙事关联的大盘指数列表"""
    return NARRATIVE_TO_MARKET_LINK.get(narrative, [])


def get_linked_narratives_for_market(market: str) -> List[str]:
    """获取大盘指数关联的宏观叙事列表"""
    return MARKET_TO_NARRATIVE_LINK.get(market, [])


def get_market_config(market: str) -> Dict[str, str]:
    """获取大盘指数的配置信息"""
    return MARKET_INDEX_CONFIG.get(market, {"name": market, "region": "UNKNOWN", "type": "unknown"})


def get_narrative_category(narrative: str) -> str:
    """获取叙事的类别：industry 或 macro"""
    return NARRATIVE_CATEGORY.get(narrative, "unknown")


def is_macro_narrative(narrative: str) -> bool:
    """判断是否为宏观叙事"""
    return get_narrative_category(narrative) == "macro"


def is_industry_narrative(narrative: str) -> bool:
    """判断是否为行业叙事"""
    return get_narrative_category(narrative) == "industry"


def is_linking_enabled() -> bool:
    """检查联动功能是否启用"""
    return NARRATIVE_SECTOR_LINKING_ENABLED


def set_linking_enabled(enabled: bool):
    """设置联动功能开关"""
    global NARRATIVE_SECTOR_LINKING_ENABLED
    NARRATIVE_SECTOR_LINKING_ENABLED = enabled
