"""
StockSectorMap - 股票-板块映射数据

提供：
1. 股票 → 板块 的静态映射
2. 板块 → 股票 的反向映射
3. 股票元数据（名称、行业、市值）
"""

import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from deva import NB


@dataclass
class StockMetadata:
    """股票元数据"""
    code: str
    name: str
    sector: str
    industry: str
    market_cap: str  # large_cap, mid_cap, small_cap
    exchange: str     # US, HK, CN


US_STOCK_SECTORS: Dict[str, Dict[str, str]] = {
    # ========== AI芯片/半导体 ==========
    "nvda": {
        "name": "英伟达",
        "sector": "ai_chip",
        "industry": "AI芯片/GPU",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "芯片", "半导体", "GPU", "算力"],
    },
    "amd": {
        "name": "超威半导体",
        "sector": "ai_chip",
        "industry": "CPU/GPU",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "芯片", "半导体", "CPU"],
    },
    "intc": {
        "name": "英特尔",
        "sector": "ai_chip",
        "industry": "CPU/AI芯片",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "芯片", "半导体", "CPU"],
    },
    "tsm": {
        "name": "台积电",
        "sector": "ai_chip",
        "industry": "晶圆代工",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "芯片", "半导体", "晶圆代工"],
    },
    "asml": {
        "name": "ASML",
        "sector": "ai_chip",
        "industry": "光刻机",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "芯片", "半导体", "光刻机"],
    },
    "smci": {
        "name": "超微电脑",
        "sector": "ai_infra",
        "industry": "AI服务器",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "服务器", "算力", "AI基础设施"],
    },
    # ========== 云计算/AI软件 ==========
    "msft": {
        "name": "微软",
        "sector": "cloud_ai",
        "industry": "云服务/AI",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云计算", "云服务", "Copilot"],
    },
    "googl": {
        "name": "谷歌",
        "sector": "cloud_ai",
        "industry": "云服务/AI",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云计算", "云服务", "Gemini", "搜索"],
    },
    "googl_class_a": {
        "name": "谷歌A类股",
        "sector": "cloud_ai",
        "industry": "云服务/AI",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云计算", "云服务", "Gemini"],
    },
    "amzn": {
        "name": "亚马逊",
        "sector": "cloud_ai",
        "industry": "电商/云服务",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云计算", "云服务", "AWS", "电商"],
    },
    "msft": {
        "name": "微软",
        "sector": "cloud_ai",
        "industry": "云服务/AI",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云计算", "云服务", "Copilot"],
    },
    "crwd": {
        "name": "CrowdStrike",
        "sector": "cloud_ai",
        "industry": "网络安全",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云计算", "网络安全"],
    },
    "pltr": {
        "name": "Palantir",
        "sector": "ai_software",
        "industry": "大数据/AI",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "大数据", "AI软件"],
    },
    # ========== 社交媒体/广告 ==========
    "meta": {
        "name": "Meta Platforms",
        "sector": "social_media",
        "industry": "社交媒体/AI",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "社交媒体", "元宇宙", "广告", "Llama"],
    },
    "p": {
        "name": "Pinterest",
        "sector": "social_media",
        "industry": "社交媒体",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "社交媒体", "广告"],
    },
    "snap": {
        "name": "Snap",
        "sector": "social_media",
        "industry": "社交媒体",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "社交媒体", "AR", "广告"],
    },
    # ========== 电商 ==========
    "baba": {
        "name": "阿里巴巴",
        "sector": "e_commerce",
        "industry": "电商/云计算",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "电商",
        "blocks": ["电商", "云计算", "阿里云", "AI"],
    },
    "pdd": {
        "name": "拼多多",
        "sector": "e_commerce",
        "industry": "电商",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "电商",
        "blocks": ["电商", "下沉市场", "Temu"],
    },
    "jd": {
        "name": "京东",
        "sector": "e_commerce",
        "industry": "电商/物流",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "电商",
        "blocks": ["电商", "物流", "自营"],
    },
    "amzn": {
        "name": "亚马逊",
        "sector": "e_commerce",
        "industry": "电商/云服务",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "电商",
        "blocks": ["电商", "云计算", "AWS", "AI"],
    },
    # ========== 电动汽车/新能源 ==========
    "tsla": {
        "name": "特斯拉",
        "sector": "ev",
        "industry": "电动汽车/AI",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "新能源",
        "blocks": ["新能源", "电动汽车", "AI", "自动驾驶", "Robotaxi"],
    },
    "nio": {
        "name": "蔚来",
        "sector": "ev",
        "industry": "电动汽车",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "新能源",
        "blocks": ["新能源", "电动汽车", "换电"],
    },
    "li": {
        "name": "理想汽车",
        "sector": "ev",
        "industry": "电动汽车",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "新能源",
        "blocks": ["新能源", "电动汽车", "增程式"],
    },
    "xpev": {
        "name": "小鹏汽车",
        "sector": "ev",
        "industry": "电动汽车",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "新能源",
        "blocks": ["新能源", "电动汽车", "自动驾驶"],
    },
    # ========== 加密货币 ==========
    "coin": {
        "name": "Coinbase",
        "sector": "crypto",
        "industry": "加密货币交易所",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "加密货币",
        "blocks": ["加密货币", "交易所", "区块链", "比特币"],
    },
    "mstr": {
        "name": "MicroStrategy",
        "sector": "crypto",
        "industry": "比特币投资",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "加密货币",
        "blocks": ["加密货币", "比特币", "Saylor"],
    },
    # ========== 流媒体 ==========
    "spot": {
        "name": "Spotify",
        "sector": "streaming",
        "industry": "音乐流媒体",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "消费",
        "blocks": ["流媒体", "音乐", "AI推荐"],
    },
    "netf": {
        "name": "Netflix",
        "sector": "streaming",
        "industry": "视频流媒体",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "消费",
        "blocks": ["流媒体", "视频", "AI推荐"],
    },
    "dis": {
        "name": "迪士尼",
        "sector": "streaming",
        "industry": "娱乐/流媒体",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "消费",
        "blocks": ["流媒体", "娱乐", "电影", "Disney+"],
    },
    # ========== 机器人/自动驾驶 ==========
    "ubnt": {
        "name": "UiPath",
        "sector": "robotics",
        "industry": "机器人自动化",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "机器人", "自动化", "RPA"],
    },
    "tsla": {
        "name": "特斯拉",
        "sector": "robotaxi",
        "industry": "自动驾驶/机器人",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "自动驾驶", "机器人", "Robotaxi"],
    },
}


SECTOR_INDUSTRY_MAP: Dict[str, str] = {
    "ai_chip": "AI芯片/半导体",
    "ai_infra": "AI基础设施",
    "cloud_ai": "云计算/AI",
    "ai_software": "AI软件",
    "social_media": "社交媒体",
    "e_commerce": "电商",
    "ev": "电动汽车",
    "robotaxi": "自动驾驶",
    "robotics": "机器人",
    "crypto": "加密货币",
    "streaming": "流媒体",
}


NARRATIVE_SECTOR_MAP: Dict[str, List[str]] = {
    "AI": ["ai_chip", "ai_infra", "cloud_ai", "ai_software", "social_media"],
    "新能源": ["ev"],
    "电商": ["e_commerce"],
    "加密货币": ["crypto"],
    "消费": ["streaming"],
}


SECTOR_US_ETF_MAP: Dict[str, str] = {
    "ai_chip": "SMH",
    "ai_infra": "AIQ",
    "cloud_ai": "CLOU",
    "ai_software": "AI",
    "social_media": "SOCL",
    "e_commerce": "EBIZ",
    "ev": "DRIV",
    "robotaxi": "DRIV",
    "robotics": "ROBO",
    "crypto": "BLOK",
    "streaming": "OGE",
}


class StockSectorMap:
    """
    股票-板块映射管理器

    功能：
    1. 查询股票的板块、行业、市值信息
    2. 查询某板块下的所有股票
    3. 持久化持仓的板块配置
    """

    PERSIST_PREFIX = "stock_sector_"
    USER_ALLOC_PREFIX = "user_sector_alloc_"

    def __init__(self):
        self._cache: Dict[str, StockMetadata] = {}
        self._sector_to_stocks: Dict[str, Set[str]] = {}
        self._initialized = False

    def _ensure_init(self):
        if self._initialized:
            return

        for code, data in US_STOCK_SECTORS.items():
            metadata = StockMetadata(
                code=code,
                name=data["name"],
                sector=data["sector"],
                industry=data["industry"],
                market_cap=data["market_cap"],
                exchange=data["exchange"]
            )
            self._cache[code] = metadata

            if data["sector"] not in self._sector_to_stocks:
                self._sector_to_stocks[data["sector"]] = set()
            self._sector_to_stocks[data["sector"]].add(code)

        self._initialized = True

    def get_metadata(self, code: str) -> Optional[StockMetadata]:
        """获取股票元数据"""
        self._ensure_init()
        return self._cache.get(code.lower())

    def get_sector(self, code: str) -> Optional[str]:
        """获取股票所属板块"""
        metadata = self.get_metadata(code)
        return metadata.sector if metadata else None

    def get_stocks_in_sector(self, sector: str) -> List[str]:
        """获取某板块下的所有股票"""
        self._ensure_init()
        return list(self._sector_to_stocks.get(sector, set()))

    def get_sector_display_name(self, sector: str) -> str:
        """获取板块的中文显示名称"""
        return SECTOR_INDUSTRY_MAP.get(sector, sector)

    def get_sector_etf(self, sector: str) -> Optional[str]:
        """获取某板块对应的美股ETF代码"""
        return SECTOR_US_ETF_MAP.get(sector)

    def register_stock(self, code: str, name: str, sector: str, industry: str = "", market_cap: str = "mid_cap"):
        """注册新的股票（运行时添加）"""
        self._ensure_init()
        code = code.lower()

        metadata = StockMetadata(
            code=code,
            name=name,
            sector=sector,
            industry=industry,
            market_cap=market_cap,
            exchange="US"
        )
        self._cache[code] = metadata

        if sector not in self._sector_to_stocks:
            self._sector_to_stocks[sector] = set()
        self._sector_to_stocks[sector].add(code)

    def get_portfolio_sector_alloc(
        self,
        positions: List[Dict[str, float]]
    ) -> Dict[str, float]:
        """
        计算持仓的板块配置

        Args:
            positions: 持仓列表 [{'code': 'nvda', 'qty': 2380, 'current': 165.17, 'entry': 168.0}, ...]

        Returns:
            板块权重分布 {sector: weight}
        """
        self._ensure_init()

        sector_values: Dict[str, float] = {}
        total_value = 0.0

        for pos in positions:
            code = pos.get('code', '').lower()
            qty = pos.get('qty', 0)
            current = pos.get('current', 0)
            value = qty * current

            if not code or not value:
                continue

            metadata = self.get_metadata(code)
            sector = metadata.sector if metadata else "other"

            if sector not in sector_values:
                sector_values[sector] = 0.0
            sector_values[sector] += value
            total_value += value

        if total_value == 0:
            return {}

        return {
            sector: value / total_value
            for sector, value in sector_values.items()
        }

    def enrich_position(self, pos: Dict) -> Dict:
        """丰富持仓数据，添加板块信息"""
        code = pos.get('code', '').lower()
        metadata = self.get_metadata(code)

        if metadata:
            pos['name'] = metadata.name
            pos['sector'] = metadata.sector
            pos['industry'] = metadata.industry
            pos['market_cap'] = metadata.market_cap
            pos['sector_name'] = self.get_sector_display_name(metadata.sector)

        return pos

    def persist_user_sector_alloc(self, user_id: str, sector_alloc: Dict[str, float]):
        """持久化用户的板块配置"""
        nb = NB(f"{self.USER_ALLOC_PREFIX}{user_id}")
        nb['sector_alloc'] = sector_alloc
        nb['update_time'] = time.time()

    def load_user_sector_alloc(self, user_id: str) -> Optional[Dict[str, float]]:
        """加载用户的板块配置"""
        nb = NB(f"{self.USER_ALLOC_PREFIX}{user_id}")
        return nb.get('sector_alloc')


_stock_sector_map: Optional[StockSectorMap] = None


def get_stock_sector_map() -> StockSectorMap:
    """获取股票-板块映射（单例）"""
    global _stock_sector_map
    if _stock_sector_map is None:
        _stock_sector_map = StockSectorMap()
    return _stock_sector_map
