"""macOS 菜单栏托盘模块"""

import os
import sys
import json
import logging
import signal
import subprocess
import time as time_module
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

NAJA_DIR = Path.home() / ".naja"
PID_FILE = NAJA_DIR / "naja.pid"
PORT_FILE = NAJA_DIR / "naja.port"
DEFAULT_PORT = 8080

STATIC_DIR = Path(__file__).parent.parent.parent / "static"
ICON_WHITE = str(STATIC_DIR / "naja_tray_white.png")
ICON_RED = str(STATIC_DIR / "naja_tray_red.png")


def _is_trading_time() -> bool:
    """检查是否在 A 股或美股交易时段"""
    from datetime import datetime, time
    now = datetime.now()
    weekday = now.weekday()
    if weekday >= 5:
        return False
    t = now.time()
    cn_start, cn_end = time(9, 30), time(15, 0)
    cn_lunch_start, cn_lunch_end = time(11, 30), time(13, 0)
    if (cn_start <= t <= cn_lunch_start) or (cn_lunch_end <= t <= cn_end):
        return True
    us_start, us_end = time(21, 30), time(4, 0)
    if (us_start <= t) or (t <= us_end):
        return True
    return False


def _get_naja_port() -> int:
    """从配置文件读取 Naja 端口，失败时返回默认值"""
    try:
        if PORT_FILE.exists():
            return int(PORT_FILE.read_text().strip())
    except Exception:
        pass
    return DEFAULT_PORT


def _get_tray_icon_path():
    base = Path(__file__).parent.parent.parent / "static"
    possible_paths = [
        base / "naja_22.png",
        base / "naja_32.png",
        base / "naja_16.png",
        base / "naja_icon.png",
        base / "naja_128.png",
        Path.home() / ".naja" / "naja_icon.png",
    ]
    for p in possible_paths:
        if p.exists():
            return str(p)
    return None


def _http_get(path: str, port: int = None, timeout: float = 5.0) -> Optional[dict]:
    """向 Naja Web API 发送 GET 请求"""
    if port is None:
        port = _get_naja_port()
    url = f"http://localhost:{port}{path}"
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "NajaTray/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug(f"HTTP GET {url} 失败: {e}")
        return None


class MenuBarTray:
    _instance: Optional['MenuBarTray'] = None

    @classmethod
    def is_available(cls):
        if sys.platform != "darwin":
            return False
        try:
            import rumps
            return True
        except ImportError:
            return False

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._app = None
        self._news_items = []
        self._hot_blocks = []
        self._icon_path = _get_tray_icon_path()
        self._seen_news_ids: set = set()
        self._max_seen_ids = 100

    def _get_latest_news(self) -> list:
        news_items = []

        # 优先使用 /api/radar/events（过滤后的金十新闻）
        data = _http_get("/api/radar/events")
        if data and data.get("success"):
            events = data.get("data", {}).get("events", [])
            for event in events:
                source = event.get("source", "")
                event_type = event.get("event_type", "")
                payload = event.get("payload", {})

                if source not in {"jin10", "jin10_important", "radar_news", "news_fetcher"}:
                    continue
                if "news" not in event_type.lower():
                    continue

                event_id = event.get("event_id", "")
                title = payload.get("title", "") or payload.get("text", "") or event.get("message", "")
                url = payload.get("url", "")

                if not title or title == "[详细内容已过滤]":
                    continue
                if event_id in self._seen_news_ids:
                    continue

                news_items.append({
                    "title": title[:60],
                    "url": url,
                    "event_id": event_id,
                    "source": "radar",
                })
                self._seen_news_ids.add(event_id)

        # fallback 到 /api/jin10/important（重要新闻）
        if len(news_items) < 6:
            data = _http_get("/api/jin10/important?limit=12")
            if data and data.get("success"):
                for item in data.get("news", []):
                    title = item.get("title", "")
                    if not title:
                        continue

                    title_hash = str(hash(title))
                    if title_hash in self._seen_news_ids:
                        continue

                    news_items.append({
                        "title": title[:60],
                        "url": item.get("url", ""),
                        "event_id": title_hash,
                        "source": "jin10",
                    })
                    self._seen_news_ids.add(title_hash)

        if len(self._seen_news_ids) > self._max_seen_ids:
            old_ids = list(self._seen_news_ids)[:len(self._seen_news_ids) - self._max_seen_ids]
            for old_id in old_ids:
                self._seen_news_ids.discard(old_id)

        return news_items[:6]

    def _get_hot_blocks(self) -> list:
        data = _http_get("/api/market/hotspot")
        if not data:
            return []

        result = []
        seen = set()

        for section_key in ["cn", "us"]:
            section = data.get(section_key, {})
            blocks = section.get("hot_blocks", [])
            for block in blocks[:3]:
                bid = block.get("block_id", "")
                name = block.get("name", bid)
                weight = block.get("weight", 0)
                key = name[:8]
                if key in seen:
                    continue
                seen.add(key)
                result.append((name, f"{weight:.2f}"))

        return result[:6]

    def _get_running_pid(self) -> Optional[int]:
        try:
            if not PID_FILE.exists():
                return None
            pid = int(PID_FILE.read_text().strip())
            if pid <= 0:
                return None
            os.kill(pid, 0)
            return pid
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            PID_FILE.unlink(missing_ok=True)
            return None

    def _on_reload(self, sender):
        logger.info("托盘菜单触发 reload")
        pid = self._get_running_pid()
        if pid:
            try:
                os.kill(pid, signal.SIGUSR1)
                logger.info(f"已向 Naja (PID {pid}) 发送 SIGUSR1")
            except ProcessLookupError:
                logger.warning(f"Naja 进程 {pid} 已不存在")
        else:
            logger.warning("Naja 未在运行")

    def _on_open_web(self, sender):
        logger.info("托盘菜单触发打开 Web")
        port = _get_naja_port()
        try:
            import webbrowser
            webbrowser.open(f"http://localhost:{port}")
        except Exception as e:
            logger.error(f"打开浏览器失败: {e}")

    def _on_quit(self, sender):
        logger.info("托盘菜单触发退出")
        import rumps
        pid = self._get_running_pid()
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        rumps.quit_application()

    def _on_refresh(self, sender):
        logger.info("刷新托盘数据")
        self._build_menu()

    def _build_menu(self):
        if self._app is None:
            return

        self._news_items = self._get_latest_news()
        self._hot_blocks = self._get_hot_blocks()

        try:
            import rumps

            icon_path = ICON_RED if _is_trading_time() else ICON_WHITE
            self._app.icon = icon_path

            self._app.menu.clear()
            self._app.menu["📊 Naja 管理平台"] = None
            self._app.menu["🌐 打开 Web"] = rumps.MenuItem("🌐 打开 Web", callback=self._on_open_web)
            self._app.menu["🔄 刷新"] = rumps.MenuItem("🔄 刷新", callback=self._on_refresh)
            self._app.menu["sep1"] = rumps.separator

            news_parent = rumps.MenuItem("📰 最新新闻")
            if self._news_items:
                for i, item in enumerate(self._news_items[:6]):
                    title = item.get("title", "无标题")[:40]
                    menu_item = rumps.MenuItem(title)
                    url = item.get("url", "")
                    if url:
                        menu_item.url = url
                    news_parent[f"n{i}"] = menu_item
            else:
                news_parent["empty"] = rumps.MenuItem("暂无数据")
            self._app.menu["news"] = news_parent

            blocks_parent = rumps.MenuItem("🔥 热点板块")
            if self._hot_blocks:
                for i, (name, weight) in enumerate(self._hot_blocks[:6]):
                    blocks_parent[f"b{i}"] = rumps.MenuItem(f"{name}: {weight}")
            else:
                blocks_parent["empty"] = rumps.MenuItem("暂无数据")
            self._app.menu["blocks"] = blocks_parent

            self._app.menu["sep2"] = rumps.separator
            self._app.menu["重启服务"] = rumps.MenuItem("🔄 重启服务", callback=self._on_reload)
            self._app.menu["退出"] = rumps.MenuItem("❌ 退出", callback=self._on_quit)

        except Exception as e:
            logger.error(f"更新菜单失败: {e}")

    def start(self):
        if not self.is_available():
            logger.warning("菜单栏托盘在非 macOS 系统上不可用")
            return

        if self._app is not None:
            logger.info("托盘已启动")
            return

        try:
            import rumps

            initial_icon = ICON_RED if _is_trading_time() else ICON_WHITE
            self._app = rumps.App("Naja", icon=initial_icon)
            self._build_menu()

            rumps.timer(interval=30)(self._on_timer)(self._app)

            self._app.run()
        except Exception as e:
            logger.error(f"启动托盘失败: {e}")

    def _on_timer(self, _sender):
        self._build_menu()

    def stop(self):
        import rumps
        if self._app:
            rumps.quit_application()
            self._app = None

    def update_data(self):
        self._build_menu()


_tray_instance: Optional[MenuBarTray] = None


def get_tray() -> MenuBarTray:
    global _tray_instance
    if _tray_instance is None:
        _tray_instance = MenuBarTray()
    return _tray_instance


def start_tray():
    tray = get_tray()
    if tray.is_available():
        tray.start()
    else:
        logger.warning("菜单栏托盘不可用（需要 macOS 和 rumps 库）")


def stop_tray():
    tray = get_tray()
    tray.stop()
