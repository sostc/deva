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

from deva.naja.infra.autostart import is_login_item_enabled, toggle_login_item
from deva.naja.infra.runtime.daemon import (
    get_running_pid, get_running_tray_pid,
    save_tray_pid, clear_tray_pid
)

logger = logging.getLogger(__name__)

NAJA_DIR = Path.home() / ".naja"
PID_FILE = NAJA_DIR / "naja.pid"
TRAY_PID_FILE = NAJA_DIR / "naja_tray.pid"
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
        self._naja_ready = False
        self._last_timeline_data = None
        self._last_timeline_ts = 0
        self._last_system_status = None
        self._last_system_status_ts = 0
        self._last_menu_build_ts = 0
        self._notified_news_ids = set()
        self._notification_enabled = True

        import threading
        self._menu_cache = {}
        self._menu_cache_lock = threading.Lock()
        self._preload_thread = None
        self._preload_running = False

    def _send_notification(self, title: str, subtitle: str = "", message: str = ""):
        """发送 macOS 通知"""
        if not self._notification_enabled:
            return
        
        try:
            import rumps
            rumps.notification(
                title=title,
                subtitle=subtitle,
                message=message,
            )
            logger.info(f"[Tray] 发送通知: {title}")
        except Exception as e:
            logger.error(f"[Tray] 发送通知失败: {e}")

    def _start_background_preloader(self):
        """启动后台预加载线程，异步加载菜单数据"""
        if self._preload_running:
            return
        
        self._preload_running = True
        
        def preloader():
            import time
            
            logger.info("[Tray] 后台预加载线程启动")
            
            while self._preload_running:
                try:
                    tray_data = _http_get("/api/tray/data", timeout=10.0)
                    
                    if tray_data and tray_data.get('success'):
                        with self._menu_cache_lock:
                            self._menu_cache = {
                                'timeline': tray_data.get('timeline', {}),
                                'status': tray_data.get('health', {}),
                                'trading': tray_data.get('trading', {}).get('is_trading', False),
                                'timestamp': time.time(),
                            }
                        logger.debug(f"[Tray] 菜单数据预加载完成")
                    else:
                        logger.warning(f"[Tray] 预加载失败: {tray_data}")
                        
                except Exception as e:
                    logger.warning(f"[Tray] 预加载失败: {e}")
                
                time.sleep(10)
            
            logger.info("[Tray] 后台预加载线程退出")
        
        import threading
        self._preload_thread = threading.Thread(target=preloader, daemon=True)
        self._preload_thread.start()
        logger.info("[Tray] 后台预加载线程已启动")

    def _get_timeline_events_cached(self):
        """获取时间线数据（后台缓存版本）"""
        import time
        now = time.time()
        
        if self._last_timeline_data and (now - self._last_timeline_ts < 300):
            return self._last_timeline_data
        
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
                event_type = event.get('type', '')
                event_time = event.get('time', '')[:5]
                title = event.get('block_name', '') or event.get('title', '') or ''
                title = title[:40]
                
                change = ''
                if event_type == 'cn_event':
                    change = event.get('change_pct', 0)
                    if change > 0:
                        change = f"+{change:.1f}%"
                    else:
                        change = f"{change:.1f}%"
                elif event_type == 'us_event':
                    change = event.get('change_pct', 0)
                    if change > 0:
                        change = f"+{change:.1f}%"
                    else:
                        change = f"{change:.1f}%"
                elif event_type == 'news':
                    change = f"[{event.get('score', 0):.1f}]"
                elif event_type == 'jin10':
                    change = "🔥"
                
                timeline_items.append({
                    'type': event_type,
                    'time': event_time,
                    'title': title,
                    'change': change,
                    'timestamp': event.get('timestamp', 0),
                    'data': event,
                })
            
            self._last_timeline_data = {
                'success': True,
                'stats': {
                    'cn_events': len(cn_events),
                    'us_events': len(us_events),
                    'high_score_news': len(news_events),
                    'jin10_count': len(jin10_news),
                },
                'list': timeline_items,
            }
            self._last_timeline_ts = now
            return self._last_timeline_data
            
        except Exception as e:
            logger.warning(f"获取时间线数据失败: {e}")
            return {"success": False, "stats": {}, "list": []}

    def _get_system_status_cached(self):
        """获取系统状态（后台缓存版本）"""
        import time
        now = time.time()
        
        if self._last_system_status and (now - self._last_system_status_ts < 30):
            return self._last_system_status
        
        health_data = _http_get("/api/health")
        result = health_data if health_data else {"status": "unknown", "message": "无法连接"}
        
        self._last_system_status = result
        self._last_system_status_ts = now
        return result

    def _check_and_send_notifications(self):
        if not self._naja_ready:
            return
        
        try:
            from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
                _get_high_score_news,
                _get_jin10_important_news,
            )
            
            high_score_news = _get_high_score_news()
            jin10_news = _get_jin10_important_news()
            
            all_news = high_score_news + jin10_news
            
            for news in all_news:
                news_id = f"{news.get('type', '')}_{news.get('timestamp', 0)}_{news.get('block_name', '')[:20]}"
                
                if news_id in self._notified_news_ids:
                    continue
                
                score = news.get('score', 0)
                if score >= 0.7:
                    title = news.get('block_name', '')
                    subtitle = f"重要新闻 · 评分: {score:.2f}"
                    
                    self._send_notification(title, subtitle)
                    self._notified_news_ids.add(news_id)
                    
                    if len(self._notified_news_ids) > 100:
                        self._notified_news_ids = set(list(self._notified_news_ids)[-50:])
                        
        except Exception as e:
            logger.error(f"[Tray] 检查通知失败: {e}")

    def _get_timeline_events(self) -> dict:
        """获取 24 小时时间线数据（带缓存）"""
        import time
        now = time.time()
        
        # 缓存 30秒
        if self._last_timeline_data and (now - self._last_timeline_ts < 30):
            return self._last_timeline_data
        
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
            
            result = {
                "success": True,
                "stats": {
                    "cn_events": len(cn_events),
                    "us_events": len(us_events),
                    "high_score_news": len(news_events),
                    "jin10_news": len(jin10_news),
                },
                "list": timeline_items,
            }
            
            # 保存缓存
            self._last_timeline_data = result
            self._last_timeline_ts = now
            return result
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
        return get_running_pid()

    def _kill_running_tray(self):
        """终止正在运行的托盘进程"""
        pid = get_running_tray_pid()
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                logger.info(f"已终止旧托盘进程 (PID: {pid})")
                time_module.sleep(0.5)
                try:
                    os.kill(pid, 0)
                    os.kill(pid, signal.SIGKILL)
                    logger.info(f"已强制终止托盘进程 (PID: {pid})")
                except (ProcessLookupError, OSError):
                    pass
            except Exception as e:
                logger.error(f"终止托盘进程失败: {e}")
            finally:
                clear_tray_pid()

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
            from deva.naja.infra.log.colorful_logger import open_rotated_file
            with open_rotated_file(str(naja_log_file)) as f:
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
        import time
        pid = self._get_running_pid()
        if pid:
            try:
                logger.info(f"正在停止 Naja 服务 (PID: {pid})...")
                os.kill(pid, signal.SIGTERM)
                # 等待进程退出（最多10秒）
                timeout = 10.0
                start = time.time()
                while time.time() - start < timeout:
                    try:
                        os.kill(pid, 0)  # 检查进程是否还存在
                        time.sleep(0.2)
                    except ProcessLookupError:
                        logger.info("Naja 服务已停止")
                        break
                else:
                    # 超时，强制终止
                    logger.warning("Naja 服务停止超时，强制终止")
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            except ProcessLookupError:
                pass
        clear_tray_pid()
        rumps.quit_application()

    def _on_refresh(self, sender):
        logger.info("刷新托盘数据")
        self._build_menu()

    def _on_sync_from_server(self, sender):
        """从服务器同步数据"""
        import threading
        import rumps
        
        logger.info("开始从服务器同步数据...")
        
        # 显示开始同步通知（在主线程）
        rumps.notification(
            title="☁️ 正在同步",
            subtitle="正在从服务器获取数据...",
            message="请稍候，同步完成后会通知您"
        )
        
        # 用于存储同步结果的共享变量
        self._sync_pending_notification = None
        
        def sync_task():
            try:
                from deva.naja.state.system.server_sync_handler import ServerDataSyncHandler
                from datetime import datetime, timedelta
                
                handler = ServerDataSyncHandler()
                now = datetime.now()
                start = now - timedelta(hours=48)
                end = now
                
                result = handler.execute_wake_sync(start, end)
                
                if result.get('success'):
                    logger.info(f"服务器同步成功: {result.get('message', '')}")
                    # 存储通知内容，让主线程显示
                    self._sync_pending_notification = {
                        'title': "☁️ 服务器同步成功",
                        'subtitle': "数据已从服务器更新",
                        'message': result.get('message', '同步完成')
                    }
                else:
                    logger.warning(f"服务器同步失败: {result.get('message', '')}")
                    # 存储通知内容，让主线程显示
                    self._sync_pending_notification = {
                        'title': "⚠️ 服务器同步失败",
                        'subtitle': "请检查网络连接",
                        'message': result.get('message', '同步失败')
                    }
                
                # 同步完成后，设置标志位让定时器在下一次循环刷新菜单
                # 不要在线程中直接调用 _build_menu()，因为 UI 操作必须在主线程
                self._last_menu_build_ts = 0  # 清空时间戳，让定时器立即刷新
                
            except Exception as e:
                logger.error(f"服务器同步异常: {e}")
                import traceback
                traceback.print_exc()
                # 存储通知内容，让主线程显示
                self._sync_pending_notification = {
                    'title': "❌ 同步异常",
                    'subtitle': "发生错误",
                    'message': str(e)
                }
        
        thread = threading.Thread(target=sync_task, daemon=True)
        thread.start()

    def _on_one_click_summary(self, sender):
        """一键总结：调用大模型总结时间线数据（带缓存）"""
        import threading
        import rumps
        
        logger.info("开始一键总结...")
        
        # 显示开始总结通知（在主线程）
        rumps.notification(
            title="🧠 正在总结",
            subtitle="正在分析市场动态...",
            message="请稍候，总结完成后会通知您"
        )
        
        # 用于存储总结结果的共享变量
        self._summary_pending_result = None
        
        def summary_task():
            try:
                # 获取时间线数据
                timeline_data = self._get_timeline_events()
                
                if not timeline_data or not timeline_data.get('success'):
                    self._summary_pending_result = {
                        'type': 'error',
                        'notification': {
                            'title': "⚠️ 总结失败",
                            'subtitle': "无法获取时间线数据",
                            'message': "请稍后重试"
                        }
                    }
                    return
                
                events = timeline_data.get('list', [])
                if not events:
                    self._summary_pending_result = {
                        'type': 'error',
                        'notification': {
                            'title': "📭 暂无数据",
                            'subtitle': "没有可总结的内容",
                            'message': "时间线数据为空"
                        }
                    }
                    return
                
                # 先检查缓存
                cached_summary = self._get_cached_summary(events)
                if cached_summary:
                    logger.info("使用缓存的总结")
                    summary = cached_summary
                    self._summary_pending_result = {
                        'type': 'cache',
                        'summary': summary,
                        'events': events
                    }
                else:
                    # 构建提示词
                    prompt = self._build_summary_prompt(events)
                    
                    # 调用大模型
                    from deva.llm.client import sync_gpt
                    summary = sync_gpt(prompt)
                    
                    # 保存缓存
                    self._save_summary_cache(events, summary)
                    logger.info("总结已缓存")
                    
                    self._summary_pending_result = {
                        'type': 'success',
                        'summary': summary,
                        'events': events
                    }
                
            except Exception as e:
                logger.error(f"一键总结异常: {e}")
                import traceback
                traceback.print_exc()
                self._summary_pending_result = {
                    'type': 'error',
                    'notification': {
                        'title': "❌ 总结失败",
                        'subtitle': "发生错误",
                        'message': str(e)[:100] if len(str(e)) > 100 else str(e)
                    }
                }
        
        thread = threading.Thread(target=summary_task, daemon=True)
        thread.start()

    def _build_summary_prompt(self, events):
        """构建大模型总结提示词（小红书爆款风格）"""
        from datetime import datetime
        
        prompt = f"""你是一个擅长写小红书爆款文案的财经博主。请根据以下24小时内的全球市场事件数据，生成一篇小红书风格的市场总结。

当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

市场事件数据：
"""
        for i, event in enumerate(events[:20], 1):
            event_type = event.get('type', 'unknown')
            time_str = event.get('time', '')
            title = event.get('title', '')
            change = event.get('change', '')
            score = event.get('score', '')
            
            type_label = {
                'cn_event': '🇨🇳 A股题材',
                'us_event': '🇺🇸 美股题材',
                'high_score_news': '📰 重要新闻',
                'jin10_news': '📌 金十快讯',
            }.get(event_type, event_type)
            
            prompt += f"{i}. [{time_str}] {type_label}"
            if change:
                prompt += f" 变动: {change}"
            if score:
                prompt += f" 评分: {score:.2f}" if isinstance(score, float) else f" 评分: {score}"
            prompt += f" - {title}\n"
        
        prompt += """

请生成一篇小红书爆款风格的市场总结，要求：
1. 🔥 开头第一句必须是核心结论，直接点明今天市场的关键特征，特别是**今天市场主要的变化和转折**（如果有的话）
2. 📝 结论后面再展开细节，每段用一个emoji开头，一行一个要点
3. 💡 语言要轻松活泼，像和朋友聊天
4. 🎯 重点突出，用加粗**强调关键内容**
5. 📊 数据要直观，涨跌幅要醒目
6. ✨ 整体控制在8-12行，每行简短有力
7. ⏰ **绝对重要！必须严格按照时间线顺序展开**：从早到晚叙述，不能打乱时间顺序。例如不能把后面发生的事放在前面，这样市场情绪的变化（先涨后跌、先冷后热）才能准确体现！
8. 🔄 **关键要求！主动梳理市场的变化和转折**：
   - 观察市场情绪的转折点（如先涨后跌、从悲观到乐观、从平静到疯狂等）
   - 观察题材轮动的变化（从A板块切换到B板块）
   - 观察重要新闻对市场的影响（某个消息出来后市场的反应）
   - 用简洁的语言把这些变化**明确说出来**！

例子风格：
🔥 **创新药**领涨！今天市场先抑后扬，题材轮动明显！
📈 早盘**创新药**板块率先爆发，涨幅惊人！
🇨🇳 午盘市场情绪升温，**文化传媒**接棒上涨！
📌 下午金十快讯传来利好，推动行情全面上涨！
🔄 注意到今天题材从医药切换到传媒，轮动很快！
💡 建议关注政策驱动型机会～

直接给出文案，不要其他说明！"""
        
        return prompt

    def _save_summary_to_file(self, summary):
        """保存总结到本地文件，返回文件路径"""
        try:
            from datetime import datetime
            import os
            
            summary_dir = NAJA_DIR / "summaries"
            summary_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            summary_file = summary_dir / f"market_summary_{timestamp}.txt"
            
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"市场总结 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")
                f.write(summary)
            
            logger.info(f"总结已保存到: {summary_file}")
            return summary_file
        except Exception as e:
            logger.error(f"保存总结失败: {e}")
            return None

    def _copy_to_clipboard(self, text):
        """复制文本到剪贴板"""
        try:
            import subprocess
            
            # macOS 使用 pbcopy
            process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
            
            logger.info("总结已复制到剪贴板")
            return True
        except Exception as e:
            logger.error(f"复制到剪贴板失败: {e}")
            return False

    def _send_to_dingtalk(self, summary):
        """发送总结到钉钉"""
        try:
            from datetime import datetime
            from deva.endpoints import Dtalk
            
            # 构建 Markdown 格式的消息
            title = f"📊 24小时市场总结 - {datetime.now().strftime('%m-%d %H:%M')}"
            markdown_content = f"@md@{title}|{summary}"
            
            # 发送到钉钉
            dtalk = Dtalk()
            markdown_content >> dtalk
            
            logger.info("总结已发送到钉钉")
            return True
        except Exception as e:
            logger.error(f"发送到钉钉失败: {e}")
            return False

    def _show_summary_notification(self, summary, summary_file, events=None):
        """显示总结通知并打开HTML页面"""
        import rumps
        import subprocess
        from datetime import datetime
        
        # 简短通知
        if len(summary) > 100:
            summary_display = summary[:100] + "..."
        else:
            summary_display = summary
        
        rumps.notification(
            title="✨ 市场总结完成",
            subtitle="已复制到剪贴板并发送到钉钉",
            message=summary_display
        )
        
        # 生成并打开漂亮的HTML页面
        html_file = self._generate_html_summary(summary, events)
        if html_file:
            try:
                subprocess.run(['open', str(html_file)], check=False)
                logger.info(f"已打开HTML总结: {html_file}")
            except Exception as e:
                logger.error(f"打开HTML总结失败: {e}")

    def _generate_html_summary(self, summary, events=None):
        """生成漂亮的HTML总结页面"""
        try:
            from datetime import datetime
            
            summary_dir = NAJA_DIR / "summaries"
            summary_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            html_file = summary_dir / f"market_summary_{timestamp}.html"
            
            # 简单的Markdown转HTML（处理换行和基本格式）
            html_content = self._simple_markdown_to_html(summary)
            
            # 生成SVG时间线图
            svg_timeline = self._generate_svg_timeline(events if events else [])
            
            html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>📊 24小时市场总结 - {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
            color: #333;
        }}
        
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        
        .timeline-section {{
            background: #f8f9fa;
            padding: 30px 40px;
            border-bottom: 1px solid #eee;
        }}
        
        .timeline-section h2 {{
            font-size: 18px;
            color: #667eea;
            margin-bottom: 20px;
            text-align: center;
        }}
        
        .timeline-svg {{
            width: 100%;
            height: auto;
            display: block;
        }}
        
        @media (max-width: 600px) {{
            body {{
                padding: 10px;
            }}
            .container {{
                border-radius: 15px;
            }}
            .header {{
                padding: 25px 20px;
            }}
            .header h1 {{
                font-size: 22px;
            }}
            .content {{
                padding: 25px 20px;
                font-size: 16px;
            }}
            .timeline-section {{
                padding: 20px 15px;
            }}
            .footer {{
                padding: 15px 20px;
            }}
            .actions {{
                flex-direction: column;
            }}
            .btn {{
                width: 100%;
                justify-content: center;
            }}
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 40px;
            text-align: center;
            color: white;
        }}
        
        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
            font-weight: 700;
        }}
        
        .header .time {{
            font-size: 14px;
            opacity: 0.9;
        }}
        
        .content {{
            padding: 40px;
            line-height: 1.9;
            font-size: 17px;
        }}
        
        .content p {{
            margin-bottom: 14px;
        }}
        
        .content strong {{
            color: #667eea;
        }}
        
        .footer {{
            padding: 20px 40px;
            background: #f8f9fa;
            text-align: center;
            color: #666;
            font-size: 13px;
        }}
        
        .actions {{
            display: flex;
            gap: 12px;
            justify-content: center;
            margin-top: 20px;
            flex-wrap: wrap;
        }}
        
        .btn {{
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }}
        
        .btn-primary {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        
        .btn-primary:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(102, 126, 234, 0.4);
        }}
        
        .btn-secondary {{
            background: #f0f0f0;
            color: #333;
        }}
        
        .btn-secondary:hover {{
            background: #e0e0e0;
        }}
        
        @media (max-width: 600px) {{
            .header, .content, .footer, .timeline-section {{
                padding: 24px;
            }}
            .header h1 {{
                font-size: 22px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 24小时市场总结</h1>
            <div class="time">{datetime.now().strftime('%Y年%m月%d日 %H:%M')}</div>
        </div>
        
        {svg_timeline}
        
        <div class="content">
            {html_content}
        </div>
        
        <div class="footer">
            <p>由 Naja 智能生成 | <a href="#" onclick="window.close(); return false;" style="color: #667eea; text-decoration: none;">关闭窗口</a></p>
            <div class="actions">
                <button class="btn btn-primary" onclick="copyToClipboard()">📋 复制全文</button>
                <button class="btn btn-secondary" onclick="window.print()">🖨️ 打印</button>
            </div>
        </div>
    </div>
    
    <script>
        function copyToClipboard() {{
            const text = `{self._escape_js(summary)}`;
            navigator.clipboard.writeText(text).then(function() {{
                alert('已复制到剪贴板！');
            }}).catch(function(err) {{
                alert('复制失败，请手动选择复制');
            }});
        }}
    </script>
</body>
</html>"""
            
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_template)
            
            logger.info(f"HTML总结已生成: {html_file}")
            return html_file
        except Exception as e:
            logger.error(f"生成HTML总结失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _simple_markdown_to_html(self, text):
        """简单的文本转HTML（优化小红书风格）"""
        import re
        
        # 转义HTML特殊字符
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        
        # 处理换行 - 每行单独一段，更适合小红书风格
        lines = text.split('\n')
        html_lines = []
        for line in lines:
            line = line.strip()
            if line:
                # 处理加粗（**text**）
                line = re.sub(r'\*\*(.*?)\*\*', r'<strong style="color: #764ba2;">\1</strong>', line)
                html_lines.append(f'<p style="margin-bottom: 12px; font-size: 17px;">{line}</p>')
        
        return '\n'.join(html_lines)
    
    def _generate_svg_timeline(self, events):
        """生成响应式垂直河流时间线 - 适配移动端"""
        if not events or len(events) == 0:
            return ''
        
        # 限制显示数量
        display_events = events[:10]
        
        # 预处理时间线事件
        simplified_events = []
        for event in display_events:
            title = event.get('title', '')
            # 精简标题 - 最多14个字
            if len(title) > 14:
                title = title[:14]
            simplified_events.append({
                'type': event.get('type', 'unknown'),
                'time': event.get('time', ''),
                'title': title,
                'change': event.get('change', '')
            })
        
        # SVG尺寸 - 使用viewBox让SVG可缩放
        svg_width = 850
        event_count = len(simplified_events)
        svg_height = 150 + event_count * 150
        
        svg_parts = []
        svg_parts.append(f'''<div class="timeline-section">
    <svg class="timeline-svg" viewBox="0 0 {svg_width} {svg_height}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">''')
        
        # 背景
        svg_parts.append(f'<rect x="0" y="0" width="{svg_width}" height="{svg_height}" fill="#f8f9fa" rx="15"/>')
        
        # 标题
        svg_parts.append(f'<text x="{svg_width//2}" y="50" text-anchor="middle" font-size="24" font-weight="bold" fill="#667eea">🌊 市场时间线</text>')
        svg_parts.append(f'<text x="{svg_width//2}" y="78" text-anchor="middle" font-size="14" fill="#999">热点变化 · 新闻驱动 · 情绪流动</text>')
        
        # 垂直主时间轴
        timeline_center = svg_width // 2
        svg_parts.append(f'<line x1="{timeline_center}" y1="110" x2="{timeline_center}" y2="{svg_height-50}" stroke="#667eea" stroke-width="5" stroke-linecap="round"/>')
        
        # 河流背景装饰
        svg_parts.append(f'<path d="M {timeline_center-10} 110 Q {timeline_center+30} 200 {timeline_center-20} 300 T {timeline_center+10} {svg_height-50}" stroke="#e0e7ff" stroke-width="70" fill="none" opacity="0.4"/>')
        
        # 逐个绘制事件
        start_y = 150
        spacing = 150
        
        # 卡片尺寸优化
        card_width = 280
        card_left_margin = 40
        
        for i, event in enumerate(simplified_events):
            y = start_y + i * spacing
            event_type = event.get('type', 'unknown')
            
            # 颜色和图标配置
            config = {
                'cn_event': {'color': '#ff6b6b', 'icon': '🇨🇳', 'label': 'A股'},
                'us_event': {'color': '#4ecdc4', 'icon': '🇺🇸', 'label': '美股'},
                'high_score_news': {'color': '#ffd166', 'icon': '📰', 'label': '新闻'},
                'jin10_news': {'color': '#06d6a0', 'icon': '📌', 'label': '金十'},
            }.get(event_type, {'color': '#667eea', 'icon': '📊', 'label': '其他'})
            
            color = config['color']
            icon = config['icon']
            
            # 事件节点
            svg_parts.append(f'<circle cx="{timeline_center}" cy="{y}" r="24" fill="{color}" stroke="white" stroke-width="4"/>')
            svg_parts.append(f'<text x="{timeline_center}" y="{y+7}" text-anchor="middle" font-size="18">{icon}</text>')
            
            # 波浪连接线
            if i < event_count - 1:
                next_y = start_y + (i + 1) * spacing
                # 交替左右的波浪
                if i % 2 == 0:
                    ctrl_x = timeline_center + 40
                else:
                    ctrl_x = timeline_center - 40
                svg_parts.append(f'<path d="M {timeline_center} {y} Q {ctrl_x} {(y+next_y)/2} {timeline_center} {next_y}" stroke="{color}" stroke-width="3" fill="none" opacity="0.65"/>')
            
            # 事件卡片 - 左右交替
            if i % 2 == 0:
                card_x = card_left_margin
                svg_parts.append(f'<line x1="{card_x+card_width}" y1="{y}" x2="{timeline_center-30}" y2="{y}" stroke="{color}" stroke-width="3" stroke-dasharray="6,5"/>')
            else:
                card_x = timeline_center + 30
                svg_parts.append(f'<line x1="{timeline_center+30}" y1="{y}" x2="{card_x}" y2="{y}" stroke="{color}" stroke-width="3" stroke-dasharray="6,5"/>')
            
            # 卡片 - 圆角更大更圆润
            svg_parts.append(f'<rect x="{card_x}" y="{y-45}" width="{card_width}" height="90" rx="15" fill="white" stroke="#e0e0e0" stroke-width="2"/>')
            
            # 模拟阴影效果
            svg_parts.append(f'<rect x="{card_x+2}" y="{y-43}" width="{card_width-4}" height="86" rx="14" fill="none" stroke="rgba(0,0,0,0.03)" stroke-width="1"/>')
            
            # 时间 - 更大更清晰
            svg_parts.append(f'<text x="{card_x+18}" y="{y-10}" font-size="17" fill="#666" font-weight="bold">⏰ {event["time"]}</text>')
            
            # 标题 - 更大字号
            svg_parts.append(f'<text x="{card_x+18}" y="{y+20}" font-size="18" fill="#333" font-weight="600">{event["title"]}</text>')
            
            # 变动（如果有）
            if event.get('change'):
                svg_parts.append(f'<text x="{card_x+18}" y="{y+50}" font-size="16" fill="{color}" font-weight="bold">{event["change"]}</text>')
        
        svg_parts.append('''</svg>
</div>''')
        
        return '\n'.join(svg_parts)
    
    def _escape_js(self, text):
        """转义JavaScript字符串"""
        return text.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')
    
    def _get_events_hash(self, events):
        """生成事件列表的hash值，用于缓存key"""
        import hashlib
        import json
        
        # 只提取关键信息生成hash（避免微小变化也能用缓存
        simplified = []
        for event in events[:15]:  # 只用前15个事件
            simplified.append({
                'type': event.get('type', ''),
                'title': event.get('title', ''),
                'change': event.get('change', ''),
            })
        
        # 生成json字符串
        events_str = json.dumps(simplified, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(events_str.encode('utf-8')).hexdigest()
    
    def _get_cached_summary(self, events):
        """获取缓存的总结"""
        import time
        import json
        
        try:
            cache_dir = NAJA_DIR / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            events_hash = self._get_events_hash(events)
            cache_file = cache_dir / f"summary_{events_hash}.json"
            
            if not cache_file.exists():
                return None
            
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # 检查是否过期（2小时 = 7200秒）
            cache_time = cache_data.get('timestamp', 0)
            if time.time() - cache_time > 7200:
                logger.info("缓存已过期")
                return None
            
            logger.info("找到缓存的总结")
            return cache_data.get('summary')
        except Exception as e:
            logger.error(f"读取缓存失败: {e}")
            return None
    
    def _save_summary_cache(self, events, summary):
        """保存总结到缓存"""
        import time
        import json
        
        try:
            cache_dir = NAJA_DIR / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            events_hash = self._get_events_hash(events)
            cache_file = cache_dir / f"summary_{events_hash}.json"
            
            cache_data = {
                'timestamp': time.time(),
                'events_hash': events_hash,
                'summary': summary
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"总结已缓存: {cache_file}")
            
            # 清理旧缓存（保留最近10个）
            self._cleanup_old_cache(cache_dir)
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")
    
    def _cleanup_old_cache(self, cache_dir):
        """清理旧缓存文件"""
        try:
            cache_files = sorted(
                cache_dir.glob("summary_*.json"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            
            # 只保留最近10个
            for old_file in cache_files[10:]:
                try:
                    old_file.unlink()
                    logger.info(f"清理旧缓存: {old_file.name}")
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")

    def _get_system_status(self):
        """获取系统运行状态（带缓存）"""
        import time
        now = time.time()
        
        # 缓存 10秒
        if self._last_system_status and (now - self._last_system_status_ts < 10):
            return self._last_system_status
        
        health_data = _http_get("/api/health")
        result = health_data if health_data else {"status": "unknown", "message": "无法连接"}
        
        # 保存缓存
        self._last_system_status = result
        self._last_system_status_ts = now
        return result

    def _check_naja_ready(self) -> bool:
        """检查 Naja 主进程是否已启动"""
        health_data = _http_get("/api/health", timeout=2.0)
        return health_data is not None

    def _build_simple_menu(self):
        """构建简化菜单（不依赖 Naja 进程，用于快速启动）"""
        if self._app is None:
            return

        try:
            import rumps
            port = _get_naja_port()
        except Exception as e:
            logger.error(f"获取端口失败: {e}")
            port = DEFAULT_PORT

        self._app.menu.clear()
        self._app.icon = ICON_PURPLE

        self._app.menu["📊 Naja 管理平台"] = None
        self._app.menu["🟡 启动中..."] = None
        self._app.menu[f"📍 端口: {port}"] = None
        self._app.menu["sep0"] = rumps.separator

        self._app.menu.add(rumps.MenuItem("🌐 打开管理界面", callback=self._on_open_web))
        self._app.menu.add(rumps.MenuItem("🔄 刷新菜单", callback=self._on_refresh))
        self._app.menu["sep1"] = rumps.separator
        self._app.menu.add(rumps.MenuItem("📋 关于", callback=lambda sender: self._show_about_simple()))

    def _show_about_simple(self):
        """显示简化版关于信息"""
        import rumps
        rumps.alert(
            title="Naja 管理平台",
            message="Naja 正在启动中...\n\n请稍后刷新菜单查看完整内容。",
            icon_path=ICON_PURPLE
        )

    def _build_menu(self):
        """构建托盘菜单（使用缓存数据，毫秒级响应）"""
        if self._app is None:
            return

        with self._menu_cache_lock:
            if self._menu_cache:
                self._timeline_events = self._menu_cache.get('timeline', {})
                system_status = self._menu_cache.get('status', {})
                trading_time = self._menu_cache.get('trading', False)
            else:
                try:
                    self._timeline_events = self._get_timeline_events()
                except Exception as e:
                    logger.error(f"获取时间线数据失败: {e}")
                    self._timeline_events = {"success": False, "stats": {}, "list": []}

                try:
                    system_status = self._get_system_status()
                except Exception as e:
                    logger.error(f"获取系统状态失败: {e}")
                    system_status = {}

                trading_time = _is_trading_time()

        try:
            port = _get_naja_port()
        except Exception as e:
            logger.error(f"获取端口失败: {e}")
            port = 8080

        try:
            import rumps

            icon_path = ICON_GREEN if trading_time else ICON_PURPLE
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
            
            # 登录启动项区域
            try:
                autostart_item = rumps.MenuItem("🚀 登录时自动启动")
                autostart_item.state = 1 if is_login_item_enabled() else 0
                autostart_item.set_callback(self._on_toggle_autostart)
                self._app.menu.add(autostart_item)
            except Exception as e:
                logger.warning(f"添加登录启动项菜单失败: {e}")
            
            self._app.menu["sep1.5"] = rumps.separator
            
            # 主功能区域
            self._app.menu.add(rumps.MenuItem("🌐 打开 Web", callback=self._on_open_web))
            self._app.menu.add(rumps.MenuItem("📄 打开日志", callback=self._on_open_logs))
            self._app.menu.add(rumps.MenuItem("🔄 刷新", callback=self._on_refresh))
            self._app.menu.add(rumps.MenuItem("☁️ 从服务器同步", callback=self._on_sync_from_server))
            self._app.menu["sep2"] = rumps.separator
            
            # --- 开始：24 小时时间线风格菜单 ---
            try:
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
                    
                    # 添加一键总结按钮
                    self._app.menu.add(rumps.MenuItem("✨ 一键总结当前时间线", callback=self._on_one_click_summary))
                    
                    events = self._timeline_events.get('list', [])
                    last_date = None
                    
                    # 最多显示 20 条，避免菜单太长
                    display_events = events[:20]
                    
                    for event in display_events:
                        try:
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
                                menu_text = f"{event_time} 📰 {title}"
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
                        except Exception as e:
                            logger.error(f"添加时间线事件失败: {e}")
                else:
                    self._app.menu.add(rumps.MenuItem("⏰ 暂无时间线数据"))
            except Exception as e:
                logger.error(f"构建时间线菜单失败: {e}")
                self._app.menu.add(rumps.MenuItem("⚠️ 时间线加载失败"))
            
            self._app.menu["sep3"] = rumps.separator
            self._app.menu["重启服务"] = rumps.MenuItem("🔄 重启服务", callback=self._on_reload)
            
            # 更新菜单构建时间戳
            import time
            self._last_menu_build_ts = time.time()
        except Exception as e:
            logger.error(f"更新菜单失败: {e}")
            import traceback
            traceback.print_exc()
            # 尝试恢复菜单到最小状态
            try:
                self._app.menu.clear()
                self._app.menu["📊 Naja 管理平台"] = None
                self._app.menu["⚠️ 菜单更新失败"] = None
                self._app.menu["sep0"] = rumps.separator
                self._app.menu["重启服务"] = rumps.MenuItem("🔄 重启服务", callback=self._on_reload)
                
                # 更新菜单构建时间戳
                import time
                self._last_menu_build_ts = time.time()
            except Exception as restore_e:
                logger.error(f"恢复菜单失败: {restore_e}")
    
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

        self._kill_running_tray()

        try:
            import rumps

            self._app = rumps.App("Naja", icon=ICON_PURPLE, quit_button=rumps.MenuItem("❌ 退出", callback=self._on_quit))
            self._build_simple_menu()
            self._naja_ready = False

            rumps.timer(interval=5)(self._on_timer)(self._app)

            self._start_background_preloader()
            save_tray_pid()

            logger.info("托盘已启动（简化菜单）")
            self._app.run()
        except Exception as e:
            logger.error(f"启动托盘失败: {e}")
            clear_tray_pid()

    def _on_timer(self, _sender):
        import time
        import rumps
        now = time.time()
        
        # 检查是否有待处理的同步通知
        if hasattr(self, '_sync_pending_notification') and self._sync_pending_notification:
            notification = self._sync_pending_notification
            rumps.notification(
                title=notification['title'],
                subtitle=notification['subtitle'],
                message=notification['message']
            )
            self._sync_pending_notification = None
        
        # 检查是否有待处理的总结结果
        if hasattr(self, '_summary_pending_result') and self._summary_pending_result:
            result = self._summary_pending_result
            self._summary_pending_result = None
            
            if result['type'] == 'error':
                # 显示错误通知
                notification = result['notification']
                rumps.notification(
                    title=notification['title'],
                    subtitle=notification['subtitle'],
                    message=notification['message']
                )
            else:
                # 处理成功结果（缓存或新生成）
                summary = result['summary']
                events = result['events']
                
                # 显示总结结果
                logger.info(f"总结完成: {summary[:100]}...")
                
                # 保存完整总结到本地文件
                summary_file = self._save_summary_to_file(summary)
                
                # 复制到剪贴板
                self._copy_to_clipboard(summary)
                
                # 发送到钉钉
                self._send_to_dingtalk(summary)
                
                # 显示简短通知，同时打开完整总结
                self._show_summary_notification(summary, summary_file, events)
        
        if not self._naja_ready:
            if self._check_naja_ready():
                logger.info("检测到 Naja 已启动，切换到完整菜单")
                self._naja_ready = True
                self._build_menu()
                self._last_menu_build_ts = now
                # 首次检测到 Naja 启动时检查一次通知
                self._check_and_send_notifications()
        else:
            # 正常状态下 30秒刷新一次，减少卡顿
            if now - self._last_menu_build_ts >= 30:
                self._build_menu()
                self._last_menu_build_ts = now
                # 检查并发送通知
                self._check_and_send_notifications()

    def stop(self):
        import rumps
        if self._app:
            rumps.quit_application()
            self._app = None
        self._clear_tray_pid()

    def update_data(self):
        """更新数据（清除缓存，强制刷新）"""
        self._last_timeline_data = None
        self._last_timeline_ts = 0
        self._last_system_status = None
        self._last_system_status_ts = 0
        self._last_menu_build_ts = 0
        self._build_menu()

    def _on_toggle_autostart(self, sender):
        """切换登录启动项状态"""
        import rumps
        
        new_state = 1 - sender.state
        try:
            if new_state == 1:
                success = toggle_login_item()
                action = "启用" if success else "启用"
            else:
                success = toggle_login_item()
                action = "禁用" if success else "禁用"
            
            if success:
                sender.state = new_state
                logger.info(f"登录启动项已{action}")
                rumps.notification(
                    title="🚀 登录启动项",
                    subtitle=f"已{action}登录时自动启动",
                    message="重启电脑后生效" if new_state == 1 else "已取消自动启动"
                )
            else:
                logger.error(f"登录启动项{action}失败")
                sender.state = 1 - new_state
        except Exception as e:
            logger.error(f"切换登录启动项失败: {e}")
            sender.state = 1 - new_state


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
