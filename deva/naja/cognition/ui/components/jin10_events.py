"""
Jin10 重要事件组件

展示从金十数据获取的重要事件（Important News / topListItems）
"""

import time
from deva.naja.infra.ui.ui_style import format_timestamp


def _get_jin10_events_data(limit: int = 20):
    """获取 Jin10 重要事件数据"""
    try:
        from deva.naja.events import get_event_bus
        from deva.naja.events.text_events import TextFetchedEvent

        bus = get_event_bus()
        recent_events = getattr(bus, '_recent_events', [])

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
                import os
                import json
                from datetime import datetime
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
            except Exception as e:
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
    from pywebio.output import put_html

    events = _get_jin10_events_data(limit=15)
    handler = _get_wake_sync_handler()

    cache_info = ""
    if handler:
        cache_size = len(handler._pushed_flash_ids)
        cache_info = f" | 缓存 {cache_size} 条"

    if not events:
        empty_state = f"""
        <div style="text-align: center; padding: 20px; color: #64748b;">
            <div style="font-size: 32px; margin-bottom: 8px;">📌</div>
            <div style="font-size: 12px;">暂无金十重要事件</div>
            <div style="font-size: 10px; margin-top: 4px;">系统休眠 30 分钟后自动抓取{cache_info}</div>
        </div>
        """
        put_html(f"""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="font-size: 13px; font-weight: 600; color: #f97316;">
                    📌 金十重要事件
                </div>
                <div style="font-size: 10px; color: #64748b;">
                    {cache_info}
                </div>
            </div>
            {empty_state}
        </div>
        """)
        return

    event_items = ""
    for i, event in enumerate(events):
        is_new = i < 3
        bg_color = "rgba(249,115,22,0.1)" if is_new else "rgba(255,255,255,0.02)"
        border_color = "rgba(249,115,22,0.3)" if is_new else "rgba(255,255,255,0.05)"

        title = event.get("title", "")[:50]
        text = event.get("text", "")[:80]
        url = event.get("url", "")
        ts = event.get("datetime", "")[-8:]

        link_html = f'<a href="{url}" target="_blank" style="color: #f97316; font-size: 9px;">🔗</a>' if url else ""

        event_items += f"""
        <div style="
            display: flex;
            align-items: flex-start;
            gap: 8px;
            padding: 8px 10px;
            background: {bg_color};
            border-left: 3px solid {border_color};
            border-radius: 4px;
            margin-bottom: 6px;
        ">
            <div style="flex-shrink: 0; font-size: 10px; color: #64748b; min-width: 55px;">{ts}</div>
            <div style="flex: 1; min-width: 0;">
                <div style="font-size: 11px; color: #f1f5f9; line-height: 1.4;">{title}</div>
                <div style="font-size: 9px; color: #64748b; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{text}</div>
            </div>
            {link_html}
        </div>
        """

    put_html(f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 16px;">📌</span>
                <div style="font-size: 13px; font-weight: 600; color: #f97316;">
                    金十重要事件
                </div>
                <span style="font-size: 10px; color: #64748b; background: rgba(249,115,22,0.15); padding: 2px 6px; border-radius: 4px;">
                    {len(events)} 条
                </span>
            </div>
            <div style="font-size: 10px; color: #64748b;">
                {cache_info}
            </div>
        </div>
        <div style="max-height: 300px; overflow-y: auto;">
            {event_items}
        </div>
    </div>
    """)
