"""Jin10 重要事件组件

展示从金十数据获取的重要事件（Important News / topListItems）。

2026-10-19：改用统一卡片版式，正文与次要信息统一到 11px 下限。
"""

import os
import json
import time

from pywebio.output import put_html

from deva.naja.infra.ui.ui_style import format_timestamp

from .layout import card, empty_line


def _get_jin10_events_data(limit: int = 20):
    """获取 Jin10 重要事件数据"""
    try:
        from deva.naja.events import get_event_bus
        from deva.naja.events.text_events import TextFetchedEvent

        bus = get_event_bus()
        recent_events = bus.get_event_history('TextFetchedEvent', max_count=100)

        jin10_events = []
        for event in recent_events:
            if isinstance(event, TextFetchedEvent) and event.source == "jin10_important":
                jin10_events.append({
                    "title": event.title,
                    "text": event.text,
                    "source": event.source,
                    "url": event.url,
                    "timestamp": event.timestamp,
                    "datetime": format_timestamp(event.timestamp),
                })
                if len(jin10_events) >= limit:
                    break

        # 如果事件总线里没有，从文件缓存读取
        if not jin10_events:
            try:
                cache_file = os.path.expanduser("~/.naja/jin10_news.json")
                if os.path.exists(cache_file):
                    with open(cache_file, 'r') as f:
                        cached_news = json.load(f)
                    for news in cached_news[:limit]:
                        jin10_events.append({
                            "title": news.get('title', ''),
                            "text": news.get('title', ''),
                            "source": "jin10_important",
                            "url": f"https://www.jin10.com/news/{news.get('flash_id', '')}",
                            "timestamp": time.time(),
                            "datetime": news.get('display_time', ''),
                        })
            except Exception:
                pass

        return jin10_events
    except Exception:
        return []


def _get_wake_sync_handler():
    """获取 Jin10LiveNewsWakeSync 实例"""
    try:
        from deva.naja.state.system.wake_sync_manager import get_wake_sync_manager
        manager = get_wake_sync_manager()
        for handler in manager._handlers:
            if handler.__class__.__name__ == "Jin10LiveNewsWakeSync":
                return handler
    except Exception:
        pass
    return None


def render_jin10_events(ui):
    """渲染 Jin10 重要事件面板"""
    events = _get_jin10_events_data(limit=15)
    handler = _get_wake_sync_handler()

    cache_info = ""
    if handler:
        cache_info = f"缓存 <b>{len(handler._pushed_flash_ids)}</b> 条"

    if not events:
        put_html(card(
            title="金十重要事件",
            icon="📌",
            meta=cache_info,
            body=empty_line("暂无金十重要事件", "系统休眠 30 分钟后自动抓取"),
        ))
        return

    items = []
    for i, event in enumerate(events):
        is_new = i < 3
        bg_color = "rgba(249,115,22,0.10)" if is_new else "rgba(255,255,255,0.02)"
        border_color = "rgba(249,115,22,0.45)" if is_new else "rgba(255,255,255,0.08)"

        full_title = event.get("title", "") or ""
        full_text = event.get("text", "") or ""
        # ❗金十快讯的 text 常常就是标题的完整版（只差一两个字），
        # 排成两行等于同一句话写两遍：每条多 18px，15 条就是 270px 的纯重复。
        # 这里用前 24 字判「是不是同一句话」，是就只留标题。
        if full_text and full_title and (
            full_text.startswith(full_title[:24]) or full_title.startswith(full_text[:24])
        ):
            full_text = ""

        title = full_title[:50]
        text = full_text[:80]
        url = event.get("url", "")
        ts = event.get("datetime", "")[-8:]

        text_html = (
            f'<div style="font-size: 11px; color: #64748b; margin-top: 2px;'
            f' overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{text}</div>'
            if text else ""
        )

        link_html = (
            f'<a href="{url}" target="_blank" style="color: #f97316; font-size: 11px; '
            f'text-decoration: none; flex-shrink: 0;">🔗</a>' if url else ""
        )
        items.append(f"""
        <div style="display: flex; align-items: flex-start; gap: 8px; padding: 6px 10px;
                    background: {bg_color}; border-left: 3px solid {border_color};
                    border-radius: 4px; margin-bottom: 4px;">
            <div style="flex-shrink: 0; font-size: 11px; color: #64748b; min-width: 56px;">{ts}</div>
            <div style="flex: 1; min-width: 0;">
                <div style="font-size: 11px; color: #e2e8f0; line-height: 1.5;">{title}</div>
                {text_html}
            </div>
            {link_html}
        </div>
        """)

    # 概览区只负责「最近发生了什么」，给 6~7 条的高度即可，其余滚动查看。
    # 原来的 288px 会让这张卡固定吃掉 348px，跟它的信息量不成比例。
    body = f'<div style="max-height: 208px; overflow-y: auto;">{"".join(items)}</div>'

    put_html(card(
        title="金十重要事件",
        icon="📌",
        meta=f"{len(events)} 条 {('· ' + cache_info) if cache_info else ''}",
        body=body,
    ))
