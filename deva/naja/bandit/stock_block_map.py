"""
StockBlockMap - 股票-行业映射数据

提供：
1. 股票 → 传统行业分类(industry_code) 的静态映射
2. 行业分类 → 股票 的反向映射
3. 股票元数据（名称、行业、市值）

注意：
- industry_code: 传统行业分类码 "ai_chip", "cloud_ai" (对应原 block)
- industry_name: 传统行业中文名 "AI芯片/GPU"
- blocks: 注意力系统的板块标签 ["AI", "芯片", "半导体"] (来自注意力层)
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
    industry_code: str
    industry_name: str
    market_cap: str
    exchange: str
    blocks: List[str] = None
    narrative: str = ""

    def __post_init__(self):
        if self.blocks is None:
            self.blocks = []


US_STOCK_BLOCKS: Dict[str, Dict[str, str]] = {
    "nvda": {
        "name": "英伟达",
        "industry_code": "ai_chip",
        "industry_name": "AI芯片/GPU",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "芯片", "半导体", "GPU", "算力"],
    },
    "amd": {
        "name": "超威半导体",
        "industry_code": "ai_chip",
        "industry_name": "CPU/GPU",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "芯片", "半导体", "CPU"],
    },
    "intc": {
        "name": "英特尔",
        "industry_code": "ai_chip",
        "industry_name": "CPU/AI芯片",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "芯片", "半导体", "CPU"],
    },
    "tsm": {
        "name": "台积电",
        "industry_code": "ai_chip",
        "industry_name": "晶圆代工",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "芯片", "半导体", "晶圆代工"],
    },
    "asml": {
        "name": "ASML",
        "industry_code": "ai_chip",
        "industry_name": "光刻机",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "芯片", "半导体", "光刻机"],
    },
    "smci": {
        "name": "超微电脑",
        "industry_code": "ai_infra",
        "industry_name": "AI服务器",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "服务器", "算力", "AI基础设施"],
    },
    "msft": {
        "name": "微软",
        "industry_code": "cloud_ai",
        "industry_name": "云服务/AI",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云计算", "云服务", "Copilot"],
    },
    "googl": {
        "name": "谷歌",
        "industry_code": "cloud_ai",
        "industry_name": "云服务/AI",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云计算", "云服务", "Gemini", "搜索"],
    },
    "googl_class_a": {
        "name": "谷歌A类股",
        "industry_code": "cloud_ai",
        "industry_name": "云服务/AI",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云计算", "云服务", "Gemini"],
    },
    "amzn": {
        "name": "亚马逊",
        "industry_code": "cloud_ai",
        "industry_name": "电商/云服务",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云计算", "云服务", "AWS", "电商"],
    },
    "crwd": {
        "name": "CrowdStrike",
        "industry_code": "cloud_ai",
        "industry_name": "网络安全",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云计算", "网络安全"],
    },
    "pltr": {
        "name": "Palantir",
        "industry_code": "ai_software",
        "industry_name": "大数据/AI",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "大数据", "AI软件"],
    },
    "meta": {
        "name": "Meta Platforms",
        "industry_code": "social_media",
        "industry_name": "社交媒体/AI",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "社交媒体", "元宇宙", "广告", "Llama"],
    },
    "p": {
        "name": "Pinterest",
        "industry_code": "social_media",
        "industry_name": "社交媒体",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "社交媒体", "广告"],
    },
    "snap": {
        "name": "Snap",
        "industry_code": "social_media",
        "industry_name": "社交媒体",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "社交媒体", "AR", "广告"],
    },
    "baba": {
        "name": "阿里巴巴",
        "industry_code": "e_commerce",
        "industry_name": "电商/云计算",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "电商",
        "blocks": ["电商", "云计算", "阿里云", "AI"],
    },
    "pdd": {
        "name": "拼多多",
        "industry_code": "e_commerce",
        "industry_name": "电商",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "电商",
        "blocks": ["电商", "下沉市场", "Temu"],
    },
    "jd": {
        "name": "京东",
        "industry_code": "e_commerce",
        "industry_name": "电商/物流",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "电商",
        "blocks": ["电商", "物流", "自营"],
    },
    "tsla": {
        "name": "特斯拉",
        "industry_code": "ev",
        "industry_name": "电动汽车/AI",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "新能源",
        "blocks": ["新能源", "电动汽车", "AI", "自动驾驶", "Robotaxi"],
    },
    "nio": {
        "name": "蔚来",
        "industry_code": "ev",
        "industry_name": "电动汽车",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "新能源",
        "blocks": ["新能源", "电动汽车", "换电"],
    },
    "li": {
        "name": "理想汽车",
        "industry_code": "ev",
        "industry_name": "电动汽车",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "新能源",
        "blocks": ["新能源", "电动汽车", "增程式"],
    },
    "xpev": {
        "name": "小鹏汽车",
        "industry_code": "ev",
        "industry_name": "电动汽车",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "新能源",
        "blocks": ["新能源", "电动汽车", "自动驾驶"],
    },
    "coin": {
        "name": "Coinbase",
        "industry_code": "crypto",
        "industry_name": "加密货币交易所",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "加密货币",
        "blocks": ["加密货币", "交易所", "区块链", "比特币"],
    },
    "mstr": {
        "name": "MicroStrategy",
        "industry_code": "crypto",
        "industry_name": "比特币投资",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "加密货币",
        "blocks": ["加密货币", "比特币", "Saylor"],
    },
    "spot": {
        "name": "Spotify",
        "industry_code": "streaming",
        "industry_name": "音乐流媒体",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "消费",
        "blocks": ["流媒体", "音乐", "AI推荐"],
    },
    "netf": {
        "name": "Netflix",
        "industry_code": "streaming",
        "industry_name": "视频流媒体",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "消费",
        "blocks": ["流媒体", "视频", "AI推荐"],
    },
    "dis": {
        "name": "迪士尼",
        "industry_code": "streaming",
        "industry_name": "娱乐/流媒体",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "消费",
        "blocks": ["流媒体", "娱乐", "电影", "Disney+"],
    },
    "ubnt": {
        "name": "UiPath",
        "industry_code": "robotics",
        "industry_name": "机器人自动化",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "机器人", "自动化", "RPA"],
    },

    # Mega Cap Tech (补充)
    "aapl": {
        "name": "苹果",
        "industry_code": "cloud_ai",
        "industry_name": "消费电子/云服务",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "消费电子", "iPhone", "Mac", "云服务"],
    },
    "goog": {
        "name": "谷歌C类股",
        "industry_code": "cloud_ai",
        "industry_name": "云服务/AI",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云计算", "云服务", "Gemini", "搜索"],
    },

    # Semiconductor (补充)
    "nxpi": {
        "name": "NXP半导体",
        "industry_code": "ai_chip",
        "industry_name": "汽车半导体",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "芯片", "半导体", "汽车电子"],
    },
    "qcom": {
        "name": "高通",
        "industry_code": "ai_chip",
        "industry_name": "移动通信芯片",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "芯片", "半导体", "5G", "手机芯片"],
    },
    "mu": {
        "name": "美光科技",
        "industry_code": "ai_chip",
        "industry_name": "存储芯片",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "芯片", "半导体", "存储", "HBM"],
    },
    "lam": {
        "name": "Lam Research",
        "industry_code": "ai_chip",
        "industry_name": "半导体设备",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "芯片", "半导体", "晶圆设备"],
    },
    "amat": {
        "name": "应用材料",
        "industry_code": "ai_chip",
        "industry_name": "半导体设备",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "芯片", "半导体", "晶圆设备"],
    },

    # Internet & E-commerce (补充)
    "pypl": {
        "name": "PayPal",
        "industry_code": "fintech",
        "industry_name": "金融科技",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "支付",
        "blocks": ["支付", "金融科技", "电商", "加密货币"],
    },
    "shop": {
        "name": "Shopify",
        "industry_code": "e_commerce",
        "industry_name": "电商SaaS",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "电商",
        "blocks": ["电商", "SaaS", "云服务", "零售"],
    },
    "pins": {
        "name": "Pinterest",
        "industry_code": "social_media",
        "industry_name": "社交媒体",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "社交媒体", "广告", "图片分享"],
    },
    "twlo": {
        "name": "Twilio",
        "industry_code": "cloud_ai",
        "industry_name": "云通信",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云服务", "通信", "SaaS"],
    },
    "roku": {
        "name": "Roku",
        "industry_code": "streaming",
        "industry_name": "流媒体平台",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "流媒体",
        "blocks": ["流媒体", "电视", "广告", "AI推荐"],
    },
    "dbx": {
        "name": "Dropbox",
        "industry_code": "cloud_ai",
        "industry_name": "云存储",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "云服务",
        "blocks": ["云服务", "云存储", "SaaS", "AI"],
    },

    # Finance (补充)
    "jpm": {
        "name": "摩根大通",
        "industry_code": "finance",
        "industry_name": "商业银行",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "金融",
        "blocks": ["金融", "银行", "投行", "金融科技"],
    },
    "bac": {
        "name": "美国银行",
        "industry_code": "finance",
        "industry_name": "商业银行",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "金融",
        "blocks": ["金融", "银行", "消费金融"],
    },
    "wfc": {
        "name": "富国银行",
        "industry_code": "finance",
        "industry_name": "商业银行",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "金融",
        "blocks": ["金融", "银行", "社区银行"],
    },
    "ms": {
        "name": "摩根士丹利",
        "industry_code": "finance",
        "industry_name": "投资银行",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "金融",
        "blocks": ["金融", "投行", "财富管理"],
    },
    "c": {
        "name": "花旗集团",
        "industry_code": "finance",
        "industry_name": "商业银行",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "金融",
        "blocks": ["金融", "银行", "全球银行"],
    },
    "v": {
        "name": "Visa",
        "industry_code": "finance",
        "industry_name": "支付网络",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "支付",
        "blocks": ["支付", "金融", "信用卡", "跨境支付"],
    },
    "ma": {
        "name": "Mastercard",
        "industry_code": "finance",
        "industry_name": "支付网络",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "支付",
        "blocks": ["支付", "金融", "信用卡", "跨境支付"],
    },

    # China Stocks (补充)
    "bidu": {
        "name": "百度",
        "industry_code": "cloud_ai",
        "industry_name": "AI/云服务",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "自动驾驶", "云服务", "搜索"],
    },

    # Others (补充)
    "nke": {
        "name": "耐克",
        "industry_code": "consumer",
        "industry_name": "消费品/运动",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "消费",
        "blocks": ["消费", "运动品牌", "鞋服"],
    },
    "mcd": {
        "name": "麦当劳",
        "industry_code": "consumer",
        "industry_name": "快餐连锁",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "消费",
        "blocks": ["消费", "餐饮", "快餐", "连锁"],
    },
    "hum": {
        "name": "联合健康",
        "industry_code": "healthcare",
        "industry_name": "健康保险",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "医疗",
        "blocks": ["医疗", "健康保险", "医疗服务"],
    },
    "unh": {
        "name": "联合健康集团",
        "industry_code": "healthcare",
        "industry_name": "健康保险",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "医疗",
        "blocks": ["医疗", "健康保险", "Optum"],
    },
    "pfe": {
        "name": "辉瑞",
        "industry_code": "healthcare",
        "industry_name": "制药",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "医疗",
        "blocks": ["医疗", "制药", "疫苗", "生物制药"],
    },

    # Crypto (补充)
    "lucid": {
        "name": "Lucid Group",
        "industry_code": "ev",
        "industry_name": "电动汽车",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "新能源",
        "blocks": ["新能源", "电动汽车", "豪华电动车"],
    },
    "wrld": {
        "name": "Worldcoin",
        "industry_code": "crypto",
        "industry_name": "加密货币/AI",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "加密货币",
        "blocks": ["加密货币", "区块链", "AI", "身份认证"],
    },
    "crwv": {
        "name": "Crown Castle",
        "industry_code": "cloud_ai",
        "industry_name": "数据中心/塔站",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "云服务",
        "blocks": ["云服务", "数据中心", "塔站", "5G"],
    },

    # Cloud & Security (补充)
    "okta": {
        "name": "Okta",
        "industry_code": "cloud_ai",
        "industry_name": "身份管理",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云服务", "网络安全", "身份管理"],
    },
    "zs": {
        "name": "Zscaler",
        "industry_code": "cloud_ai",
        "industry_name": "云安全",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云服务", "网络安全", "零信任"],
    },
    "net": {
        "name": "Cloudflare",
        "industry_code": "cloud_ai",
        "industry_name": "云/CDN",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云服务", "CDN", "网络安全"],
    },
    "ddog": {
        "name": "Datadog",
        "industry_code": "cloud_ai",
        "industry_name": "云监控",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云服务", "监控", "DevOps"],
    },
    "snow": {
        "name": "Snowflake",
        "industry_code": "cloud_ai",
        "industry_name": "数据分析云",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "AI",
        "blocks": ["AI", "云服务", "数据分析", "大数据"],
    },

    # Streaming & Gaming (补充)
    "nflx": {
        "name": "Netflix",
        "industry_code": "streaming",
        "industry_name": "流媒体",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "流媒体",
        "blocks": ["流媒体", "视频", "AI推荐", "原创内容"],
    },
    "ea": {
        "name": "Electronic Arts",
        "industry_code": "gaming",
        "industry_name": "游戏",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "游戏",
        "blocks": ["游戏", "电子游戏", "体育游戏"],
    },
    "atvi": {
        "name": "动视暴雪",
        "industry_code": "gaming",
        "industry_name": "游戏",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "游戏",
        "blocks": ["游戏", "电子游戏", "魔兽世界", "使命召唤"],
    },

    # EV & Energy (补充)
    "f": {
        "name": "福特汽车",
        "industry_code": "ev",
        "industry_name": "传统/电动汽车",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "新能源",
        "blocks": ["新能源", "电动汽车", "自动驾驶", "皮卡"],
    },
    "gm": {
        "name": "通用汽车",
        "industry_code": "ev",
        "industry_name": "传统/电动汽车",
        "market_cap": "large_cap",
        "exchange": "US",
        "narrative": "新能源",
        "blocks": ["新能源", "电动汽车", "自动驾驶", "Cruise"],
    },
    "rivn": {
        "name": "Rivian",
        "industry_code": "ev",
        "industry_name": "电动皮卡/SUV",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "新能源",
        "blocks": ["新能源", "电动汽车", "皮卡", "R1T", "R1S"],
    },

    # Crypto Mining (补充)
    "mara": {
        "name": "Marathon Digital",
        "industry_code": "crypto",
        "industry_name": "比特币挖矿",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "加密货币",
        "blocks": ["加密货币", "比特币", "挖矿", "区块链"],
    },
    "riot": {
        "name": "Riot Platforms",
        "industry_code": "crypto",
        "industry_name": "比特币挖矿",
        "market_cap": "mid_cap",
        "exchange": "US",
        "narrative": "加密货币",
        "blocks": ["加密货币", "比特币", "挖矿", "区块链"],
    },
}


INDUSTRY_CODE_TO_NAME: Dict[str, str] = {
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
    "finance": "金融/银行",
    "fintech": "金融科技",
    "consumer": "消费品",
    "healthcare": "医疗健康",
    "gaming": "游戏",
}


NARRATIVE_INDUSTRY_MAP: Dict[str, List[str]] = {
    "AI": ["ai_chip", "ai_infra", "cloud_ai", "ai_software", "social_media"],
    "新能源": ["ev"],
    "电商": ["e_commerce"],
    "加密货币": ["crypto"],
    "消费": ["streaming", "consumer"],
    "金融": ["finance", "fintech"],
    "医疗": ["healthcare"],
    "游戏": ["gaming"],
}


INDUSTRY_ETF_MAP: Dict[str, str] = {
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


class StockBlockMap:
    """
    股票-行业映射管理器

    功能：
    1. 查询股票的 industry 信息
    2. 查询某 industry 下的所有股票
    3. 持久化持仓的 industry 配置
    """

    PERSIST_PREFIX = "stock_block_"
    USER_ALLOC_PREFIX = "user_industry_alloc_"

    def __init__(self):
        self._cache: Dict[str, StockMetadata] = {}
        self._industry_to_stocks: Dict[str, Set[str]] = {}
        self._initialized = False

    def _ensure_init(self):
        if self._initialized:
            return

        for code, data in US_STOCK_BLOCKS.items():
            metadata = StockMetadata(
                code=code,
                name=data["name"],
                industry_code=data["industry_code"],
                industry_name=data["industry_name"],
                market_cap=data["market_cap"],
                exchange=data["exchange"],
                blocks=data.get("blocks", []),
                narrative=data.get("narrative", ""),
            )
            self._cache[code] = metadata

            ind_code = data["industry_code"]
            if ind_code not in self._industry_to_stocks:
                self._industry_to_stocks[ind_code] = set()
            self._industry_to_stocks[ind_code].add(code)

        self._initialized = True

    def get_metadata(self, code: str) -> Optional[StockMetadata]:
        """获取股票元数据"""
        self._ensure_init()
        return self._cache.get(code.lower())

    def get_industry(self, code: str) -> Optional[str]:
        """获取股票所属的传统行业分类码"""
        metadata = self.get_metadata(code)
        return metadata.industry_code if metadata else None

    def get_stocks_in_industry(self, industry_code: str) -> List[str]:
        """获取某传统行业分类下的所有股票"""
        self._ensure_init()
        return list(self._industry_to_stocks.get(industry_code, set()))

    def get_industry_display_name(self, industry_code: str) -> str:
        """获取传统行业分类的中文显示名称"""
        return INDUSTRY_CODE_TO_NAME.get(industry_code, industry_code)

    def get_industry_etf(self, industry_code: str) -> Optional[str]:
        """获取某传统行业分类对应的美股ETF代码"""
        return INDUSTRY_ETF_MAP.get(industry_code)

    def get_stock_blocks(self, code: str) -> List[str]:
        """获取股票对应的注意力系统 block 标签"""
        metadata = self.get_metadata(code)
        return metadata.blocks if metadata else []

    def get_stock_narrative(self, code: str) -> str:
        """获取股票对应的叙事主题"""
        metadata = self.get_metadata(code)
        return metadata.narrative if metadata else ""

    def register_stock(
        self,
        code: str,
        name: str,
        industry_code: str,
        industry_name: str = "",
        blocks: Optional[List[str]] = None,
        narrative: str = "",
        market_cap: str = "mid_cap",
    ):
        """注册新的股票（运行时添加）"""
        self._ensure_init()
        code = code.lower()

        metadata = StockMetadata(
            code=code,
            name=name,
            industry_code=industry_code,
            industry_name=industry_name,
            market_cap=market_cap,
            exchange="US",
            blocks=blocks or [],
            narrative=narrative,
        )
        self._cache[code] = metadata

        if industry_code not in self._industry_to_stocks:
            self._industry_to_stocks[industry_code] = set()
        self._industry_to_stocks[industry_code].add(code)

    def get_portfolio_industry_alloc(
        self,
        positions: List[Dict[str, float]]
    ) -> Dict[str, float]:
        """
        计算持仓的行业配置

        Args:
            positions: 持仓列表 [{'code': 'nvda', 'qty': 2380, 'current': 165.17, 'entry': 168.0}, ...]

        Returns:
            行业权重分布 {industry_code: weight}
        """
        self._ensure_init()

        industry_values: Dict[str, float] = {}
        total_value = 0.0

        for pos in positions:
            code = pos.get('code', '').lower()
            qty = pos.get('qty', 0)
            current = pos.get('current', 0)
            value = qty * current

            if not code or not value:
                continue

            metadata = self.get_metadata(code)
            industry_code = metadata.industry_code if metadata else "other"

            if industry_code not in industry_values:
                industry_values[industry_code] = 0.0
            industry_values[industry_code] += value
            total_value += value

        if total_value == 0:
            return {}

        return {
            industry_code: value / total_value
            for industry_code, value in industry_values.items()
        }

    def enrich_position(self, pos: Dict) -> Dict:
        """丰富持仓数据，添加行业信息"""
        code = pos.get('code', '').lower()
        metadata = self.get_metadata(code)

        if metadata:
            pos['name'] = metadata.name
            pos['industry_code'] = metadata.industry_code
            pos['industry_name'] = metadata.industry_name
            pos['market_cap'] = metadata.market_cap
            pos['industry_display'] = self.get_industry_display_name(metadata.industry_code)
            pos['blocks'] = metadata.blocks
            pos['narrative'] = metadata.narrative

        return pos

    def persist_user_industry_alloc(self, user_id: str, industry_alloc: Dict[str, float]):
        """持久化用户的行业配置"""
        nb = NB(f"{self.USER_ALLOC_PREFIX}{user_id}")
        nb['industry_alloc'] = industry_alloc
        nb['update_time'] = time.time()

    def load_user_industry_alloc(self, user_id: str) -> Optional[Dict[str, float]]:
        """加载用户的行业配置"""
        nb = NB(f"{self.USER_ALLOC_PREFIX}{user_id}")
        return nb.get('industry_alloc')


_stock_block_map: Optional[StockBlockMap] = None


def get_stock_block_map() -> StockBlockMap:
    """获取股票-行业映射（单例）"""
    global _stock_block_map
    if _stock_block_map is None:
        _stock_block_map = StockBlockMap()
    return _stock_block_map
