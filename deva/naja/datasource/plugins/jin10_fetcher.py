"""
金十数据 (jin10.com) 重要事件 (Important News) 异步获取器

数据来源分析（2026-05-06 逆向完成）:
  - 首页 "重要事件" 区块 DOM: .flash-top-list__item
  - 数据通过 WebSocket (FLASHSOCKET) 实时推送，非 REST API
  - /flash/hot REST API 已 502，不可用
  - WebSocket 服务器: wss://wss-flash-2.jin10.com/ (news2)
  - 实际可用域名需通过 CDN (ESA/阿里云)，直连返回 520
  - 重要事件存储在 Vuex store state.topListItems
  - 数据结构: [{action, display_time, expiration_time, flash_id, title}]

协议逆向结果:
  - 帧格式: 自定义二进制协议 (Little Endian)
  - Header: [msg_type: uint16]
  - Body: [str_len: uint16] [str_bytes: UTF-8] (rStrL 方法)
  - 消息类型常量:
      MSG_NEWS_FLASH    = 1000  (普通快讯)
      MSG_EVENTS_FLASH  = 1001  (事件快讯)
      MSG_VOICE_NEWS    = 1002  (语音快讯)
      MSG_OPINION_NEWS  = 1003  (观点)
      MSG_VIP_NEWS_FLASH= 1100  (VIP快讯)
      MSG_TOP_LIST      = 1005  (重要事件列表!)
      MSG_LAST_NEWS_LIST= 1200  (历史快讯批量)
      MSG_HEARTBEAT     = 1201  (心跳)
      MSG_USER_LOGIN    = 4002  (登录握手)
      MSG_GET_RILI      = 2001  (日历)
  - 登录帧: [4002:u16] [user_id:u32] [empty:u16+str] [browser:u16+str] [level:u32] [platform:u16+str] [last_id:u16+str?]
  - 心跳响应: 回复空字节 b''
  - config.js 路径: https://www.jin10.com/new/config.js
  - JS bundle: https://www.jin10.com/new/js/index.*.js (动态 hash)

方案1 (Playwright - 推荐): 渲染页面 → 从 Vuex store 提取数据
方案2 (WebSocket):      纯协议实现，但需过 CDN 防护（ESA JS Challenge）

依赖:
  pip install playwright
  playwright install chromium
"""

import asyncio
import json
import logging
import struct
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

logger = logging.getLogger("jin10_fetcher")

# ---------------------------------------------------------------------------
# 模块级互斥锁 + 结果缓存：防止多个入口并发拉起 Chromium
# ---------------------------------------------------------------------------
_fetch_lock = threading.Lock()
_fetch_cache: List["Jin10ImportantNews"] | None = None
_fetch_cache_ts: float = 0.0
_FETCH_CACHE_TTL: float = 300.0  # 5 分钟缓存

def _get_cached_news() -> List["Jin10ImportantNews"] | None:
    """读取缓存，TTL 内直接返回"""
    global _fetch_cache, _fetch_cache_ts
    if _fetch_cache is not None and (time.time() - _fetch_cache_ts) < _FETCH_CACHE_TTL:
        return _fetch_cache
    return None

def _set_cached_news(news_list: List["Jin10ImportantNews"]):
    """写入缓存"""
    global _fetch_cache, _fetch_cache_ts
    _fetch_cache = news_list
    _fetch_cache_ts = time.time()

# ---------------------------------------------------------------------------
# 协议常量 (从 index.*.js 逆向)
# ---------------------------------------------------------------------------

class MsgType:
    """金十 WebSocket 消息类型常量"""
    NEWS_FLASH = 1000
    EVENTS_FLASH = 1001
    VOICE_NEWS = 1002
    OPINION_NEWS = 1003
    VIP_NEWS_FLASH = 1100
    TOP_LIST = 1005           # 重要事件!
    LAST_NEWS_LIST = 1200
    HEARTBEAT = 1201
    GET_RILI_BY_DATE = 2001
    USER_LOGIN = 4002

# WebSocket 服务器 (来自 config.js flashServer)
WS_SERVERS = {
    "news": ["wss://wss-flash-1.jin10.com/"],
    "news2": ["wss://wss-flash-2.jin10.com/"],          # 实际使用 (非VIP)
    "vip_news": ["wss://wss-flash-vip-1.jin10.com/"],
    "vip_news2": ["wss://wss-flash-vip-2.jin10.com/"],
    "classify_news": ["wss://classify-ws.jin10.com:5142/"],
}


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class Jin10ImportantNews:
    """单条重要事件"""
    rank: int
    title: str
    flash_id: str
    display_time: str
    action: int = 0
    expiration_time: str = ""
    fetched_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_dict(cls, data: dict, rank: int = 0) -> "Jin10ImportantNews":
        return cls(
            rank=rank,
            title=data.get("title", ""),
            flash_id=data.get("flash_id", ""),
            display_time=data.get("display_time", ""),
            action=data.get("action", 0),
            expiration_time=data.get("expiration_time", ""),
        )


@dataclass
class Jin10Flash:
    """单条快讯"""
    flash_id: str = ""
    content: str = ""
    display_time: str = ""
    action: int = 0
    fetched_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_dict(cls, data: dict) -> "Jin10Flash":
        return cls(
            flash_id=data.get("id", data.get("flash_id", "")),
            content=data.get("content", ""),
            display_time=data.get("display_time", data.get("time", "")),
            action=data.get("action", 0),
        )


# ---------------------------------------------------------------------------
# 二进制协议编解码 (从 JS bundle 逆向)
# ---------------------------------------------------------------------------

class Jin10BinaryCodec:
    """
    金十 WebSocket 二进制协议编解码器

    帧格式 (Little Endian):
      [msg_type: uint16] [payload...]
    其中 payload 通常是 rStrL 编码的 JSON 字符串:
      [str_len: uint16] [str_bytes: UTF-8]
    """

    @staticmethod
    def read_u16(buf: bytes, pos: int) -> tuple:
        return struct.unpack_from('<H', buf, pos)[0], pos + 2

    @staticmethod
    def read_u32(buf: bytes, pos: int) -> tuple:
        return struct.unpack_from('<I', buf, pos)[0], pos + 4

    @staticmethod
    def read_str(buf: bytes, pos: int) -> tuple:
        """rStrL: [length:u16] [utf8_bytes]"""
        length, pos = Jin10BinaryCodec.read_u16(buf, pos)
        s = buf[pos:pos + length].decode('utf-8', errors='replace')
        return s, pos + length

    @staticmethod
    def build_login_msg(
        user_id: str = "",
        browser: str = "web",
        user_level: int = 0,
        platform: str = "web",
        last_id: str = "",
    ) -> bytes:
        """
        构建登录握手消息 (sendLogin)

        格式: [4002:u16] [userId:u32] [emptyStr:u16+str]
              [browser:u16+str] [userLevel:u32] [platform:u16+str] [lastId:u16+str?]
        """
        b = struct.pack('<H', MsgType.USER_LOGIN)
        b += struct.pack('<I', int(user_id) if user_id else 0)
        b += struct.pack('<H', 0)  # empty string
        for s in [browser, platform]:
            sb = s.encode('utf-8')
            b += struct.pack('<H', len(sb)) + sb
            if s == browser:
                b += struct.pack('<I', user_level)
        if last_id:
            lb = last_id.encode('utf-8')
            b += struct.pack('<H', len(lb)) + lb
        return b

    @staticmethod
    def decode_frame(buf: bytes) -> tuple:
        """
        解码一条二进制消息

        Returns:
            (msg_type, payload_data_or_list, raw_remaining)
        """
        if len(buf) < 2:
            return None, None, buf

        msg_type, pos = Jin10BinaryCodec.read_u16(buf, 0)

        if msg_type == MsgType.HEARTBEAT:
            return msg_type, None, b''

        elif msg_type == MsgType.TOP_LIST:
            data_str, _ = Jin10BinaryCodec.read_str(buf, pos)
            data = json.loads(data_str)
            return msg_type, data, b''

        elif msg_type in (MsgType.NEWS_FLASH, MsgType.VIP_NEWS_FLASH,
                          MsgType.EVENTS_FLASH, MsgType.VOICE_NEWS,
                          MsgType.OPINION_NEWS):
            data_str, _ = Jin10BinaryCodec.read_str(buf, pos)
            data = json.loads(data_str)
            return msg_type, data, b''

        elif msg_type == MsgType.LAST_NEWS_LIST:
            count, pos = Jin10BinaryCodec.read_u32(buf, pos)
            items = []
            for _ in range(count):
                s, pos = Jin10BinaryCodec.read_str(buf, pos)
                items.append(json.loads(s))
            is_full, pos = Jin10BinaryCodec.read_u32(buf, pos)
            return msg_type, {"items": items, "full": bool(is_full)}, b''

        else:
            return msg_type, buf[pos:], b''


# ---------------------------------------------------------------------------
# 方案1: Playwright 渲染抓取 (推荐)
# ---------------------------------------------------------------------------

async def fetch_important_news_playwright(
    headless: bool = True,
    timeout_ms: int = 30000,
    proxy: Optional[str] = None,
    extra_wait: float = 2.0,
) -> List[Jin10ImportantNews]:
    """
    使用 Playwright 渲染 jin10.com，从 Vuex store 提取重要事件

    原理:
      1. 启动浏览器 → 打开 jin10.com
      2. 等待 WebSocket 连接 + 数据推送完成
      3. 从 Vue 组件树找到 JinFlash → 提取 Vuex store.state.topListItems
      4. 比 DOM 解析更可靠、更完整（包含 flash_id、时间等字段）

    防并发机制:
      模块级 threading.Lock + 5 分钟缓存，确保同一时刻只有 1 个 Chromium 实例，
      多个入口（WakeSync / yaml定时任务 / Tray轮询）共享同一结果，不会重复拉起浏览器。

    Args:
        headless:    是否无头模式
        timeout_ms:  等待元素超时 (ms)
        proxy:       代理地址，如 "http://127.0.0.1:6152"
        extra_wait:  元素出现后额外等待时间 (秒)

    Returns:
        重要事件列表
    """
    # 第一次检查缓存（无需锁，快速路径）
    cached = _get_cached_news()
    if cached is not None:
        logger.debug("fetch_important_news_playwright: 命中缓存，直接返回")
        return list(cached)

    # 获取锁，同一时刻只有 1 个 Chromium 实例运行
    acquired = _fetch_lock.acquire(blocking=True, timeout=60.0)
    if not acquired:
        logger.warning("无法获取 Chromium 锁（等待超时），返回空列表")
        return []

    try:
        # 双重检查：获取锁期间可能有其他线程已填充缓存
        cached = _get_cached_news()
        if cached is not None:
            logger.debug("fetch_important_news_playwright: 双重检查命中缓存")
            return list(cached)

        news_list: List[Jin10ImportantNews] = await _do_fetch_important_news(
            headless=headless,
            timeout_ms=timeout_ms,
            proxy=proxy,
            extra_wait=extra_wait,
        )

        # 写入缓存（即使为空也缓存，避免击穿）
        _set_cached_news(news_list)
        return news_list

    finally:
        _fetch_lock.release()


async def _do_fetch_important_news(
    headless: bool,
    timeout_ms: int,
    proxy: Optional[str],
    extra_wait: float,
) -> List["Jin10ImportantNews"]:
    """实际执行 Playwright 抓取（由 fetch_important_news_playwright 内部调用）"""
    from playwright.async_api import async_playwright

    news_list: List["Jin10ImportantNews"] = []
    browser = None

    try:
        async with async_playwright() as p:
            launch_args: dict = {"headless": headless}
            if proxy:
                launch_args["proxy"] = {"server": proxy}

            browser = await p.chromium.launch(**launch_args)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
            )
            async with context:
                page = await context.new_page()
                try:
                    logger.info("正在打开 jin10.com ...")
                    await page.goto(
                        "https://www.jin10.com/",
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )

                    selector = ".flash-top-list__item"
                    logger.info(f"等待 {selector} 出现 ...")
                    await page.wait_for_selector(selector, timeout=timeout_ms)
                    logger.info("重要事件区块已加载")

                    await asyncio.sleep(extra_wait)

                    store_data = await page.evaluate("""() => {
                        const root = document.querySelector('#app').__vue__;
                        let jinFlash = null;
                        const walker = vm => {
                            if (vm.$options.name === 'JinFlash') jinFlash = vm;
                            vm.$children.forEach(walker);
                        };
                        walker(root);
                        if (!jinFlash || !jinFlash.$store) return null;
                        const store = jinFlash.$store.state;
                        return {
                            topListItems: store.topListItems || [],
                            topListLoaded: store.topListLoaded,
                            flashSocketConnected: store.flashSocketConnected,
                        };
                    }""")

                    if store_data and store_data.get("topListItems"):
                        items = store_data["topListItems"]
                        logger.info(f"从 Vuex store 提取到 {len(items)} 条重要事件")
                        for i, item in enumerate(items):
                            news_list.append(Jin10ImportantNews.from_dict(item, rank=i + 1))
                    else:
                        logger.warning("Vuex store 提取失败，回退到 DOM 解析")
                        dom_items = await page.query_selector_all(selector)
                        for dom_item in dom_items:
                            num_el = await dom_item.query_selector(".flash-top-list__item-number")
                            content_el = await dom_item.query_selector(".flash-top-list__item-content")
                            if num_el and content_el:
                                number = (await num_el.text_content()).strip()
                                title = (await content_el.text_content()).strip()
                                news_list.append(Jin10ImportantNews(
                                    rank=int(number), title=title,
                                ))

                except Exception as e:
                    logger.error(f"Playwright 抓取失败: {e}")
                    try:
                        await page.screenshot(path="/tmp/jin10_error.png")
                    except Exception:
                        pass
    finally:
        if browser is not None:
            try:
                await asyncio.wait_for(browser.close(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("browser.close() 超时，强制终止 Chromium")
                try:
                    await browser.close(force=True)
                except Exception:
                    pass

    return news_list


# ---------------------------------------------------------------------------
# 方案2: WebSocket 实时监听 (需过 CDN)
# ---------------------------------------------------------------------------

async def fetch_important_news_websocket(
    duration_seconds: int = 30,
    proxy: Optional[str] = None,
    on_flash: Optional[Callable] = None,
) -> List[Jin10ImportantNews]:
    """
    通过 WebSocket 连接金十数据，监听实时推送

    注意:
      金十 WS 前有 ESA/阿里云 CDN 防护，直连返回 520。
      需要配合 Playwright 获取 cookies 后才能裸连。
      推荐使用方案1 (Playwright)，或使用 Playwright 持久化 session 来复用 CDN session。

    Args:
        duration_seconds: 监听时长
        proxy:            代理地址
        on_flash:         收到快讯时的回调 Jin10Flash

    Returns:
        重要事件列表
    """
    import websockets

    news_list: List[Jin10ImportantNews] = []
    ws_url = WS_SERVERS["news2"][0]

    codec = Jin10BinaryCodec()
    login_msg = codec.build_login_msg()

    logger.info(f"连接 WebSocket: {ws_url}")

    connect_kwargs: dict = {
        "additional_headers": {
            "Origin": "https://www.jin10.com",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        },
        "open_timeout": 15,
    }
    if proxy:
        connect_kwargs["proxy"] = proxy

    try:
        async with websockets.connect(ws_url, **connect_kwargs) as ws:
            logger.info("WebSocket 已连接")
            await ws.send(login_msg)
            logger.info("登录消息已发送")

            start = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start < duration_seconds:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=10)
                except asyncio.TimeoutError:
                    continue

                if isinstance(raw, bytes) and len(raw) > 2:
                    msg_type, data, _ = codec.decode_frame(raw)

                    if msg_type == MsgType.HEARTBEAT:
                        await ws.send(b'')
                        continue

                    elif msg_type == MsgType.TOP_LIST:
                        items = list(reversed(data))  # 前端 reverse，还原
                        news_list = [
                            Jin10ImportantNews.from_dict(item, rank=i + 1)
                            for i, item in enumerate(items)
                        ]
                        logger.info(f"收到 {len(items)} 条重要事件")
                        for n in news_list:
                            logger.info(f"  #{n.rank:02d} {n.title}")

                    elif msg_type in (MsgType.NEWS_FLASH, MsgType.VIP_NEWS_FLASH,
                                      MsgType.EVENTS_FLASH):
                        flash = Jin10Flash.from_dict(data)
                        if on_flash:
                            on_flash(flash)

    except Exception as e:
        logger.error(f"WebSocket 失败: {e}")

    return news_list


# ---------------------------------------------------------------------------
# 方案3: Playwright + 持久化 WebSocket (最佳实时方案)
# ---------------------------------------------------------------------------

async def create_jin10_live_session(
    proxy: Optional[str] = None,
    headless: bool = True,
) -> tuple:
    """
    创建一个持久的 Playwright session，返回 (page, close_func)

    这个 session 可以:
    1. 用 Playwright 处理 CDN 防护
    2. 通过 page.evaluate 访问 Vuex store
    3. 通过 page.expose_function 实时获取 WebSocket 推送回调

    Returns:
        (page, close_func)
    """
    from playwright.async_api import async_playwright

    p = await async_playwright().start()

    launch_args: dict = {"headless": headless}
    if proxy:
        launch_args["proxy"] = {"server": proxy}

    browser = await p.chromium.launch(**launch_args)
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1440, "height": 900},
    )
    page = await context.new_page()

    await page.goto("https://www.jin10.com/", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_selector(".flash-top-list__item", timeout=30000)
    await asyncio.sleep(2)

    async def close():
        # browser.close() 加超时，防止卡死导致进程泄漏
        try:
            await asyncio.wait_for(browser.close(), timeout=10.0)
        except asyncio.TimeoutError:
            try:
                await browser.close(force=True)
            except Exception:
                pass
        try:
            await p.stop()
        except Exception:
            pass

    return page, close


async def poll_important_news_live(
    page,
    poll_interval: float = 5.0,
) -> List[Jin10ImportantNews]:
    """
    在已建立的 Playwright session 中轮询重要事件

    Args:
        page:          Playwright page 实例
        poll_interval: 轮询间隔 (秒)

    Returns:
        当前重要事件列表
    """
    store_data = await page.evaluate("""() => {
        const root = document.querySelector('#app').__vue__;
        let jinFlash = null;
        const walker = vm => {
            if (vm.$options.name === 'JinFlash') jinFlash = vm;
            vm.$children.forEach(walker);
        };
        walker(root);
        if (!jinFlash || !jinFlash.$store) return null;
        return jinFlash.$store.state.topListItems || [];
    }""")

    if store_data:
        return [
            Jin10ImportantNews.from_dict(item, rank=i + 1)
            for i, item in enumerate(store_data)
        ]
    return []


# ---------------------------------------------------------------------------
# 输出格式化
# ---------------------------------------------------------------------------

def format_news(news_list: List[Jin10ImportantNews]) -> str:
    """格式化输出重要事件"""
    if not news_list:
        return "（暂无重要事件）"

    lines = [
        f"{'='*60}",
        f"  金十数据 · 重要事件 Important News",
        f"  抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"{'='*60}",
    ]
    for n in news_list:
        lines.append(f"  {n.rank:02d} | {n.title}")
        if n.display_time:
            lines.append(f"      | {n.display_time}")
    lines.append(f"{'='*60}")
    lines.append(f"  共 {len(news_list)} 条")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("\n" + "=" * 60)
    print("  金十数据 · 重要事件获取器")
    print("=" * 60)

    # ── 方案1: Playwright 渲染 ──
    print("\n▶ 方案1: Playwright 渲染抓取")
    news = await fetch_important_news_playwright(headless=True)
    print(format_news(news))


if __name__ == "__main__":
    asyncio.run(main())
