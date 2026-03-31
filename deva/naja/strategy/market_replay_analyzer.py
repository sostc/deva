"""
MarketReplayAnalyzer - 市场复盘分析器

三步分析封装：
1. 全市场横截面分析 - 结果可缓存复用
2. 热点叙事主题 + 持仓分析 - 基于第一步，可复用
3. 天道 + 民心信号分析 - 必须实时计算

缓存机制：
- 第一步和第二步的结果会在当天内复用
- 第三步（天道/民心）每次实时计算
- 手动触发时：如果当天已完成第一步，直接复用

用法:
    analyzer = MarketReplayAnalyzer()
    result = analyzer.run_full_analysis()

    # 或分步执行
    analyzer.step1_full_market()
    analyzer.step2_hot_narrative()
    analyzer.step3_tiandao_minxin()
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from deva.naja.cognition.narrative_tracker import (
    NarrativeTracker, TIANDAO_KEYWORDS, MINXIN_KEYWORDS
)
from deva.naja.bandit.portfolio_manager import get_portfolio_manager
from deva.naja.bandit.stock_sector_map import (
    US_STOCK_SECTORS, SECTOR_INDUSTRY_MAP, NARRATIVE_SECTOR_MAP
)
from deva.naja.strategy.market_combo_analyzer import MarketComboAnalyzer


_MARKET_DATA_CACHE: Dict[str, Any] = {}
_MARKET_DATA_CACHE_DATE: str = ""


def _get_today_str() -> str:
    """获取今天的日期字符串"""
    return datetime.now().strftime('%Y-%m-%d')


def _is_cache_valid() -> bool:
    """检查缓存是否有效（当天）"""
    return _MARKET_DATA_CACHE_DATE == _get_today_str() and bool(_MARKET_DATA_CACHE)


@dataclass
class MarketOverview:
    """市场概览"""
    ashare_count: int = 0
    usstock_count: int = 0
    total_count: int = 0

    ashare_advancing: int = 0
    ashare_declining: int = 0
    ashare_unchanged: int = 0
    ashare_avg_change: float = 0.0
    ashare_median_change: float = 0.0
    ashare_breadth: float = 0.0

    usstock_advancing: int = 0
    usstock_declining: int = 0
    usstock_unchanged: int = 0
    usstock_avg_change: float = 0.0
    usstock_median_change: float = 0.0
    usstock_breadth: float = 0.0

    combined_breadth: float = 0.0
    combined_avg_change: float = 0.0
    combined_sentiment: str = "未知"
    fund_flow: str = "未知"


@dataclass
class NarrativePerformance:
    """叙事主题表现"""
    narrative: str
    avg_change: float = 0.0
    gainer_ratio: float = 0.0
    stock_count: int = 0
    top_stock: Optional[Dict] = None
    bottom_stock: Optional[Dict] = None


@dataclass
class PositionAnalysis:
    """持仓分析"""
    code: str
    name: str
    account: str
    quantity: float
    entry_price: float
    current_price: float
    return_pct: float = 0.0
    today_change: float = 0.0
    market_value: float = 0.0
    sector: str = "other"
    narrative: str = ""
    narrative_avg_change: float = 0.0
    relative_change: float = 0.0
    status: str = "⚪"


@dataclass
class TiandaoMinxinAnalysis:
    """天道民心分析"""
    tiandao_score: float = 0.0
    minxin_score: float = 0.0
    recommendation: str = "WATCH"
    reason: str = ""
    tiandao_signals: Dict[str, List[str]] = field(default_factory=dict)
    minxin_signals: Dict[str, List[str]] = field(default_factory=dict)
    pattern: str = "➡️ 观察"

    tiandao_summary: str = ""
    minxin_summary: str = ""
    tiandao_changes: List[str] = field(default_factory=list)
    minxin_changes: List[str] = field(default_factory=list)


@dataclass
class ReplayReport:
    """复盘报告"""
    timestamp: float
    market_overview: MarketOverview
    top_narratives: List[NarrativePerformance]
    positions: List[PositionAnalysis]
    tiandao_minxin: TiandaoMinxinAnalysis
    risks: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    llm_reflection: Optional[Dict[str, Any]] = None

    def _get_llm_reflection(self) -> Optional[Dict[str, Any]]:
        """获取最新的 LLM 反思结果（带超时保护）"""
        import concurrent.futures
        try:
            def fetch():
                from deva.naja.cognition.insight import get_llm_reflection_engine
                engine = get_llm_reflection_engine()
                recent = engine.get_recent_reflections(limit=1)
                return recent[0] if recent else None

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(fetch)
                return future.result(timeout=30)
        except Exception:
            return None

    def to_markdown(self) -> str:
        """转换为Markdown格式"""
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp))

        lines = [
            f"# 📊 市场复盘报告",
            f"",
            f"**生成时间**: {ts}",
            f"",
            f"---",
            f"",
            f"## 📈 市场概览",
            f"",
            f"### 🅰️ A股",
            f"",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 股票数 | {self.market_overview.ashare_count} 只 |",
            f"| 上涨/下跌/平盘 | {self.market_overview.ashare_advancing}/{self.market_overview.ashare_declining}/{self.market_overview.ashare_unchanged} |",
            f"| 平均涨跌 | {self.market_overview.ashare_avg_change:+.2f}% |",
            f"| 中位数涨跌 | {self.market_overview.ashare_median_change:+.2f}% |",
            f"| 市场广度 | {self.market_overview.ashare_breadth:.3f} |",
            f"",
            f"### 🅱️ 美股",
            f"",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 股票数 | {self.market_overview.usstock_count} 只 |",
            f"| 上涨/下跌/平盘 | {self.market_overview.usstock_advancing}/{self.market_overview.usstock_declining}/{self.market_overview.usstock_unchanged} |",
            f"| 平均涨跌 | {self.market_overview.usstock_avg_change:+.2f}% |",
            f"| 中位数涨跌 | {self.market_overview.usstock_median_change:+.2f}% |",
            f"| 市场广度 | {self.market_overview.usstock_breadth:.3f} |",
            f"",
        ]

        # 热点叙事
        lines.extend([
            f"## 🔥 热点叙事",
            f"",
        ])
        for i, nar in enumerate(self.top_narratives[:5], 1):
            bar = "▓" * int(nar.avg_change) if nar.avg_change > 0 else "░" * int(abs(nar.avg_change))
            lines.append(f"{i}. **{nar.narrative}**: {nar.avg_change:+.2f}% {bar}")
            if nar.top_stock:
                lines.append(f"   - 🏆 龙头: {nar.top_stock.get('name', '')} {nar.top_stock.get('change', 0):+.2f}%")
        lines.append(f"")

        # 持仓分析
        lines.extend([
            f"## 💼 持仓分析",
            f"",
            f"| 股票 | 持仓收益 | 今日涨跌 | vs板块 | 状态 |",
            f"|------|----------|----------|---------|------|",
        ])
        for pos in self.positions:
            lines.append(f"| {pos.name}({pos.code}) | {pos.return_pct:+.2f}% | {pos.today_change:+.2f}% | {pos.narrative_avg_change:+.2f}% | {pos.status} |")
        lines.append(f"")

        # 天道民心
        lines.extend([
            f"## ☀️ 天道 + 💓 民心",
            f"",
            f"| 信号 | 评分 | 说明 |",
            f"|------|------|------|",
            f"| ☀️ 天道 | {self.tiandao_minxin.tiandao_score:.2f} | {self.tiandao_minxin.tiandao_summary} |",
            f"| 💓 民心 | {self.tiandao_minxin.minxin_score:.2f} | {self.tiandao_minxin.minxin_summary} |",
            f"| 推荐行动 | {self.tiandao_minxin.recommendation} | {self.tiandao_minxin.pattern} |",
            f"",
        ])

        if self.tiandao_minxin.tiandao_changes:
            lines.extend([
                f"**天道信号变化:**",
                f"",
            ])
            for change in self.tiandao_minxin.tiandao_changes:
                lines.append(f"- {change}")
            lines.append(f"")

        if self.tiandao_minxin.minxin_changes:
            lines.extend([
                f"**民心信号变化:**",
                f"",
            ])
            for change in self.tiandao_minxin.minxin_changes:
                lines.append(f"- {change}")
            lines.append(f"")

        # 风险提示
        if self.risks:
            lines.extend([
                f"## ⚠️ 风险提示",
                f"",
            ])
            for risk in self.risks:
                lines.append(f"- {risk}")
            lines.append(f"")

        # 建议
        if self.suggestions:
            lines.extend([
                f"## 💡 建议",
                f"",
            ])
            for suggestion in self.suggestions:
                lines.append(f"- {suggestion}")
            lines.append(f"")

        # LLM 反思（可选，超时则跳过）
        llm_refl = self.llm_reflection
        if not llm_refl:
            llm_refl = self._get_llm_reflection()
        if llm_refl:
            lines.extend([
                f"## 🤖 LLM 深度反思",
                f"",
                f"**主题**: {llm_refl.get('theme', '市场反思')}",
                f"",
                f"{llm_refl.get('summary', '暂无反思内容')}",
                f"",
            ])
            symbols = llm_refl.get('symbols', [])
            if symbols:
                lines.append(f"| 涉及股票 |")
                lines.append(f"|------|")
                for s in symbols[:10]:
                    if isinstance(s, str):
                        lines.append(f"| {s} |")
                    else:
                        lines.append(f"| {s.get('code', '')} |")

            narratives = llm_refl.get('narratives', [])
            if narratives:
                lines.append(f"| 叙事 | 阶段 | 趋势 | 关注度 |")
                lines.append(f"|------|------|------|------|")
                for n in narratives[:5]:
                    if isinstance(n, dict):
                        lines.append(f"| {n.get('narrative', '-')} | {n.get('stage', '-')} | {n.get('trend', 0):.0f} | {n.get('attention_score', 0):.3f} |")
                    else:
                        lines.append(f"| {n} | - | - | - |")

        lines.extend([
            f"---",
            f"",
            f"*报告生成时间: {ts}*",
        ])

        return "\n".join(lines)


def _is_trading_hours() -> bool:
    """判断当前是否在交易时间内（A股）"""
    from datetime import datetime
    now = datetime.now()
    weekday = now.weekday()
    if weekday >= 5:
        return False
    hour = now.hour
    minute = now.minute
    current_minutes = hour * 60 + minute
    trading_start = 9 * 60 + 30
    trading_end = 15 * 60
    return trading_start <= current_minutes <= trading_end


class MarketReplayAnalyzer:
    """
    市场复盘分析器

    三步分析：
    1. 全市场横截面分析 - 结果可缓存复用（盘中强制刷新，盘前/盘后用缓存）
    2. 热点叙事主题 + 持仓分析 - 基于第一步，可复用
    3. 天道 + 民心信号分析 - 必须实时计算
    """

    def __init__(self):
        self.nt = NarrativeTracker()
        self.analyzer = MarketComboAnalyzer()

        self.market_overview: Optional[MarketOverview] = None
        self.all_stocks: Dict[str, Dict] = {}
        self.narrative_performance: Dict[str, Dict] = {}
        self.top_narratives: List[NarrativePerformance] = []
        self.positions: List[PositionAnalysis] = []
        self.tiandao_minxin: Optional[TiandaoMinxinAnalysis] = None

        self._check_and_use_cache()

    def _check_and_use_cache(self):
        """检查并使用缓存（盘中不使用缓存）"""
        global _MARKET_DATA_CACHE, _MARKET_DATA_CACHE_DATE

        if _is_trading_hours():
            print("[MarketReplayAnalyzer] 当前交易时间内，不使用缓存")
            return

        if _is_cache_valid():
            print(f"[MarketReplayAnalyzer] 使用缓存数据 (缓存时间: {_MARKET_DATA_CACHE.get('cache_time', 'unknown')})")
            self.all_stocks = _MARKET_DATA_CACHE.get("all_stocks", {})
            self.market_overview = _MARKET_DATA_CACHE.get("market_overview")
            self.narrative_performance = _MARKET_DATA_CACHE.get("narrative_performance", {})
            self.top_narratives = _MARKET_DATA_CACHE.get("top_narratives", [])
            self.positions = _MARKET_DATA_CACHE.get("positions", [])

    def _save_to_cache(self):
        """保存到全局缓存"""
        global _MARKET_DATA_CACHE, _MARKET_DATA_CACHE_DATE

        _MARKET_DATA_CACHE_DATE = _get_today_str()
        _MARKET_DATA_CACHE = {
            "cache_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "all_stocks": self.all_stocks,
            "market_overview": self.market_overview,
            "narrative_performance": self.narrative_performance,
            "top_narratives": self.top_narratives,
            "positions": self.positions,
        }

    def _fetch_market_data(self) -> Dict[str, Dict]:
        """获取市场数据"""
        ashare = self.nt._fetch_ashare_data()
        usstock = self.nt._fetch_us_stock_data()
        return {**ashare, **usstock}

    def step1_full_market(self, force_refresh: bool = False) -> MarketOverview:
        """第一步：全市场横截面分析

        Args:
            force_refresh: 是否强制刷新（忽略缓存）
        """
        if not force_refresh and self.market_overview is not None:
            print("[MarketReplayAnalyzer] 第一步已缓存，跳过")
            return self.market_overview

        self.all_stocks = self._fetch_market_data()

        ashare_data = [s for s in self.all_stocks.values() if s.get("market") == "A"]
        usstock_data = [s for s in self.all_stocks.values() if s.get("market") == "US"]

        ashare_count = len(ashare_data)
        usstock_count = len(usstock_data)

        ashare_report = self.analyzer.analyze(ashare_data) if ashare_data else None
        usstock_report = self.analyzer.analyze(usstock_data) if usstock_data else None

        self.market_overview = MarketOverview(
            ashare_count=ashare_count,
            usstock_count=usstock_count,
            total_count=len(self.all_stocks),

            ashare_advancing=ashare_report.cross_sectional.get("advancing_count", 0) if ashare_report else 0,
            ashare_declining=ashare_report.cross_sectional.get("declining_count", 0) if ashare_report else 0,
            ashare_unchanged=ashare_report.cross_sectional.get("unchanged_count", 0) if ashare_report else 0,
            ashare_avg_change=ashare_report.cross_sectional.get("avg_change", 0) if ashare_report else 0,
            ashare_median_change=ashare_report.cross_sectional.get("median_change", 0) if ashare_report else 0,
            ashare_breadth=ashare_report.market_breadth if ashare_report else 0,

            usstock_advancing=usstock_report.cross_sectional.get("advancing_count", 0) if usstock_report else 0,
            usstock_declining=usstock_report.cross_sectional.get("declining_count", 0) if usstock_report else 0,
            usstock_unchanged=usstock_report.cross_sectional.get("unchanged_count", 0) if usstock_report else 0,
            usstock_avg_change=usstock_report.cross_sectional.get("avg_change", 0) if usstock_report else 0,
            usstock_median_change=usstock_report.cross_sectional.get("median_change", 0) if usstock_report else 0,
            usstock_breadth=usstock_report.market_breadth if usstock_report else 0,

            combined_breadth=(ashare_report.market_breadth + usstock_report.market_breadth) / 2 if (ashare_report and usstock_report) else 0,
            combined_avg_change=(ashare_report.cross_sectional.get("avg_change", 0) + usstock_report.cross_sectional.get("avg_change", 0)) / 2 if (ashare_report and usstock_report) else 0,
            combined_sentiment="偏暖" if (ashare_report and usstock_report and ashare_report.market_breadth > 0 and usstock_report.market_breadth > 0) else "偏冷",
            fund_flow="均衡",
        )

        self._save_to_cache()
        return self.market_overview

    def step2_hot_narrative(self, force_refresh: bool = False) -> List[NarrativePerformance]:
        """第二步：热点叙事主题 + 持仓分析

        Args:
            force_refresh: 是否强制刷新
        """
        if not force_refresh and self.top_narratives:
            print("[MarketReplayAnalyzer] 第二步已缓存，跳过")
            return self.top_narratives

        if not self.all_stocks:
            self.step1_full_market()

        self.narrative_performance = {}

        for narrative, sectors in NARRATIVE_SECTOR_MAP.items():
            sector_changes = []
            for sector in sectors:
                for code_lower, info in US_STOCK_SECTORS.items():
                    if info.get("sector") == sector:
                        code = code_lower.upper()
                        stock_data = self.all_stocks.get(code)
                        if stock_data:
                            change = stock_data.get("change_pct", 0) * 100
                            sector_changes.append({
                                "code": code,
                                "name": stock_data.get("name", code),
                                "change": change,
                            })

            if sector_changes:
                changes = [s["change"] for s in sector_changes]
                avg_change = sum(changes) / len(changes)
                gainer_ratio = sum(1 for c in changes if c > 0) / len(changes)

                sorted_stocks = sorted(sector_changes, key=lambda x: x["change"], reverse=True)
                top_stock = sorted_stocks[0] if sorted_stocks else None
                bottom_stock = sorted_stocks[-1] if len(sorted_stocks) > 1 else top_stock

                self.narrative_performance[narrative] = {
                    "avg_change": avg_change,
                    "gainer_ratio": gainer_ratio,
                    "stock_count": len(sector_changes),
                    "stocks": sector_changes,
                    "top_stock": top_stock,
                    "bottom_stock": bottom_stock,
                }

        sorted_narratives = sorted(
            self.narrative_performance.items(),
            key=lambda x: x[1]["avg_change"],
            reverse=True
        )

        self.top_narratives = [
            NarrativePerformance(
                narrative=n,
                avg_change=data["avg_change"],
                gainer_ratio=data["gainer_ratio"],
                stock_count=data["stock_count"],
                top_stock=data["top_stock"],
                bottom_stock=data["bottom_stock"],
            )
            for n, data in sorted_narratives[:5]
        ]

        self._analyze_positions()
        self._save_to_cache()

        return self.top_narratives

    def _analyze_positions(self) -> List[PositionAnalysis]:
        """分析持仓"""
        pm = get_portfolio_manager()
        self.positions = []

        for account_name in ["Spark", "Cutie"]:
            portfolio = pm.get_us_portfolio(account_name)
            if not portfolio:
                continue

            for pos in portfolio.get_all_positions():
                code = pos.stock_code.upper()
                stock_data = self.all_stocks.get(code)
                sector_info = US_STOCK_SECTORS.get(pos.stock_code.lower(), {})
                narrative = sector_info.get("narrative", "")
                sector = sector_info.get("sector", "other")

                today_change = stock_data.get("change_pct", 0) * 100 if stock_data else 0

                narrative_avg = 0.0
                relative = 0.0
                status = "⚪"

                if narrative in self.narrative_performance:
                    narrative_avg = self.narrative_performance[narrative]["avg_change"]
                    relative = today_change - narrative_avg
                    if relative > 1:
                        status = "🟢"
                    elif relative > -1:
                        status = "🟡"
                    else:
                        status = "🔴"

                self.positions.append(PositionAnalysis(
                    code=code,
                    name=pos.stock_name,
                    account=account_name,
                    quantity=pos.quantity,
                    entry_price=pos.entry_price,
                    current_price=pos.current_price,
                    return_pct=pos.return_pct,
                    today_change=today_change,
                    market_value=pos.market_value,
                    sector=sector,
                    narrative=narrative,
                    narrative_avg_change=narrative_avg,
                    relative_change=relative,
                    status=status,
                ))

        return self.positions

    def step3_tiandao_minxin(self) -> TiandaoMinxinAnalysis:
        """第三步：天道 + 民心信号分析（每次实时计算）"""
        print("[MarketReplayAnalyzer] 第三步：实时计算天道/民心信号")
        summary = self.nt.get_tiandao_minxin_summary()

        tiandao_score = summary.get("tiandao_score", 0.0)
        minxin_score = summary.get("minxin_score", 0.0)

        if tiandao_score > 0.5 and minxin_score < 0.3:
            pattern = "🌟 最佳时机：天道强 + 民心弱"
        elif tiandao_score > 0.5 and minxin_score > 0.5:
            pattern = "📈 顺势持有：天道强 + 民心强"
        elif tiandao_score < 0.2 and minxin_score > 0.5:
            pattern = "⚠️ 警惕：天道弱 + 民心强"
        elif tiandao_score < 0.2 and minxin_score < 0.3:
            pattern = "❄️ 观望：天道弱 + 民心弱"
        else:
            pattern = "➡️ 观察：信号不明显"

        tiandao_signals = summary.get("signals", {}).get("tiandao", {})
        minxin_signals = summary.get("signals", {}).get("minxin", {})

        tiandao_hits = sum(len(v) for v in tiandao_signals.values())
        minxin_hits = sum(len(v) for v in minxin_signals.values())

        tiandao_changes = []
        for cat, kws in tiandao_signals.items():
            if kws:
                tiandao_changes.append(f"{cat}: {', '.join(kws[:3])}")

        minxin_changes = []
        for cat, kws in minxin_signals.items():
            if kws:
                minxin_changes.append(f"{cat}: {', '.join(kws[:3])}")

        if tiandao_hits >= 3:
            tiandao_summary = f"AI落地加速，{tiandao_hits}个天道信号"
        elif tiandao_hits >= 1:
            tiandao_summary = f"存在{tiandao_hits}个天道信号"
        else:
            tiandao_summary = "无明显天道信号"

        if minxin_hits >= 3:
            minxin_summary = f"市场情绪高涨，{minxin_hits}个民心信号"
        elif minxin_hits >= 1:
            minxin_summary = f"存在{minxin_hits}个民心信号"
        else:
            minxin_summary = "市场情绪平稳"

        self.tiandao_minxin = TiandaoMinxinAnalysis(
            tiandao_score=tiandao_score,
            minxin_score=minxin_score,
            recommendation=summary.get("recommendation", "WATCH"),
            reason=summary.get("reason", ""),
            tiandao_signals=tiandao_signals,
            minxin_signals=minxin_signals,
            pattern=pattern,
            tiandao_summary=tiandao_summary,
            minxin_summary=minxin_summary,
            tiandao_changes=tiandao_changes,
            minxin_changes=minxin_changes,
        )

        return self.tiandao_minxin

    def run_full_analysis(self, force_refresh: bool = False) -> ReplayReport:
        """执行完整三步分析

        Args:
            force_refresh: 是否强制刷新（忽略缓存）
        """
        self.step1_full_market(force_refresh=force_refresh)
        self.step2_hot_narrative(force_refresh=force_refresh)
        self.step3_tiandao_minxin()

        risks = self._extract_risks()
        suggestions = self._generate_suggestions()

        return ReplayReport(
            timestamp=time.time(),
            market_overview=self.market_overview,
            top_narratives=self.top_narratives,
            positions=self.positions,
            tiandao_minxin=self.tiandao_minxin,
            risks=risks,
            suggestions=suggestions,
        )

    def _extract_risks(self) -> List[str]:
        """提取风险"""
        risks = []

        if not self.market_overview:
            return risks

        if self.market_overview.combined_avg_change < -2:
            risks.append(f"大盘整体下跌({self.market_overview.combined_avg_change:+.1f}%)，注意系统性风险")

        if self.market_overview.ashare_avg_change < -2:
            risks.append(f"A股下跌({self.market_overview.ashare_avg_change:+.1f}%)")

        if self.market_overview.usstock_avg_change < -2:
            risks.append(f"美股下跌({self.market_overview.usstock_avg_change:+.1f}%)")

        for pos in self.positions:
            if pos.return_pct > 30:
                risks.append(f"{pos.name}盈利较大({pos.return_pct:.0f}%)，警惕回调")
            if pos.today_change < -3:
                risks.append(f"{pos.name}今日大跌({pos.today_change:.1f}%)，关注是否破位")

        if len(self.positions) < 3:
            risks.append("持仓过于集中，注意分散风险")

        return risks

    def _generate_suggestions(self) -> List[str]:
        """生成建议"""
        suggestions = []

        if not self.tiandao_minxin:
            return suggestions

        rec = self.tiandao_minxin.recommendation
        if rec == "STRONG_BUY":
            suggestions.append("天道强信号，建议加仓AI/算力相关")
        elif rec == "ALL_IN":
            suggestions.append("天道信号强劲，继续持有/加仓")
        elif rec == "HOLD":
            suggestions.append("天道信号存在，持有观望")
        elif rec == "REDUCE":
            suggestions.append("天道信号减弱，考虑减仓")
        else:
            if self.market_overview and self.market_overview.combined_sentiment == "极度乐观":
                suggestions.append("市场极度乐观，警惕回调风险")
            elif self.market_overview and self.market_overview.combined_sentiment == "极度悲观":
                suggestions.append("市场极度悲观，关注买入机会")

        return suggestions


def _save_replay_to_history(report: ReplayReport):
    """保存复盘记录到历史"""
    try:
        from deva import NB
        nb = NB("naja_market_replay_history")
        history = nb.get("records") or []
        record = {
            "timestamp": report.timestamp,
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(report.timestamp)),
            "market_sentiment": report.market_overview.market_sentiment if report.market_overview else "未知",
            "avg_change": report.market_overview.avg_change if report.market_overview else 0,
            "market_breadth": report.market_overview.market_breadth if report.market_overview else 0,
            "top_narrative": report.top_narratives[0].narrative if report.top_narratives else "无",
            "top_narrative_change": report.top_narratives[0].avg_change if report.top_narratives else 0,
            "positions_count": len(report.positions),
            "positions_summary": [
                {"name": p.name, "change": p.today_change, "status": p.status}
                for p in report.positions
            ],
            "tiandao_score": report.tiandao_minxin.tiandao_score if report.tiandao_minxin else 0,
            "minxin_score": report.tiandao_minxin.minxin_score if report.tiandao_minxin else 0,
            "markdown": report.to_markdown(),
        }
        history.insert(0, record)
        history = history[:30]
        nb["records"] = history
        return True
    except Exception as e:
        print(f"[MarketReplay] 保存历史失败: {e}")
        return False


def get_replay_history(limit: int = 5) -> list:
    """获取复盘历史记录"""
    try:
        from deva import NB
        nb = NB("naja_market_replay_history")
        history = nb.get("records") or []
        return history[:limit]
    except Exception:
        return []


def run_replay_and_push() -> ReplayReport:
    """
    运行复盘并推送结果到DTalk，同时保存历史记录

    用于盘后定时任务
    """
    analyzer = MarketReplayAnalyzer()
    report = analyzer.run_full_analysis(force_refresh=True)

    _save_replay_to_history(report)

    try:
        from deva.endpoints import Dtalk
        markdown_content = report.to_markdown()
        dtalk_msg = f"@md@市场复盘报告|{markdown_content}"
        dtalk = Dtalk()
        dtalk.send(dtalk_msg)
        print(f"[MarketReplay] 复盘报告已推送到DTalk")
    except Exception as e:
        print(f"[MarketReplay] 推送失败: {e}")

    return report


def run_replay_no_push() -> ReplayReport:
    """
    运行复盘但不推送（用于UI展示）
    """
    analyzer = MarketReplayAnalyzer()
    report = analyzer.run_full_analysis()
    _save_replay_to_history(report)
    return report


if __name__ == "__main__":
    analyzer = MarketReplayAnalyzer()
    report = analyzer.run_full_analysis()
    print(report.to_markdown())