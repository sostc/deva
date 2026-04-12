"""
DailyReviewAnalyzer - 市场复盘分析器

三步分析封装：
1. 全市场横截面分析 - 结果可缓存复用
2. 热点叙事主题 + 持仓分析 - 基于第一步，可复用
3. 天道 + 民心信号分析 - 必须实时计算

缓存机制：
- 第一步和第二步的结果会在当天内复用
- 第三步（天道/民心）每次实时计算
- 手动触发时：如果当天已完成第一步，直接复用

用法:
    analyzer = DailyReviewAnalyzer()
    result = analyzer.run_full_analysis()

    # 或分步执行
    analyzer.step1_full_market()
    analyzer.step2_hot_narrative()
    analyzer.step3_tiandao_minxin()
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_IMESSAGE_PHONE = "+8618626880688"


def send_imessage(phone: str, text: str) -> bool:
    """发送iMessage"""
    try:
        import subprocess
        cmd = [
            'osascript', '-e',
            f'''tell application "Messages"
                send "{text.replace('"', '\\"')}" to buddy "{phone}"
            end tell'''
        ]
        subprocess.run(cmd, capture_output=True, timeout=10)
        return True
    except Exception as e:
        log.warning(f"iMessage发送失败: {e}")
        return False


from deva.naja.cognition.narrative import NarrativeTracker
from deva.naja.cognition.keyword_registry import DYNAMICS_KEYWORDS, SENTIMENT_KEYWORDS
from deva.naja.bandit.portfolio_manager import get_portfolio_manager
from deva.naja.bandit.stock_block_map import (
    US_STOCK_BLOCKS, INDUSTRY_CODE_TO_NAME, NARRATIVE_INDUSTRY_MAP
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
    ashare_effective_count: int = 0
    ashare_data_date: str = ""
    ashare_last_snapshot_time: str = ""
    ashare_data_stale: bool = False
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

    ashare_top_blocks: List[Dict[str, Any]] = field(default_factory=list)
    ashare_flow_timeline: List[Dict[str, Any]] = field(default_factory=list)
    ashare_breakouts: List[Dict[str, Any]] = field(default_factory=list)
    ashare_anomalies: List[Dict[str, Any]] = field(default_factory=list)

    # A股注意力系统数据
    ashare_attention: float = 0.0
    ashare_activity: float = 0.0
    ashare_top_attention_stocks: List[Dict[str, Any]] = field(default_factory=list)
    ashare_top_attention_blocks: List[Dict[str, Any]] = field(default_factory=list)

    # 美股注意力系统数据
    us_attention: float = 0.0
    us_activity: float = 0.0
    us_top_attention_stocks: List[Dict[str, Any]] = field(default_factory=list)
    us_top_attention_blocks: List[Dict[str, Any]] = field(default_factory=list)

    # 历史热点切换数据
    hotspot_shift_timeline: List[Dict[str, Any]] = field(default_factory=list)
    block_shift_events: List[Dict[str, Any]] = field(default_factory=list)
    symbol_shift_events: List[Dict[str, Any]] = field(default_factory=list)


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
    block: str = "other"
    narrative: str = ""
    narrative_avg_change: float = 0.0
    relative_change: float = 0.0
    status: str = "⚪"


@dataclass
class TiandaoMinxinAnalysis:
    """价值/市场分析（天道/民心）

    【天道】= 价值评分（value_score）：我们认定的核心价值信号
    【民心】= 市场叙事评分（market_narrative_score）：市场当前关注的话题热度
    """
    value_score: float = 0.0
    market_narrative_score: float = 0.0
    recommendation: str = "WATCH"
    reason: str = ""
    value_signals: Dict[str, List[str]] = field(default_factory=dict)
    market_narrative_signals: Dict[str, List[str]] = field(default_factory=dict)
    pattern: str = "➡️ 观察"

    value_summary: str = ""
    market_narrative_summary: str = ""
    value_changes: List[str] = field(default_factory=list)
    market_narrative_changes: List[str] = field(default_factory=list)


@dataclass
class WisdomPerspective:
    """知识库观点"""
    narrative: str
    change: float
    snippets: List[Dict[str, str]] = field(default_factory=list)
    insight: str = ""

    @staticmethod
    def clean_html(text: str) -> str:
        """清理HTML标签如<em>"""
        import re
        text = re.sub(r'</?em>', '', text)
        return text.strip()

    def to_markdown(self) -> str:
        """转换为Markdown格式"""
        if not self.snippets:
            return f"**{self.narrative}**({self.change:+.1f}%): 暂无相关观点"

        lines = [f"**{self.narrative}**({self.change:+.1f}%):"]

        if self.insight:
            lines.append(f"\n💭 {self.insight}\n")
        else:
            for s in self.snippets[:2]:
                title = self.clean_html(s.get('title', ''))
                highlight = self.clean_html(s.get('highlight', ''))
                lines.append(f"  - **{title}**: {highlight[:80]}...")

        return "\n".join(lines)


@dataclass
class ReviewReport:
    """复盘报告"""
    timestamp: float
    market_overview: MarketOverview
    top_narratives: List[NarrativePerformance]
    positions: List[PositionAnalysis]
    tiandao_minxin: TiandaoMinxinAnalysis
    risks: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    wisdom_perspectives: List[WisdomPerspective] = field(default_factory=list)
    llm_reflection: Optional[Dict[str, Any]] = None
    
    # 美林时钟数据
    merrill_clock_signal: Optional[Dict[str, Any]] = None
    
    # 跨市场流动性追踪数据
    liquidity_insights: List[Dict[str, Any]] = field(default_factory=list)

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

        ashare_effective = max(self.market_overview.ashare_effective_count, 0)
        if ashare_effective > 0:
            adv_pct = self.market_overview.ashare_advancing / ashare_effective * 100
            dec_pct = self.market_overview.ashare_declining / ashare_effective * 100
            flat_pct = self.market_overview.ashare_unchanged / ashare_effective * 100
            adv_dec_flat = f"{adv_pct:.1f}%/{dec_pct:.1f}%/{flat_pct:.1f}%"
        else:
            adv_dec_flat = "0.0%/0.0%/0.0%"

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
            f"| 数据日期 | {self.market_overview.ashare_data_date or '未知'} |",
            f"| 最新快照 | {self.market_overview.ashare_last_snapshot_time or '未知'} |",
            f"| 有效股票数 | {self.market_overview.ashare_effective_count} 只 |",
            f"| 上涨/下跌/平盘 | {adv_dec_flat} |",
            f"| 平均涨跌 | {self.market_overview.ashare_avg_change:+.2f}% |",
            f"| 中位数涨跌 | {self.market_overview.ashare_median_change:+.2f}% |",
            f"| 市场广度 | {self.market_overview.ashare_breadth:.3f} |",
            f"| 注意力 | {self.market_overview.ashare_attention:.3f} |",
            f"| 活跃度 | {self.market_overview.ashare_activity:.3f} |",
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
            f"| 注意力 | {self.market_overview.us_attention:.3f} |",
            f"| 活跃度 | {self.market_overview.us_activity:.3f} |",
            f"",
        ]

        if self.market_overview.ashare_data_stale:
            lines.extend([
                f"**提示**: A股数据非今日最新交易日，请确认回放数据表是否更新",
                f"",
            ])

        if self.market_overview.ashare_top_blocks:
            lines.extend([
                f"#### 🧭 A股题材重点（Top3）",
                f"",
            ])
            for sec in self.market_overview.ashare_top_blocks[:3]:
                leaders = sec.get("leaders", [])
                leader_text = ", ".join([f"{s.get('name','')}{s.get('change',0):+.1f}%" for s in leaders]) if leaders else "无"
                flow_text = sec.get("flow_hint", "")
                breakout_text = sec.get("breakout_hint", "")
                anomaly_text = sec.get("anomaly_hint", "")
                lines.append(f"- **{sec.get('block','')}**：平均涨跌 {sec.get('avg_change',0):+.2f}%，资金 {sec.get('flow', '未知')}")
                lines.append(f"- 龙头: {leader_text}")
                if flow_text:
                    lines.append(f"- 资金流向: {flow_text}")
                if breakout_text:
                    lines.append(f"- 突破: {breakout_text}")
                if anomaly_text:
                    lines.append(f"- 异动: {anomaly_text}")
                lines.append(f"")

        if self.market_overview.ashare_top_attention_blocks:
            lines.extend([
                f"#### 🎯 A股热点题材（Top5）",
                f"",
            ])
            for block_info in self.market_overview.ashare_top_attention_blocks:
                block = block_info.get('block', '')
                att = block_info.get('attention', 0)
                lines.append(f"- **{block}**: 注意力 {att:.3f}")
            lines.append(f"")

        if self.market_overview.ashare_top_attention_stocks:
            lines.extend([
                f"#### ⭐ A股注意力个股（Top10）",
                f"",
            ])
            for i, stock_info in enumerate(self.market_overview.ashare_top_attention_stocks[:10], 1):
                code = stock_info.get('code', '')
                weight = stock_info.get('weight', 0)
                lines.append(f"{i}. {code}: 权重 {weight:.2f}")
            lines.append(f"")

        if self.market_overview.ashare_flow_timeline:
            lines.extend([
                f"#### 💧 资金流向时间轴",
                f"",
            ])
            for ev in self.market_overview.ashare_flow_timeline[:6]:
                inflow = ", ".join([f"{s}↑" for s in ev.get("inflow_blocks", [])])
                outflow = ", ".join([f"{s}↓" for s in ev.get("outflow_blocks", [])])
                lines.append(f"- {ev.get('time', '')}: {inflow} | {outflow}")
            lines.append(f"")

        if self.market_overview.us_top_attention_blocks:
            lines.extend([
                f"#### 🎯 美股热点题材（Top5）",
                f"",
            ])
            for block_info in self.market_overview.us_top_attention_blocks:
                block = block_info.get('block', '')
                att = block_info.get('attention', 0)
                lines.append(f"- **{block}**: 注意力 {att:.3f}")
            lines.append(f"")

        if self.market_overview.us_top_attention_stocks:
            lines.extend([
                f"#### ⭐ 美股注意力个股（Top10）",
                f"",
            ])
            for i, stock_info in enumerate(self.market_overview.us_top_attention_stocks[:10], 1):
                code = stock_info.get('code', '')
                weight = stock_info.get('weight', 0)
                lines.append(f"{i}. {code}: 权重 {weight:.2f}")
            lines.append(f"")

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
            f"| 股票 | 持仓收益 | 今日涨跌 | vs题材 | 状态 |",
            f"|------|----------|----------|---------|------|",
        ])
        for pos in self.positions:
            lines.append(f"| {pos.name}({pos.code}) | {pos.return_pct:+.2f}% | {pos.today_change:+.2f}% | {pos.narrative_avg_change:+.2f}% | {pos.status} |")
        lines.append(f"")

        # 天道民心
        lines.extend([
            f"## ☀️ 天道(价值) + 💓 民心(市场叙事)",
            f"",
            f"| 信号 | 评分 | 说明 |",
            f"|------|------|------|",
            f"| ☀️ 天道(价值) | {self.tiandao_minxin.value_score:.2f} | {self.tiandao_minxin.value_summary} |",
            f"| 💓 民心(市场叙事) | {self.tiandao_minxin.market_narrative_score:.2f} | {self.tiandao_minxin.market_narrative_summary} |",
            f"| 推荐行动 | {self.tiandao_minxin.recommendation} | {self.tiandao_minxin.pattern} |",
            f"",
        ])

        if self.tiandao_minxin.value_changes:
            lines.extend([
                f"**天道(价值)信号变化:**",
                f"",
            ])
            for change in self.tiandao_minxin.value_changes:
                lines.append(f"- {change}")
            lines.append(f"")

        if self.tiandao_minxin.market_narrative_changes:
            lines.extend([
                f"**民心(市场叙事)信号变化:**",
                f"",
            ])
            for change in self.tiandao_minxin.market_narrative_changes:
                lines.append(f"- {change}")
            lines.append(f"")

        if self.tiandao_minxin.value_signals:
            lines.extend([
                f"**天道(价值)具体信号:**",
                f"",
            ])
            for cat, kws in self.tiandao_minxin.value_signals.items():
                if kws:
                    lines.append(f"- {cat}: {', '.join(kws[:5])}")
            lines.append(f"")

        if self.tiandao_minxin.market_narrative_signals:
            lines.extend([
                f"**民心(市场叙事)具体信号:**",
                f"",
            ])
            for cat, kws in self.tiandao_minxin.market_narrative_signals.items():
                if kws:
                    lines.append(f"- {cat}: {', '.join(kws[:5])}")
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
            core_summary = llm_refl.get('summary', '暂无反思内容')
            if isinstance(core_summary, list):
                core_summary_text = "；".join([str(s) for s in core_summary if s])
            else:
                core_summary_text = str(core_summary)
            lines.extend([
                f"## 🤖 LLM 深度反思",
                f"",
                f"**主题**: {llm_refl.get('theme', '市场反思')}",
                f"",
                f"1. 核心结论: {core_summary_text}",
            ])
            symbols = llm_refl.get('symbols', [])
            if symbols:
                sym_list = []
                for s in symbols[:10]:
                    if isinstance(s, str):
                        sym_list.append(s)
                    else:
                        sym_list.append(s.get('code', ''))
                sym_list = [s for s in sym_list if s]
                if sym_list:
                    lines.append(f"2. 涉及股票: {', '.join(sym_list)}")

            narratives = llm_refl.get('narratives', [])
            if narratives:
                lines.append(f"3. 叙事变化: 见下表")
                lines.append(f"")
                lines.append(f"| 叙事 | 阶段 | 趋势 | 关注度 |")
                lines.append(f"|------|------|------|------|")
                for n in narratives[:5]:
                    if isinstance(n, dict):
                        lines.append(f"| {n.get('narrative', '-')} | {n.get('stage', '-')} | {n.get('trend', 0):.0f} | {n.get('attention_score', 0):.3f} |")
                    else:
                        lines.append(f"| {n} | - | - | - |")

        # 美林时钟数据
        if self.merrill_clock_signal:
            mc = self.merrill_clock_signal
            phase_name = mc.get('phase_name', mc.get('phase', '未知'))
            confidence = mc.get('confidence', 0)
            growth_score = mc.get('growth_score', 0)
            inflation_score = mc.get('inflation_score', 0)
            asset_ranking = mc.get('asset_ranking', [])
            
            # 阶段 emoji
            phase_emoji = {
                "复苏": "🌱",
                "过热": "🔥",
                "滞胀": "⚠️",
                "衰退": "🥶",
            }.get(phase_name, "❓")
            
            asset_text = " > ".join(asset_ranking) if asset_ranking else "暂无"
            
            lines.extend([
                f"## 🌡️ 美林时钟周期",
                f"",
                f"**{phase_emoji} 当前周期**: {phase_name}（置信度 {confidence*100:.0f}%）",
                f"",
                f"| 指标 | 数值 |",
                f"|------|------|",
                f"| 增长评分 | {growth_score:+.2f} |",
                f"| 通胀评分 | {inflation_score:+.2f} |",
                f"| 资产偏好 | {asset_text} |",
                f"",
            ])
            
            # 如果有数据摘要
            data_summary = mc.get('data_summary', {})
            if data_summary:
                gdp = data_summary.get('gdp_growth')
                pce = data_summary.get('pce_yoy')
                unemployment = data_summary.get('unemployment_rate')
                
                summary_items = []
                if gdp is not None:
                    summary_items.append(f"GDP同比 {gdp:+.1f}%")
                if pce is not None:
                    summary_items.append(f"PCE同比 {pce:+.1f}%")
                if unemployment is not None:
                    summary_items.append(f"失业率 {unemployment:.1f}%")
                
                if summary_items:
                    lines.append(f"**核心数据**: {', '.join(summary_items)}")
                    lines.append(f"")

        # 跨市场流动性追踪
        if self.liquidity_insights:
            lines.extend([
                f"## 💧 跨市场流动性追踪",
                f"",
            ])
            
            # 按来源市场分组
            by_source = {}
            for insight in self.liquidity_insights:
                source = insight.get('source_market', '未知')
                by_source.setdefault(source, []).append(insight)
            
            for source, insights in by_source.items():
                lines.append(f"**📍 {source}**")
                for insight in insights[:3]:
                    narrative = insight.get('narrative', '')
                    target = insight.get('target_markets', [])
                    prob = insight.get('propagation_probability', 0)
                    severity = insight.get('severity', 0)
                    
                    target_text = ', '.join(target[:3]) if target else '无'
                    severity_emoji = "🔴" if severity > 0.7 else "🟡" if severity > 0.4 else "🟢"
                    
                    lines.append(f"- {severity_emoji} {narrative} → {target_text} (概率{prob:.0%})")
                lines.append(f"")

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


class DailyReviewAnalyzer:
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
        self._ashare_block_cache: Dict[str, str] = {}
        self._ashare_block_ready: bool = False
        self._ashare_block_error: Optional[str] = None

        self._check_and_use_cache()

    def _check_and_use_cache(self):
        """检查并使用缓存（盘中不使用缓存）"""
        global _MARKET_DATA_CACHE, _MARKET_DATA_CACHE_DATE

        if _is_trading_hours():
            log.debug("[DailyReviewAnalyzer] 当前交易时间内，不使用缓存")
            return

        if _is_cache_valid():
            log.debug(f"[DailyReviewAnalyzer] 使用缓存数据 (缓存时间: {_MARKET_DATA_CACHE.get('cache_time', 'unknown')})")
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

    def _normalize_change_pct(self, data: Dict[str, Dict]):
        """统一涨跌幅为小数（1% = 0.01）"""
        for _, item in data.items():
            market = item.get("market", "A")
            change_pct = item.get("change_pct", 0)
            try:
                change_pct = float(change_pct)
            except Exception:
                change_pct = 0.0

            if market == "US":
                # 美股数据默认是百分比，统一转为小数
                change_pct = change_pct / 100.0

            item["change_pct"] = change_pct
            item["p_change"] = change_pct

    def _filter_ashare_effective(self, stocks: List[Dict]) -> List[Dict]:
        """A股噪音过滤，返回有效股票列表"""
        if not stocks:
            return []

        try:
            import pandas as pd
            from deva.naja.market_hotspot.processing.noise_filter import NoiseFilter

            df = pd.DataFrame(stocks)
            if df.empty:
                return []

            df["name"] = df.get("name", "").astype(str)
            if "price" in df.columns:
                df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0)
            if "volume" in df.columns:
                df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)

            from deva.naja.market_hotspot.processing.noise_filter import get_noise_filter
            noise_filter = get_noise_filter()
            filtered = noise_filter.filter_dataframe(
                df,
                symbol_col="code" if "code" in df.columns else None,
                amount_col="amount" if "amount" in df.columns else None,
                volume_col="volume" if "volume" in df.columns else None,
                price_col="price" if "price" in df.columns else None,
                name_col="name" if "name" in df.columns else None,
            )

            return filtered.to_dict("records")
        except Exception:
            return stocks

    def _filter_ashare_snapshot(self, records: List[Dict]) -> List[Dict]:
        """对单个快照进行噪音过滤"""
        return self._filter_ashare_effective(records)

    def _ensure_ashare_block_ready(self):
        if self._ashare_block_ready or self._ashare_block_error:
            return
        try:
            from deva.naja.dictionary.tongdaxin_blocks import _parse_blocks_file
            _parse_blocks_file()
            self._ashare_block_ready = True
        except Exception as e:
            self._ashare_block_error = str(e)

    def _get_ashare_block(self, code: str) -> str:
        """获取A股题材"""
        if not code:
            return "其他"
        if code in self._ashare_block_cache:
            return self._ashare_block_cache[code]

        self._ensure_ashare_block_ready()
        if not self._ashare_block_ready:
            self._ashare_block_cache[code] = "其他"
            return "其他"

        try:
            from deva.naja.dictionary.tongdaxin_blocks import get_stock_blocks
            norm = code.replace("sh", "").replace("sz", "").replace("SZ", "").replace("SH", "")
            norm = norm.zfill(6) if norm.isdigit() else norm
            blocks = get_stock_blocks(norm)
            block_id = blocks[0] if blocks else "其他"
            self._ashare_block_cache[code] = block_id
            return block_id
        except Exception:
            self._ashare_block_cache[code] = "其他"
            return "其他"

    def _attach_ashare_block(self, records: List[Dict]) -> List[Dict]:
        """为A股记录补充题材字段"""
        for r in records:
            if not r.get("block"):
                r["block"] = self._get_ashare_block(r.get("code", ""))
        return records

    def _normalize_ashare_records(self, data_list: List[Dict]) -> List[Dict]:
        """标准化A股快照记录"""
        records = []
        for item in data_list:
            code = str(item.get("code", "")).strip()
            if not code:
                continue
            now = float(item.get("now", 0) or 0)
            close = float(item.get("close", 0) or 0)
            p_change = item.get("p_change")
            if p_change is None:
                p_change = (now - close) / close if close else 0.0
            try:
                p_change = float(p_change)
            except Exception:
                p_change = 0.0

            volume = float(item.get("volume", 0) or 0)
            amount = item.get("amount")
            if amount is None or amount == 0:
                # volume 是「手」（1手=100股），需要乘以100转换为股数，再乘以价格
                amount = volume * 100 * now
            try:
                amount = float(amount)
            except Exception:
                amount = 0.0

            records.append({
                "code": code,
                "name": item.get("name", code),
                "price": now,
                "change_pct": p_change,
                "p_change": p_change,
                "volume": volume,
                "amount": amount,
                "high": item.get("high", 0),
                "low": item.get("low", 0),
                "open": item.get("open", 0),
                "prev_close": close,
                "market": "A",
            })
        return records

    def _load_ashare_snapshots_for_day(self) -> tuple[list, str, str, bool]:
        """加载A股当日完整快照数据"""
        try:
            from deva import NB
            snapshot_db = NB('quant_snapshot_5min_window', key_mode='time')
            keys = list(snapshot_db.keys())
            if not keys:
                return [], "", "", True

            key_pairs = []
            for k in keys:
                try:
                    ts = float(k)
                except Exception:
                    continue
                key_pairs.append((ts, k))

            if not key_pairs:
                return [], "", "", True

            key_pairs.sort(key=lambda x: x[0])
            today = datetime.now().strftime('%Y-%m-%d')

            def _date_of(ts: float) -> str:
                return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')

            today_pairs = [p for p in key_pairs if _date_of(p[0]) == today]
            if today_pairs:
                day_pairs = today_pairs
                data_date = today
                stale = False
            else:
                data_date = _date_of(key_pairs[-1][0])
                day_pairs = [p for p in key_pairs if _date_of(p[0]) == data_date]
                stale = True

            if not day_pairs:
                return [], data_date, "", True

            snapshots = []
            for ts, key in day_pairs:
                data_list = snapshot_db.get(key)
                if not data_list or not isinstance(data_list, list):
                    continue
                records = self._normalize_ashare_records(data_list)
                records = self._filter_ashare_snapshot(records)
                records = self._attach_ashare_block(records)
                snapshots.append({
                    "ts": ts,
                    "time_str": datetime.fromtimestamp(ts).strftime('%H:%M'),
                    "records": records,
                })

            # 只保留盘前集合竞价到收盘区间（09:00-15:00）
            def _in_session(ts_val: float) -> bool:
                t = datetime.fromtimestamp(ts_val).time()
                return dtime(9, 0) <= t <= dtime(15, 0)

            session_snaps = [s for s in snapshots if _in_session(s["ts"])]

            if session_snaps:
                last_ts = session_snaps[-1]["ts"]
                last_time_str = datetime.fromtimestamp(last_ts).strftime('%Y-%m-%d %H:%M:%S')
                return session_snaps, data_date, last_time_str, stale

            # 若没有盘中快照，退回为空并标记数据异常
            return [], data_date, "", True
        except Exception:
            return [], "", "", True

    def _analyze_ashare_intraday(
        self,
        snapshots: List[Dict],
        top_blocks: List[str],
    ) -> tuple[List[Dict], List[Dict], List[Dict], List[Dict]]:
        """A股盘中动态分析：资金流向、突破、异动"""
        flow_timeline = []
        breakouts = []
        anomalies = []

        if not snapshots:
            return flow_timeline, breakouts, anomalies, []

        prev_block_amount = None
        breakout_seen = set()
        rolling_max = {}

        for snap in snapshots:
            records = snap.get("records", [])
            block_amount = {}
            for r in records:
                block = r.get("block", "其他")
                amount = r.get("amount", 0)
                block_amount[block] = block_amount.get(block, 0) + amount

                code = r.get("code", "")
                price = r.get("price", 0)
                if code and price > 0:
                    prev_max = rolling_max.get(code, price)
                    if code not in breakout_seen and price >= prev_max * 1.01:
                        breakouts.append({
                            "time": snap.get("time_str", ""),
                            "block": block,
                            "code": code,
                            "name": r.get("name", code),
                            "change": r.get("p_change", 0) * 100,
                        })
                        breakout_seen.add(code)
                    if price > prev_max:
                        rolling_max[code] = price

                change = abs(r.get("p_change", 0) * 100)
                if change >= 6:
                    anomalies.append({
                        "time": snap.get("time_str", ""),
                        "block": block,
                        "code": code,
                        "name": r.get("name", code),
                        "change": r.get("p_change", 0) * 100,
                    })

            if prev_block_amount is not None:
                deltas = {}
                for sec in set(list(prev_block_amount.keys()) + list(block_amount.keys())):
                    deltas[sec] = block_amount.get(sec, 0) - prev_block_amount.get(sec, 0)

                inflow = sorted([(s, v) for s, v in deltas.items() if v > 0], key=lambda x: x[1], reverse=True)[:3]
                outflow = sorted([(s, v) for s, v in deltas.items() if v < 0], key=lambda x: x[1])[:3]
                if inflow or outflow:
                    flow_timeline.append({
                        "time": snap.get("time_str", ""),
                        "inflow_blocks": [s for s, _ in inflow],
                        "outflow_blocks": [s for s, _ in outflow],
                    })

            prev_block_amount = block_amount

        # 只保留与Top3题材相关的突破/异动
        if top_blocks:
            breakouts = [b for b in breakouts if b.get("block") in top_blocks]
            anomalies = [a for a in anomalies if a.get("block") in top_blocks]

        return flow_timeline, breakouts, anomalies, snapshots

    def step1_full_market(self, force_refresh: bool = False) -> MarketOverview:
        """第一步：全市场横截面分析

        Args:
            force_refresh: 是否强制刷新（忽略缓存）
        """
        if not force_refresh and self.market_overview is not None:
            log.debug("[DailyReviewAnalyzer] 第一步已缓存，跳过")
            return self.market_overview

        self.all_stocks = self._fetch_market_data()

        self._normalize_change_pct(self.all_stocks)

        ashare_data = [s for s in self.all_stocks.values() if s.get("market") == "A"]
        usstock_data = [s for s in self.all_stocks.values() if s.get("market") == "US"]

        snapshots, data_date, last_time_str, data_stale = self._load_ashare_snapshots_for_day()
        if snapshots:
            ashare_effective = snapshots[-1].get("records", [])
        else:
            ashare_effective = self._filter_ashare_effective(ashare_data)
            data_date = datetime.now().strftime('%Y-%m-%d')
            last_time_str = ""
            data_stale = True

        ashare_count = len(ashare_data)
        ashare_effective_count = len(ashare_effective)
        usstock_count = len(usstock_data)

        ashare_report = self.analyzer.analyze(ashare_effective) if ashare_effective else None
        usstock_report = self.analyzer.analyze(usstock_data) if usstock_data else None

        # A股题材Top3与动态分析
        top_blocks = []
        block_stats = {}
        for r in ashare_effective:
            block = r.get("block", "其他")
            block_stats.setdefault(block, []).append(r)

        block_perf = []
        for blk, items in block_stats.items():
            changes = [i.get("p_change", 0) * 100 for i in items]
            avg_change = sum(changes) / len(changes) if changes else 0
            total_amount = sum([i.get("amount", 0) for i in items])
            block_perf.append({
                "block": blk,
                "avg_change": avg_change,
                "total_amount": total_amount,
                "items": items,
            })

        block_perf.sort(key=lambda x: x["avg_change"], reverse=True)
        top_blocks = [s["block"] for s in block_perf[:3]]

        flow_timeline, breakouts, anomalies, _ = self._analyze_ashare_intraday(snapshots, top_blocks)

        top_block_details = []
        for sec_info in block_perf[:3]:
            sec = sec_info["block"]
            items = sec_info["items"]
            leaders = sorted(items, key=lambda x: x.get("p_change", 0), reverse=True)[:2]
            leaders_fmt = [
                {"code": l.get("code", ""), "name": l.get("name", l.get("code", "")), "change": l.get("p_change", 0) * 100}
                for l in leaders
            ]

            last_flow = ""
            for ev in reversed(flow_timeline):
                if sec in ev.get("inflow_blocks", []):
                    last_flow = f"{ev.get('time','')} 流入"
                    break
                if sec in ev.get("outflow_blocks", []):
                    last_flow = f"{ev.get('time','')} 流出"
                    break

            sec_breakouts = [b for b in breakouts if b.get("block") == sec][:2]
            breakout_hint = ""
            if sec_breakouts:
                breakout_hint = ", ".join([f"{b.get('name','')}{b.get('change',0):+.1f}%@{b.get('time','')}" for b in sec_breakouts])

            sec_anomalies = [a for a in anomalies if a.get("block") == sec][:2]
            anomaly_hint = ""
            if sec_anomalies:
                anomaly_hint = ", ".join([f"{a.get('name','')}{a.get('change',0):+.1f}%@{a.get('time','')}" for a in sec_anomalies])

            top_block_details.append({
                "block": sec,
                "avg_change": sec_info["avg_change"],
                "flow": last_flow or "均衡",
                "leaders": leaders_fmt,
                "flow_hint": last_flow,
                "breakout_hint": breakout_hint,
                "anomaly_hint": anomaly_hint,
            })

        self.market_overview = MarketOverview(
            ashare_count=ashare_count,
            ashare_effective_count=ashare_effective_count,
            ashare_data_date=data_date,
            ashare_last_snapshot_time=last_time_str,
            ashare_data_stale=data_stale,
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
            ashare_top_blocks=top_block_details,
            ashare_flow_timeline=flow_timeline,
            ashare_breakouts=breakouts,
            ashare_anomalies=anomalies,
        )

        self._load_attention_state()
        self._save_to_cache()
        return self.market_overview

    def _load_attention_state(self):
        """从注意力系统加载注意力状态数据"""
        try:
            from deva.naja.market_hotspot.integration import get_market_hotspot_integration

            integration = get_market_hotspot_integration()
            if integration is None or integration.hotspot_system is None:
                return

            attention_system = integration.hotspot_system

            ashare_state = attention_system.get_cn_hotspot_state()
            us_state = attention_system.get_us_hotspot_state()

            self.market_overview.ashare_attention = ashare_state.get('attention', 0.0)
            self.market_overview.ashare_activity = ashare_state.get('activity', 0.0)

            symbol_weights = ashare_state.get('symbol_weights', {})
            if symbol_weights:
                sorted_stocks = sorted(symbol_weights.items(), key=lambda x: x[1], reverse=True)[:10]
                self.market_overview.ashare_top_attention_stocks = [
                    {'code': code, 'weight': weight}
                    for code, weight in sorted_stocks
                ]

            block_attention = ashare_state.get('block_attention', {})
            if block_attention:
                sorted_blocks = sorted(block_attention.items(), key=lambda x: x[1], reverse=True)[:5]
                self.market_overview.ashare_top_attention_blocks = [
                    {'block': block, 'attention': att}
                    for block, att in sorted_blocks
                ]

            self.market_overview.us_attention = us_state.get('global_attention', 0.0)
            self.market_overview.us_activity = us_state.get('activity', 0.0)

            us_symbol_weights = us_state.get('symbol_weights', {})
            if us_symbol_weights:
                sorted_us_stocks = sorted(us_symbol_weights.items(), key=lambda x: x[1], reverse=True)[:10]
                self.market_overview.us_top_attention_stocks = [
                    {'code': code.upper(), 'weight': weight}
                    for code, weight in sorted_us_stocks
                ]

            us_block_attention = us_state.get('block_attention', {})
            if us_block_attention:
                sorted_us_blocks = sorted(us_block_attention.items(), key=lambda x: x[1], reverse=True)[:5]
                self.market_overview.us_top_attention_blocks = [
                    {'block': block, 'attention': att}
                    for block, att in sorted_us_blocks
                ]

            log.info(f"[DailyReviewAnalyzer] 加载注意力状态: A股 attention={self.market_overview.ashare_attention:.3f}, 美股 attention={self.market_overview.us_attention:.3f}")
        except Exception as e:
            log.warning(f"[DailyReviewAnalyzer] 加载注意力状态失败: {e}")

    def step5_hotspot_shift_history(self, market: str = None, lookback_hours: int = 24) -> Dict[str, Any]:
        """
        第五步：获取历史热点切换数据（从持久化历史中查询）

        Args:
            market: 市场标识 ('CN' 或 'US')，None 表示所有市场
            lookback_hours: 回溯小时数

        Returns:
            包含历史热点切换信息的字典
        """
        try:
            from deva.naja.market_hotspot.tracking.history_tracker import get_history_tracker

            tracker = get_history_tracker()
            if tracker is None:
                return {'status': 'no_tracker'}

            cutoff_time = time.time() - (lookback_hours * 3600)

            block_events = []
            symbol_events = []
            snapshots_timeline = []

            for snapshot in tracker.snapshots:
                if snapshot.timestamp < cutoff_time:
                    continue

                market_str = snapshot.market_time_str.split()[0] if snapshot.market_time_str else ''
                if market == 'CN' and 'sh' in market_str.lower():
                    continue
                if market == 'US' and 'US' not in market_str and not any(x in str(snapshot.symbol_weights.keys()) for x in ['AAPL', 'NVDA', 'MSFT']):
                    continue

                snapshots_timeline.append({
                    'timestamp': snapshot.timestamp,
                    'time': snapshot.market_time_str,
                    'global_hotspot': snapshot.global_hotspot,
                    'top_blocks': dict(sorted(snapshot.block_weights.items(), key=lambda x: x[1], reverse=True)[:5]),
                    'top_symbols': dict(sorted(snapshot.symbol_weights.items(), key=lambda x: x[1], reverse=True)[:5]),
                })

            for event in tracker.block_hotspot_events_medium:
                if event.timestamp < cutoff_time:
                    continue
                block_events.append({
                    'timestamp': event.timestamp,
                    'time': event.market_time,
                    'date': event.market_date,
                    'block_id': event.block_id,
                    'block_name': event.block_name,
                    'event_type': event.event_type,
                    'weight_change': event.weight_change,
                    'change_percent': event.change_percent,
                    'description': event.description,
                })

            for change in tracker.changes:
                if change.timestamp < cutoff_time:
                    continue
                if change.item_type != 'symbol':
                    continue
                symbol_events.append({
                    'timestamp': change.timestamp,
                    'time': change.market_time,
                    'symbol': change.item_id,
                    'name': change.item_name,
                    'change_type': change.change_type,
                    'old_weight': change.old_weight,
                    'new_weight': change.new_weight,
                    'change_percent': change.change_percent,
                    'description': change.description,
                })

            block_events.sort(key=lambda x: x['timestamp'], reverse=True)
            symbol_events.sort(key=lambda x: x['timestamp'], reverse=True)
            snapshots_timeline.sort(key=lambda x: x['timestamp'])

            self.market_overview.hotspot_shift_timeline = snapshots_timeline
            self.market_overview.block_shift_events = block_events[:50]
            self.market_overview.symbol_shift_events = symbol_events[:50]

            return {
                'status': 'ok',
                'lookback_hours': lookback_hours,
                'snapshot_count': len(snapshots_timeline),
                'block_event_count': len(block_events),
                'symbol_event_count': len(symbol_events),
                'block_events': block_events[:20],
                'symbol_events': symbol_events[:20],
                'timeline': snapshots_timeline,
            }

        except Exception as e:
            log.warning(f"[DailyReviewAnalyzer] 获取热点切换历史失败: {e}")
            return {'status': 'error', 'error': str(e)}

    def step2_hot_narrative(self, force_refresh: bool = False) -> List[NarrativePerformance]:
        """第二步：热点叙事主题 + 持仓分析

        Args:
            force_refresh: 是否强制刷新
        """
        if not force_refresh and self.top_narratives:
            log.debug("[DailyReviewAnalyzer] 第二步已缓存，跳过")
            return self.top_narratives

        if not self.all_stocks:
            self.step1_full_market()

        self.narrative_performance = {}

        for narrative, industry_codes in NARRATIVE_INDUSTRY_MAP.items():
            block_changes = []
            for industry_code in industry_codes:
                for code_lower, info in US_STOCK_BLOCKS.items():
                    if info.get("industry_code") == industry_code:
                        code = code_lower.upper()
                        stock_data = self.all_stocks.get(code)
                        if stock_data:
                            change = stock_data.get("change_pct", 0) * 100
                            block_changes.append({
                                "code": code,
                                "name": stock_data.get("name", code),
                                "change": change,
                            })

            if block_changes:
                changes = [b["change"] for b in block_changes]
                avg_change = sum(changes) / len(changes)
                gainer_ratio = sum(1 for c in changes if c > 0) / len(changes)

                sorted_stocks = sorted(block_changes, key=lambda x: x["change"], reverse=True)
                top_stock = sorted_stocks[0] if sorted_stocks else None
                bottom_stock = sorted_stocks[-1] if len(sorted_stocks) > 1 else top_stock

                self.narrative_performance[narrative] = {
                    "avg_change": avg_change,
                    "gainer_ratio": gainer_ratio,
                    "stock_count": len(block_changes),
                    "stocks": block_changes,
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
                industry_info = US_STOCK_BLOCKS.get(pos.stock_code.lower(), {})
                narrative = industry_info.get("narrative", "")
                industry_code = industry_info.get("industry_code", "other")
                blocks = industry_info.get("blocks", [])
                block = ",".join(blocks) if blocks else "其他"

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
                    block=block,
                    narrative=narrative,
                    narrative_avg_change=narrative_avg,
                    relative_change=relative,
                    status=status,
                ))

        return self.positions

    def step3_tiandao_minxin(self) -> TiandaoMinxinAnalysis:
        """第三步：天道(价值) + 民心(市场叙事)信号分析（每次实时计算）"""
        log.info("[DailyReviewAnalyzer] 第三步：实时计算天道(价值)/民心(市场叙事)信号")
        summary = self.nt.get_value_market_summary()

        value_score = summary.get("value_score", 0.0)
        market_narrative_score = summary.get("market_narrative_score", 0.0)

        if value_score > 0.5 and market_narrative_score < 0.3:
            pattern = "🌟 最佳时机：价值信号强 + 市场叙事弱"
        elif value_score > 0.5 and market_narrative_score > 0.5:
            pattern = "📈 顺势持有：价值信号强 + 市场叙事强"
        elif value_score < 0.2 and market_narrative_score > 0.5:
            pattern = "⚠️ 警惕：价值信号弱 + 市场叙事强"
        elif value_score < 0.2 and market_narrative_score < 0.3:
            pattern = "❄️ 观望：价值信号弱 + 市场叙事弱"
        else:
            pattern = "➡️ 观察：信号不明显"

        value_signals = summary.get("signals", {}).get("value", {})
        market_signals = summary.get("signals", {}).get("market_narrative", {})

        value_hits = sum(len(v) for v in value_signals.values())
        market_hits = sum(len(v) for v in market_signals.values())

        value_changes = []
        for cat, kws in value_signals.items():
            if kws:
                value_changes.append(f"{cat}: {', '.join(kws[:3])}")

        market_changes = []
        for cat, kws in market_signals.items():
            if kws:
                market_changes.append(f"{cat}: {', '.join(kws[:3])}")

        if value_hits >= 3:
            value_summary_text = f"AI落地加速，{value_hits}个价值信号"
        elif value_hits >= 1:
            value_summary_text = f"存在{value_hits}个价值信号"
        else:
            value_summary_text = "无明显价值信号"

        if market_hits >= 3:
            market_summary_text = f"市场情绪高涨，{market_hits}个市场叙事信号"
        elif market_hits >= 1:
            market_summary_text = f"存在{market_hits}个市场叙事信号"
        else:
            market_summary_text = "市场情绪平稳"

        self.tiandao_minxin = TiandaoMinxinAnalysis(
            value_score=value_score,
            market_narrative_score=market_narrative_score,
            recommendation=summary.get("recommendation", "WATCH"),
            reason=summary.get("reason", ""),
            value_signals=value_signals,
            market_narrative_signals=market_signals,
            pattern=pattern,
            value_summary=value_summary_text,
            market_narrative_summary=market_summary_text,
            value_changes=value_changes,
            market_narrative_changes=market_changes,
        )

        return self.tiandao_minxin

    def step4_wisdom_perspective(self) -> List['WisdomPerspective']:
        """
        第四步：从知识库检索针对热门叙事的个人观点，并LLM生成洞察

        根据今天表现最强的叙事主题，检索知识库中对这些主题的看法，
        形成"用自己投资哲学审视今天市场"的复盘视角。
        """
        try:
            from deva.naja.knowledge.wisdom.wisdom_retriever import WisdomRetriever

            retriever = WisdomRetriever()
            perspectives = []

            if not self.top_narratives:
                return perspectives

            for nar in self.top_narratives[:5]:
                narrative = nar.narrative
                change = nar.avg_change

                snippets = retriever.search(narrative, limit=3)

                if snippets:
                    perspective = WisdomPerspective(
                        narrative=narrative,
                        change=change,
                        snippets=[{"title": s.title, "highlight": s.highlight} for s in snippets]
                    )
                    self._generate_wisdom_insight(perspective)
                    perspectives.append(perspective)

            self._wisdom_perspectives = perspectives
            return perspectives

        except ImportError:
            import logging
            log = logging.getLogger(__name__)
            log.warning("[DailyReviewAnalyzer] WisdomRetriever 不可用，跳过知识库观点检索")
            return []
        except Exception as e:
            import logging
            log = logging.getLogger(__name__)
            log.error(f"[DailyReviewAnalyzer] 知识库观点检索失败: {e}")
            return []

    def _generate_wisdom_insight(self, perspective: 'WisdomPerspective') -> None:
        """使用LLM根据知识库片段生成连贯洞察"""
        import logging
        log = logging.getLogger(__name__)

        try:
            import asyncio
            import concurrent.futures

            async def generate_async():
                from deva.llm import GPT
                from deva.naja.config import get_llm_config

                cfg = get_llm_config()
                gpt = GPT(model_type=cfg.get("model_type", "deepseek"))

                snippets_text = "\n".join([
                    f"- \"{WisdomPerspective.clean_html(s['title'])}\": {WisdomPerspective.clean_html(s['highlight'])}"
                    for s in perspective.snippets[:3]
                ])

                prompt = f"""你是一个投资者的私人顾问，正在结合自己过去的思考来审视今天的市场。

**主题**: {perspective.narrative}
**今日涨跌**: {perspective.change:+.1f}%

**你过去写过/收藏过相关文章的摘录**:
{snippets_text}

**任务**:
请结合你过去的思考，对今天"{perspective.narrative}"的表现({perspective.change:+.1f}%)发表一段连贯的、有态度的个人见解。
要求：
1. 100字左右
2. 语气像你自己在思考，有观点有态度
3. 不要简单复述摘录，要有自己的观点
4. 可以联系今天的涨跌谈看法

请直接输出你的见解，不要有"以下是..."之类的引导语："""

                response = await gpt.async_query(prompt)
                return response.strip() if response else ""

            def run_sync():
                try:
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(generate_async())
                    finally:
                        new_loop.close()
                except Exception as e:
                    log.error(f"[DailyReviewAnalyzer] LLM生成洞察失败: {e}")
                    return ""

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_sync)
                insight = future.result(timeout=30)

            if insight:
                perspective.insight = insight
                log.info(f"[DailyReviewAnalyzer] 为'{perspective.narrative}'生成洞察: {insight[:50]}...")
            else:
                log.warning(f"[DailyReviewAnalyzer] LLM未返回洞察")

        except Exception as e:
            log.error(f"[DailyReviewAnalyzer] 生成洞察异常: {e}")

    def run_full_analysis(self, force_refresh: bool = False) -> ReviewReport:
        """执行完整四步分析

        Args:
            force_refresh: 是否强制刷新（忽略缓存）
        """
        self.step1_full_market(force_refresh=force_refresh)
        self.step2_hot_narrative(force_refresh=force_refresh)
        self.step3_tiandao_minxin()

        risks = self._extract_risks()
        suggestions = self._generate_suggestions()

        # 收集美林时钟数据
        merrill_clock_signal = self._collect_merrill_clock_signal()

        # 收集跨市场流动性追踪数据
        liquidity_insights = self._collect_liquidity_insights()

        # 收集 LLM 反思
        llm_reflection = None
        try:
            import concurrent.futures
            def fetch():
                from deva.naja.cognition.insight import get_llm_reflection_engine
                engine = get_llm_reflection_engine()
                recent = engine.get_recent_reflections(limit=1)
                return recent[0] if recent else None
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(fetch)
                llm_reflection = future.result(timeout=30)
        except Exception:
            llm_reflection = None

        return ReviewReport(
            timestamp=time.time(),
            market_overview=self.market_overview,
            top_narratives=self.top_narratives,
            positions=self.positions,
            tiandao_minxin=self.tiandao_minxin,
            risks=risks,
            suggestions=suggestions,
            wisdom_perspectives=getattr(self, '_wisdom_perspectives', []),
            merrill_clock_signal=merrill_clock_signal,
            liquidity_insights=liquidity_insights,
            llm_reflection=llm_reflection,
        )

    def _collect_merrill_clock_signal(self) -> Optional[Dict[str, Any]]:
        """收集美林时钟信号"""
        try:
            from deva.naja.cognition.merrill_clock import get_merrill_clock_engine, MerrillClockPhase
            from deva.naja.cognition.merrill_clock.adapter import get_merrill_phase_display

            clock = get_merrill_clock_engine()
            signal = clock.get_current_signal()

            if not signal:
                return None

            phase_name = get_merrill_phase_display(signal.phase)

            # 经济数据摘要
            data_summary = {}
            if hasattr(signal, 'data_summary') and signal.data_summary:
                data_summary = signal.data_summary
            elif hasattr(signal, '_economic_data') and signal._economic_data:
                ed = signal._economic_data
                data_summary = {
                    'gdp_growth': ed.gdp_growth if hasattr(ed, 'gdp_growth') else None,
                    'pce_yoy': ed.pce_yoy if hasattr(ed, 'pce_yoy') else None,
                    'unemployment_rate': ed.unemployment_rate if hasattr(ed, 'unemployment_rate') else None,
                }

            return {
                'phase': signal.phase.value,
                'phase_name': phase_name,
                'confidence': signal.confidence,
                'growth_score': signal.growth_score,
                'inflation_score': signal.inflation_score,
                'asset_ranking': signal.asset_ranking,
                'data_summary': data_summary,
            }
        except Exception as e:
            import logging
            log = logging.getLogger(__name__)
            log.warning(f"[DailyReviewAnalyzer] 收集美林时钟信号失败: {e}")
            return None

    def _collect_liquidity_insights(self) -> List[Dict[str, Any]]:
        """收集跨市场流动性追踪数据"""
        try:
            from deva.naja.cognition.liquidity.liquidity_cognition import get_liquidity_cognition

            lc = get_liquidity_cognition()
            if not lc:
                return []

            # 获取最近的流动性洞察
            insights = lc.get_insights(limit=10)
            
            result = []
            for insight in insights:
                # GlobalMarketInsight 是 dataclass，需要转换属性
                if hasattr(insight, '__dict__'):
                    # dataclass 对象
                    result.append({
                        'source_market': getattr(insight, 'source_market', ''),
                        'narrative': getattr(insight, 'narrative', ''),
                        'target_markets': getattr(insight, 'target_markets', []),
                        'propagation_probability': getattr(insight, 'propagation_probability', 0.5),
                        'severity': getattr(insight, 'severity', 0.5),
                        'insight_type': getattr(insight, 'insight_type', 'unknown'),
                    })
                elif isinstance(insight, dict):
                    result.append({
                        'source_market': insight.get('source_market', ''),
                        'narrative': insight.get('narrative', ''),
                        'target_markets': insight.get('target_markets', []),
                        'propagation_probability': insight.get('propagation_probability', 0.5),
                        'severity': insight.get('severity', 0.5),
                        'insight_type': insight.get('insight_type', 'unknown'),
                    })
            return result
        except Exception as e:
            import logging
            log = logging.getLogger(__name__)
            log.warning(f"[DailyReviewAnalyzer] 收集流动性洞察失败: {e}")
            return []

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


def _save_review_to_history(report: ReviewReport):
    """保存复盘记录到历史"""
    try:
        from deva import NB
        nb = NB("naja_daily_review_history")
        history = nb.get("records") or []
        record = {
            "timestamp": report.timestamp,
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(report.timestamp)),
            "market_sentiment": report.market_overview.combined_sentiment if report.market_overview else "未知",
            "avg_change": report.market_overview.ashare_avg_change if report.market_overview else 0,
            "market_breadth": report.market_overview.ashare_breadth if report.market_overview else 0,
            "top_narrative": report.top_narratives[0].narrative if report.top_narratives else "无",
            "top_narrative_change": report.top_narratives[0].avg_change if report.top_narratives else 0,
            "positions_count": len(report.positions),
            "positions_summary": [
                {"name": p.name, "change": p.today_change, "status": p.status}
                for p in report.positions
            ],
            "value_score": report.tiandao_minxin.value_score if report.tiandao_minxin else 0,
            "market_narrative_score": report.tiandao_minxin.market_narrative_score if report.tiandao_minxin else 0,
            "markdown": report.to_markdown(),
        }
        history.insert(0, record)
        history = history[:30]
        nb["records"] = history
        return True
    except Exception as e:
        log.error(f"[DailyReview] 保存历史失败: {e}")
        return False


def get_review_history(limit: int = 5) -> list:
    """获取复盘历史记录"""
    try:
        from deva import NB
        nb = NB("naja_daily_review_history")
        history = nb.get("records") or []
        return history[:limit]
    except Exception:
        return []


def run_review_and_push(market: str = 'a_share') -> tuple[ReviewReport, bool]:
    """
    运行复盘并推送结果到 iMessage，同时保存历史记录

    Args:
        market: 'a_share' 或 'us_share'

    用于盘后定时任务
    """
    market_name = "A股" if market == 'a_share' else "美股"
    analyzer = DailyReviewAnalyzer()
    report = analyzer.run_full_analysis(force_refresh=True)

    _save_review_to_history(report)

    collector = None
    resonance_result = None

    try:
        from deva.naja.strategy.review_data_collector import get_review_data_collector
        from deva.naja.strategy.resonance_analyzer import get_resonance_analyzer

        collector = get_review_data_collector()
        resonance_analyzer = get_resonance_analyzer()

        data = collector.collect_all()
        resonance_result = resonance_analyzer.analyze(
            market_focus=data.get("market_focus", {}),
            news_focus=data.get("news_focus", {}),
            internal_changes=data.get("internal_changes", {}),
        )
    except Exception as e:
        log.warning(f"[DailyReview] 收集变化数据或共振分析失败: {e}")

    pushed_ok = False

    dtalk_msg = None
    imessage_text = None

    try:
        from deva.endpoints import Dtalk
        dtalk_msg = _build_change_driven_report(
            report,
            market=market,
            collector=collector,
            resonance_result=resonance_result,
        )
        dtalk_markdown = f"@md@{market_name}市场复盘报告|\n{dtalk_msg}"
        dtalk = Dtalk()
        dtalk.send(dtalk_markdown)
        pushed_ok = True
        log.info(f"[DailyReview] {market_name}复盘报告已推送到DTalk")
    except Exception as e:
        log.error(f"[DailyReview] 推送DTalk失败: {e}")

    try:
        if imessage_text is None:
            imessage_text = _build_change_driven_report(
                report,
                market=market,
                collector=collector,
                resonance_result=resonance_result,
            )
        sent = send_imessage("+8618626880688", imessage_text)
        if sent:
            log.info(f"[DailyReview] {market_name}复盘报告已推送到iMessage")
        else:
            log.warning(f"[DailyReview] {market_name}推送iMessage失败")
    except Exception as e:
        log.error(f"[DailyReview] {market_name}推送iMessage失败: {e}")

    return report, pushed_ok


def _build_change_driven_report(
    report: "ReviewReport",
    market: str = 'a_share',
    collector=None,
    resonance_result=None,
) -> str:
    """
    生成变化驱动的复盘报告

    结构：
    1. 今日变化（市场焦点、舆情焦点、外部变化）
    2. 共振分析
    3. 内部焦点变化
    4. 背景锚点（不变的）
    """
    from datetime import datetime as dt

    lines = []
    market_name = "A股" if market == 'a_share' else "美股"
    ts_str = dt.now().strftime("%Y-%m-%d %H:%M")

    lines.append(f"📊 {market_name}市场复盘报告 | {ts_str}")
    lines.append("")

    lines.append("🔥 【今日变化】")
    lines.append("")

    market_focus_data = {}
    news_focus_data = {}
    internal_changes_data = {}

    if collector:
        try:
            data = collector.collect_all()
            market_focus_data = data.get("market_focus", {})
            news_focus_data = data.get("news_focus", {})
            internal_changes_data = data.get("internal_changes", {})
        except Exception as e:
            log.warning(f"[DailyReview] 收集变化数据失败: {e}")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💰 市场焦点（行情）")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.extend(_format_market_focus(market_focus_data, report))
    lines.append("")

    lines.append("📰 舆情焦点（新闻）")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.extend(_format_news_focus(news_focus_data))
    lines.append("")

    external_changes = collector.collect_external_changes() if collector else {}
    if external_changes.get("has_changes"):
        lines.append("📦 外部变化")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.extend(_format_external_changes(external_changes))
        lines.append("")

    if resonance_result and resonance_result.get("status") == "ok":
        lines.append("⚡ 共振分析")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.extend(_format_resonance(resonance_result))
        lines.append("")

    if internal_changes_data.get("has_changes"):
        lines.append("📋 内部焦点变化")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.extend(_format_internal_changes(internal_changes_data))
        lines.append("")

    lines.append("📌 【背景锚点】")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.extend(_format_background_anchor(report))

    lines.append("")
    lines.append("─────────────────")
    lines.append("来自 Naja 自动复盘系统")

    return "\n".join(lines)


def _format_market_focus(market_focus: Dict, report: "ReviewReport") -> List[str]:
    """格式化市场焦点"""
    lines = []

    mo = report.market_overview
    if not mo:
        lines.append("  暂无数据")
        return lines

    lines.append("  📈 整体状态：")
    ashare_change = getattr(mo, "ashare_avg_change", 0)
    us_change = getattr(mo, "usstock_avg_change", 0)
    sentiment = getattr(mo, "combined_sentiment", "未知")
    lines.append(f"     A股：{'+' if ashare_change >= 0 else ''}{ashare_change:.1f}%（情绪：{sentiment}）")
    lines.append(f"     美股：{'+' if us_change >= 0 else ''}{us_change:.1f}%")
    lines.append("")

    narratives = getattr(report, "top_narratives", []) or []
    if narratives:
        lines.append("  🏭 行业热点：")
        for n in narratives[:3]:
            name = getattr(n, "narrative", str(n))
            change = getattr(n, "avg_change", 0)
            lines.append(f"     · {name}：{'+' if change >= 0 else ''}{change:.1f}%")
        lines.append("")

    return lines


def _format_news_focus(news_focus: Dict) -> List[str]:
    """格式化舆情焦点"""
    lines = []

    if news_focus.get("status") != "ok":
        lines.append("  暂无数据")
        return lines

    macro_news = news_focus.get("macro_news", [])
    if macro_news:
        lines.append("  🌍 宏观舆情：")
        for news in macro_news[:3]:
            title = news.get("title", "")[:40]
            lines.append(f"     · {title}")
        lines.append("")

    industry_news = news_focus.get("industry_news", [])
    if industry_news:
        lines.append("  📋 行业舆情：")
        for news in industry_news[:3]:
            title = news.get("title", "")[:40]
            lines.append(f"     · {title}")
        lines.append("")

    if not macro_news and not industry_news:
        lines.append("  暂无重要舆情")
        lines.append("")

    return lines


def _format_external_changes(external_changes: Dict) -> List[str]:
    """格式化外部变化"""
    lines = []

    changes = external_changes.get("changes", {})

    narrative_changes = changes.get("narrative_changes", [])
    if narrative_changes:
        for nc in narrative_changes[:3]:
            narrative = nc.get("narrative", "")
            change = nc.get("change", 0)
            direction = "↑" if change > 0 else "↓"
            lines.append(f"  · {narrative}：变化 {direction}{abs(change):.1f}%")

    sentiment_changes = changes.get("sentiment_changes", [])
    if sentiment_changes:
        for sc in sentiment_changes:
            yesterday = sc.get("yesterday", "")
            today = sc.get("today", "")
            lines.append(f"  · 市场情绪：{yesterday} → {today}")

    if not narrative_changes and not sentiment_changes:
        lines.append("  无显著外部变化")

    lines.append("")
    return lines


def _format_internal_changes(internal_changes: Dict) -> List[str]:
    """格式化内部变化"""
    lines = []

    trade_changes = internal_changes.get("trade_changes", [])
    if trade_changes:
        lines.append("  · 交易变动：")
        for tc in trade_changes[:3]:
            action = tc.get("action", "")
            symbol = tc.get("symbol", "")
            qty = tc.get("quantity", 0)
            lines.append(f"     {action} {symbol} {qty}手")

    pain_points = internal_changes.get("pain_point_changes", [])
    if pain_points:
        lines.append("  · 痛点挖掘：")
        for pp in pain_points[:2]:
            pp_id = pp.get("id", str(pp))[:30]
            lines.append(f"     发现「{pp_id}」")

    knowledge_changes = internal_changes.get("knowledge_changes", [])
    if knowledge_changes:
        lines.append("  · 知识学习：")
        for kc in knowledge_changes:
            kc_type = kc.get("type", "")
            items = kc.get("items", [])
            for item in items[:2]:
                if kc_type == "new":
                    lines.append(f"     新增知识：{item.get('cause', '')[:30]}")
                elif kc_type == "promoted":
                    lines.append(f"     知识上岗：{item.get('knowledge', '')[:30]}")

    if not trade_changes and not pain_points and not knowledge_changes:
        lines.append("  无内部变化")

    lines.append("")
    return lines


def _format_resonance(resonance_result: Dict) -> List[str]:
    """格式化共振分析"""
    lines = []

    resonances = resonance_result.get("resonances", {})
    for key, res in resonances.items():
        if res.get("resonance"):
            desc = res.get("description", "")
            if desc:
                lines.append(f"  {desc}")

    conclusion = resonance_result.get("conclusion", "")
    if conclusion:
        lines.append(f"  💡 结论：{conclusion}")

    lines.append("")
    return lines


def _format_background_anchor(report: "ReviewReport") -> List[str]:
    """格式化背景锚点"""
    lines = []

    if hasattr(report, "merrill_clock_signal") and report.merrill_clock_signal:
        mc = report.merrill_clock_signal
        phase = mc.get("phase_name", mc.get("phase", "未知"))
        confidence = mc.get("confidence", 0)
        lines.append(f"  · 美林时钟：{phase}（置信度 {confidence:.0%}，未变）")

    positions = getattr(report, "positions", None)
    if positions:
        position_count = len(positions) if isinstance(positions, (list, dict)) else 0
        lines.append(f"  · 当前持仓：{position_count} 只股票")

    if not lines:
        lines.append("  暂无背景数据")

    return lines


def _build_weixin_replay_text(report: "ReviewReport", market: str = 'a_share') -> str:
    """将复盘报告转换为微信纯文字格式（无 Markdown）

    Args:
        report: 复盘报告
        market: 'a_share' 或 'us_share'
    """
    from datetime import datetime as dt
    lines = []

    market_name = "A股" if market == 'a_share' else "美股"

    # 标题和时间
    ts_str = dt.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"📊 {market_name}市场复盘报告 | {ts_str}")
    lines.append("")

    # 美林时钟
    if hasattr(report, "merrill_clock_signal") and report.merrill_clock_signal:
        mc = report.merrill_clock_signal
        phase = mc.get("phase_name", mc.get("phase", "未知"))
        confidence = mc.get("confidence", 0)
        asset = " > ".join(mc.get("asset_ranking", [])) if mc.get("asset_ranking") else "无"
        lines.append(f"🌡️ 美林时钟：{phase}（置信度 {confidence:.0%}）")
        lines.append(f"   资产优先级：{asset}")
        lines.append("")

    # 市场概况
    mo = report.market_overview
    if mo:
        lines.append(f"🌍 市场概况")
        sentiment = getattr(mo, "combined_sentiment", getattr(mo, "market_sentiment", "未知"))
        lines.append(f"   整体情绪：{sentiment}")
        lines.append("")

    # 叙事洞察（用 top_narratives，ReviewReport 没有 narrative_insights 字段）
    if report.top_narratives:
        lines.append(f"📖 主要叙事：")
        for ni in report.top_narratives[:3]:
            name = getattr(ni, "narrative", str(ni))
            change = getattr(ni, "avg_change", 0)
            change_str = f"{change:+.1f}%" if change else ""
            lines.append(f"   · {name} {change_str}")
        lines.append("")

    # LLM 反思摘要
    if report.llm_reflection:
        theme = report.llm_reflection.get("theme", "")
        summary = report.llm_reflection.get("summary", "")
        if isinstance(summary, list):
            summary = "；".join(str(s) for s in summary[:2])
        if theme:
            lines.append(f"🤖 AI 反思：{theme}")
        if summary:
            summary_short = str(summary)[:200]
            lines.append(f"   {summary_short}{'...' if len(str(summary)) > 200 else ''}")
        lines.append("")

    # 跨市场流动性
    if hasattr(report, "liquidity_insights") and report.liquidity_insights:
        lines.append(f"💧 流动性信号：")
        for li in report.liquidity_insights[:2]:
            if isinstance(li, dict):
                narrative = li.get("narrative", li.get("theme", ""))
            else:
                narrative = str(li)
            lines.append(f"   · {narrative}")
        lines.append("")

    lines.append("─────────────────")
    lines.append("来自 Naja 自动复盘系统")

    return "\n".join(lines)


def run_review_no_push() -> ReviewReport:
    """
    运行复盘但不推送（用于UI展示）
    """
    analyzer = DailyReviewAnalyzer()
    report = analyzer.run_full_analysis()
    _save_review_to_history(report)
    return report


if __name__ == "__main__":
    analyzer = DailyReviewAnalyzer()
    report = analyzer.run_full_analysis()
    log.info(report.to_markdown())
