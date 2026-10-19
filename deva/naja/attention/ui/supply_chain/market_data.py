"""供应链 UI - 实时行情与估值

❗「加载中」不是状态，是借口
═══════════════════════════════════════════════════════════════════════════
这两个函数以前在拿不到数据时一律写「实时行情加载中...」/「估值分析加载中...」。
问题是它会**永远**这么显示：东方财富被代理拒了、估值引擎导入断了，页面都只是
温和地说「加载中」，看不出是数据源挂了还是代码挂了。

合法的空比异常更危险。所以现在：拿不到数据时必须把**原因**写上去。
"""

from typing import List, Dict, Tuple
from datetime import datetime
import html as _html

from pywebio.output import (
    put_html, put_row, put_column, put_text, put_button, put_table,
    put_scope, use_scope, clear_scope
)
from pywebio.session import run_js
import math

def _source_status_banner(diag: Dict) -> str:
    """数据来源状态条：有几只拿不到、为什么拿不到。

    全成功时不占版面（返回空串）；只要有失败就必须上屏，且要写真实原因。
    """
    if not diag:
        return ""

    failed_count = diag.get("failed_count", 0)
    if failed_count <= 0:
        return ""

    by_reason: Dict[str, int] = {}
    for reason in diag.get("failed", {}).values():
        key = str(reason).split("：")[0]
        by_reason[key] = by_reason.get(key, 0) + 1

    reasons = "、".join(f"{k} {v} 只" for k, v in sorted(by_reason.items(), key=lambda x: -x[1]))
    detail = ""
    for src, err in (diag.get("source_errors") or {}).items():
        detail += (
            f'<div style="font-size:10px;color:#64748b;margin-top:3px;">'
            f'{_html.escape(str(src))}: {_html.escape(str(err)[:120])}</div>'
        )

    return (
        '<div style="background:rgba(239,68,68,0.12);border-left:3px solid #ef4444;'
        'border-radius:6px;padding:8px 10px;margin-bottom:12px;">'
        f'<div style="font-size:11px;color:#fca5a5;">⚠ {failed_count} 只股票取不到行情 —— {_html.escape(reasons)}</div>'
        f'{detail}'
        "</div>"
    )


def _render_realtime_market_data() -> str:
    """渲染实时市场数据部分"""
    try:
        from deva.naja.bandit import get_fundamental_data_fetcher

        fetcher = get_fundamental_data_fetcher()
        fundamentals = fetcher.get_supply_chain_fundamentals()

        # ❗诊断必须在抓取之后取，否则负缓存还没记上，看不出失败原因
        try:
            diag = fetcher.get_fetch_diagnostics()
        except Exception:
            diag = {}

        if not fundamentals:
            # 一只都拿不到：必须说清楚是源挂了，不能说「加载中」
            src_err = "；".join(
                f"{k}: {str(v)[:100]}" for k, v in (diag.get("source_errors") or {}).items()
            )
            return (
                '<div style="background:#1e293b;border-radius:12px;padding:20px;margin:12px 0;">'
                '<div style="font-size:14px;color:#fca5a5;margin-bottom:6px;">'
                "行情源不可达 —— 全部股票都取不到数据</div>"
                + (
                    f'<div style="font-size:11px;color:#64748b;">{_html.escape(src_err)}</div>'
                    if src_err else
                    '<div style="font-size:11px;color:#64748b;">未采集到任何数据源错误，检查抓取器是否被禁用</div>'
                )
                + "</div>"
            )

        stocks_html = ""
        sorted_stocks = sorted(
            fundamentals.items(),
            key=lambda x: abs(x[1].change_pct) if x[1].change_pct else 0,
            reverse=True
        )

        for code, fundamental in sorted_stocks[:12]:
            if not fundamental.is_valid:
                continue

            change_color = "#22c55e" if fundamental.change_pct >= 0 else "#ef4444"
            change_symbol = "+" if fundamental.change_pct >= 0 else ""

            market_icon = "🇺🇸" if fundamental.market.value == "US" else "🇨🇳"

            pe_display = f"PE: {fundamental.pe_ratio:.1f}" if fundamental.pe_ratio > 0 else "PE: N/A"

            stocks_html += f"""
            <div style="background: rgba(255,255,255,0.03); border-radius: 6px; padding: 10px; margin-bottom: 6px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span style="color: #f1f5f9; font-size: 12px; font-weight: 500;">{market_icon} {fundamental.stock_name}</span>
                        <span style="color: #64748b; font-size: 10px; margin-left: 6px;">{fundamental.stock_code}</span>
                    </div>
                    <div style="text-align: right;">
                        <span style="color: #f1f5f9; font-size: 13px; font-weight: 500;">${fundamental.current_price:.2f}</span>
                        <span style="color: {change_color}; font-size: 11px; margin-left: 6px;">{change_symbol}{fundamental.change_pct:.2f}%</span>
                    </div>
                </div>
                <div style="display: flex; gap: 12px; margin-top: 6px; font-size: 10px; color: #64748b;">
                    <span>{pe_display}</span>
                    <span>市值: {fundamental.market_cap_str if fundamental.market_cap_str else 'N/A'}</span>
                </div>
            </div>"""

        if not stocks_html:
            return (
                '<div style="background:#1e293b;border-radius:12px;padding:20px;margin:12px 0;">'
                '<div style="font-size:14px;color:#fca5a5;">行情数据全部无效（价格为 0）</div>'
                + _source_status_banner(diag)
                + "</div>"
            )

        total_tried = diag.get("total", len(fundamentals))
        ok_count = diag.get("ok", len(fundamentals))
        scope = (
            f"可取 {ok_count}/{total_tried} 只"
            if total_tried and ok_count != total_tried
            else f"共 {len(fundamentals)} 只"
        )

        return f"""
        <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 12px; padding: 20px; margin: 12px 0;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <h2 style="margin: 0; color: #f1f5f9; font-size: 16px;">📊 实时市场行情</h2>
                <div style="font-size: 11px; color: #64748b;">
                    {scope} | 数据来源: 新浪(美股)/东方财富(A股)
                </div>
            </div>
            {_source_status_banner(diag)}

            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px;">
                <div style="max-height: 400px; overflow-y: auto;">
                    {stocks_html}
                </div>
                <div>
                    <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">📈 涨幅榜</div>
                    <div style="max-height: 180px; overflow-y: auto;">
                        {''.join([f'''
                        <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                            <span style="color: #f1f5f9; font-size: 11px;">{f"{'🇺🇸' if f.market.value == 'US' else '🇨🇳'} {f.stock_name}"}</span>
                            <span style="color: #22c55e; font-size: 11px;">+{f.change_pct:.2f}%</span>
                        </div>''' for _, f in sorted(fundamentals.items(), key=lambda x: x[1].change_pct if x[1].change_pct else 0, reverse=True)[:6] if f.is_valid and f.change_pct > 0])}
                    </div>

                    <div style="font-size: 12px; color: #94a3b8; margin: 12px 0 8px 0;">📉 跌幅榜</div>
                    <div style="max-height: 180px; overflow-y: auto;">
                        {''.join([f'''
                        <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                            <span style="color: #f1f5f9; font-size: 11px;">{f"{'🇺🇸' if f.market.value == 'US' else '🇨🇳'} {f.stock_name}"}</span>
                            <span style="color: #ef4444; font-size: 11px;">{f.change_pct:.2f}%</span>
                        </div>''' for _, f in sorted(fundamentals.items(), key=lambda x: x[1].change_pct if x[1].change_pct else 0)[:6] if f.is_valid and f.change_pct < 0])}
                    </div>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        return f"""
        <div style="background: #1e293b; border-radius: 12px; padding: 20px; margin: 12px 0;">
            <div style="font-size: 13px; color: #fca5a5;">实时行情渲染失败</div>
            <div style="font-size: 11px; color: #64748b; margin-top: 4px;">{type(e).__name__}: {_html.escape(str(e)[:160])}</div>
        </div>
        """


def _render_valuation_analysis() -> str:
    """渲染估值分析部分"""
    try:
        from deva.naja.bandit import get_supply_chain_valuation_engine
        engine = get_supply_chain_valuation_engine()
        summary = engine.get_valuation_summary()

        undervalued_html = ""
        for item in summary.get('top_undervalued', []):
            level_color = "#22c55e" if "严重" in item.get('valuation_level', '') else "#4ade80"
            upside = item.get('upside', 0)
            undervalued_html += f"""
            <div style="background: rgba(34, 197, 94, 0.1); border-radius: 8px; padding: 12px; margin-bottom: 8px; border-left: 3px solid #22c55e;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span style="color: #f1f5f9; font-size: 13px; font-weight: 500;">{item.get('stock_name', '')}</span>
                        <span style="color: #64748b; font-size: 11px; margin-left: 8px;">{item.get('stock_code', '')}</span>
                    </div>
                    <span style="background: {level_color}; padding: 2px 8px; border-radius: 12px; font-size: 10px; color: white;">
                        {item.get('valuation_level', '')}
                    </span>
                </div>
                <div style="display: flex; gap: 16px; margin-top: 8px; font-size: 11px; color: #94a3b8;">
                    <span>估值: {item.get('valuation_score', 0):.1f}</span>
                    <span>基本面: {item.get('fundamental_score', 0):.1f}</span>
                    <span>供应链: {item.get('supply_chain_score', 0):.1f}</span>
                    <span>叙事: {item.get('narrative_score', 0):.1f}</span>
                </div>
                <div style="margin-top: 6px; font-size: 12px; color: #22c55e;">
                    📈 潜在上涨: +{upside}%
                </div>
                <div style="font-size: 11px; color: #64748b; margin-top: 4px;">
                    {item.get('recommendation', '')}
                </div>
            </div>"""

        overvalued_html = ""
        for item in summary.get('top_overvalued', []):
            level_color = "#ef4444" if "严重" in item.get('valuation_level', '') else "#f87171"
            upside = item.get('upside', 0)
            overvalued_html += f"""
            <div style="background: rgba(239, 68, 68, 0.1); border-radius: 8px; padding: 12px; margin-bottom: 8px; border-left: 3px solid #ef4444;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span style="color: #f1f5f9; font-size: 13px; font-weight: 500;">{item.get('stock_name', '')}</span>
                        <span style="color: #64748b; font-size: 11px; margin-left: 8px;">{item.get('stock_code', '')}</span>
                    </div>
                    <span style="background: {level_color}; padding: 2px 8px; border-radius: 12px; font-size: 10px; color: white;">
                        {item.get('valuation_level', '')}
                    </span>
                </div>
                <div style="display: flex; gap: 16px; margin-top: 8px; font-size: 11px; color: #94a3b8;">
                    <span>估值: {item.get('valuation_score', 0):.1f}</span>
                    <span>基本面: {item.get('fundamental_score', 0):.1f}</span>
                    <span>供应链: {item.get('supply_chain_score', 0):.1f}</span>
                    <span>叙事: {item.get('narrative_score', 0):.1f}</span>
                </div>
                <div style="margin-top: 6px; font-size: 12px; color: #ef4444;">
                    📉 潜在下跌: {upside}%
                </div>
                <div style="font-size: 11px; color: #64748b; margin-top: 4px;">
                    {item.get('recommendation', '')}
                </div>
            </div>"""

        if not undervalued_html and not overvalued_html:
            # 不是「正在计算」，是这批股票里没有落在低估/高估区间的
            undervalued_html = (
                '<div style="color:#64748b;font-size:12px;text-align:center;padding:20px;">'
                "当前无标的落入低估(&lt;60)或高估(&gt;70)区间 —— 共评估 "
                f"{summary.get('total_stocks', 0)} 只</div>"
            )

        return f"""
        <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 12px; padding: 20px; margin: 12px 0;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <h2 style="margin: 0; color: #f1f5f9; font-size: 16px;">📊 综合估值分析</h2>
                <div style="font-size: 11px; color: #64748b;">
                    {summary.get('total_stocks', 0)} 只股票 |低估: {summary.get('undervalued_count', 0)} |合理: {summary.get('fair_count', 0)} |高估: {summary.get('overvalued_count', 0)}
                </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                <div>
                    <div style="font-size: 12px; color: #22c55e; margin-bottom: 8px; font-weight: 500;">
                        🟢 低估机会 (综合评分 &lt; 60)
                    </div>
                    {undervalued_html}
                </div>
                <div>
                    <div style="font-size: 12px; color: #ef4444; margin-bottom: 8px; font-weight: 500;">
                        🔴 高估风险 (综合评分 &gt; 70)
                    </div>
                    {overvalued_html}
                </div>
            </div>

            <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.1);">
                <div style="font-size: 10px; color: #64748b;">
                    💡 估值模型说明: 综合考虑基本面(35%)、供应链位置(25%)、叙事热度(25%)、动量(15%)
                </div>
                <div style="font-size: 10px; color: #64748b; margin-top: 4px;">
                    📅 上次更新: {summary.get('last_update', '从未')}
                </div>
            </div>
        </div>
        """
    except Exception as e:
        # ❗导入断裂就靠这行暴露 —— 以前写「加载中」，估值面板死了半年没人发现
        return f"""
        <div style="background: #1e293b; border-radius: 12px; padding: 20px; margin: 12px 0;">
            <div style="font-size: 13px; color: #fca5a5;">估值分析不可用</div>
            <div style="font-size: 11px; color: #64748b; margin-top: 4px;">{type(e).__name__}: {_html.escape(str(e)[:160])}</div>
        </div>
        """


