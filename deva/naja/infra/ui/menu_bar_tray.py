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
ICON_PURPLE = str(STATIC_DIR / "naja_tray_purple_22.png")
ICON_GREEN = str(STATIC_DIR / "naja_tray_red_22.png")


def _is_trading_time() -> bool:
    """通过 API 或本地计算判断是否在交易时段"""
    data = _http_get("/api/trading/status")
    if data and data.get("success"):
        return data.get("is_trading", False)
    return _is_trading_time_local()


def _is_trading_time_local() -> bool:
    """本地计算判断是否在交易时段"""
    from datetime import datetime, time
    now = datetime.now()
    current_time = now.time()
    weekday = now.weekday()
    
    if weekday >= 5:
        return False
    
    if time(9, 25) <= current_time <= time(11, 35):
        return True
    if time(12, 55) <= current_time <= time(15, 5):
        return True
    
    us_hour, us_min = current_time.hour, current_time.minute
    us_total = us_hour * 60 + us_min
    if time(21, 30) <= current_time <= time(23, 59):
        return True
    if time(0, 0) <= current_time <= time(4, 0):
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
        self._timeline_events = []
        self._icon_path = _get_tray_icon_path()

    def _get_timeline_events(self) -> dict:
        """获取 24 小时时间线数据"""
        try:
            from datetime import datetime, timedelta
            from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
                _get_a_block_events,
                _get_us_events,
                _get_high_score_news,
                _get_jin10_important_news,
            )
            
            cn_events = _get_a_block_events()
            us_events = _get_us_events()
            news_events = _get_high_score_news()
            jin10_news = _get_jin10_important_news()
            
            all_events = cn_events + us_events + news_events + jin10_news
            all_events.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            
            cutoff = (datetime.now() - timedelta(hours=24)).timestamp()
            all_events = [e for e in all_events if e.get('timestamp', 0) >= cutoff]
            
            timeline_items = []
            for event in all_events[:15]:
                ts = event.get('timestamp', 0)
                dt = datetime.fromtimestamp(ts)
                event_type = event.get('type', '')
                block_name = event.get('block_name', '')
                
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
                    item['url'] = event.get('url', '')
                elif event_type in ('cn_event', 'us_event'):
                    change_percent = event.get('change_percent', 0)
                    sign = '+' if change_percent >= 0 else ''
                    item['change'] = f"{sign}{change_percent:.1f}%"
                    item['weight'] = event.get('weight', 0.5)
                
                timeline_items.append(item)
            
            return {
                "success": True,
                "stats": {
                    "cn_events": len(cn_events),
                    "us_events": len(us_events),
                    "high_score_news": len(news_events),
                    "jin10_news": len(jin10_news),
                },
                "list": timeline_items,
            }
        except Exception as e:
            logger.error(f"获取 timeline 事件失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "stats": {},
                "list": [],
            }

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
        """重启 Naja 服务器和托盘程序"""
        import rumps
        logger.info("正在重启 Naja 服务...")

        env = os.environ.copy()
        env["LSUIElement"] = "1"
        deva_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
        python_path = env.get("PYTHONPATH", "")
        if python_path:
            env["PYTHONPATH"] = f"{deva_root}:{python_path}"
        else:
            env["PYTHONPATH"] = deva_root

        # 先停止旧的 Naja 服务器
        pid = self._get_running_pid()
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                logger.info(f"已停止旧 Naja 服务器 (PID: {pid})")
            except ProcessLookupError:
                pass
            time_module.sleep(1.0)

        # 启动新的 Naja 服务器
        naja_cmd = [sys.executable, "-m", "deva.naja", "-s", "start"]
        naja_log_file = NAJA_DIR / "logs" / "naja_restart.log"
        try:
            with open(naja_log_file, 'a') as f:
                subprocess.Popen(
                    naja_cmd,
                    env=env,
                    cwd=deva_root,
                    start_new_session=True,
                    stdout=f,
                    stderr=subprocess.STDOUT
                )
            logger.info(f"已启动新的 Naja 服务器")
        except Exception as e:
            logger.error(f"启动新的 Naja 服务器失败: {e}")

        # 等待 Naja 服务器启动
        time_module.sleep(1.5)

        # 退出当前托盘（新托盘会由 Naja 服务器自动启动）
        logger.info("正在退出当前托盘...")
        rumps.quit_application()

    def _on_reload(self, sender):
        logger.info("托盘菜单触发 reload")
        self._restart_tray()

    def _on_open_web(self, sender):
        logger.info("托盘菜单触发打开 Web")
        port = _get_naja_port()
        try:
            import webbrowser
            webbrowser.open(f"http://localhost:{port}")
        except Exception as e:
            logger.error(f"打开浏览器失败: {e}")

    def _on_open_logs(self, sender):
        logger.info("托盘菜单触发打开日志")
        log_dir = NAJA_DIR / "logs"
        try:
            import subprocess
            subprocess.run(["open", str(log_dir)], check=False)
        except Exception as e:
            logger.error(f"打开日志目录失败: {e}")

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

    def _get_system_status(self):
        """获取系统运行状态"""
        health_data = _http_get("/api/health")
        if health_data:
            return health_data
        return {"status": "unknown", "message": "无法连接"}

    def _build_menu(self):
        if self._app is None:
            return

        self._timeline_events = self._get_timeline_events()
        port = _get_naja_port()
        system_status = self._get_system_status()

        try:
            import rumps

            icon_path = ICON_GREEN if _is_trading_time() else ICON_PURPLE
            self._app.icon = icon_path

            self._app.menu.clear()
            
            # 服务状态区域
            self._app.menu["📊 Naja 管理平台"] = None
            status_text = "🟢 运行中" if self._get_running_pid() else "🔴 已停止"
            self._app.menu[status_text] = None
            self._app.menu[f"📍 端口: {port}"] = None
            self._app.menu["sep0"] = rumps.separator
            
            # 常用页面区域 - 使用 add 方法创建子菜单
            common_pages = rumps.MenuItem("📈 常用页面")
            common_pages.add(rumps.MenuItem("🔥 市场热点", callback=self._on_open_page("/market")))
            common_pages.add(rumps.MenuItem("⚡ 交易中心", callback=self._on_open_page("/awakening")))
            common_pages.add(rumps.MenuItem("🧠 认知系统", callback=self._on_open_page("/cognition")))
            common_pages.add(rumps.MenuItem("📜 系统日志", callback=self._on_open_page("/logstream")))
            common_pages.add(rumps.MenuItem("⚙️ 系统状态", callback=self._on_open_page("/health")))
            self._app.menu.add(common_pages)
            
            # 管理页面区域 - 使用 add 方法创建子菜单
            admin_tools = rumps.MenuItem("🔧 管理工具")
            admin_tools.add(rumps.MenuItem("📋 策略管理", callback=self._on_open_page("/strategyadmin")))
            admin_tools.add(rumps.MenuItem("📊 信号管理", callback=self._on_open_page("/signaladmin")))
            admin_tools.add(rumps.MenuItem("📁 数据源管理", callback=self._on_open_page("/dsadmin")))
            admin_tools.add(rumps.MenuItem("📅 任务管理", callback=self._on_open_page("/taskadmin")))
            self._app.menu.add(admin_tools)
            
            self._app.menu["sep1"] = rumps.separator
            
            # 主功能区域
            self._app.menu.add(rumps.MenuItem("🌐 打开 Web", callback=self._on_open_web))
            self._app.menu.add(rumps.MenuItem("📄 打开日志", callback=self._on_open_logs))
            self._app.menu.add(rumps.MenuItem("🔄 刷新", callback=self._on_refresh))
            self._app.menu["sep2"] = rumps.separator
            
            # --- 开始：24 小时时间线风格菜单 ---
            if self._timeline_events and self._timeline_events.get("success", False):
                # 统计条
                stats = self._timeline_events.get('stats', {})
                cn_count = stats.get('cn_events', 0)
                us_count = stats.get('us_events', 0)
                news_count = stats.get('high_score_news', 0)
                jin10_count = stats.get('jin10_news', 0)
                
                stats_menu = rumps.MenuItem(f"⏰ 全球市场时间线 | 🇨🇳 {cn_count} | 🇺🇸 {us_count} | 📰 {news_count} | 📌 {jin10_count}")
                stats_menu.set_callback(self._on_open_page("/market"))
                self._app.menu.add(stats_menu)
                
                events = self._timeline_events.get('list', [])
                last_date = None
                
                # 最多显示 20 条，避免菜单太长
                display_events = events[:20]
                
                for event in display_events:
                    event_date = event.get('date', '')
                    event_time = event.get('time', '')
                    event_type = event.get('type', '')
                    title = event.get('title', '')
                    url = event.get('url', '')
                    change = event.get('change', '')
                    
                    # 日期分隔
                    if event_date != last_date:
                        self._app.menu.add(rumps.MenuItem(f"{'─'*30}"))
                        self._app.menu.add(rumps.MenuItem(f"📅 {event_date}"))
                        last_date = event_date
                    
                    # 事件菜单项
                    if event_type == 'cn_event':
                        menu_text = f"{event_time} 🇨🇳 {change} {title}"
                        callback = self._on_open_page("/market")
                    elif event_type == 'us_event':
                        menu_text = f"{event_time} 🇺🇸 {change} {title}"
                        callback = self._on_open_page("/market")
                    elif event_type == 'high_score_news':
                        score = event.get('score', 0)
                        stars = '⭐' * min(5, int(score * 5 + 0.5))
                        menu_text = f"{event_time} 📰 {stars} {title}"
                        callback = self._on_open_page("/cognition")
                    elif event_type == 'jin10_news':
                        menu_text = f"{event_time} 📌 {title}"
                        
                        def make_callback(news_url):
                            def callback(sender):
                                if news_url:
                                    import webbrowser
                                    webbrowser.open(news_url)
                            return callback
                        
                        callback = make_callback(url) if url else None
                    else:
                        menu_text = f"{event_time} {title}"
                        callback = None
                    
                    menu_item = rumps.MenuItem(menu_text, callback=callback)
                    self._app.menu.add(menu_item)
            else:
                self._app.menu.add(rumps.MenuItem("⏰ 暂无时间线数据"))
            
            self._app.menu["sep3"] = rumps.separator
            self._app.menu["重启服务"] = rumps.MenuItem("🔄 重启服务", callback=self._on_reload)
            self._app.menu["退出"] = rumps.MenuItem("❌ 退出", callback=self._on_quit)

        except Exception as e:
            logger.error(f"更新菜单失败: {e}")
    
    def _on_open_page(self, path):
        """打开指定页面"""
        def callback(sender):
            logger.info(f"托盘菜单触发打开页面: {path}")
            port = _get_naja_port()
            try:
                import webbrowser
                webbrowser.open(f"http://localhost:{port}{path}")
            except Exception as e:
                logger.error(f"打开浏览器失败: {e}")
        return callback

    def start(self):
        if not self.is_available():
            logger.warning("菜单栏托盘在非 macOS 系统上不可用")
            return

        if self._app is not None:
            logger.info("托盘已启动")
            return

        try:
            import rumps

            initial_icon = ICON_GREEN if _is_trading_time() else ICON_PURPLE
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
