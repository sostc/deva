"""认知页版式骨架

背景（2026-10-19）：认知页曾把 18 个组件平铺在一列里，每个组件自带同权重的
卡片标题，整页 9,420px、无任何页级分节，用户滚下去找不到"断点"。

这里提供三样东西，全部由一次 ``put_page_css()`` + 若干 ``put_html`` 组成：

1. ``render_anchor_nav`` / ``render_section`` —— 页级分组抬头（强视觉断点）+ 顶部锚点导航；
2. ``fold`` —— 原生 ``<details>`` 折叠块，静态说明/长列表默认收起；
3. ``empty_line`` —— 一行式空态，替代原来各占 230px 的"暂无数据"大卡片。

❗一条 HTML 必须一次 put_html 渲完（PyWebIO 的 put_html 是并列追加，
跨调用「开 div / 关 div」不会嵌套，历史组件因此都踩过这个坑）。
"""

import threading
from typing import Iterable, Tuple

from pywebio.output import put_html


#: 分节主色。选色只用于左侧竖条与图标，正文一律中性色，避免页面变调色板。
SECTION_COLORS = {
    "overview": "#14b8a6",
    "thinking": "#a855f7",
    "memory": "#60a5fa",
    "deep": "#22c55e",
    "tools": "#94a3b8",
}


_PAGE_CSS = """
<style>
/* ── 认知页版式（cognition/ui/components/layout.py） ── */
/* 底色修正：本页所有组件文本都是 slate 浅色（为深色底设计），
   但 PyWebIO 的 body.webio-theme-default 优先级高于 get_global_styles()
   里的 body{}，实际一直是白底 → 卡片标题对比度约 1.4:1，几乎读不出来。
   这里只作用于认知页（CSS 随本页渲染注入），不动其它页面。 */
body.webio-theme-default { background-color: #0b1220 !important; }
.markdown-body { color: #cbd5e1; }
footer.footer { background: transparent !important; color: #64748b !important; border: 0 !important; }
#pywebio-scope-ROOT, .markdown-body { scroll-behavior: smooth; }

.cog-nav {
    position: sticky; top: 56px; z-index: 60;
    display: flex; gap: 6px; flex-wrap: wrap; align-items: center;
    padding: 8px 0 10px; margin: 0 0 4px;
    background: linear-gradient(#0b1220 78%, rgba(11,18,32,0));
}
.cog-nav a {
    font-size: 11px; color: #94a3b8; text-decoration: none;
    padding: 4px 11px; border-radius: 999px;
    border: 1px solid rgba(255,255,255,.10); background: rgba(255,255,255,.04);
    transition: color .15s ease, border-color .15s ease;
}
.cog-nav a:hover { color: #e2e8f0; border-color: rgba(255,255,255,.24); }
.cog-nav a b { color: #64748b; font-weight: 400; margin-left: 4px; }

.cog-sec {
    margin: 30px 0 12px; padding-left: 12px;
    border-left: 3px solid var(--sec, #64748b);
    scroll-margin-top: 112px;
}
.cog-sec.first { margin-top: 6px; }
.cog-sec-t {
    display: flex; align-items: center; gap: 8px;
    font-size: 19px; font-weight: 600; color: #e2e8f0; letter-spacing: .2px;
}
.cog-sec-s { font-size: 11px; color: #7b8aa0; margin-top: 4px; }
.cog-sec hr {
    border: 0; border-top: 1px solid rgba(255,255,255,.07); margin: 10px 0 0;
}

.cog-card {
    background: #131d2f; border: 1px solid rgba(255,255,255,.07);
    border-radius: 12px; padding: 14px 18px; margin: 0 0 10px;
}
.cog-hd { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.cog-hd + .cog-body { margin-top: 10px; }
.cog-title { font-size: 13px; font-weight: 600; color: #dbe4ef; display: flex; align-items: center; gap: 6px; }
.cog-meta { font-size: 11px; color: #7b8aa0; white-space: nowrap; }
.cog-meta b { color: #b6c2d2; font-weight: 500; }

.cog-empty {
    display: flex; align-items: baseline; gap: 8px;
    padding: 8px 10px; border-radius: 6px;
    background: rgba(255,255,255,.03); border-left: 2px solid rgba(255,255,255,.10);
    font-size: 11px; color: #7b8aa0;
}
.cog-empty b { color: #b6c2d2; font-weight: 500; }

details.cog-fold { margin-top: 8px; }
details.cog-fold > summary {
    list-style: none; cursor: pointer;
    display: flex; align-items: center; gap: 8px;
    padding: 7px 10px; border-radius: 6px;
    background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.07);
    font-size: 11px; color: #94a3b8;
}
details.cog-fold > summary::-webkit-details-marker { display: none; }
details.cog-fold > summary::before { content: "▸"; color: #64748b; font-size: 10px; }
details.cog-fold[open] > summary::before { content: "▾"; }
details.cog-fold > summary:hover { border-color: rgba(255,255,255,.16); color: #cbd5e1; }
details.cog-fold > summary .cog-fold-meta { margin-left: auto; color: #64748b; font-size: 11px; }
details.cog-fold .cog-fold-body { padding: 10px 2px 2px; }

.cog-pill {
    display: inline-block; padding: 2px 7px; border-radius: 4px;
    font-size: 11px; line-height: 1.5;
}
</style>
"""


def put_page_css() -> None:
    """注入认知页共用的版式样式（每页一次）。"""
    put_html(_PAGE_CSS)


def render_anchor_nav(items: Iterable[Tuple[str, str]]) -> None:
    """顶部锚点导航。

    Args:
        items: ``(anchor_id, 显示名)`` 序列，顺序即展示顺序。
    """
    links = "".join(
        f'<a href="#{anchor}">{label}</a>' for anchor, label in items
    )
    put_html(f'<div class="cog-nav">{links}</div>')


def render_section(anchor: str, icon: str, title: str, subtitle: str,
                   color: str = "#64748b", first: bool = False) -> None:
    """页级分节抬头 —— 页面上唯一的“断点”。

    Args:
        anchor: DOM id，供锚点导航跳转。
        icon: 抬头左侧图标。
        title: 分节标题。
        subtitle: 一句话说明这一节回答什么问题。
        color: 左侧竖条颜色，取 ``SECTION_COLORS``。
        first: 是否为第一节（收掉顶部大间距）。
    """
    cls = "cog-sec first" if first else "cog-sec"
    put_html(f"""
    <div id="{anchor}" class="{cls}" style="--sec: {color};">
        <div class="cog-sec-t"><span>{icon}</span>{title}</div>
        <div class="cog-sec-s">{subtitle}</div>
        <hr>
    </div>
    """)


def card(title: str, body: str, icon: str = "", meta: str = "") -> str:
    """返回一张标准卡片的 HTML 片段（供组件拼接）。"""
    head_left = f'<span>{icon}</span>{title}' if icon else title
    meta_html = f'<div class="cog-meta">{meta}</div>' if meta else ""
    return f"""
    <div class="cog-card">
        <div class="cog-hd">
            <div class="cog-title">{head_left}</div>
            {meta_html}
        </div>
        <div class="cog-body">{body}</div>
    </div>
    """


def jump_card(icon: str, title: str, desc: str, href: str, meta: str = "") -> str:
    """一行式跳转卡：模块**搬去别的页面**后，在本页留下的入口。

    ❗搬走不等于「够不着」。认知页把供应链联动挪去 ``/supplychain`` 之后，
    这里留一张 46px 的入口卡，指向它真正的家并写明「在那边能看到什么」，
    否则用户只会看到这块内容凭空消失。
    """
    meta_html = f'<div class="cog-meta">{meta}</div>' if meta else ""
    return f"""
    <a href="{href}" style="text-decoration: none;">
        <div class="cog-card" style="display: flex; align-items: center;
                    justify-content: space-between; gap: 12px;">
            <div>
                <div class="cog-title">{icon} {title}</div>
                <div style="font-size: 11px; color: #64748b; margin-top: 3px;">{desc}</div>
            </div>
            <div style="display: flex; align-items: center; gap: 10px; flex-shrink: 0;">
                {meta_html}
                <div style="background: rgba(255,255,255,.05); padding: 5px 11px;
                            border-radius: 8px; font-size: 11px; color: #94a3b8;
                            white-space: nowrap;">查看 →</div>
            </div>
        </div>
    </a>
    """


def fold(summary: str, body: str, meta: str = "", open_by_default: bool = False) -> str:
    """返回一个原生 ``<details>`` 折叠块。

    用于两类内容：纯静态说明文档（默认收起）、以及长列表的“其余 N 条”。
    """
    opened = " open" if open_by_default else ""
    meta_html = f'<span class="cog-fold-meta">{meta}</span>' if meta else ""
    return f"""
    <details class="cog-fold"{opened}>
        <summary>{summary}{meta_html}</summary>
        <div class="cog-fold-body">{body}</div>
    </details>
    """


def empty_line(text: str, hint: str = "") -> str:
    """一行式空态：``未就绪 · 原因``，不再用 230px 的大卡片说“暂无”。"""
    hint_html = f'<span>{hint}</span>' if hint else ""
    return f'<div class="cog-empty"><b>{text}</b>{hint_html}</div>'


# ❗风险色图例：本页的色标衡量的是「健康度 / 需求强弱」，与 A 股涨红跌绿相反，
# 没有图例就会被按股价涨跌读反。凡是卡片里出现风险色的地方都必须带一条。
_LEGEND_ITEMS = (
    ("#ef4444", "红 = 危险 / 不利"),
    ("#f59e0b", "橙 = 偏弱"),
    ("#3b82f6", "蓝 = 中性"),
    ("#22c55e", "绿 = 健康"),
    ("#94a3b8", "灰 = 不可用"),
)


def legend_bar() -> str:
    """返回一行风险色图例。"""
    items = "".join(
        f'<span style="font-size:11px;color:{c};">● {t}</span>'
        for c, t in _LEGEND_ITEMS
    )
    return (
        '<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;'
        'padding:5px 9px;border-radius:6px;background:rgba(255,255,255,.02);'
        'border:1px solid rgba(255,255,255,.05);">{items}</div>'.format(items=items)
    )


# ── 空态汇总 ──────────────────────────────────────────────────────────
# 深度分析下的五个板块（供应链/叙事价值/传播网络/预测闭环）常常同时“暂无”，
# 各画一张 92px 的空卡片，加起来就是半屏空白。改为各自上报状态，
# 由页面在分节末尾统一 flush 成一条状态带。
#
# ❗必须是线程局部：PyWebIO 每个会话在自己的线程里渲染，模块级 list 会让
# 两个同时打开的页面把对方的空板块收进自己的状态带（A 页显示 B 页的「暂无」）。

_EMPTY_LOCAL = threading.local()


def _empty_buffer() -> list:
    buf = getattr(_EMPTY_LOCAL, "buf", None)
    if buf is None:
        buf = []
        _EMPTY_LOCAL.buf = buf
    return buf


def report_empty(icon: str, name: str, text: str, hint: str = "") -> None:
    """登记一个空板块，等 ``flush_empty_states`` 统一渲染。"""
    _empty_buffer().append({"icon": icon, "name": name, "text": text, "hint": hint})


def flush_empty_states(title: str = "暂无可展开内容") -> bool:
    """把已登记的空板块合并成一条状态带。返回是否渲染了内容。"""
    buffer = _empty_buffer()
    if not buffer:
        return False

    rows = "".join(
        f"""
        <div style="display: flex; gap: 8px; align-items: baseline; padding: 4px 0;">
            <span style="flex-shrink: 0;">{item['icon']}</span>
            <span style="font-size: 11px; color: #94a3b8; flex-shrink: 0;">{item['name']}</span>
            <span style="font-size: 11px; color: #64748b;">{item['text']}</span>
            <span style="font-size: 11px; color: #475569;">{item['hint']}</span>
        </div>
        """
        for item in buffer
    )
    count = len(buffer)
    buffer.clear()

    put_html(card(
        title=title,
        icon="🗂️",
        meta=f"{count} 个板块等待数据",
        body=f"<div>{rows}</div>",
    ))
    return True
