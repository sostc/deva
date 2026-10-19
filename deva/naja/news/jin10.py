"""金十重要事件 —— 取数与展示片段（``/news`` 页）

═══════════════════════════════════════════════════════════════════════════
为什么从认知页搬到这里
═══════════════════════════════════════════════════════════════════════════

它展示的是**原始新闻快讯流**（金十 important 快讯），不是认知层加工出来的
结论。认知页的「概览」分节回答的是「系统此刻看到了什么/得出了什么」，把一条
未经消化的外部新闻流放在那里，既占 268px，又让人误以为它是认知产出。
新闻页才是它的家——和「今日新闻消化」报告放在一起，一屏能看到「刚刚发生」
和「今天该读什么」。

═══════════════════════════════════════════════════════════════════════════
❗配色：白底
═══════════════════════════════════════════════════════════════════════════

站点正文是**白底**（``ui_theme.get_global_styles()`` 里的深色 ``body_bg``
并没有真正生效）；只有认知页自己用 ``body.webio-theme-default !important``
强制了深色。所以这里全部按浅色底写深色字 —— 直接把认知页那段深色卡片搬
过来会变成**白底白字**，整块看不见。

═══════════════════════════════════════════════════════════════════════════
取数两条路（与搬移前一致）
═══════════════════════════════════════════════════════════════════════════

1. 事件总线里的 ``TextFetchedEvent(source="jin10_important")``（实时）
2. 拿不到时回落文件缓存 ``~/.naja/jin10_news.json``

两条都拿不到就返回空列表，由调用方显示空态。**绝不编造条目**。
"""

from __future__ import annotations

import json
import logging
import os
import time

log = logging.getLogger(__name__)

#: 展示条数上限。快讯流刷新很快，超过这个数在页面上没有意义。
DEFAULT_LIMIT = 15


def _get_wake_sync_handler():
    """取 ``Jin10LiveNewsWakeSync`` 实例（用于显示已推送缓存条数）。"""
    try:
        from deva.naja.state.system.wake_sync_manager import get_wake_sync_manager

        manager = get_wake_sync_manager()
        for handler in manager._handlers:
            if handler.__class__.__name__ == "Jin10LiveNewsWakeSync":
                return handler
    except Exception:  # pragma: no cover - 拿不到只是少显示一条缓存计数
        pass
    return None


def get_jin10_important_events(limit: int = DEFAULT_LIMIT) -> list:
    """返回金十重要事件列表（按总线倒序，最新的在前）。

    每项：``{title, text, url, timestamp, datetime}``。
    """
    try:
        from deva.naja.events import get_event_bus
        from deva.naja.events.text_events import TextFetchedEvent
        from deva.naja.infra.ui.ui_style import format_timestamp

        bus = get_event_bus()
        recent_events = bus.get_event_history("TextFetchedEvent", max_count=100)

        events = []
        for event in recent_events:
            if isinstance(event, TextFetchedEvent) and event.source == "jin10_important":
                events.append(
                    {
                        "title": event.title,
                        "text": event.text,
                        "url": event.url,
                        "timestamp": event.timestamp,
                        "datetime": format_timestamp(event.timestamp),
                    }
                )
                if len(events) >= limit:
                    break
        if events:
            return events
    except Exception:
        log.debug("[Jin10Panel] 事件总线取数失败，回落文件缓存", exc_info=True)

    # ── 回落：文件缓存 ──────────────────────────────────────────────
    try:
        cache_file = os.path.expanduser("~/.naja/jin10_news.json")
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                cached_news = json.load(f)
            return [
                {
                    "title": news.get("title", ""),
                    # ❗Jin10ImportantNews 没有正文字段，缓存里也只有 title。
                    # 这里不再复制一份当 text —— 展示端按「前 24 字判同」折叠，
                    # 复制过来等于同一句话写两遍。
                    "text": "",
                    "url": f"https://www.jin10.com/news/{news.get('flash_id', '')}",
                    "timestamp": time.time(),
                    "datetime": news.get("display_time", ""),
                }
                for news in cached_news[:limit]
            ]
    except Exception:
        log.debug("[Jin10Panel] 文件缓存读取失败", exc_info=True)

    return []


def render_jin10_fragment(limit: int = DEFAULT_LIMIT, hours_text: str = "") -> str:
    """返回「📌 金十重要事件」面板的完整 HTML 片段（一次性闭合）。

    ``hours_text`` 用于说明这个面板**不受**上方时间窗口按钮影响 ——
    快讯流是实时流，不是 24/48/72h 的消化报告，不说明会被当成窗口失灵。
    """
    import html as _html

    def esc(value) -> str:
        return _html.escape(str(value if value is not None else ""))

    events = get_jin10_important_events(limit=limit)
    handler = _get_wake_sync_handler()
    cache_info = f"已推送缓存 {len(handler._pushed_flash_ids)} 条" if handler else ""

    head_sub = " · ".join(x for x in (hours_text, cache_info) if x)

    if not events:
        return (
            '<div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;'
            'padding:14px 16px;margin:0 0 16px;">'
            '<div style="display:flex;align-items:baseline;justify-content:space-between;gap:12px;">'
            '<div style="font-size:13px;font-weight:600;color:#0f172a;">📌 金十重要事件</div>'
            f'<div style="font-size:11px;color:#94a3b8;">{esc(head_sub)}</div>'
            "</div>"
            '<div style="margin-top:8px;font-size:12px;color:#64748b;">'
            "暂无金十重要事件 · 系统休眠 30 分钟后自动抓取"
            "</div>"
            "</div>"
        )

    items = []
    for i, event in enumerate(events):
        is_new = i < 3
        bg = "#fff7ed" if is_new else "#f8fafc"
        border = "#fb923c" if is_new else "#e2e8f0"

        full_title = event.get("title", "") or ""
        full_text = event.get("text", "") or ""
        # ❗金十快讯的 text 常常就是标题的完整版（只差一两个字），
        # 排成两行等于同一句话写两遍：每条多 18px，15 条就是 270px 的纯重复。
        # 但**不能整条删掉**：text 常是「标题 + 补充」，比如
        #     title: 芝商所将推出钨期货
        #     text : 芝商所将推出钨期货，最迟于 2027 年第一季度初开始交易
        # 整条丢掉就把「最迟 2027Q1」这个真信息弄没了。
        # 所以只剪掉与标题重叠的那一段，保留**多出来的尾部**。
        if full_text and full_title:
            head_n = min(len(full_title), 24)
            if full_text[:head_n] == full_title[:head_n]:
                tail = full_text[len(full_title):].lstrip("，,。:：;； ")
                # 尾部太短（<4 字）没有信息量，不值得多占一行
                full_text = tail if len(tail) >= 4 else ""
            elif full_title[:head_n] == full_text[:head_n]:
                full_text = ""

        title = esc(full_title[:50])
        text = esc(full_text[:80])
        url = event.get("url", "") or ""
        ts = esc((event.get("datetime", "") or "")[-8:])

        text_html = (
            '<div style="font-size:11px;color:#64748b;margin-top:2px;'
            f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{text}</div>'
            if text
            else ""
        )
        link_html = (
            f'<a href="{esc(url)}" target="_blank" rel="noopener" '
            'style="color:#1d4ed8;font-size:11px;text-decoration:none;flex-shrink:0;">🔗</a>'
            if url
            else ""
        )
        items.append(
            '<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 10px;'
            f'background:{bg};border-left:3px solid {border};'
            'border-radius:4px;margin-bottom:4px;">'
            f'<div style="flex-shrink:0;font-size:11px;color:#64748b;min-width:56px;">{ts}</div>'
            '<div style="flex:1;min-width:0;">'
            f'<div style="font-size:12px;color:#0f172a;line-height:1.5;">{title}</div>'
            f"{text_html}"
            "</div>"
            f"{link_html}"
            "</div>"
        )

    return (
        '<div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;'
        'padding:14px 16px;margin:0 0 16px;">'
        '<div style="display:flex;align-items:baseline;justify-content:space-between;gap:12px;">'
        '<div style="font-size:13px;font-weight:600;color:#0f172a;">📌 金十重要事件</div>'
        f'<div style="font-size:11px;color:#94a3b8;">{len(events)} 条 · {esc(head_sub)}</div>'
        "</div>"
        '<div style="font-size:11px;color:#64748b;margin-top:2px;">'
        "实时快讯流，不随上方时间窗口变化</div>"
        f'<div style="max-height:208px;overflow-y:auto;margin-top:8px;">{"".join(items)}</div>'
        "</div>"
    )


__all__ = ["get_jin10_important_events", "render_jin10_fragment", "DEFAULT_LIMIT"]
