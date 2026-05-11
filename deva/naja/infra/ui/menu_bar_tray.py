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
ICON_PURPLE = str(STATIC_DIR / "naja_purple_22.png")
ICON_GREEN = str(STATIC_DIR / "naja_green_22.png")


def _is_trading_time() -> bool:
    """通过 API 判断是否在交易时段"""
    data = _http_get("/api/trading/status")
    if data and data.get("success"):
        return data.get("is_trading", False)
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

    def _get_latest_news(self) -> list:
        news_items = []

        try:
            import asyncio
            from deva.naja.datasource.plugins.jin10_fetcher import fetch_important_news_playwright

            news_list = asyncio.run(
                fetch_important_news_playwright(headless=True, timeout_ms=15000, extra_wait=1.5)
            )

            for news in news_list[:6]:
                title = news.title
                if not title:
                    continue

                flash_id = news.flash_id or ""
                news_items.append({
                    "title": title[:60],
                    "url": f"https://www.jin10.com/news/{flash_id}" if flash_id else "",
                })

        except Exception as e:
            logger.debug(f"获取金十重要新闻失败: {e}")

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

    def _get_tray_script_path(self) -> str:
        """获取托盘脚本路径"""
        return os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "naja_tray.py")

    def _restart_tray(self):
        """重启托盘程序"""
        import rumps
        tray_script = self._get_tray_script_path()
        if not os.path.exists(tray_script):
            logger.error(f"托盘脚本不存在: {tray_script}")
            return

        env = os.environ.copy()
        env["NO_TRAY_AUTOSTART"] = "1"
        env["LSUIElement"] = "1"

        cmd = [sys.executable, tray_script]
        subprocess.Popen(
            cmd,
            env=env,
            cwd=os.getcwd(),
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logger.info("已启动新的托盘进程")

        time_module.sleep(0.5)
        rumps.quit_application()

    def _on_reload(self, sender):
        logger.info("托盘菜单触发 reload")
        self._restart_tray()

    def _on_open_web(self, sender):
        import subprocess
        port = _get_naja_port()
        url = f"http://localhost:{port}"

        script = f'''
tell application "Safari"
    make new document at end of documents
    set URL of front document to "{url}"
    activate
end tell
'''
        try:
            subprocess.run(['osascript', '-e', script], check=True, capture_output=True)
            logger.info(f"已在 Safari 新窗口打开 {url}")
        except Exception as e:
            logger.error(f"打开 Safari 窗口失败: {e}")

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

            icon_path = ICON_GREEN if _is_trading_time() else ICON_PURPLE
            self._app.icon = icon_path

            self._app.menu.clear()
            self._app.menu["📊 Naja 管理平台"] = None
            self._app.menu["🌐 打开 Web"] = rumps.MenuItem("🌐 打开 Web", callback=self._on_open_web)
            self._app.menu["🔄 刷新"] = rumps.MenuItem("🔄 刷新", callback=self._on_refresh)
            self._app.menu["sep0"] = rumps.separator

            if self._news_items:
                for item in self._news_items[:5]:
                    title = item.get("title", "无标题")[:40]
                    url = item.get("url", "")

                    def make_callback(news_url):
                        def callback(sender):
                            if news_url:
                                import webbrowser
                                webbrowser.open(news_url)
                        return callback

                    menu_item = rumps.MenuItem(title, callback=make_callback(url) if url else None)
                    self._app.menu.add(menu_item)

            if self._hot_blocks:
                for name, weight in self._hot_blocks[:3]:
                    self._app.menu.add(rumps.MenuItem(f"🔥 {name} ({weight})"))

            self._app.menu["sep1"] = rumps.separator
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

            initial_icon = ICON_RED if _is_trading_time() else ICON_PURPLE
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
