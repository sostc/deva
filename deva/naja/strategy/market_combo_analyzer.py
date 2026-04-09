"""
MarketComboAnalyzer - 组合市场分析器

整合三种分析策略：
1. 横截面分析 (Cross-sectional) - RiverTickSingleDayAnalyzer
2. 时序分析 (Temporal) - River异常检测、漂移检测
3. 题材聚类分析 (Block Clustering) - 题材内股票聚类

作者: AI
日期: 2026-04-01
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import pandas as pd
except Exception:
    pd = None

from river import anomaly, cluster, drift, stats, stream


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


@dataclass
class BlockClusterResult:
    """题材聚类结果"""
    block: str
    stock_count: int
    avg_change: float
    change_std: float
    correlation: float
    top_gainer: Optional[Dict] = None
    top_loser: Optional[Dict] = None
    anomaly_stocks: List[Dict] = field(default_factory=list)


@dataclass
class TemporalAnalysisResult:
    """时序分析结果"""
    anomaly_score: float
    drift_detected: bool
    drift_direction: str
    trend_strength: float
    volatility: float
    recent_anomalies: List[Dict] = field(default_factory=list)


@dataclass
class MarketComboReport:
    """组合市场分析报告"""
    timestamp: float
    stock_count: int

    cross_sectional: Dict[str, Any]
    temporal: TemporalAnalysisResult
    block_clusters: Dict[str, BlockClusterResult]

    market_sentiment: str
    market_breadth: float
    fund_flow: str

    summary: str
    key_insights: List[str] = field(default_factory=list)
    risk_warnings: List[str] = field(default_factory=list)


class MarketComboAnalyzer:
    """
    组合市场分析器

    整合横截面、时序、题材聚类三种分析
    """

    def __init__(
        self,
        anomaly_window: int = 200,
        drift_sensitivity: float = 0.002,
        cluster_n: int = 3,
    ):
        self._anomaly_model = anomaly.HalfSpaceTrees(
            n_trees=20,
            height=10,
            window_size=anomaly_window,
        )
        self._drift_model = drift.ADWIN()
        self._cluster_models: Dict[str, cluster.KMeans] = {}
        self._cluster_n = cluster_n

        self._temporal_history: List[Dict] = []
        self._block_history: Dict[str, List[Dict]] = defaultdict(list)
        self._last_drift_ts = 0
        self._drift_direction = "none"

    def analyze(
        self,
        stocks: List[Dict],
        blocks_param: Optional[Dict[str, List[Dict]]] = None,
    ) -> MarketComboReport:
        """
        执行组合分析

        Args:
            stocks: 股票数据列表
            blocks: 题材分组 {block_name: [stock, ...]}
        """
        if not stocks:
            return self._empty_report()

        df = self._prepare_dataframe(stocks)

        cross_sectional = self._cross_sectional_analysis(df, stocks)
        temporal = self._temporal_analysis(df)
        block_clusters = self._block_clustering(stocks, blocks_param)

        sentiment = self._classify_sentiment(cross_sectional)
        breadth = cross_sectional.get("market_breadth", 0)
        fund_flow = self._classify_fund_flow(cross_sectional)

        summary = self._generate_summary(
            cross_sectional, temporal, block_clusters, sentiment, breadth
        )

        return MarketComboReport(
            timestamp=time.time(),
            stock_count=len(stocks),
            cross_sectional=cross_sectional,
            temporal=temporal,
            block_clusters=block_clusters,
            market_sentiment=sentiment,
            market_breadth=breadth,
            fund_flow=fund_flow,
            summary=summary,
            key_insights=self._extract_insights(cross_sectional, block_clusters, temporal),
            risk_warnings=self._extract_warnings(cross_sectional, block_clusters, temporal),
        )

    def _prepare_dataframe(self, stocks: List[Dict]) -> pd.DataFrame:
        """准备DataFrame"""
        if pd is None:
            return pd.DataFrame()

        df = pd.DataFrame(stocks)

        if "p_change" in df.columns and "change_pct" not in df.columns:
            df["change_pct"] = df["p_change"] * 100

        if "change_pct" in df.columns and "p_change" not in df.columns:
            df["p_change"] = df["change_pct"] / 100

        return df

    def _cross_sectional_analysis(
        self, df: pd.DataFrame, stocks: List[Dict]
    ) -> Dict[str, Any]:
        """横截面分析"""
        if df.empty:
            return {}

        p_change_col = "p_change" if "p_change" in df.columns else "change_pct"
        if p_change_col not in df.columns:
            return {}

        advancing = int((df[p_change_col] > 0).sum())
        declining = int((df[p_change_col] < 0).sum())
        unchanged = int((df[p_change_col] == 0).sum())
        total = len(df)

        market_breadth = (advancing - declining) / max(total, 1)

        avg_change = _safe_float(df[p_change_col].mean())
        median_change = _safe_float(df[p_change_col].median())
        std_change = _safe_float(df[p_change_col].std())

        return {
            "advancing_count": advancing,
            "declining_count": declining,
            "unchanged_count": unchanged,
            "market_breadth": market_breadth,
            "avg_change": avg_change * 100,
            "median_change": median_change * 100,
            "std_change": std_change * 100,
            "total": total,
        }

    def _temporal_analysis(self, df: pd.DataFrame) -> TemporalAnalysisResult:
        """时序分析 - River异常检测和漂移检测"""
        if df.empty or "p_change" not in df.columns:
            return TemporalAnalysisResult(
                anomaly_score=0.0,
                drift_detected=False,
                drift_direction="none",
                trend_strength=0.0,
                volatility=0.0,
            )

        p_changes = df["p_change"].tolist()
        self._temporal_history.extend(p_changes)

        if len(self._temporal_history) > 500:
            self._temporal_history = self._temporal_history[-500:]

        if len(p_changes) < 2:
            return TemporalAnalysisResult(
                anomaly_score=0.0,
                drift_detected=False,
                drift_direction="none",
                trend_strength=0.0,
                volatility=0.0,
            )

        avg = np.mean(p_changes)
        std = np.std(p_changes)

        features = {
            "mean": avg,
            "std": std,
            "positive_ratio": sum(1 for p in p_changes if p > 0) / len(p_changes),
            "max": max(p_changes),
            "min": min(p_changes),
        }

        anomaly_score = self._anomaly_model.score_one(features)
        self._anomaly_model.learn_one(features)

        drift_detected = self._drift_model.update(avg)
        if drift_detected:
            self._drift_direction = "up" if avg > 0 else "down"
            self._last_drift_ts = time.time()

        trend_strength = self._compute_trend_strength(p_changes)
        volatility = std

        recent_anomalies = self._detect_recent_anomalies(df)

        return TemporalAnalysisResult(
            anomaly_score=float(anomaly_score),
            drift_detected=bool(drift_detected),
            drift_direction=self._drift_direction,
            trend_strength=float(trend_strength),
            volatility=float(volatility),
            recent_anomalies=recent_anomalies,
        )

    def _compute_trend_strength(self, values: List[float]) -> float:
        """计算趋势强度"""
        if len(values) < 2:
            return 0.0

        pos = sum(1 for v in values if v > 0)
        neg = sum(1 for v in values if v < 0)

        if pos > neg:
            return (pos - neg) / len(values)
        elif neg > pos:
            return -(neg - pos) / len(values)
        return 0.0

    def _detect_recent_anomalies(self, df: pd.DataFrame, threshold: float = 0.09) -> List[Dict]:
        """检测异常波动股票"""
        anomalies = []

        if "p_change" not in df.columns:
            return anomalies

        for _, row in df.iterrows():
            change = abs(row.get("p_change", 0))
            if change > threshold:
                anomalies.append({
                    "code": row.get("code", ""),
                    "name": row.get("name", ""),
                    "change": change * 100,
                    "block": row.get("block", row.get("block", "other")),
                })

        anomalies.sort(key=lambda x: x["change"], reverse=True)
        return anomalies[:10]

    def _block_clustering(
        self, stocks: List[Dict], blocks_param: Optional[Dict[str, List[Dict]]]
    ) -> Dict[str, BlockClusterResult]:
        """题材聚类分析"""
        effective_blocks = blocks_param if blocks_param is not None else self._auto_group_blocks(stocks)

        results = {}

        for block_name, block_stocks in effective_blocks.items():
            if len(block_stocks) < 2:
                continue

            changes = [s.get("p_change", 0) or s.get("change_pct", 0) / 100 for s in block_stocks]
            changes = [c if abs(c) < 1 else c / 100 for c in changes]

            avg_change = np.mean(changes) if changes else 0
            std_change = np.std(changes) if len(changes) > 1 else 0

            correlation = self._compute_block_correlation(block_stocks)

            sorted_stocks = sorted(block_stocks, key=lambda x: x.get("p_change", 0) or x.get("change_pct", 0), reverse=True)

            top_gainer = None
            top_loser = None
            if sorted_stocks:
                best = sorted_stocks[0]
                top_gainer = {
                    "code": best.get("code", ""),
                    "name": best.get("name", ""),
                    "change": (best.get("p_change", 0) or best.get("change_pct", 0) / 100) * 100,
                }
                if len(sorted_stocks) > 1:
                    worst = sorted_stocks[-1]
                    top_loser = {
                        "code": worst.get("code", ""),
                        "name": worst.get("name", ""),
                        "change": (worst.get("p_change", 0) or worst.get("change_pct", 0) / 100) * 100,
                    }

            anomaly_stocks = [
                {
                    "code": s.get("code", ""),
                    "name": s.get("name", ""),
                    "change": (s.get("p_change", 0) or s.get("change_pct", 0) / 100) * 100,
                }
                for s in block_stocks
                if abs((s.get("p_change", 0) or s.get("change_pct", 0) / 100)) > 0.05
            ]

            results[block_name] = BlockClusterResult(
                block=block_name,
                stock_count=len(block_stocks),
                avg_change=float(avg_change * 100),
                change_std=float(std_change * 100),
                correlation=float(correlation),
                top_gainer=top_gainer,
                top_loser=top_loser,
                anomaly_stocks=anomaly_stocks[:5],
            )

        return results

    def _auto_group_blocks(self, stocks: List[Dict]) -> Dict[str, List[Dict]]:
        """自动按block字段分组"""
        blocks = defaultdict(list)
        for stock in stocks:
            block = stock.get("block", "other")
            blocks[block].append(stock)
        return dict(blocks)

    def _compute_block_correlation(self, block_stocks: List[Dict]) -> float:
        """计算题材内股票相关性（简化版：涨跌一致性）"""
        if len(block_stocks) < 2:
            return 0.0

        changes = [s.get("p_change", 0) or s.get("change_pct", 0) / 100 for s in block_stocks]
        pos_count = sum(1 for c in changes if c > 0)
        neg_count = sum(1 for c in changes if c < 0)

        agreement = abs(pos_count - neg_count) / len(changes)
        return agreement

    def _classify_sentiment(self, cross_sectional: Dict[str, Any]) -> str:
        """分类市场情绪"""
        avg = cross_sectional.get("avg_change", 0)
        breadth = cross_sectional.get("market_breadth", 0)

        if avg > 2 and breadth > 0.3:
            return "极度乐观"
        elif avg > 1 and breadth > 0.2:
            return "乐观"
        elif avg > 0.3:
            return "偏暖"
        elif avg > -0.3:
            return "中性"
        elif avg > -1:
            return "偏冷"
        elif avg > -2 or breadth < -0.2:
            return "悲观"
        else:
            return "极度悲观"

    def _classify_fund_flow(self, cross_sectional: Dict[str, Any]) -> str:
        """分类资金流向"""
        avg = cross_sectional.get("avg_change", 0)

        if avg > 1.5:
            return "大幅流入"
        elif avg > 0.5:
            return "流入"
        elif avg > -0.5:
            return "均衡"
        elif avg > -1.5:
            return "流出"
        else:
            return "大幅流出"

    def _generate_summary(
        self,
        cross_sectional: Dict[str, Any],
        temporal: TemporalAnalysisResult,
        block_clusters: Dict[str, BlockClusterResult],
        sentiment: str,
        breadth: float,
    ) -> str:
        """生成总结"""
        total = cross_sectional.get("total", 0)
        advancing = cross_sectional.get("advancing_count", 0)
        avg_change = cross_sectional.get("avg_change", 0)

        best_blocks = sorted(
            block_clusters.items(),
            key=lambda x: x[1].avg_change,
            reverse=True,
        )[:3]

        parts = [
            f"市场({total}只): 涨{advancing}/{total-advancing}跌",
            f"均幅{avg_change:+.2f}%",
            f"情绪{sentiment}",
        ]

        if best_blocks:
            block_str = ", ".join([f"{s[0]}{s[1].avg_change:+.1f}%" for s in best_blocks])
            parts.append(f"强势题材: {block_str}")

        if temporal.drift_detected:
            parts.append(f"检测到趋势{temporal.drift_direction}向漂移")

        if temporal.anomaly_score > 0.7:
            parts.append("市场异常波动")

        return " | ".join(parts)

    def _extract_insights(
        self,
        cross_sectional: Dict[str, Any],
        block_clusters: Dict[str, BlockClusterResult],
        temporal: TemporalAnalysisResult,
    ) -> List[str]:
        """提取关键洞察"""
        insights = []

        avg_change = cross_sectional.get("avg_change", 0)
        breadth = cross_sectional.get("market_breadth", 0)

        if avg_change > 1.5:
            insights.append("市场强势上涨，关注趋势持续性")
        elif avg_change < -1.5:
            insights.append("市场大幅下跌，警惕进一步下行风险")

        if breadth > 0.3:
            insights.append("市场广度健康，上涨具有持续性")
        elif breadth < -0.3:
            insights.append("市场广度恶化，下跌股票范围广")

        strong_blocks = [
            s for s in block_clusters.values()
            if s.avg_change > 2 and s.stock_count >= 3
        ]
        if strong_blocks:
            block_names = ", ".join([s.block for s in strong_blocks[:3]])
            insights.append(f"强势题材: {block_names}")

        weak_blocks = [
            s for s in block_clusters.values()
            if s.avg_change < -3 and s.stock_count >= 3
        ]
        if weak_blocks:
            block_names = ", ".join([s.block for s in weak_blocks[:3]])
            insights.append(f"弱势题材: {block_names}")

        if temporal.drift_detected:
            insights.append(f"时序漂移: 趋势向{temporal.drift_direction}变化")

        return insights

    def _extract_warnings(
        self,
        cross_sectional: Dict[str, Any],
        block_clusters: Dict[str, BlockClusterResult],
        temporal: TemporalAnalysisResult,
    ) -> List[str]:
        """提取风险警告"""
        warnings = []

        std_change = cross_sectional.get("std_change", 0)
        if std_change > 10:
            warnings.append(f"市场波动剧烈(标准差{std_change:.1f}%)")

        large_cap_loss = [
            s for s in block_clusters.values()
            if s.avg_change < -5 and s.stock_count >= 5
        ]
        if large_cap_loss:
            block_names = ", ".join([s.block for s in large_cap_loss[:2]])
            warnings.append(f"重点题材大幅下跌: {block_names}")

        if temporal.anomaly_score > 0.8:
            warnings.append("时序异常分数极高，市场可能面临拐点")

        return warnings

    def _empty_report(self) -> MarketComboReport:
        """空报告"""
        return MarketComboReport(
            timestamp=time.time(),
            stock_count=0,
            cross_sectional={},
            temporal=TemporalAnalysisResult(
                anomaly_score=0.0,
                drift_detected=False,
                drift_direction="none",
                trend_strength=0.0,
                volatility=0.0,
            ),
            block_clusters={},
            market_sentiment="未知",
            market_breadth=0.0,
            fund_flow="未知",
            summary="无数据",
            key_insights=[],
            risk_warnings=[],
        )


class USStockBlockMapper:
    """美股题材映射器"""

    SECTORS = {
        "ai_chip": ["nvda", "amd", "intc", "tsm", "asml", "smci"],
        "cloud_ai": ["msft", "googl", "googl_class_a", "amzn", "crwd"],
        "ai_software": ["pltr"],
        "social_media": ["meta", "p", "snap"],
        "e_commerce": ["baba", "pdd", "jd", "amzn"],
        "ev": ["tsla", "nio", "li", "xpev"],
        "robotaxi": ["tsla"],
        "robotics": ["ubnt"],
        "crypto": ["coin", "mstr"],
        "streaming": ["spot", "netf", "dis"],
    }

    @classmethod
    def get_block(cls, code: str) -> Optional[str]:
        """获取股票所属题材"""
        code_lower = code.lower()
        for block, codes in cls.BLOCKS.items():
            if code_lower in codes:
                return block
        return None


def run_combo_analysis(stocks: List[Dict]) -> MarketComboReport:
    """便捷函数：运行组合分析"""
    analyzer = MarketComboAnalyzer()

    blocks = defaultdict(list)
    for stock in stocks:
        block = stock.get("block", "other")
        blocks[block].append(stock)

    return analyzer.analyze(stocks, dict(blocks))


def format_combo_report(report: MarketComboReport) -> str:
    """格式化报告为可读字符串"""
    lines = [
        "=" * 60,
        "组合市场分析报告 (横截面 + 时序 + 聚类)",
        "=" * 60,
        "",
        f"时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(report.timestamp))}",
        f"股票数: {report.stock_count}",
        "",
        "-" * 60,
        "【横截面分析】",
        "-" * 60,
        f"上涨/下跌/平盘: {report.cross_sectional.get('advancing_count', 0)}/{report.cross_sectional.get('declining_count', 0)}/{report.cross_sectional.get('unchanged_count', 0)}",
        f"市场广度: {report.market_breadth:.3f}",
        f"平均涨跌: {report.cross_sectional.get('avg_change', 0):+.2f}%",
        f"中位数涨跌: {report.cross_sectional.get('median_change', 0):+.2f}%",
        "",
        "-" * 60,
        "【时序分析】",
        "-" * 60,
        f"异常分数: {report.temporal.anomaly_score:.3f}",
        f"漂移检测: {'是' if report.temporal.drift_detected else '否'} ({report.temporal.drift_direction})",
        f"趋势强度: {report.temporal.trend_strength:.3f}",
        f"波动率: {report.temporal.volatility:.4f}",
        "",
        "-" * 60,
        "【题材聚类】(按平均涨跌排序)",
        "-" * 60,
    ]

    sorted_blocks = sorted(
        report.block_clusters.items(),
        key=lambda x: x[1].avg_change,
        reverse=True,
    )

    for block_name, cluster in sorted_blocks[:15]:
        gainer_pct = (cluster.top_gainer["change"] if cluster.top_gainer else 0)
        lines.append(
            f"  {block_name}: {cluster.avg_change:+.2f}% ({cluster.stock_count}只, "
            f"涨跌一致率{cluster.correlation:.0%})"
        )

    lines.extend([
        "",
        "-" * 60,
        "【综合判断】",
        "-" * 60,
        f"市场情绪: {report.market_sentiment}",
        f"资金流向: {report.fund_flow}",
        "",
        f"总结: {report.summary}",
    ])

    if report.key_insights:
        lines.append("")
        lines.append("【关键洞察】")
        for insight in report.key_insights:
            lines.append(f"  • {insight}")

    if report.risk_warnings:
        lines.append("")
        lines.append("【风险警告】")
        for warning in report.risk_warnings:
            lines.append(f"  ⚠️ {warning}")

    lines.append("=" * 60)

    return "\n".join(lines)