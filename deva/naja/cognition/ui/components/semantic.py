"""Semantic 组件 —— 语义冷启动图谱

2026-10-19 修：这个面板此前**从未渲染过**。

原实现是 `from .semantic_cold_start import SemanticColdStart` ——
`semantic_cold_start` 模块实际在 `deva/naja/cognition/semantic/` 下，
`components/` 目录里没有这个文件，import 必然失败；而失败被
`except Exception: return` 吞掉，面板就当不存在。同一条路径上还有第二处：
即便 import 成功，它也调用了不存在的 `SemanticColdStart.get_graph()`
（真实接口是 `get_summary()` / `.graph`）。

现在改成读运行中的认知引擎 —— `ui.engine.get_memory_report()['semantic_graph']`
（由 `CognitionCore.get_memory_report` 产出，是同一份实时图谱），
既不会在 UI 层私自 new 一个空实例，也不会把"没数据"和"链路断了"混为一谈：
拿不到就明确写「未构建」，不再静默消失。
"""

import html

from pywebio.output import put_html

from .layout import card, empty_line


_LEVEL_STYLE = {
    0: ("一级 L0", "#f87171"),
    1: ("二级 L1", "#fb923c"),
}


def _level_style(level: int):
    return _LEVEL_STYLE.get(level, ("深层 L2+", "#60a5fa"))


def _node_bar(node) -> str:
    term = html.escape(str(node.get('term', '-')))
    weight = float(node.get('weight', 0) or 0)
    confidence = float(node.get('confidence', 0) or 0)
    relation = html.escape(str(node.get('relation', '')))
    level = int(node.get('level', 0) or 0)
    _, color = _level_style(level)
    bar_width = max(3, min(100, int(weight * 100)))

    relation_html = f'<span>{relation[:20]} · </span>' if relation else ""
    return f"""
    <div style="margin-bottom: 7px;">
        <div style="display: flex; justify-content: space-between; font-size: 11px;
                    color: #94a3b8; margin-bottom: 2px;">
            <span style="color: {color};">{term[:18]}</span>
            <span style="color: #a855f7;">{weight:.3f}</span>
        </div>
        <div style="height: 3px; background: rgba(255,255,255,.08); border-radius: 2px; overflow: hidden;">
            <div style="width: {bar_width}%; height: 100%; background: {color};"></div>
        </div>
        <div style="font-size: 11px; color: #64748b; margin-top: 2px;">{relation_html}置信 {confidence:.2f}</div>
    </div>
    """


def render_semantic(ui):
    graph = {}
    try:
        report = ui.engine.get_memory_report() if ui.engine else {}
        graph = (report or {}).get('semantic_graph') or {}
    except Exception:
        graph = {}

    seeds = graph.get('seeds', []) or []
    top_nodes = graph.get('top_nodes', []) or []
    node_count = int(graph.get('node_count', 0) or 0)
    edge_count = int(graph.get('edge_count', 0) or 0)

    meta = f"种子 <b>{len(seeds)}</b> · 节点 <b>{node_count}</b> · 边 <b>{edge_count}</b>"

    if not seeds and not top_nodes:
        put_html(card(
            title="语义冷启动",
            icon="🔗",
            meta=meta,
            body=empty_line("语义图谱未构建", "种子词为空或冷启动 prompt 尚未执行"),
        ))
        return

    seed_tags = "".join(
        f'<span class="cog-pill" style="background: rgba(96,165,250,.15); color: #60a5fa;">{html.escape(str(s))}</span> '
        for s in seeds[:12]
    )
    if len(seeds) > 12:
        seed_tags += f'<span style="color: #64748b; font-size: 11px;">+{len(seeds) - 12}</span>'

    head = f"""
    <div>
        <div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">🎯 种子词</div>
        <div style="line-height: 2;">{seed_tags or '<span style="color:#64748b;font-size:11px;">暂无</span>'}</div>
    </div>
    """

    if top_nodes:
        bars = "".join(_node_bar(n) for n in top_nodes[:10])
        body = head + f"""
        <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.06);">
            <div style="font-size: 11px; color: #64748b; margin-bottom: 8px;">权重 Top {min(10, len(top_nodes))}</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px 18px;">{bars}</div>
        </div>
        """
    else:
        body = head + empty_line("暂无节点权重", "图谱已建但还没写入节点")

    put_html(card(title="语义冷启动", icon="🔗", meta=meta, body=body))
