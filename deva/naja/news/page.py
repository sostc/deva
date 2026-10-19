"""今日新闻消化独立页面（``/news``）

═══════════════════════════════════════════════════════════════════════════
为什么从 ``/awakening`` 拆出来
═══════════════════════════════════════════════════════════════════════════

觉醒页回答的是「系统此刻怎么想」（manas 三维、决策计划、门审计），新闻消化
回答的是「今天该读什么」——两者的**刷新节奏**和**信息密度**完全不同，混在
一页里，新闻只能挤成一块 64 字截断的紧凑面板，条目一多就没法读。

拆出来后这里用**报告级呈现**（卡片 + 相关度条 + 命中标签 + 分组），也就是
归档文件 ``~/.naja/news_digest/YYYY-MM-DD.html`` 的那套 UI —— 同一份
``render_digest_fragment()``，不会出现「网页和我存下来的报告长得不一样」。

═══════════════════════════════════════════════════════════════════════════
实现约定
═══════════════════════════════════════════════════════════════════════════

* **每次 ``put_html`` 都传完整闭合片段**（详见 ``news/ui.py`` 头部）；
  ``render_digest_fragment()`` 已经把 ``<style>`` 和正文拼成一个字符串，
  这里不再拆开输出。
* **按钮回调里重绘整块 scope**，不做局部 patch。
* **消化报告的数据只走 ``get_news_digest_summary()``**（纯 dict）；UI 不碰
  ``NewsTriage`` / ``NewsFocusState``。取不到就显示 ``reason``，绝不编造。
* 顶部另有一块**金十实时快讯**（``news/jin10.py``），是未消化的原始流，
  ❗**不受** 24/48/72h 窗口影响 —— 面板里写明了，别让人当成窗口失灵。
"""

from __future__ import annotations

import html
import logging
from typing import Any, Dict

from pywebio.output import clear, put_buttons, put_html, put_scope, toast, use_scope

log = logging.getLogger(__name__)

ROOT_SCOPE = "news_digest_page_root"
HEAD_SCOPE = "news_digest_page_head"
BODY_SCOPE = "news_digest_page_body"

#: 可切换的时间窗口（小时）。24 是默认——「今日」就是这个意思。
WINDOWS = (24, 48, 72)
DEFAULT_WINDOW = 24


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _head_html(hours: int) -> str:
    """页面标题。

    ❗配色按**实测**来：站点正文是**白底**（`ui_theme.get_global_styles()` 里那个
    深色 `body_bg` 并没有真正生效，只有顶部导航条是深色）。第一版按深色底写了
    浅色字（`#f1f5f9`），结果白底白字 —— 标题直接看不见。
    """
    return (
        '<div style="display:flex;align-items:flex-start;justify-content:space-between;'
        'gap:16px;flex-wrap:wrap;margin:4px 0 14px;">'
        '<div>'
        '<div style="font-size:20px;font-weight:600;color:#0f172a;">📰 今日新闻消化</div>'
        '<div style="font-size:12px;color:#64748b;margin-top:4px;">'
        f"最近 {_esc(hours)} 小时已评分新闻 · 持仓优先排序 · "
        "同一事件已合并（标 <b>×N</b> 的是同一条的不同版本/语种）"
        "</div></div>"
        '<div style="display:flex;align-items:center;gap:16px;">'
        '<a href="/focusadmin" style="font-size:12px;color:#1d4ed8;'
        'text-decoration:none;">⚙️ 关注设置</a>'
        '<a href="/awakening" style="font-size:12px;color:#1d4ed8;'
        'text-decoration:none;">← 回觉醒页</a>'
        "</div>"
        "</div>"
    )


def _error_html(exc: BaseException) -> str:
    return (
        '<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:10px;'
        'padding:14px;max-width:880px;margin:0 auto;">'
        '<div style="font-size:13px;font-weight:600;color:#b91c1c;">'
        f"报告生成失败：{_esc(type(exc).__name__)}</div>"
        f'<div style="font-size:12px;color:#7f1d1d;margin-top:4px;">{_esc(exc)}</div>'
        "</div>"
    )


def _render_jin10() -> None:
    """金十实时快讯面板（新闻页顶部）。

    2026-10-19 从认知页搬来：它是一条**未经消化的原始快讯流**，放在认知页
    「概览」里会被误读成认知产出。这里与消化报告同页，一屏能看到
    「刚刚发生」和「今天该读什么」。
    """
    try:
        from deva.naja.news.jin10 import render_jin10_fragment

        put_html(render_jin10_fragment())
    except Exception:  # pragma: no cover - 快讯流挂了不该连累报告
        log.exception("[NewsDigestPage] 金十快讯面板渲染失败")


def _render_body(hours: int) -> None:
    """渲染报告正文（含样式，一次性 put_html）。"""
    from deva.naja.news.digest import get_news_digest_summary, render_digest_fragment

    _render_jin10()
    try:
        digest = get_news_digest_summary(hours=hours)
        put_html(render_digest_fragment(digest))
    except Exception as exc:  # pragma: no cover - 防御（get_news_digest_summary 已兜一层）
        log.exception("[NewsDigestPage] 渲染失败")
        put_html(_error_html(exc))


def _save_digest(hours: int) -> None:
    """把当前窗口的报告落成今天的归档文件（与定时任务同一产出口径）。"""
    from deva.naja.news.digest import get_news_digest_summary, write_daily_digest

    try:
        path = write_daily_digest(get_news_digest_summary(hours=hours))
        toast(f"已保存：{path}", color="success")
    except Exception as exc:
        log.exception("[NewsDigestPage] 保存归档失败")
        toast(f"保存失败：{type(exc).__name__}: {exc}", color="error")


def _dispatch(value: str, state: Dict[str, Any], repaint) -> None:
    """按钮回调（同步入口）。"""
    if value.startswith("win:"):
        state["hours"] = int(value.split(":", 1)[1])
        repaint()
    elif value == "refresh":
        repaint()
    elif value == "save":
        from pywebio.session import run_async

        # 落盘是 I/O：投到异步执行，别卡住按钮回调
        run_async(_save_async(state["hours"]))
    else:  # pragma: no cover - 按钮值是代码内常量
        log.warning("[NewsDigestPage] 未知按钮值: %s", value)


async def _save_async(hours: int) -> None:
    _save_digest(hours)


def render_news_digest_page(ctx: Dict[str, Any] | None = None) -> None:
    """渲染「今日新闻消化」页（同步；按钮回调内重绘 scope）。"""
    state: Dict[str, Any] = {"hours": DEFAULT_WINDOW}

    def repaint() -> None:
        with use_scope(HEAD_SCOPE, clear=True):
            put_html(_head_html(state["hours"]))
            put_buttons(
                [
                    {"label": "🔄 刷新", "value": "refresh", "color": "primary"},
                    *[
                        {
                            "label": f"{h}h",
                            "value": f"win:{h}",
                            "color": "primary" if h == state["hours"] else "secondary",
                        }
                        for h in WINDOWS
                    ],
                    {"label": "💾 存今日 HTML", "value": "save", "color": "info"},
                ],
                onclick=lambda v: _dispatch(v, state, repaint),
                small=True,
            )
        with use_scope(BODY_SCOPE, clear=True):
            _render_body(state["hours"])

    clear(ROOT_SCOPE)
    with use_scope(ROOT_SCOPE):
        put_scope(HEAD_SCOPE)
        put_scope(BODY_SCOPE)
    repaint()


__all__ = ["render_news_digest_page", "ROOT_SCOPE"]
