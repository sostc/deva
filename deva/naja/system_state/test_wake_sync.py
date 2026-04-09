"""
测试唤醒同步链路 - 新闻获取和发布到雷达

运行方式: python -m deva.naja.system_state.test_wake_sync
"""

import asyncio
import requests
import time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup


def test_jin10_api():
    """测试金十重要新闻 API"""
    print("\n" + "="*60)
    print("1. 测试金十重要新闻 API")
    print("="*60)

    url = "https://flash-api.jin10.com/get_flash_list"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Origin': 'https://www.jin10.com',
        'Referer': 'https://www.jin10.com/',
    }

    session = requests.Session()
    session.headers.update(headers)

    try:
        response = session.post(
            url,
            json={
                "channel": "-8200",
                "maxid": 0,
                "category": "1",
                "limit": 10
            },
            timeout=15
        )

        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"API状态: {data.get('status')}")
            print(f"获取数量: {len(data.get('data', []))}")

            items = data.get('data', [])
            for i, item in enumerate(items[:3]):
                print(f"\n--- 新闻 {i+1} ---")
                print(f"ID: {item.get('id')}")
                print(f"时间: {item.get('time')}")
                print(f"内容: {item.get('content', '')[:100]}...")
                print(f"URL: {item.get('url', '')}")

            return items
        else:
            print(f"请求失败: {response.text[:200]}")
            return None

    except Exception as e:
        print(f"异常: {e}")
        return None


def test_fetch_news_detail(url):
    """测试获取新闻详情"""
    print("\n" + "="*60)
    print(f"2. 测试获取新闻详情: {url[:80]}...")
    print("="*60)

    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })

        response = session.get(url, timeout=15)
        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')

            article = soup.find('div', class_='article-content')
            if article:
                content = article.get_text(strip=True)
                print(f"内容长度: {len(content)}")
                print(f"内容预览: {content[:200]}...")
                return content
            else:
                print("未找到 article-content")

                title = soup.find('title')
                print(f"页面标题: {title.get_text() if title else 'N/A'}")

                body = soup.find('body')
                if body:
                    print(f"Body长度: {len(body.get_text())}")
                    print(f"Body预览: {body.get_text()[:200]}...")

                return None
        else:
            print(f"请求失败")
            return None

    except Exception as e:
        print(f"异常: {e}")
        return None


def test_publish_to_radar(news_item):
    """测试发布到雷达系统"""
    print("\n" + "="*60)
    print("3. 测试发布到雷达系统")
    print("="*60)

    try:
        from deva.naja.attention.attention_os import AttentionOS
        from deva.naja.events import get_event_bus
        from deva.naja.events.text_events import TextFetchedEvent

        AttentionOS()
        bus = get_event_bus()
        focused_events = []

        def _on_focused(event):
            focused_events.append(event)

        bus.subscribe('TextFocusedEvent', _on_focused, priority=99)

        event = TextFetchedEvent(
            text=news_item.get('content', '测试内容'),
            title=news_item.get('title', '测试标题'),
            source="radar_news",
            url=news_item.get('url', 'https://www.jin10.com/'),
            timestamp=time.time(),
        )

        bus.publish(event)
        print("✓ 已发布 TextFetchedEvent 到 NajaEventBus")

        if focused_events:
            print(f"✓ Attention 已处理并发布 TextFocusedEvent: {focused_events[0].routing_level}")
        else:
            print("✗ 未收到 TextFocusedEvent（Attention 未处理）")

        bus.unsubscribe('TextFocusedEvent', _on_focused)
        return True

    except Exception as e:
        print(f"异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("="*60)
    print("唤醒同步链路测试")
    print("="*60)

    items = test_jin10_api()

    if items:
        first_item = items[0]
        url = first_item.get('url', '')

        if url:
            test_fetch_news_detail(url)

        test_publish_to_radar(first_item)
    else:
        print("\n[Fallback] 使用模拟新闻验证事件总线链路")
        test_publish_to_radar({
            "content": "模拟新闻：AI算力需求上升，算力板块活跃",
            "url": "https://example.com/mock-news",
        })

    print("\n" + "="*60)
    print("测试完成")
    print("="*60)


if __name__ == "__main__":
    main()
