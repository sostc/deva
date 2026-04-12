"""供应链 UI - 知识图谱"""

from typing import List, Dict, Tuple
from datetime import datetime

from pywebio.output import (
    put_html, put_row, put_column, put_text, put_button, put_table,
    put_scope, use_scope, clear_scope
)
from pywebio.session import run_js
import math

from .market_data import _render_realtime_market_data, _render_valuation_analysis


def _render_supply_chain_svg(graph, stock_code: str, max_depth: int = 3) -> str:
    """生成供应链SVG可视化 - 增强版"""
    node = graph.get_stock_node(stock_code)
    if not node:
        return f'<div style="color:#64748b;">未找到股票: {stock_code}</div>'

    upstream = graph.get_upstream(node.id, max_depth)
    downstream = graph.get_downstream(node.id, max_depth)

    all_nodes = [node] + upstream + downstream
    node_ids = [n.id for n in all_nodes]

    node_map = {n.id: i for i, n in enumerate(all_nodes)}

    pe_ratios = {}
    try:
        import json
        import os
        json_path = os.path.join(os.path.dirname(__file__), '..', '..', 'bandit', 'supply_chain_fundamentals.json')
        json_path = os.path.normpath(json_path)
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                fundamentals_data = json.load(f)
            for node_id, data in fundamentals_data.items():
                if data.get('pe'):
                    pe_ratios[node_id] = data['pe']
    except:
        pass

    width = 900
    height = 600
    center_x = width // 2
    center_y = height // 2

    layer_0 = [node] if node else []

    layer_1_upstream = upstream[:6]
    layer_1_downstream = downstream[:6]

    layer_2_upstream = []
    layer_2_downstream = []
    layer_2_related = []

    upstream_ids = {n.id for n in layer_1_upstream}
    downstream_ids = {n.id for n in layer_1_downstream}

    for edge in graph._edges:
        if edge.from_id in upstream_ids and edge.type.value in ['supplies_to', 'produces']:
            if edge.to_id not in upstream_ids and edge.to_id not in downstream_ids:
                target = graph.get_stock_node(edge.to_id)
                if target and target.id not in layer_2_upstream and len(layer_2_upstream) < 4:
                    layer_2_upstream.append(target)
        if edge.to_id in upstream_ids and edge.type.value in ['supplies_to', 'produces']:
            if edge.from_id not in upstream_ids and edge.from_id not in downstream_ids:
                source = graph.get_stock_node(edge.from_id)
                if source and source.id not in layer_2_upstream and len(layer_2_upstream) < 4:
                    layer_2_upstream.append(source)
        if edge.type.value == 'competes_with':
            competitor = graph.get_stock_node(edge.from_id if edge.to_id == node.id else edge.to_id)
            if competitor and competitor.id not in layer_2_related and len(layer_2_related) < 3:
                layer_2_related.append(competitor)

    downstream_related = []
    for edge in graph._edges:
        if edge.from_id in downstream_ids and edge.type.value == 'supplies_to':
            if edge.to_id not in upstream_ids and edge.to_id not in downstream_ids:
                target = graph.get_stock_node(edge.to_id)
                if target and target.id not in downstream_related and len(downstream_related) < 3:
                    downstream_related.append(target)

    positions = {}
    positions[node.id] = (center_x, center_y)

    radius_1 = 160
    all_layer1 = layer_1_upstream + layer_1_downstream
    for i, n in enumerate(all_layer1):
        angle = (2 * math.pi * i / len(all_layer1)) - math.pi / 2
        x = center_x + radius_1 * math.cos(angle)
        y = center_y + radius_1 * math.sin(angle)
        positions[n.id] = (x, y)

    radius_2 = 280
    all_layer2 = layer_2_upstream + layer_2_related + downstream_related
    for i, n in enumerate(all_layer2):
        angle = (2 * math.pi * i / max(len(all_layer2), 1)) - math.pi / 2 + (math.pi / 8)
        x = center_x + radius_2 * math.cos(angle)
        y = center_y + radius_2 * math.sin(angle)
        positions[n.id] = (x, y)

    node_colors = {
        "company": "#3b82f6",
        "product": "#8b5cf6",
        "technology": "#f97316",
        "component": "#22c55e",
        "equipment": "#eab308",
        "material": "#64748b",
        "infrastructure": "#ec4899",
    }

    market_bg_colors = {
        "US": "rgba(59, 130, 246, 0.3)",
        "A": "rgba(239, 68, 68, 0.3)",
    }

    svg_parts = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">']

    svg_parts.append('''
    <style>
        .node-group:hover .tooltip-bg { fill: rgba(30,41,59,0.95); }
        .tooltip-text { pointer-events: none; opacity: 0; transition: opacity 0.2s; }
        .node-group:hover .tooltip-text { opacity: 1; }
        .tooltip-bg { opacity: 0; transition: opacity 0.2s; }
        .node-group:hover .tooltip-bg { opacity: 1; }
    </style>
    ''')

    svg_parts.append('''
    <defs>
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="blur"/>
            <feMerge>
                <feMergeNode in="blur"/>
                <feMergeNode in="SourceGraphic"/>
            </feMerge>
        </filter>
        <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="2" flood-opacity="0.5"/>
        </filter>
        <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#60a5fa"/>
        </marker>
    </defs>
    ''')

    svg_parts.append(f'<rect width="{width}" height="{height}" fill="rgba(15,23,42,0.8)" rx="12"/>')

    svg_parts.append(f'''
    <text x="20" y="35" fill="#f1f5f9" font-size="18" font-weight="bold" font-family="system-ui">
        🔗 供应链关系图
    </text>
    <text x="20" y="55" fill="#94a3b8" font-size="11" font-family="system-ui">
        中心: {node.name} ({node.stock_code}) | 上游: {len(upstream)} 家 | 下游: {len(downstream)} 种
    </text>
    ''')

    edges = []
    for edge in graph._edges:
        if edge.from_id in node_ids and edge.to_id in node_ids:
            edges.append(edge)

    for edge in edges:
        src_id = edge.from_id
        tgt_id = edge.to_id
        if src_id not in positions or tgt_id not in positions:
            continue
        x1, y1 = positions[src_id]
        x2, y2 = positions[tgt_id]

        weight = edge.weight
        opacity = 0.2 + weight * 0.5
        stroke_width = max(1, weight * 3)
        color = '#60a5fa' if edge.type.value in ['supplies_to', 'produces'] else '#a78bfa'

        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        dist = math.sqrt((x2-x1)**2 + (y2-y1)**2)
        offset = 30 * (1 - min(dist / 400, 1))
        ctrl_x = mid_x + offset
        ctrl_y = mid_y - offset

        arrow_marker = 'marker-end="url(#arrowhead)"' if weight > 0.5 else ''

        svg_parts.append(
            f'<path d="M {x1:.1f} {y1:.1f} Q {ctrl_x:.1f} {ctrl_y:.1f} {x2:.1f} {y2:.1f}" '
            f'stroke="{color}" stroke-width="{stroke_width:.1f}" fill="none" opacity="{opacity:.2f}" stroke-linecap="round" {arrow_marker}/>'
        )

    cap_size_map = {"large_cap": 36, "mid_cap": 28, "small_cap": 22}

    for n in all_nodes:
        if n.id not in positions:
            continue
        x, y = positions[n.id]

        is_center = (n.id == node.id)
        node_type = n.type.value
        color = node_colors.get(node_type, '#64748b')
        market = n.metadata.get('market', '')
        market_bg = market_bg_colors.get(market, 'rgba(100,100,100,0.3)')

        cap = n.market_cap or 'mid_cap'
        node_size = cap_size_map.get(cap, 28) if node_type == 'company' else 24

        description = n.metadata.get('description', '')
        if not description and n.type.value == 'company':
            description = f"{n.name} ({n.stock_code.upper() if n.stock_code else 'N/A'})"
            if market == 'US':
                description += " - 美股"
            elif market == 'A':
                description += " - A股"

        tooltip_x = x + node_size + 15
        tooltip_y = y - 40

        svg_parts.append(f'''
        <g class="node-group">
            <circle cx="{x:.1f}" cy="{y:.1f}" r="{node_size + 8:.1f}"
                fill="{market_bg}" opacity="0.6"/>
            <circle cx="{x:.1f}" cy="{y:.1f}" r="{node_size:.1f}"
                fill="{color}" opacity="0.9" filter="{"url(#glow)" if is_center else "url(#shadow)"}"/>
            <circle cx="{x:.1f}" cy="{y:.1f}" r="{node_size * 0.45:.1f}"
                fill="rgba(255,255,255,0.2)"/>
        ''')

        if description:
            svg_parts.append(f'''
            <g class="tooltip-group" transform="translate({tooltip_x:.1f}, {tooltip_y:.1f})">
                <rect class="tooltip-bg" x="0" y="0" width="160" height="50" rx="6"
                    fill="rgba(30,41,59,0.9)" stroke="rgba(100,116,139,0.3)" stroke-width="1"/>
                <text x="8" y="18" fill="#f1f5f9" font-size="10" font-weight="bold" font-family="system-ui">
                    {n.name}
                </text>
                <text x="8" y="34" fill="#94a3b8" font-size="9" font-family="system-ui">
                    {description[:25]}{'...' if len(description) > 25 else ''}
                </text>
                <text x="8" y="46" fill="#64748b" font-size="8" font-family="system-ui">
                    类型: {node_type} | 市值: {cap}
                </text>
            </g>
            ''')

        svg_parts.append('</g>')

        label_lines = []
        name = n.name
        if len(name) > 6:
            label_lines.append(name[:6])
            label_lines.append(name[6:])
        else:
            label_lines.append(name)

        if n.stock_code:
            label_lines.append(n.stock_code.upper())

        if n.id in pe_ratios:
            pe = pe_ratios[n.id]
            label_lines.append(f"P/E: {pe:.1f}")

        for j, line in enumerate(label_lines[:3]):
            line_y = y + (j - (len(label_lines) - 1) / 2) * 11
            font_size = 10 if is_center else 8
            font_weight = "bold" if is_center else "normal"
            svg_parts.append(f'''
            <text x="{x:.1f}" y="{line_y:.1f}" text-anchor="middle" dominant-baseline="central"
                fill="#f1f5f9" font-size="{font_size}" font-weight="{font_weight}" font-family="system-ui">
                {line}
            </text>
            ''')

    legend_x = width - 180
    legend_y = 30
    svg_parts.append(f'''
    <rect x="{legend_x - 10}" y="{legend_y - 5}" width="170" height="95" fill="rgba(30,41,59,0.8)" rx="6"/>
    <text x="{legend_x}" y="{legend_y + 10}" fill="#f1f5f9" font-size="10" font-weight="bold" font-family="system-ui">图例</text>
    <circle cx="{legend_x + 10}" cy="{legend_y + 28}" r="8" fill="#3b82f6"/>
    <text x="{legend_x + 25}" y="{legend_y + 32}" fill="#94a3b8" font-size="9" font-family="system-ui">公司</text>
    <circle cx="{legend_x + 10}" cy="{legend_y + 48}" r="6" fill="#8b5cf6"/>
    <text x="{legend_x + 25}" y="{legend_y + 52}" fill="#94a3b8" font-size="9" font-family="system-ui">产品</text>
    <circle cx="{legend_x + 10}" cy="{legend_y + 68}" r="6" fill="#f97316"/>
    <text x="{legend_x + 25}" y="{legend_y + 72}" fill="#94a3b8" font-size="9" font-family="system-ui">技术/组件</text>
    <rect x="{legend_x + 5}" y="{legend_y + 80}" width="12" height="8" fill="rgba(59,130,246,0.3)"/>
    <text x="{legend_x + 25}" y="{legend_y + 87}" fill="#94a3b8" font-size="9" font-family="system-ui">🇺🇸 美股</text>
    <rect x="{legend_x + 80}" y="{legend_y + 80}" width="12" height="8" fill="rgba(239,68,68,0.3)"/>
    <text x="{legend_x + 100}" y="{legend_y + 87}" fill="#94a3b8" font-size="9" font-family="system-ui">🇨🇳 A股</text>
    ''')

    svg_parts.append('</svg>')
    return ''.join(svg_parts)


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

        <h3 style="margin: 20px 0 12px 0; color: #f1f5f9; font-size: 14px;">📈 热门题材映射</h3>

        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;">
        """)

    try:
        from deva.naja.market_hotspot.ui_components.common import get_hot_blocks_and_stocks
        hot_data = get_hot_blocks_and_stocks()
        hot_blocks = hot_data.get("blocks", [])
    except Exception:
        hot_blocks = []

    theme_colors = {
        "AI": "#8b5cf6", "人工智能": "#8b5cf6", "芯片": "#3b82f6",
        "半导体": "#f97316", "GPU": "#ec4899", "HBM": "#14b8a6",
        "中美关系": "#ef4444", "国产替代": "#22c55e", "大模型": "#a855f7",
        "算力": "#f59e0b", "新能源": "#22c55e", "汽车": "#f97316",
    }

    theme_icons = {
        "AI": "🤖", "人工智能": "🤖", "芯片": "💎", "半导体": "⚡",
        "GPU": "🎮", "HBM": "💾", "中美关系": "🌐", "国产替代": "🇨🇳",
        "大模型": "🧠", "算力": "⚙️", "新能源": "⚡", "汽车": "🚗",
    }

    from deva.naja.dictionary.blocks import get_all_blocks, get_block_stocks, get_stock_name, get_stock_info
    all_blocks = get_all_blocks()
    if hot_blocks:
        blocks_to_show = hot_blocks[:9]
    else:
        ai_blocks = [b for b in all_blocks if any(k in b.name for k in ['AI', '人工', '芯片', '半导体', '算力'])]
        blocks_to_show = [{"name": b.name, "weight": 0.0} for b in ai_blocks[:9]]

    for block in blocks_to_show:
        block_name = block.get("name", "")
        weight = block.get("weight", 0)
        color = theme_colors.get(block_name, "#64748b")
        icon = theme_icons.get(block_name, "📊")
        stock_codes = get_block_stocks(block_name)[:4]
        stock_names = []
        for code in stock_codes:
            info = get_stock_info(code)
            if info:
                stock_names.append(info.name)
            else:
                stock_names.append(code)
        html_parts.append(f"""
            <div style="background: rgba(255,255,255,0.05); border-radius: 8px; padding: 12px; border-left: 3px solid {color};">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    <span>{icon}</span>
                    <span style="color: #f1f5f9; font-size: 13px; font-weight: 500;">{block_name}</span>
                    <span style="color: #64748b; font-size: 11px;">({weight:.2f})</span>
                </div>
                <div style="font-size: 11px; color: #94a3b8;">
                    {', '.join(stock_names) if stock_names else '暂无数据'}
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

    try:
        svg_html = _render_supply_chain_svg(graph, 'nvda', max_depth=2)
        html_parts.append(f"""
        <div style="display: flex; justify-content: center; margin: 12px 0;">
            {svg_html}
        </div>
        """)
    except Exception as e:
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


