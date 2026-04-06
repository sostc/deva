"""
Semantic 组件
"""


def render_semantic(ui):
    def _render_semantic_cold_start(self):
        try:
            from .semantic_cold_start import SemanticColdStart
            cold_start = SemanticColdStart()
            graph = cold_start.get_graph()
            seeds = graph.get("seeds", [])
            nodes = graph.get("nodes", [])
            edges = graph.get("edges", [])
            decay = graph.get("industry_decay", [])
        except Exception:
            return

        node_count = len(nodes)
        edge_count = len(edges)
        seed_count = len(seeds)
        decay_count = len(decay)

        seed_tags = ""
        for seed in seeds[:10]:
            seed_tags += f'<span style="display: inline-block; padding: 2px 6px; background: rgba(96,165,250,0.15); color: #60a5fa; border-radius: 4px; font-size: 9px; margin: 2px;">{seed}</span>'
        if seeds:
            seed_tags += f'<span style="color: #64748b; font-size: 9px;">+{max(0, seed_count - 10)}</span>'

        level0_nodes = [n for n in nodes if n.get('level', 0) == 0]
        level1_nodes = [n for n in nodes if n.get('level', 0) == 1]
        level2_nodes = [n for n in nodes if n.get('level', 0) >= 2]

        top_level0 = sorted(level0_nodes, key=lambda x: x.get('weight', 0), reverse=True)[:4]
        top_level1 = sorted(level1_nodes, key=lambda x: x.get('weight', 0), reverse=True)[:4]
        top_level2 = sorted(level2_nodes, key=lambda x: x.get('weight', 0), reverse=True)[:4]

        def render_node_bar(node, color):
            term = node.get('term', '-')
            weight = float(node.get('weight', 0))
            confidence = float(node.get('confidence', 0))
            relation = node.get('relation', '')
            bar_width = min(100, int(weight * 100))
            return f"""
            <div style="margin-bottom: 6px;">
                <div style="display: flex; justify-content: space-between; font-size: 10px; color: #94a3b8; margin-bottom: 2px;">
                    <span style="color: {color};">{term[:15]}</span>
                    <span style="color: #a855f7;">{weight:.3f}</span>
                </div>
                <div style="height: 3px; background: rgba(255,255,255,0.08); border-radius: 2px; overflow: hidden;">
                    <div style="width: {bar_width}%; height: 100%; background: linear-gradient(90deg, {color}, {color}aa);"></div>
                </div>
                <div style="font-size: 8px; color: #64748b;">{relation[:20]} | 置信 {confidence:.2f}</div>
            </div>
            """

        level0_bars = "".join([render_node_bar(n, "#f87171") for n in top_level0]) if top_level0 else '<div style="color: #64748b; font-size: 10px;">暂无</div>'
        level1_bars = "".join([render_node_bar(n, "#fb923c") for n in top_level1]) if top_level1 else '<div style="color: #64748b; font-size: 10px;">暂无</div>'
        level2_bars = "".join([render_node_bar(n, "#60a5fa") for n in top_level2]) if top_level2 else '<div style="color: #64748b; font-size: 10px;">暂无</div>'

        decay_items = ""
        top_decay = sorted(decay, key=lambda x: x.get('lambda', 0), reverse=True)[:5]
        for d in top_decay:
            term = d.get('term', '-')
            lam = float(d.get('lambda', 0))
            decay_items += f"""
            <div style="display: flex; justify-content: space-between; font-size: 9px; color: #94a3b8; padding: 2px 0;">
                <span>{term[:10]}</span>
                <span style="color: #4ade80;">λ={lam:.4f}</span>
            </div>
            """
        if not decay_items:
            decay_items = '<div style="color: #64748b; font-size: 9px;">暂无衰减配置</div>'

        edge_items = ""
        relation_types = {}
        for e in edges[:10]:
            src = e.get('src', '-')
            dst = e.get('dst', '-')
            rel = e.get('relation', 'related')
            w = float(e.get('weight', 0))
            relation_types[rel] = relation_types.get(rel, 0) + 1
            src_short = src[:8] if len(src) > 8 else src
            dst_short = dst[:8] if len(dst) > 8 else dst
            rel_short = rel[:10] if len(rel) > 10 else rel
            edge_items += f"""
            <div style="font-size: 9px; color: #94a3b8; padding: 2px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                <span style="color: #a855f7;">{src_short}</span> → <span style="color: #60a5fa;">{dst_short}</span>
                <span style="color: #64748b;">({rel_short})</span>
                <span style="color: #4ade80; float: right;">{w:.2f}</span>
            </div>
            """
        if not edge_items:
            edge_items = '<div style="color: #64748b; font-size: 9px;">暂无边关系</div>'

        relation_summary = ""
        for rel, cnt in sorted(relation_types.items(), key=lambda x: x[1], reverse=True)[:4]:
            relation_summary += f'<span style="display: inline-block; padding: 1px 4px; background: rgba(168,85,247,0.1); color: #a855f7; border-radius: 3px; font-size: 8px; margin: 2px;">{rel}({cnt})</span>'

        from pywebio.output import put_html
        put_html(f"""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <div style="font-size: 13px; font-weight: 600; color: #a855f7;">
                    🔗 语义冷启动
                </div>
                <div style="font-size: 10px; color: #475569;">
                    种子: {seed_count} | 节点: {node_count} | 边: {edge_count} | 衰减: {decay_count}
                </div>
            </div>
            <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
                种子词 → 语义扩展 → 权重计算 → 图谱构建
            </div>

            <div style="display: grid; grid-template-columns: 1fr 2fr; gap: 12px; margin-bottom: 12px;">
                <div style="background: rgba(96,165,250,0.08); border-radius: 8px; padding: 10px;">
                    <div style="font-size: 10px; color: #60a5fa; font-weight: 600; margin-bottom: 6px;">🎯 种子词</div>
                    <div style="margin-bottom: 10px;">{seed_tags or '<span style="color: #64748b; font-size: 10px;">暂无种子</span>'}</div>

                    <div style="font-size: 10px; color: #4ade80; font-weight: 600; margin-bottom: 6px;">📉 衰减配置 (Top5)</div>
                    <div>{decay_items}</div>
                </div>

                <div>
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 10px;">
                        <div style="background: rgba(248,113,113,0.1); border: 1px solid rgba(248,113,113,0.2); padding: 8px; border-radius: 6px; text-align: center;">
                            <div style="font-size: 16px; font-weight: 700; color: #f87171;">{len(level0_nodes)}</div>
                            <div style="font-size: 9px; color: #64748b;">一级节点</div>
                        </div>
                        <div style="background: rgba(251,146,60,0.1); border: 1px solid rgba(251,146,60,0.2); padding: 8px; border-radius: 6px; text-align: center;">
                            <div style="font-size: 16px; font-weight: 700; color: #fb923c;">{len(level1_nodes)}</div>
                            <div style="font-size: 9px; color: #64748b;">二级节点</div>
                        </div>
                        <div style="background: rgba(96,165,250,0.1); border: 1px solid rgba(96,165,250,0.2); padding: 8px; border-radius: 6px; text-align: center;">
                            <div style="font-size: 16px; font-weight: 700; color: #60a5fa;">{len(level2_nodes)}</div>
                            <div style="font-size: 9px; color: #64748b;">深层节点</div>
                        </div>
                    </div>

                    {relation_summary if relation_summary else ''}
                </div>
            </div>

            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 10px;">
                <div style="background: rgba(248,113,113,0.08); border-radius: 6px; padding: 8px;">
                    <div style="font-size: 9px; color: #f87171; font-weight: 600; margin-bottom: 4px;">🔴 一级 (L0)</div>
                    {level0_bars}
                </div>
                <div style="background: rgba(251,146,60,0.08); border-radius: 6px; padding: 8px;">
                    <div style="font-size: 9px; color: #fb923c; font-weight: 600; margin-bottom: 4px;">🟠 二级 (L1)</div>
                    {level1_bars}
                </div>
                <div style="background: rgba(96,165,250,0.08); border-radius: 6px; padding: 8px;">
                    <div style="font-size: 9px; color: #60a5fa; font-weight: 600; margin-bottom: 4px;">🔵 深层 (L2+)</div>
                    {level2_bars}
                </div>
            </div>

            <div style="background: rgba(255,255,255,0.02); border-radius: 6px; padding: 8px;">
                <div style="font-size: 10px; color: #a855f7; font-weight: 600; margin-bottom: 4px;">🔗 边关系 (Top10)</div>
                <div>{edge_items}</div>
            </div>

            <div style="margin-top: 10px; padding: 8px; background: rgba(74,222,128,0.08); border-radius: 6px; border: 1px solid rgba(74,222,128,0.15);">
                <div style="font-size: 9px; color: #4ade80; font-weight: 600; margin-bottom: 4px;">💡 权重计算公式</div>
                <div style="font-size: 8px; color: #64748b; font-family: monospace;">
                    weight = 0.6 × historical_relevance + 0.4 × confidence
                </div>
            </div>
        </div>
        """)

    _render_semantic_cold_start(ui)