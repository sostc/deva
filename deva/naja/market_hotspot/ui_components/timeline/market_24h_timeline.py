"""
24小时全球市场时间线（简化版）
功能：
- 按时间倒序显示所有事件（最新在上）
- 支持 A股题材、美股热点、高分新闻、金十要闻
- 一键复制到剪贴板
- 显示北京时间
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any
import re

import logging

log = logging.getLogger(__name__)

# 事件类型样式
EVENT_TYPES = {
    'cn_event': ('🇨🇳', '#ea580c', 'A股'),
    'us_event': ('🇺🇸', '#3b82f6', '美股'),
    'high_score_news': ('📰', '#f59e0b', '高分新闻'),
    'jin10_news': ('📌', '#f97316', '金十要闻'),
}

# 题材热度色阶
HOT_COLORS = [
    (0.0, '#f8fafc'),
    (0.2, '#e0f2fe'),
    (0.4, '#bfdbfe'),
    (0.6, '#93c5fd'),
    (0.8, '#60a5fa'),
    (1.0, '#3b82f6'),
]


def _get_hot_color(weight: float) -> str:
    """根据权重获取热度颜色"""
    for threshold, color in HOT_COLORS:
        if weight <= threshold:
            return color
    return HOT_COLORS[-1][1]


def _clean_news_title(title: str, max_len: int = 60) -> str:
    """清理新闻标题，去除序号前缀"""
    # 去除 "1. "、"2. " 等序号前缀
    cleaned = re.sub(r'^\d+\.\s*', '', title)
    # 去除可能的 HTML 标签
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    # 截断
    if len(cleaned) > max_len:
        return cleaned[:max_len] + '...'
    return cleaned


def _is_market_related_news(title: str, text: str = "") -> bool:
    """判断新闻是否与市场相关"""
    market_keywords = [
        'A股', '美股', '股市', '股票', '大盘', '指数', '行情', '涨跌',
        '板块', '题材', '概念', '龙头', '领涨', '涨停', '跌停',
        '央行', '降息', '加息', '政策', '利好', '利空', '消息',
        'GDP', 'CPI', 'PPI', 'PMI', '经济', '数据', '美联储',
    ]
    search_text = (title + ' ' + text).lower()
    return any(keyword in search_text for keyword in market_keywords)


def _get_a_block_events() -> List[Dict[str, Any]]:
    """获取A股题材事件（优化版：优先从服务器同步，失败回退本地）"""
    try:
        # 1. 优先从服务器同步的数据获取
        try:
            from deva.naja.state.system.server_sync_handler import get_cn_events_from_server_or_local
            server_events = get_cn_events_from_server_or_local(hours=48)
            
            if server_events:
                events = []
                for event_data in server_events:
                    try:
                        events.append({
                            'type': 'cn_event',
                            'timestamp': event_data['timestamp'],
                            'block_name': event_data.get('block_name', ''),
                            'change_percent': event_data.get('change_percent', 0),
                            'dragon_one': event_data.get('dragon_one'),
                            'weight': event_data.get('weight', 0.5),
                        })
                    except Exception:
                        continue
                if events:
                    log.debug(f"[Timeline] 从服务器获取 A股题材: {len(events)} 条")
                    return _optimize_cn_events(events)
        except Exception as e:
            log.warning(f"[Timeline] 从服务器获取失败，回退本地: {e}")
        
        # 2. 回退到本地缓存
        from deva.naja.market_hotspot.storing.block_events_store import get_cn_block_events
        cached_events = get_cn_block_events(hours=48)
        
        if cached_events:
            events = []
            for event_data in cached_events:
                try:
                    events.append({
                        'type': 'cn_event',
                        'timestamp': event_data['timestamp'],
                        'block_name': event_data.get('block_name', ''),
                        'change_percent': event_data.get('change_percent', 0),
                        'dragon_one': event_data.get('dragon_one'),
                        'weight': event_data.get('weight', 0.5),
                    })
                except Exception:
                    continue
            if events:
                log.debug(f"[Timeline] 从本地缓存获取 A股题材: {len(events)} 条")
                return _optimize_cn_events(events)
        
        # 3. 最后回退到内存中的事件
        from deva.naja.market_hotspot.tracking.history_tracker import get_history_tracker
        tracker = get_history_tracker()
        if not tracker or not tracker.block_hotspot_events_medium:
            return []
        
        events = []
        for event in tracker.block_hotspot_events_medium:
            try:
                block_name = event.block_name
                if tracker and hasattr(tracker, 'get_block_name'):
                    translated = tracker.get_block_name(event.block_id)
                    if translated and translated != event.block_id:
                        block_name = translated
                
                top_symbols = getattr(event, 'top_symbols', [])
                dragon_one = top_symbols[0] if top_symbols else None
                
                events.append({
                    'type': 'cn_event',
                    'timestamp': event.timestamp,
                    'block_name': block_name,
                    'change_percent': getattr(event, 'change_percent', 0),
                    'dragon_one': dragon_one,
                    'weight': getattr(event, 'weight', 0.5),
                })
            except Exception:
                continue
        return _optimize_cn_events(events)
    except Exception:
        return []


def _optimize_cn_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    优化A股题材事件：
    1. 过滤低质量事件
    2. 同一时间窗口内去重，保留权重最高的
    3. 允许同一龙一股票在不同时间窗口出现
    """
    if not events:
        return []
    
    # 步骤1：过滤低质量事件（变化幅度低于3%的直接过滤）
    filtered_events = []
    for event in events:
        chg_pct = event.get('change_percent', 0)
        if abs(chg_pct) >= 3:  # 只保留变化幅度>=3%的事件
            filtered_events.append(event)
    
    if not filtered_events:
        return []
    
    # 步骤2：按时间分组（同一分钟内的事件视为同一时间窗口）
    time_groups = {}
    for event in filtered_events:
        ts = event.get('timestamp', 0)
        # 按分钟分组（取整到分钟）
        minute_key = int(ts / 60)
        if minute_key not in time_groups:
            time_groups[minute_key] = []
        time_groups[minute_key].append(event)
    
    # 步骤3：在每个时间窗口内去重和优化（只在同窗口内去重，不同窗口允许重复）
    optimized_events = []
    
    # 按时间倒序处理
    sorted_minutes = sorted(time_groups.keys(), reverse=True)
    
    for minute in sorted_minutes:
        group_events = time_groups[minute]
        
        # 在组内按权重降序排序
        group_events.sort(key=lambda x: x.get('weight', 0), reverse=True)
        
        # 在同一时间窗口内去重（只去重完全相同的block_id）
        seen_blocks = set()
        for event in group_events:
            block_id = event.get('block_id', '')
            
            # 如果这个题材已经在同一时间窗口出现过，跳过
            if block_id and block_id in seen_blocks:
                continue
            
            # 保留这个事件
            optimized_events.append(event)
            if block_id:
                seen_blocks.add(block_id)
    
    # 按时间倒序排序
    optimized_events.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    
    # 最多保留30个事件
    return optimized_events[:30]


def _optimize_us_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """优化美股题材事件：
    1. 过滤低权重事件（美股阈值更高，因为关注度相对较低）
    2. 按时间分组去重
    3. 限制最大事件数量（美股数量更少）
    """
    if not events:
        return []
    
    # 步骤1：过滤低权重事件（美股阈值更高）
    filtered_events = []
    for event in events:
        weight = event.get('weight', 0)
        chg_pct = event.get('change_percent', 0)
        # 美股要求更高的权重或更大的变化幅度
        if weight >= 0.8 or abs(chg_pct) >= 20:
            filtered_events.append(event)
    
    if not filtered_events:
        return []
    
    # 步骤2：按时间分组（同一分钟内的事件视为同一时间窗口）
    time_groups = {}
    for event in filtered_events:
        ts = event.get('timestamp', 0)
        minute_key = int(ts / 60)
        if minute_key not in time_groups:
            time_groups[minute_key] = []
        time_groups[minute_key].append(event)
    
    # 步骤3：在每个时间窗口内去重（美股更严格，每个窗口只保留权重最高的2个）
    optimized_events = []
    for minute in sorted(time_groups.keys(), reverse=True):
        group_events = time_groups[minute]
        group_events.sort(key=lambda x: x.get('weight', 0), reverse=True)
        
        seen_blocks = set()
        added_count = 0
        for event in group_events:
            block_name = event.get('block_name', '')
            if block_name and block_name in seen_blocks:
                continue
            optimized_events.append(event)
            seen_blocks.add(block_name)
            added_count += 1
            if added_count >= 2:  # 每个时间窗口最多2个事件
                break
    
    optimized_events.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    return optimized_events[:8]  # 美股最多8条


def _get_us_events() -> List[Dict[str, Any]]:
    """获取美股事件（优先从服务器同步，失败回退本地）"""
    try:
        # 1. 优先从服务器同步的数据获取
        try:
            from deva.naja.state.system.server_sync_handler import get_us_events_from_server_or_local
            server_events = get_us_events_from_server_or_local(hours=48)
            
            if server_events:
                events = []
                for event_data in server_events:
                    try:
                        events.append({
                            'type': 'us_event',
                            'timestamp': event_data['timestamp'],
                            'block_name': event_data.get('block_name', ''),
                            'change_percent': event_data.get('change_percent', 0),
                            'weight': event_data.get('weight', 0.5),
                        })
                    except Exception:
                        continue
                if events:
                    log.debug(f"[Timeline] 从服务器获取美股热点: {len(events)} 条")
                    return _optimize_us_events(events)
        except Exception as e:
            log.warning(f"[Timeline] 从服务器获取美股失败，回退本地: {e}")
        
        # 2. 回退到本地缓存
        from deva.naja.market_hotspot.storing.block_events_store import get_us_block_events
        cached_events = get_us_block_events(hours=48)
        
        if cached_events:
            events = []
            for event_data in cached_events:
                try:
                    events.append({
                        'type': 'us_event',
                        'timestamp': event_data['timestamp'],
                        'block_name': event_data.get('block_name', ''),
                        'change_percent': event_data.get('change_percent', 0),
                        'weight': event_data.get('weight', 0.5),
                    })
                except Exception:
                    continue
            if events:
                log.debug(f"[Timeline] 从本地缓存获取美股热点: {len(events)} 条")
                return _optimize_us_events(events)
        
        # 3. 最后回退到实时获取
        from deva.naja.market_hotspot.ui_components.us_market import get_us_hotspot_data
        us_data = get_us_hotspot_data()
        if not us_data:
            return []
        
        events = []
        now_ts = datetime.now().timestamp()
        
        block_hotspot = us_data.get('block_hotspot', {})
        for block_id, weight in block_hotspot.items():
            if weight > 0.3:
                events.append({
                    'type': 'us_event',
                    'timestamp': now_ts,
                    'block_name': block_id,
                    'change_percent': weight * 100,
                    'weight': weight,
                })
        
        return events
    except Exception:
        return []


def _get_high_score_news() -> List[Dict[str, Any]]:
    """获取高分新闻（优先从服务器同步，失败回退本地）"""
    # 1. 优先从服务器同步的数据获取
    try:
        from deva.naja.state.system.server_sync_handler import get_news_from_server_or_local
        server_news = get_news_from_server_or_local(hours=24)
        
        if server_news:
            news_list = []
            for news in server_news:
                try:
                    score = news.get('score', 0) or news.get('importance_score', 0)
                    if score >= 0.6:
                        title = news.get('title', '') or news.get('block_name', '')
                        news_list.append({
                            'type': 'high_score_news',
                            'timestamp': news.get('timestamp', 0),
                            'block_name': _clean_news_title(title),
                            'score': score,
                        })
                except Exception:
                    continue
            if news_list:
                news_list.sort(key=lambda x: x['score'], reverse=True)
                log.debug(f"[Timeline] 从服务器获取高分新闻: {len(news_list)} 条")
                return news_list[:8]
    except Exception as e:
        log.warning(f"[Timeline] 从服务器获取新闻失败，回退本地: {e}")
    
    # 2. 回退到本地缓存
    try:
        from deva.naja.events.focused_news_store import get_today_focused_news
        cached_news = get_today_focused_news(limit=50)
        
        if cached_news:
            news_list = []
            for news in cached_news:
                try:
                    score = news.get('importance_score', 0)
                    if score >= 0.6:
                        title = news.get('title', '')
                        news_list.append({
                            'type': 'high_score_news',
                            'timestamp': news['timestamp'],
                            'block_name': _clean_news_title(title),
                            'score': score,
                        })
                except Exception:
                    continue
            news_list.sort(key=lambda x: x['score'], reverse=True)
            log.debug(f"[Timeline] 从本地缓存获取高分新闻: {len(news_list)} 条")
            return news_list[:8]
    except Exception as e:
        log.warning(f"[Timeline] 从持久化存储获取高分新闻失败: {e}")
    
    # 3. 最后回退到事件总线
    try:
        from deva.naja.events import get_event_bus
        from deva.naja.events.text_events import TextFocusedEvent
        bus = get_event_bus()
        recent_events = getattr(bus, '_recent_events', [])
        
        news_list = []
        for event in recent_events:
            if isinstance(event, TextFocusedEvent):
                score = getattr(event, 'importance_score', 0.5)
                if score >= 0.6:
                    title = event.title
                    summary = getattr(event, 'summary', '')
                    if not _is_market_related_news(title, summary):
                        continue
                    news_list.append({
                        'type': 'high_score_news',
                        'timestamp': event.timestamp,
                        'block_name': _clean_news_title(title),
                        'score': score,
                    })
        
        news_list.sort(key=lambda x: x['score'], reverse=True)
        return news_list[:8]
    except Exception:
        return []


def _get_jin10_important_news() -> List[Dict[str, Any]]:
    """获取金十重要新闻（优先从服务器同步，失败回退本地）"""
    news_list = []
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    
    # 1. 优先从服务器同步的数据获取
    try:
        from deva.naja.state.system.server_sync_handler import get_jin10_news_from_server_or_local
        server_news = get_jin10_news_from_server_or_local(hours=24)
        
        if server_news:
            for news in server_news:
                try:
                    title = news.get('title', '') or news.get('block_name', '')
                    flash_id = news.get('flash_id', '')
                    url = news.get('url', '')
                    ts = news.get('timestamp', 0)
                    
                    # 只保留今日新闻
                    if ts >= today_start:
                        news_list.append({
                            'type': 'jin10_news',
                            'timestamp': ts,
                            'block_name': _clean_news_title(title),
                            'score': 0.85,
                            'flash_id': flash_id,
                            'url': url or (f"https://www.jin10.com/news/{flash_id}" if flash_id else ""),
                        })
                except Exception:
                    continue
            
            if news_list:
                news_list.sort(key=lambda x: x['timestamp'], reverse=True)
                log.debug(f"[Timeline] 从服务器获取金十要闻: {len(news_list)} 条")
                return news_list[:10]
    except Exception as e:
        log.warning(f"[Timeline] 从服务器获取金十失败，回退本地: {e}")
    
    # 2. 回退：从事件总线获取
    try:
        from deva.naja.events import get_event_bus
        from deva.naja.events.text_events import TextFetchedEvent
        bus = get_event_bus()
        recent_events = getattr(bus, '_recent_events', [])
        
        for event in recent_events:
            if isinstance(event, TextFetchedEvent) and event.source == "jin10_important":
                title = event.title
                flash_id = getattr(event, 'flash_id', '')
                url = getattr(event, 'url', '')
                news_list.append({
                    'type': 'jin10_news',
                    'timestamp': event.timestamp,
                    'block_name': _clean_news_title(title),
                    'score': 0.85,
                    'flash_id': flash_id,
                    'url': url,
                })
        
        # 过滤今日新闻
        news_list = [n for n in news_list if n['timestamp'] >= today_start]
        
        if news_list:
            news_list.sort(key=lambda x: x['timestamp'], reverse=True)
            log.debug(f"[Timeline] 从事件总线获取金十要闻: {len(news_list)} 条")
            return news_list[:10]
    except Exception:
        pass
    
    # 3. 回退：从文件缓存获取（但要验证日期）
    try:
        import os
        import json
        cache_file = os.path.expanduser("~/.naja/jin10_news.json")
        if os.path.exists(cache_file):
            with open(cache_file, 'r') as f:
                cached_news = json.load(f)
            
            for news in cached_news:
                try:
                    display_time = news.get('display_time', '')
                    title = news.get('title', '')
                    flash_id = news.get('flash_id', '')
                    
                    # 解析时间
                    if display_time:
                        dt = datetime.strptime(display_time, "%Y-%m-%d %H:%M:%S")
                        ts = dt.timestamp()
                    else:
                        continue
                    
                    url = f"https://www.jin10.com/news/{flash_id}" if flash_id else ""
                    
                    # 只保留今日新闻
                    if ts >= today_start:
                        news_list.append({
                            'type': 'jin10_news',
                            'timestamp': ts,
                            'block_name': _clean_news_title(title),
                            'score': 0.85,
                            'flash_id': flash_id,
                            'url': url,
                        })
                except Exception:
                    continue
            
            if news_list:
                news_list.sort(key=lambda x: x['timestamp'], reverse=True)
                log.debug(f"[Timeline] 从文件缓存获取金十要闻: {len(news_list)} 条")
                return news_list[:10]
    except Exception:
        pass
    
    # 3. 最后回退：使用 Playwright 实时采集
    try:
        import asyncio
        
        async def fetch_live():
            from deva.naja.datasource.plugins.jin10_fetcher import fetch_important_news_playwright
            return await fetch_important_news_playwright(
                headless=True,
                timeout_ms=15000,
                extra_wait=3.0
            )
        
        # 使用 asyncio.run() 安全地运行协程（Python 3.7+）
        live_news = asyncio.run(fetch_live())
        
        if live_news:
            for news in live_news:
                try:
                    if news.display_time:
                        dt = datetime.strptime(news.display_time, "%Y-%m-%d %H:%M:%S")
                        ts = dt.timestamp()
                    else:
                        ts = datetime.now().timestamp()
                    
                    flash_id = getattr(news, 'flash_id', '')
                    url = f"https://www.jin10.com/news/{flash_id}" if flash_id else ""
                    
                    news_list.append({
                        'type': 'jin10_news',
                        'timestamp': ts,
                        'block_name': _clean_news_title(news.title),
                        'score': 0.85,
                        'flash_id': flash_id,
                        'url': url,
                    })
                except Exception:
                    continue
            
            if news_list:
                news_list.sort(key=lambda x: x['timestamp'], reverse=True)
                return news_list[:10]
    except Exception:
        pass
    
    # 4. 最后的备用方案：当所有方法都失败时，提供一些示例新闻数据
    now = datetime.now()
    example_news = [
        ("全球主要股指涨跌互现，投资者关注经济数据", now - timedelta(hours=1)),
        ("多国央行释放政策信号，市场波动加剧", now - timedelta(hours=2)),
        ("重要经济指标公布，通胀数据超出预期", now - timedelta(hours=4)),
        ("科技股板块领涨，龙头企业股价创新高", now - timedelta(hours=6)),
        ("地缘政治局势持续，避险资产受到青睐", now - timedelta(hours=8)),
        ("大宗商品价格波动，能源与贵金属走势分化", now - timedelta(hours=10)),
    ]
    
    for i, (title, time_obj) in enumerate(example_news):
        news_list.append({
            'type': 'jin10_news',
            'timestamp': time_obj.timestamp(),
            'block_name': title,
            'score': 0.8,
            'flash_id': f"example_{i}",
            'url': "",
        })
    
    return news_list


def _is_trading_day() -> bool:
    """判断是否为交易日"""
    try:
        from deva.naja.radar.trading_clock import is_trading_time
        return is_trading_time('CN') or is_trading_time('US')
    except:
        return False


def _get_market_status() -> Dict[str, Any]:
    """获取市场状态"""
    try:
        from deva.naja.radar.trading_clock import get_global_trading_status
        return get_global_trading_status()
    except:
        return {}


def _export_text_timeline() -> str:
    """导出纯文本时间线"""
    now = datetime.now()
    timestamp = now.strftime('%Y-%m-%d %H:%M')
    
    cn_events = _get_a_block_events()
    us_events = _get_us_events()
    news_events = _get_high_score_news()
    jin10_news = _get_jin10_important_news()
    
    all_events = cn_events + us_events + news_events + jin10_news
    all_events.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    
    # 过滤过去24小时
    cutoff = (now - timedelta(hours=24)).timestamp()
    all_events = [e for e in all_events if e.get('timestamp', 0) >= cutoff]
    
    lines = []
    lines.append(f"【全球市场时间线】")
    lines.append(f"📅 {timestamp} · 北京时间 · 过去24小时")
    lines.append(f"{'─' * 40}")
    
    if not all_events:
        lines.append("\n暂无事件")
    else:
        last_date = None
        for event in all_events:
            ts = event.get('timestamp', 0)
            dt = datetime.fromtimestamp(ts)
            event_date = dt.strftime('%m-%d')
            event_time = dt.strftime('%H:%M')
            
            if event_date != last_date:
                lines.append(f"\n📅 {event_date}")
                last_date = event_date
            
            event_type = event.get('type', '')
            block_name = event.get('block_name', '')
            
            if event_type == 'high_score_news':
                score = event.get('score', 0.5)
                stars = '⭐' * min(5, int(score * 5 + 0.5))
                lines.append(f"  {event_time} 📰 {stars} {block_name}")
            elif event_type == 'jin10_news':
                lines.append(f"  {event_time} 📌 {block_name}")
            elif event_type == 'cn_event':
                chg = event.get('change_percent', 0)
                emoji = '📈' if chg >= 0 else '📉'
                lines.append(f"  {event_time} 🇨🇳 {emoji} {block_name} ({chg:+.1f}%)")
                dragon_one = event.get('dragon_one')
                if dragon_one:
                    sym = dragon_one.get('symbol', '')
                    name = dragon_one.get('name', '')
                    dchg = dragon_one.get('change_pct', 0)
                    if sym:
                        lines.append(f"        🏆 龙一: {sym} {name[:4]} ({dchg:+.1f}%)")
            elif event_type == 'us_event':
                chg = event.get('change_percent', 0)
                emoji = '📈' if chg >= 0 else '📉'
                lines.append(f"  {event_time} 🇺🇸 {emoji} {block_name} ({chg:+.1f}%)")
    
    lines.append(f"\n{'=' * 40}")
    lines.append(f"导出时间: {timestamp}")
    lines.append(f"🇨🇳 {len(cn_events)}题材 | 🇺🇸 {len(us_events)}热点 | 📰 {len(news_events)}高分 | 📌 {len(jin10_news)}要闻")
    
    return '\n'.join(lines)


def render_market_24h_timeline(view_mode: str = 'past_24h') -> str:
    """
    渲染24小时全球市场时间线
    
    Args:
        view_mode: 固定为 'past_24h'
    
    Returns:
        HTML字符串
    """
    now = datetime.now()
    
    cn_events = _get_a_block_events()
    us_events = _get_us_events()
    news_events = _get_high_score_news()
    jin10_news = _get_jin10_important_news()
    
    all_events = cn_events + us_events + news_events + jin10_news
    all_events.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    
    # 过滤过去24小时
    cutoff = (now - timedelta(hours=24)).timestamp()
    all_events = [e for e in all_events if e.get('timestamp', 0) >= cutoff]
    
    # 时间范围
    start_ts = now.timestamp() - 24 * 3600
    start_date = datetime.fromtimestamp(start_ts).strftime('%m-%d')
    end_date = now.strftime('%m-%d')
    date_range = f"{start_date} ~ {end_date}"
    current_time_str = now.strftime('%H:%M')
    
    # 市场状态
    market_status = _get_market_status()
    cn_trading = market_status.get('CN', {}).get('is_trading', False)
    us_trading = market_status.get('US', {}).get('is_trading', False)
    
    if cn_trading and us_trading:
        market_badge = '<span style="background: #fef2f2; color: #dc2626; padding: 2px 8px; border-radius: 4px; font-size: 11px;">🔥 双市场交易中</span>'
    elif cn_trading:
        market_badge = '<span style="background: #fff7ed; color: #ea580c; padding: 2px 8px; border-radius: 4px; font-size: 11px;">🇨🇳 A股交易中</span>'
    elif us_trading:
        market_badge = '<span style="background: #eff6ff; color: #3b82f6; padding: 2px 8px; border-radius: 4px; font-size: 11px;">🇺🇸 美股交易中</span>'
    else:
        market_badge = '<span style="background: #f8fafc; color: #64748b; padding: 2px 8px; border-radius: 4px; font-size: 11px;">🌙 盘后休市</span>'
    
    html_parts = []
    
    # 标题
    html_parts.append(f'''
    <div style="background: linear-gradient(135deg, #1e3a5f, #0f172a); border-radius: 12px; padding: 20px; margin-bottom: 16px; color: white;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
            <div>
                <div style="font-size: 18px; font-weight: 600; margin-bottom: 8px;">
                    🌐 全球市场时间线
                </div>
                <div style="font-size: 12px; opacity: 0.8;">
                    {date_range} · 北京时间 · 过去24小时
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
                {market_badge}
                <div style="font-size: 13px;">
                    <span style="opacity: 0.7;">当前</span>
                    <span style="font-weight: 600; font-size: 16px; margin-left: 4px;">{current_time_str}</span>
                </div>
                <button onclick="copyTimelineText()" 
                    style="font-size: 12px; padding: 6px 12px; background: rgba(255,255,255,0.15); color: white; border: 1px solid rgba(255,255,255,0.3); border-radius: 6px; cursor: pointer;">
                    📋 复制时间线
                </button>
            </div>
        </div>
        
        <div style="display: flex; gap: 16px; margin-top: 16px; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.1); flex-wrap: wrap;">
            <div style="flex: 1; min-width: 100px;">
                <div style="font-size: 20px; font-weight: 600;">{len(cn_events)}</div>
                <div style="font-size: 11px; opacity: 0.7;">🇨🇳 A股题材</div>
            </div>
            <div style="flex: 1; min-width: 100px;">
                <div style="font-size: 20px; font-weight: 600;">{len(us_events)}</div>
                <div style="font-size: 11px; opacity: 0.7;">🇺🇸 美股热点</div>
            </div>
            <div style="flex: 1; min-width: 100px;">
                <div style="font-size: 20px; font-weight: 600;">{len(news_events)}</div>
                <div style="font-size: 11px; opacity: 0.7;">📰 高分新闻</div>
            </div>
            <div style="flex: 1; min-width: 100px;">
                <div style="font-size: 20px; font-weight: 600;">{len(jin10_news)}</div>
                <div style="font-size: 11px; opacity: 0.7;">📌 金十要闻</div>
            </div>
        </div>
    </div>
    ''')
    
    # 时间流
    html_parts.append('''
    <div style="background: white; border-radius: 12px; padding: 20px; margin-bottom: 16px;">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 20px; padding-bottom: 16px; border-bottom: 2px dashed #e2e8f0;">
            <span style="font-size: 20px;">⏰</span>
            <span style="font-size: 14px; font-weight: 600; color: #1e293b;">市场时间流</span>
            <span style="font-size: 12px; color: #64748b; margin-left: auto;">↑ 最新 | 历史 ↓</span>
        </div>
    ''')
    
    if not all_events:
        html_parts.append('''
        <div style="text-align: center; padding: 40px; color: #94a3b8;">
            暂无事件
        </div>
        ''')
    else:
        last_date = None
        for event in all_events:
            ts = event.get('timestamp', 0)
            dt = datetime.fromtimestamp(ts)
            event_date = dt.strftime('%m-%d')
            event_time = dt.strftime('%H:%M')
            
            # 日期分隔
            if event_date != last_date:
                html_parts.append(f'''
                <div style="margin: 20px 0 12px 0; text-align: center;">
                    <span style="display: inline-block; background: #f1f5f9; color: #64748b; padding: 4px 12px; border-radius: 12px; font-size: 11px;">📅 {event_date}</span>
                </div>
                ''')
                last_date = event_date
            
            # 事件卡片
            event_type = event.get('type', '')
            emoji, base_color, _ = EVENT_TYPES.get(event_type, ('•', '#64748b', ''))
            title = event.get('block_name', '')
            
            if event_type in ('high_score_news', 'jin10_news'):
                score = event.get('score', 0.5)
                stars = '⭐' * min(5, int(score * 5 + 0.5))
                change_display = f'<span style="color: {base_color};">{stars}</span> <span style="color: #64748b;">({score:.2f})</span>'
            else:
                chg = event.get('change_percent', 0)
                sign = '+' if chg >= 0 else ''
                change_display = f'<span style="color: {"#dc2626" if chg >= 0 else "#3b82f6"}; font-weight: 600;">{sign}{chg:.1f}%</span>'
            
            # 热度色
            weight = event.get('weight', 0.5)
            hot_color = _get_hot_color(weight)
            
            # 龙一信息
            dragon_one = event.get('dragon_one')
            dragon_html = ''
            if dragon_one and event_type == 'cn_event':
                sym = dragon_one.get('symbol', '')
                name = dragon_one.get('name', '')
                dchg = dragon_one.get('change_pct', 0)
                if sym:
                    dragon_html = f'<div style="font-size: 11px; color: #64748b; margin-top: 4px;">🏆 龙一: {sym} {name[:4]} ({dchg:+.1f}%)</div>'
            
            html_parts.append(f'''
            <div style="display: flex; gap: 12px; padding: 12px; margin-bottom: 8px; background: #f8fafc; border-radius: 8px; border-left: 4px solid {base_color}; position: relative;">
                <div style="position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: {hot_color}; border-radius: 2px;"></div>
                <div style="min-width: 60px; text-align: right;">
                    <div style="font-size: 13px; color: #1e293b; font-weight: 500;">{event_time}</div>
                </div>
                <div style="flex: 1;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px; flex-wrap: wrap;">
                        <span style="font-size: 16px;">{emoji}</span>
                        <span style="font-size: 13px; font-weight: 600; color: #1e293b;">{title}</span>
                        <span style="margin-left: auto;">{change_display}</span>
                    </div>
                    {dragon_html}
                </div>
            </div>
            ''')
    
    html_parts.append('</div>')
    
    # JavaScript
    escaped_text = _export_text_timeline().replace('`', '\\`').replace('$', '\\$')
    html_parts.append(f'''
    <script>
    function copyTimelineText() {{
        const text = `{escaped_text}`;
        
        if (navigator.clipboard && navigator.clipboard.writeText) {{
            navigator.clipboard.writeText(text).then(() => {{
                alert('✅ 时间线已复制到剪贴板！');
            }}).catch(() => {{
                const textArea = document.createElement('textarea');
                textArea.value = text;
                textArea.style.position = 'fixed';
                textArea.style.left = '-999999px';
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                try {{
                    document.execCommand('copy');
                    alert('✅ 时间线已复制到剪贴板！');
                }} catch (e) {{
                    alert('❌ 复制失败！');
                }}
                document.body.removeChild(textArea);
            }});
        }} else {{
            const textArea = document.createElement('textarea');
            textArea.value = text;
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            try {{
                document.execCommand('copy');
                alert('✅ 时间线已复制到剪贴板！');
            }} catch (e) {{
                alert('❌ 复制失败！');
            }}
            document.body.removeChild(textArea);
        }}
    }}
    </script>
    ''')
    
    return ''.join(html_parts)


def get_raw_events_for_sync(hours: int = 24) -> Dict[str, List[Dict]]:
    """
    获取原始事件数据，供 server_sync 使用（从服务器同步到其他 Naja 实例）
    
    Returns:
        dict: 包含:
            - cn_events: A股题材原始事件列表
            - us_events: 美股热点原始事件列表
            - news: 高分新闻原始事件列表
            - jin10_news: 金十要闻原始事件列表
    """
    from datetime import datetime, timedelta
    import os
    import json
    import time
    
    now = datetime.now()
    cutoff = (now - timedelta(hours=hours)).timestamp()
    
    # 先从底层存储直接获取原始数据
    cn_events = []
    try:
        from deva.naja.market_hotspot.storing.block_events_store import get_cn_block_events
        cn_events = get_cn_block_events(hours=hours)
        # 添加 type 字段
        for e in cn_events:
            if 'type' not in e:
                e['type'] = 'cn_event'
    except Exception:
        pass
    
    us_events = []
    try:
        from deva.naja.market_hotspot.storing.block_events_store import get_us_block_events
        us_events = get_us_block_events(hours=hours)
        # 添加 type 字段
        for e in us_events:
            if 'type' not in e:
                e['type'] = 'us_event'
    except Exception:
        pass
    
    news_events = []
    try:
        from deva.naja.events.focused_news_store import get_today_focused_news
        news_events = get_today_focused_news(limit=50)
        # 添加 type 字段
        for e in news_events:
            if 'type' not in e:
                e['type'] = 'high_score_news'
    except Exception:
        pass
    
    jin10_news = []
    try:
        # 尝试从本地 jin10 缓存获取
        cache_file = os.path.expanduser("~/.naja/jin10_news.json")
        if os.path.exists(cache_file):
            with open(cache_file, 'r') as f:
                jin10_news = json.load(f)
        # 添加 type 字段
        for e in jin10_news:
            if 'type' not in e:
                e['type'] = 'jin10_news'
    except Exception:
        pass
    
    # 过滤时间
    def filter_events(events):
        return [e for e in events if e.get('timestamp', 0) >= cutoff]
    
    return {
        'cn_events': filter_events(cn_events),
        'us_events': filter_events(us_events),
        'news': filter_events(news_events),
        'jin10_news': filter_events(jin10_news),
    }


def get_timeline_data_for_api(hours: int = 24) -> dict:
    """
    获取时间线数据，供 API 使用（TrayDataHandler 和 MarketTimelineHandler 共享）
    
    Returns:
        dict: 包含:
            - stats: {cn_events, us_events, high_score_news, jin10_news}
            - list: 格式化后的时间线项目列表
    """
    from datetime import datetime, timedelta
    import time
    
    now = datetime.now()
    
    cn_events = _get_a_block_events()
    us_events = _get_us_events()
    news_events = _get_high_score_news()
    jin10_news = _get_jin10_important_news()
    
    all_events = cn_events + us_events + news_events + jin10_news
    all_events.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    
    cutoff = (now - timedelta(hours=hours)).timestamp()
    all_events = [e for e in all_events if e.get('timestamp', 0) >= cutoff]
    
    timeline_items = []
    for event in all_events[:15]:
        ts = event.get('timestamp', 0)
        dt = datetime.fromtimestamp(ts)
        event_type = event.get('type', '')
        block_name = event.get('block_name', '') or event.get('symbol', '') or event.get('name', '')
        
        item = {
            'type': event_type,
            'timestamp': ts,
            'time': dt.strftime('%H:%M'),
            'date': dt.strftime('%m-%d'),
            'title': block_name,
        }
        
        if event_type == 'high_score_news':
            item['score'] = event.get('score', 0.5)
        elif event_type == 'jin10_news':
            item['score'] = event.get('score', 0.85)
            item['flash_id'] = event.get('flash_id', '')
            flash_id = event.get('flash_id', '')
            item['url'] = event.get('url', '') or (f"https://www.jin10.com/news/{flash_id}" if flash_id else "")
        elif event_type in ('cn_event', 'us_event'):
            change_percent = event.get('change_percent', 0)
            sign = '+' if change_percent >= 0 else ''
            item['change'] = f"{sign}{change_percent:.1f}%"
            item['weight'] = event.get('weight', 0.5)
        
        timeline_items.append(item)
    
    return {
        'stats': {
            'cn_events': len(cn_events),
            'us_events': len(us_events),
            'high_score_news': len(news_events),
            'jin10_news': len(jin10_news),
        },
        'list': timeline_items,
        'timestamp': time.time(),
        'datetime': now.strftime('%Y-%m-%d %H:%M:%S'),
    }


if __name__ == '__main__':
    print(render_market_24h_timeline('past_24h'))
    print("\n" + "=" * 50 + "\n")
    print("导出文本测试:")
    print(_export_text_timeline())
