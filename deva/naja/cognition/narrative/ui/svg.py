"""
Narrative SVG 组件
"""

import math
from typing import List, Dict


def render_narrative_svg(nodes: List[Dict], edges: List[Dict]) -> str:
    if not nodes:
        return '<div style="color:#64748b;font-size:11px;">暂无叙事数据</div>'

    width = 380
    height = 260
    center_x = width // 2
    center_y = height // 2
    radius = 90

    stage_colors = {
        '萌芽': '#60a5fa',
        '扩散': '#818cf8',
        '高潮': '#f87171',
        '消退': '#fb923c',
    }

    node_count = len(nodes)
    if node_count == 1:
        positions = [(center_x, center_y)]
    elif node_count <= 4:
        positions = []
        for i in range(node_count):
            angle = (2 * math.pi * i / node_count) - math.pi / 2
            x = center_x + radius * 0.6 * math.cos(angle)
            y = center_y + radius * 0.6 * math.sin(angle)
            positions.append((x, y))
        positions.extend([(center_x, center_y)] * (4 - node_count))
    else:
        positions = []
        for i in range(node_count):
            angle = (2 * math.pi * i / node_count) - math.pi / 2
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            positions.append((x, y))

    node_map = {}
    for i, node in enumerate(nodes):
        node_map[node['id']] = i

    svg_parts = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">']

    svg_parts.append(f'''
    <defs>
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur"/>
            <feMerge>
                <feMergeNode in="blur"/>
                <feMergeNode in="SourceGraphic"/>
            </feMerge>
        </filter>
        <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="2" flood-opacity="0.4"/>
        </filter>
    </defs>
    ''')

    svg_parts.append(f'<rect width="{width}" height="{height}" fill="rgba(15,23,42,0.3)" rx="8"/>')

    for edge in edges:
        src = edge.get('source', '')
        tgt = edge.get('target', '')
        weight = float(edge.get('weight', 0))
        if src not in node_map or tgt not in node_map:
            continue

        src_idx = node_map[src]
        tgt_idx = node_map[tgt]
        x1, y1 = positions[src_idx]
        x2, y2 = positions[tgt_idx]

        opacity = 0.3 + weight * 0.5
        stroke_width = max(1, weight * 3)
        color = '#a78bfa'

        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2

        if node_count <= 4:
            ctrl_x = mid_x
            ctrl_y = mid_y - 15
        else:
            dist = math.sqrt((x2-x1)**2 + (y2-y1)**2)
            offset = 20 * (1 - dist / (2 * radius))
            ctrl_x = mid_x + offset
            ctrl_y = mid_y - offset

        svg_parts.append(
            f'<path d="M {x1:.1f} {y1:.1f} Q {ctrl_x:.1f} {ctrl_y:.1f} {x2:.1f} {y2:.1f}" '
            f'stroke="{color}" stroke-width="{stroke_width:.1f}" fill="none" opacity="{opacity:.2f}" stroke-linecap="round"/>'
        )

    for i, node in enumerate(nodes):
        x, y = positions[i]
        stage = node.get('stage', '萌芽')
        attention = float(node.get('attention_score', 0))
        node_color = stage_colors.get(stage, '#60a5fa')
        node_size = 28 + attention * 12

        svg_parts.append(f'''
        <circle cx="{x:.1f}" cy="{y:.1f}" r="{node_size:.1f}"
            fill="{node_color}" opacity="0.85" filter="url(#shadow)"/>
        <circle cx="{x:.1f}" cy="{y:.1f}" r="{node_size * 0.6:.1f}"
            fill="rgba(255,255,255,0.15)"/>
        ''')

        font_size = 9 if len(node['id']) > 3 else 10
        svg_parts.append(f'''
        <text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" dominant-baseline="central"
            fill="#f1f5f9" font-size="{font_size}" font-weight="600" font-family="system-ui">
            {node['id']}
        </text>
        ''')

        stage_text_x = x + node_size + 4
        stage_text_y = y - 6
        svg_parts.append(f'''
        <text x="{stage_text_x:.1f}" y="{stage_text_y:.1f}"
            fill="#94a3b8" font-size="8" font-family="system-ui">
            {stage}
        </text>
        ''')

    svg_parts.append('</svg>')
    return ''.join(svg_parts)