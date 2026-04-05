"""
单日Tick数据横截面分析策略

用于分析单日全市场数据，识别：
1. 市场广度（上涨/下跌比例）
2. 板块(block)表现
3. 异常波动股票
4. 资金流向
5. 市场情绪

作者: AI
日期: 2026-03-31
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

from deva.naja.bandit.stock_sector_map import INDUSTRY_CODE_TO_NAME


@dataclass
class BlockAnalysis:
    """板块分析结果"""
    block_id: str
    stock_count: int
    avg_change: float
    total_volume: int
    gainer_count: int
    loser_count: int
    top_gainer: Optional[Dict] = None
    top_loser: Optional[Dict] = None


@dataclass
class SingleDayAnalysis:
    """单日分析结果"""
    stock_count: int
    market_breadth: float
    advancing_count: int
    declining_count: int
    unchanged_count: int
    avg_change: float
    median_change: float
    total_volume: int
    blocks: Dict[str, BlockAnalysis]
    anomalies: List[Dict]
    market_sentiment: str
    fund_flow: str
    market_feature: str


class RiverTickSingleDayAnalyzer:
    """单日Tick数据横截面分析器

    使用River风格的在线学习思想，但针对单日横截面数据进行批量分析
    """

    def __init__(
        self,
        volume_threshold: float = 3.0,
        change_threshold: float = 9.0,
        block_names: Optional[Dict[str, str]] = None
    ):
        """
        Args:
            volume_threshold: 量比阈值（超过均值多少倍为异常）
            change_threshold: 涨跌幅阈值（超过9%为剧烈波动）
            block_names: 板块名称映射
        """
        self.volume_threshold = volume_threshold
        self.change_threshold = change_threshold
        self.block_names = block_names or self._default_block_map()

        self.reset()

    def _default_block_map(self) -> Dict[str, str]:
        """默认板块映射 - 合并A股和美股板块"""
        block_map: Dict[str, str] = {}
        block_map.update(INDUSTRY_CODE_TO_NAME)

        block_map.update({
            "AI": "人工智能",
            "储能": "新能源",
            "电池": "新能源",
            "锂电池": "新能源",
            "固态电池": "新能源",
            "光伏": "新能源",
            "风电": "新能源",
            "银行": "金融",
            "保险": "金融",
            "证券": "金融",
            "房地产": "地产",
            "食品": "消费",
            "饮料": "消费",
            "白酒": "消费",
            "家电": "消费",
            "军工": "军工",
            "航空": "军工",
            "通信": "科技",
            "软件": "科技",
            "互联网": "科技",
        })

        return block_map

    def reset(self):
        """重置分析器"""
        self.data: List[Dict] = []
        self.blocks: Dict[str, List[Dict]] = {}
        self.volume_mean = 0
        self.volume_std = 0

    def on_data(self, data: Dict[str, Any]) -> None:
        """接收一条股票数据"""
        data = dict(data)

        if "p_change" in data:
            p_change = float(data["p_change"])
            data["p_change"] = p_change
        elif "change_pct" in data:
            change_pct = float(data["change_pct"])
            if abs(change_pct) > 1:
                data["p_change"] = change_pct / 100
            else:
                data["p_change"] = change_pct

        self.data.append(data)

        block_id = self._classify_block(data)
        if block_id not in self.blocks:
            self.blocks[block_id] = []
        self.blocks[block_id].append(data)

    def _classify_block(self, data: Dict) -> str:
        """根据股票数据分类板块

        优先级：
        1. 如果有narrative字段（从US_STOCK_SECTORS或通达信来的），使用industry_code
        2. 如果是美股板块（下划线格式如ai_chip），直接使用
        3. 如果A股已有block字段且不是'other'，使用它
        4. 否则根据名称关键词匹配
        5. 最后根据代码判断（主板/创业板等）
        """
        if "narrative" in data and data["narrative"]:
            return data.get("industry_code", "other")

        if "block_id" in data and data["block_id"]:
            block_id = data["block_id"]
            if block_id != "other" and "_" not in block_id:
                return block_id
            if "_" in block_id:
                return block_id

        if "block" in data and data["block"]:
            block_id = data["block"]
            if block_id != "other" and "_" not in block_id:
                return block_id
            if "_" in block_id:
                return block_id

        name = data.get("name", "").lower()

        for keyword, block_name in self.block_names.items():
            if keyword.lower() in name:
                return block_name

        code = str(data.get("code", ""))
        if code.startswith("sh60") or code.startswith("sh68"):
            return "主板"
        elif code.startswith("sz00"):
            return "主板"
        elif code.startswith("sz30"):
            return "创业板"
        elif code.startswith("bj"):
            return "北交所"

        return "其他"

    def get_signal(self) -> SingleDayAnalysis:
        """获取分析信号"""
        if not self.data:
            return None

        df = pd.DataFrame(self.data)

        if "volume" in df.columns and "p_change" in df.columns:
            pass
        elif "change_pct" in df.columns:
            df["p_change"] = df["change_pct"] / 100

        return self._analyze(df)

    def _analyze(self, df: pd.DataFrame) -> SingleDayAnalysis:
        """执行横截面分析"""

        advancing = len(df[df["p_change"] > 0])
        declining = len(df[df["p_change"] < 0])
        unchanged = len(df[df["p_change"] == 0])
        total = len(df)

        market_breadth = (advancing - declining) / max(total, 1) if total > 0 else 0

        avg_change = df["p_change"].mean() * 100
        median_change = df["p_change"].median() * 100

        block_analysis: Dict[str, BlockAnalysis] = {}
        for block_id, stocks in self.blocks.items():
            if not stocks:
                continue
            block_df = pd.DataFrame(stocks)
            gainers = len(block_df[block_df["p_change"] > 0])
            losers = len(block_df[block_df["p_change"] < 0])

            block_analysis[block_id] = BlockAnalysis(
                block_id=block_id,
                stock_count=len(stocks),
                avg_change=block_df["p_change"].mean() * 100,
                total_volume=int(block_df["volume"].sum()) if "volume" in block_df.columns else 0,
                gainer_count=gainers,
                loser_count=losers,
                top_gainer=self._get_top(block_df, "p_change", True),
                top_loser=self._get_top(block_df, "p_change", False),
            )

        anomalies = self._detect_anomalies(df)

        sentiment = self._classify_sentiment(avg_change, market_breadth)
        fund_flow = self._classify_flow(avg_change, df["p_change"].std() * 100)
        market_feature = self._classify_market_feature(df)

        return SingleDayAnalysis(
            stock_count=total,
            market_breadth=market_breadth,
            advancing_count=advancing,
            declining_count=declining,
            unchanged_count=unchanged,
            avg_change=avg_change,
            median_change=median_change,
            total_volume=int(df["volume"].sum()) if "volume" in df.columns else 0,
            blocks=block_analysis,
            anomalies=anomalies,
            market_sentiment=sentiment,
            fund_flow=fund_flow,
            market_feature=market_feature,
        )

    def _get_top(self, df: pd.DataFrame, col: str, ascending: bool) -> Optional[Dict]:
        """获取排名最高/低的股票"""
        if df.empty:
            return None
        sorted_df = df.sort_values(col, ascending=ascending)
        row = sorted_df.iloc[0]
        return {
            "code": row.get("code", ""),
            "name": row.get("name", ""),
            "change": row.get("p_change", 0) * 100,
        }

    def _detect_anomalies(self, df: pd.DataFrame) -> List[Dict]:
        """检测异常波动股票"""
        anomalies = []

        change_col = "p_change"
        if "change_pct" in df.columns:
            df = df.copy()
            df["p_change"] = df["change_pct"] / 100

        for _, row in df.iterrows():
            is_anomaly = False
            reasons = []

            change = abs(row.get("p_change", 0) * 100)
            if change > self.change_threshold:
                is_anomaly = True
                reasons.append(f"剧烈波动{change:+.2f}%")

            if "volume" in row and self.volume_mean > 0:
                volume_ratio = row["volume"] / self.volume_mean
                if volume_ratio > self.volume_threshold:
                    is_anomaly = True
                    reasons.append(f"量比异常{volume_ratio:.1f}x")

            if is_anomaly:
                anomalies.append({
                    "code": row.get("code", ""),
                    "name": row.get("name", ""),
                    "change": change,
                    "reasons": "; ".join(reasons),
                })

        return anomalies[:20]

    def _classify_sentiment(self, avg_change: float, market_breadth: float) -> str:
        """分类市场情绪"""
        if avg_change > 2 and market_breadth > 0.3:
            return "极度乐观"
        elif avg_change > 1 and market_breadth > 0.2:
            return "乐观"
        elif avg_change > 0.3:
            return "偏暖"
        elif avg_change > -0.3:
            return "中性"
        elif avg_change > -1:
            return "偏冷"
        elif avg_change > -2 or market_breadth < -0.2:
            return "悲观"
        else:
            return "极度悲观"

    def _classify_flow(self, avg_change: float, change_std: float) -> str:
        """分类资金流向"""
        if avg_change > 1.5:
            return "大幅流入"
        elif avg_change > 0.5:
            return "流入"
        elif avg_change > -0.5:
            return "均衡"
        elif avg_change > -1.5:
            return "流出"
        else:
            return "大幅流出"

    def _classify_market_feature(self, df: pd.DataFrame) -> str:
        """分类市场特征"""
        if "volume" in df.columns:
            vol_cv = df["volume"].std() / max(df["volume"].mean(), 1)
        else:
            vol_cv = 0

        change_std = df["p_change"].std() * 100

        if vol_cv > 2:
            return "分化严重"
        elif change_std > 5:
            return "波动剧烈"
        elif change_std > 3:
            return "波动较大"
        elif abs(df["p_change"].mean() * 100) < 0.5:
            return "横盘整理"
        else:
            return "正常"


def analyze_single_day_data(stocks: List[Dict]) -> SingleDayAnalysis:
    """便捷函数：分析单日股票数据"""
    analyzer = RiverTickSingleDayAnalyzer()
    for stock in stocks:
        analyzer.on_data(stock)
    return analyzer.get_signal()
