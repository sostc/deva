"""供应链叙事 UI 组件

在认知系统和注意力系统中展示供应链知识图谱和叙事联动
"""

from typing import List, Dict, Tuple
from datetime import datetime

from pywebio.output import (
    put_html, put_row, put_column, put_text, put_button, put_table,
    put_scope, use_scope, clear_scope
)
from pywebio.session import run_js


def render_supply_chain_risk_card(risk_level: str = "LOW", narrative_risk: float = 0.5) -> dict:
    """渲染供应链风险状态卡片"""
    color_map = {
        "HIGH": "#dc2626",
        "MEDIUM": "#ca8a04",
        "LOW": "#22c55e",
        "unknown": "#64748b"
    }

    emoji_map = {
        "HIGH": "🚨",
        "MEDIUM": "⚠️",
        "LOW": "✅",
        "unknown": "❓"
    }

    color = color_map.get(risk_level, "#64748b")
    emoji = emoji_map.get(risk_level, "❓")

    return {
        "emoji": emoji,
        "risk_level": risk_level,
        "narrative_risk": narrative_risk,
        "color": color
    }


def render_narrative_supply_chain_panel() -> None:
    """渲染叙事供应链联动面板"""
    from deva.naja.cognition import get_supply_chain_linker
    from deva.naja.attention.kernel.manas_engine import ManasEngine

    linker = get_supply_chain_linker()

    hot_narratives = linker.get_hot_narratives(10)
    recent_events = linker.get_recent_events(5)
    summary = linker.get_supply_chain_summary()

    html_parts = []
    html_parts.append("""
    <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 12px; padding: 16px; margin: 8px 0;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
            <h3 style="margin: 0; color: #f1f5f9; font-size: 16px;">🔗 叙事-供应链联动</h3>
            <span style="background: #3b82f6; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px;">""")
    html_parts.append(f"{len(linker._narrative_stock_link)} 个叙事映射")
    html_parts.append("""</span>
        </div>
    """)

    html_parts.append("""
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px;">
            <div style="background: rgba(59, 130, 246, 0.1); border-radius: 8px; padding: 12px; text-align: center;">
                <div style="font-size: 24px; font-weight: bold; color: #3b82f6;">""")
    html_parts.append(f"{len(linker._stock_narrative_link)}")
    html_parts.append("""</div>
                <div style="font-size: 12px; color: #94a3b8;">映射股票</div>
            </div>
            <div style="background: rgba(239, 68, 68, 0.1); border-radius: 8px; padding: 12px; text-align: center;">
                <div style="font-size: 24px; font-weight: bold; color: #ef4444;">""")
    html_parts.append(f"{len(recent_events)}")
    html_parts.append("""</div>
                <div style="font-size: 12px; color: #94a3b8;">风险事件</div>
            </div>
            <div style="background: rgba(34, 197, 94, 0.1); border-radius: 8px; padding: 12px; text-align: center;">
                <div style="font-size: 24px; font-weight: bold; color: #22c55e;">""")
    html_parts.append(f"{summary['recent_events_count']}")
    html_parts.append("""</div>
                <div style="font-size: 12px; color: #94a3b8;">总事件</div>
            </div>
        </div>
    """)

    if hot_narratives:
        html_parts.append("""
        <div style="margin-bottom: 16px;">
            <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">🔥 最热叙事</div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px;">
            """)
        for narrative, importance in hot_narratives[:6]:
            intensity = min(1.0, importance / 3.0)
            bg_color = f"rgba(239, 68, 68, {0.3 + intensity * 0.7})"
            html_parts.append(f"""
                <span style="background: {bg_color}; padding: 4px 10px; border-radius: 16px; font-size: 12px; color: white;">
                    {narrative} ({importance:.1f})
                </span>
            """)
        html_parts.append("""
            </div>
        </div>
        """)

    if recent_events:
        html_parts.append("""
        <div>
            <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">⚠️ 最近风险事件</div>
            <div style="max-height: 150px; overflow-y: auto;">
            """)
        for event in recent_events[-5:]:
            dt = datetime.fromtimestamp(event.timestamp)
            time_str = dt.strftime("%m-%d %H:%M")
            risk_color = "#ef4444" if event.risk_level.value in ["high", "critical"] else "#ca8a04"
            html_parts.append(f"""
                <div style="background: rgba(255,255,255,0.05); border-radius: 6px; padding: 8px; margin-bottom: 6px; border-left: 3px solid {risk_color};">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                        <span style="color: #f1f5f9; font-size: 13px;">{event.description}</span>
                        <span style="color: #94a3b8; font-size: 11px;">{time_str}</span>
                    </div>
                    <div style="font-size: 11px; color: #64748b;">
                        关联: {', '.join(event.narratives[:3])}
                    </div>
                </div>
            """)
        html_parts.append("""
            </div>
        </div>
        """)

    html_parts.append("</div>")

    put_html("".join(html_parts))


def render_supply_chain_narrative_detail(narrative: str = None) -> None:
    """渲染特定叙事的供应链详情"""
    from deva.naja.cognition import get_supply_chain_linker

    linker = get_supply_chain_linker()

    if narrative:
        summary = linker.get_supply_chain_for_narrative(narrative)
        stocks = linker.get_stocks_by_narrative(narrative)
    else:
        summary = linker.get_supply_chain_summary()
        stocks = list(linker._stock_narrative_link.keys())
        narrative = "全部叙事"

    html_parts = []
    html_parts.append(f"""
    <div style="background: #1e293b; border-radius: 12px; padding: 16px; margin: 8px 0;">
        <h4 style="margin: 0 0 16px 0; color: #f1f5f9; font-size: 14px;">
            📊 供应链分析: {narrative}
        </h4>
    """)

    if 'importance' in summary:
        html_parts.append(f"""
        <div style="display: flex; gap: 16px; margin-bottom: 16px;">
            <div style="flex: 1; background: rgba(59, 130, 246, 0.1); border-radius: 8px; padding: 12px;">
                <div style="font-size: 20px; font-weight: bold; color: #3b82f6;">{summary['importance']:.2f}</div>
                <div style="font-size: 11px; color: #94a3b8;">叙事重要性</div>
            </div>
            <div style="flex: 1; background: rgba(239, 68, 68, 0.1); border-radius: 8px; padding: 12px;">
                <div style="font-size: 20px; font-weight: bold; color: #ef4444;">{summary['total_risk']}</div>
                <div style="font-size: 11px; color: #94a3b8;">风险等级</div>
            </div>
            <div style="flex: 1; background: rgba(34, 197, 94, 0.1); border-radius: 8px; padding: 12px;">
                <div style="font-size: 20px; font-weight: bold; color: #22c55e;">{len(stocks)}</div>
                <div style="font-size: 11px; color: #94a3b8;">关联股票</div>
            </div>
        </div>
        """)

    if stocks:
        html_parts.append("""
        <div style="margin-bottom: 16px;">
            <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">💼 核心股票</div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px;">
            """)
        for code in stocks[:12]:
            node = linker._graph.get_stock_node(code)
            if node:
                market_icon = "🇨🇳" if node.metadata.get("market") == "A" else "🇺🇸"
                html_parts.append(f"""
                    <span style="background: rgba(255,255,255,0.1); padding: 4px 10px; border-radius: 16px; font-size: 12px; color: #e2e8f0;">
                        {market_icon} {node.name}({node.stock_code})
                    </span>
                """)
        html_parts.append("""
            </div>
        </div>
        """)

    if summary.get('upstream_stocks'):
        html_parts.append("""
        <div style="margin-bottom: 16px;">
            <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">🏭 上游供应商</div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px;">
            """)
        for code in summary['upstream_stocks'][:8]:
            node = linker._graph.get_stock_node(code)
            if node:
                html_parts.append(f"""
                    <span style="background: rgba(251, 146, 60, 0.2); padding: 4px 10px; border-radius: 16px; font-size: 12px; color: #fb923c;">
                        ↑ {node.name}
                    </span>
                """)
        html_parts.append("""
            </div>
        </div>
        """)

    if summary.get('downstream_stocks'):
        html_parts.append("""
        <div>
            <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">💰 下游客户</div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px;">
            """)
        for code in summary['downstream_stocks'][:8]:
            node = linker._graph.get_stock_node(code)
            if node:
                html_parts.append(f"""
                    <span style="background: rgba(34, 197, 94, 0.2); padding: 4px 10px; border-radius: 16px; font-size: 12px; color: #4ade80;">
                        ↓ {node.name}
                    </span>
                """)
        html_parts.append("""
            </div>
        </div>
        """)

    html_parts.append("</div>")

    put_html("".join(html_parts))


def render_supply_chain_graph_mini(stock_code: str = None) -> None:
    """渲染供应链知识图谱迷你视图"""
    from deva.naja.bandit import get_supply_chain_graph

    graph = get_supply_chain_graph()

    if stock_code:
        text_viz = graph.visualize_supply_chain(stock_code, max_depth=2)
    else:
        text_viz = graph.visualize_supply_chain('nvda', max_depth=2)

    html = f"""
    <div style="background: #0f172a; border-radius: 12px; padding: 16px; margin: 8px 0; font-family: monospace; font-size: 12px;">
        <pre style="color: #94a3b8; margin: 0; white-space: pre-wrap; max-height: 400px; overflow-y: auto;">{text_viz}</pre>
    </div>
    """

    put_html(html)


def render_supply_chain_knowledge_graph_page() -> None:
    """渲染完整的供应链知识图谱页面"""
    from deva.naja.bandit import get_supply_chain_graph

    graph = get_supply_chain_graph()

    html_parts = []

    html_parts.append("""
    <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 12px; padding: 20px; margin: 12px 0;">
        <h2 style="margin: 0 0 20px 0; color: #f1f5f9; font-size: 18px;">🔗 AI/芯片 产业链知识图谱</h2>

        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px;">
            <div style="background: rgba(59, 130, 246, 0.1); border-radius: 8px; padding: 16px; text-align: center;">
                <div style="font-size: 28px; font-weight: bold; color: #3b82f6;">""")
    html_parts.append(f"{len(graph._nodes)}")
    html_parts.append("""</div>
                <div style="font-size: 12px; color: #94a3b8;">总节点</div>
            </div>
            <div style="background: rgba(59, 130, 246, 0.1); border-radius: 8px; padding: 16px; text-align: center;">
                <div style="font-size: 28px; font-weight: bold; color: #3b82f6;">""")
    html_parts.append(f"{len(graph._edges)}")
    html_parts.append("""</div>
                <div style="font-size: 12px; color: #94a3b8;">关系边</div>
            </div>
            <div style="background: rgba(239, 68, 68, 0.1); border-radius: 8px; padding: 16px; text-align: center;">
                <div style="font-size: 28px; font-weight: bold; color: #ef4444;">""")

    a_share_count = len(graph.get_all_a_share_stocks())
    html_parts.append(f"{a_share_count}")
    html_parts.append("""</div>
                <div style="font-size: 12px; color: #94a3b8;">A 股公司</div>
            </div>
            <div style="background: rgba(34, 197, 94, 0.1); border-radius: 8px; padding: 16px; text-align: center;">
                <div style="font-size: 28px; font-weight: bold; color: #22c55e;">""")

    us_count = len(graph.get_all_us_stocks())
    html_parts.append(f"{us_count}")
    html_parts.append("""</div>
                <div style="font-size: 12px; color: #94a3b8;">美股公司</div>
            </div>
        </div>

        <h3 style="margin: 20px 0 12px 0; color: #f1f5f9; font-size: 14px;">📈 主要主题映射</h3>

        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;">
        """)

    themes_to_show = [
        ("AI", "🤖", "#8b5cf6"),
        ("芯片", "💎", "#3b82f6"),
        ("半导体", "⚡", "#f97316"),
        ("GPU", "🎮", "#ec4899"),
        ("HBM", "💾", "#14b8a6"),
        ("中美关系", "🌐", "#ef4444"),
        ("国产替代", "🇨🇳", "#22c55e"),
        ("大模型", "🧠", "#a855f7"),
        ("算力", "⚙️", "#f59e0b"),
    ]

    for theme, icon, color in themes_to_show:
        stocks = graph.get_recommended_stocks(theme)
        html_parts.append(f"""
            <div style="background: rgba(255,255,255,0.05); border-radius: 8px; padding: 12px; border-left: 3px solid {color};">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    <span>{icon}</span>
                    <span style="color: #f1f5f9; font-size: 13px; font-weight: 500;">{theme}</span>
                    <span style="color: #64748b; font-size: 11px;">({len(stocks)}只)</span>
                </div>
                <div style="font-size: 11px; color: #94a3b8;">
                    {', '.join(stocks[:4])}{'...' if len(stocks) > 4 else ''}
                </div>
            </div>
        """)

    html_parts.append("""
        </div>
    </div>
    """)

    html_parts.append("""
    <div style="background: #1e293b; border-radius: 12px; padding: 20px; margin: 12px 0;">
        <h3 style="margin: 0 0 16px 0; color: #f1f5f9; font-size: 16px;">🔍 英伟达供应链关系图</h3>
    """)

    text_viz = graph.visualize_supply_chain('nvda', max_depth=2)
    html_parts.append(f"""
        <pre style="background: #0f172a; border-radius: 8px; padding: 16px; color: #94a3b8; font-family: monospace; font-size: 12px; overflow-x: auto;">{text_viz}</pre>
    """)

    html_parts.append("</div>")

    html_parts.append("""
    <div style="background: #1e293b; border-radius: 12px; padding: 20px; margin: 12px 0;">
        <h3 style="margin: 0 0 16px 0; color: #f1f5f9; font-size: 16px;">🇨🇳 A 股 AI/芯片 供应链全景</h3>
    """)

    a_share_nodes = graph.get_all_a_share_stocks()
    if a_share_nodes:
        html_parts.append("""
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;">
        """)
        for node in a_share_nodes[:16]:
            html_parts.append(f"""
                    <div style="background: rgba(239, 68, 68, 0.1); border-radius: 6px; padding: 8px;">
                        <div style="color: #f1f5f9; font-size: 12px; font-weight: 500;">{node.name}</div>
                        <div style="color: #64748b; font-size: 10px;">{node.stock_code}</div>
                        <div style="color: #94a3b8; font-size: 10px; margin-top: 4px;">{node.metadata.get('description', '')}</div>
                    </div>
                """)
        html_parts.append("""
        </div>
        """)

    html_parts.append("</div>")

    valuation_html = _render_valuation_analysis()
    html_parts.append(valuation_html)

    realtime_html = _render_realtime_market_data()
    html_parts.append(realtime_html)

    put_html("".join(html_parts))


def _render_realtime_market_data() -> str:
    """渲染实时市场数据部分"""
    try:
        from deva.naja.bandit import get_fundamental_data_fetcher

        fetcher = get_fundamental_data_fetcher()
        fundamentals = fetcher.get_supply_chain_fundamentals()

        if not fundamentals:
            return """
            <div style="background: #1e293b; border-radius: 12px; padding: 20px; margin: 12px 0;">
                <div style="font-size: 14px; color: #94a3b8;">实时行情加载中...</div>
            </div>
            """

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
            return """
            <div style="background: #1e293b; border-radius: 12px; padding: 20px; margin: 12px 0;">
                <div style="font-size: 14px; color: #94a3b8;">正在获取实时数据...</div>
            </div>
            """

        return f"""
        <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 12px; padding: 20px; margin: 12px 0;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <h2 style="margin: 0; color: #f1f5f9; font-size: 16px;">📊 实时市场行情</h2>
                <div style="font-size: 11px; color: #64748b;">
                    共 {len(fundamentals)} 只股票 | 数据来源: 新浪/东方财富
                </div>
            </div>

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
        import traceback
        return f"""
        <div style="background: #1e293b; border-radius: 12px; padding: 20px; margin: 12px 0;">
            <div style="font-size: 12px; color: #64748b;">实时行情加载中... ({str(e)[:50]})</div>
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
            undervalued_html = '<div style="color: #64748b; font-size: 12px; text-align: center; padding: 20px;">正在计算估值数据...</div>'

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
        return f"""
        <div style="background: #1e293b; border-radius: 12px; padding: 20px; margin: 12px 0;">
            <div style="font-size: 12px; color: #64748b;">估值分析加载中...</div>
        </div>
        """


def get_supply_chain_summary_html() -> str:
    """获取供应链摘要的 HTML（用于嵌入其他页面）"""
    from deva.naja.cognition import get_supply_chain_linker

    linker = get_supply_chain_linker()
    summary = linker.get_supply_chain_summary()
    hot = linker.get_hot_narratives(3)

    hot_html = ""
    if hot:
        for narrative, importance in hot:
            hot_html += f'<span style="background: rgba(239,68,68,0.2); padding: 2px 8px; border-radius: 12px; font-size: 11px; color: #fca5a5; margin-right: 4px;">{narrative} {importance:.1f}</span>'

    return f"""
    <div style="background: rgba(59,130,246,0.1); border-radius: 8px; padding: 12px; margin: 8px 0;">
        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">🔗 供应链叙事</div>
        <div style="display: flex; gap: 16px; flex-wrap: wrap;">
            <div><span style="color: #3b82f6; font-weight: bold;">{summary['total_narratives']}</span> <span style="color: #64748b; font-size: 11px;">叙事</span></div>
            <div><span style="color: #22c55e; font-weight: bold;">{summary['total_stocks_mapped']}</span> <span style="color: #64748b; font-size: 11px;">股票</span></div>
            <div><span style="color: #ef4444; font-weight: bold;">{summary['recent_events_count']}</span> <span style="color: #64748b; font-size: 11px;">事件</span></div>
        </div>
        <div style="margin-top: 8px;">{hot_html}</div>
    </div>
    """
