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
from deva.naja.infra.prefs import get_pref, set_pref
from deva.naja.infra.runtime.daemon import (
    get_running_pid, get_running_tray_pid,
    save_tray_pid, clear_tray_pid, clear_pid
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


# 注意：这里**刻意不提供**「HTTP 版」的交易时段判断。
# 它原来长这样：`_http_get("/api/trading/status")`（5s 超时、无缓存），
# 只在 _build_menu() 里被调用一次 —— 也就是 AppKit 主线程上。
# 服务端口径（含节假日）已经随 /api/tray/data 进了 _menu_cache['trading']，
# 主线程只需要「缓存优先、回退本地纯计算」两条路，任何一条都不允许发请求。


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
        # 这是本机 API 调用，必须绕开环境代理（如 Surge 的 http_proxy），
        # 否则会被转发出去导致 502/超时，托盘就永远拿不到数据。
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(url, headers={"User-Agent": "NajaTray/1.0"})
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug(f"HTTP GET {url} 失败: {e}")
        return None


class MenuBarTray:
    _instance: Optional['MenuBarTray'] = None

    #: 操作状态位。**必须留在类上**：``__init__`` 里会重新赋值为 ``None``，
    #: 但守卫（如 ``verify_naja_restart``）会 ``object.__new__`` 跳过 rumps 初始化，
    #: 此时若只有实例属性，``_update_op`` / ``_clear_op`` / ``_apply_op_status``
    #: 会直接 AttributeError —— 而它们正是「重启服务」第一步要走的路径。
    #: 类级默认既是兜底，也让「未初始化」与「空闲」同义，不会误报「有任务在跑」。
    _op_status = None

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
        self._last_menu_build_ts = 0
        self._notified_news_ids = set()
        self._notification_enabled = True
        # 通知聚合限流：修好时间线截断后，单轮可能出现多条达标新闻，
        # 逐条弹会从"从不响"直接变成"轰炸"。改为时间窗内最多一条聚合通知。
        self._last_notify_ts = 0.0
        # 相关性关键词缓存（持仓/关注主题），用于给通知排序——5 分钟 TTL
        self._relevance_kw_cache = None
        self._relevance_kw_ts = 0.0

        # 操作状态位：长任务在菜单栏文字（app.title）上呈现进度。
        # 结构 {"key", "label", "started", "busy"} 或 None；busy=True 的长任务互斥。
        self._op_status = None

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
                        self._log_preload_failure(tray_data)

                except Exception as e:
                    self._log_preload_failure(e)
                finally:
                    time.sleep(10)

            logger.info("[Tray] 后台预加载线程退出")

        import threading
        self._preload_thread = threading.Thread(target=preloader, daemon=True)
        self._preload_thread.start()
        logger.info("[Tray] 后台预加载线程已启动")

    def _log_preload_failure(self, detail):
        """预加载失败的日志分级。

        托盘通常比 Naja 先起来，启动期必然有若干轮拿不到数据；那不是故障，
        按 warning 打会长期污染日志、掩盖真正的失败（服务已监听却仍取不到）。
        只在「端口确实在监听」时才升级为 warning。
        """
        try:
            service_up = self._check_naja_listening()
        except Exception:
            service_up = False

        if service_up:
            logger.warning(f"[Tray] 预加载失败（服务已就绪）: {detail}")
        else:
            logger.debug(f"[Tray] 预加载跳过：服务尚未监听，稍后重试")

    # ── 通知聚合限流参数 ─────────────────────────────────────────────
    # 修好时间线截断（见 select_timeline_events）后，单轮可能出现多条达标新闻，
    # 若仍逐条弹，会从"从不响"直接变成"轰炸"。改为时间窗内最多一条**聚合**通知。
    NOTIFY_MIN_INTERVAL = 300.0    # 时间窗：每 5 分钟最多一条通知
    NOTIFY_MIN_SCORE = 0.7         # 分数线（沿用原逻辑）
    NOTIFY_RELEVANCE_TTL = 300.0   # 相关性关键词缓存时长

    def _relevance_keywords(self) -> set:
        """持仓 / 自选 / 关注主题的关键词，供通知排序用；缓存 5 分钟。

        读不到就返回空集 → 排序降级为纯分数排序，**绝不阻断通知本身**。
        与 ``news.focus`` 共用同一份焦点快照（60s TTL），不重复造数据。
        """
        import time
        now = time.time()
        if (self._relevance_kw_cache is not None
                and (now - self._relevance_kw_ts) < self.NOTIFY_RELEVANCE_TTL):
            return self._relevance_kw_cache

        kws = set()
        try:
            from deva.naja.news.focus import build_focus_state
            state = build_focus_state()
            for ident in state.own_identifiers():
                if ident and len(str(ident).strip()) >= 2:
                    kws.add(str(ident))
            for name, keywords in state.themes:
                if name and len(str(name).strip()) >= 2:
                    kws.add(str(name))
                for k in keywords:
                    if k and len(str(k).strip()) >= 2:
                        kws.add(str(k))
            for n in (*state.narratives, *state.blocks):
                if n and len(str(n).strip()) >= 2:
                    kws.add(str(n))
        except Exception as e:
            logger.debug(f"[Tray] 相关性关键词读取失败（降级为纯分数排序）: {e}")

        self._relevance_kw_cache = kws
        self._relevance_kw_ts = now
        return kws

    def _check_and_send_notifications(self):
        if not self._naja_ready:
            return

        try:
            # 只消费后台预加载线程从 /api/tray/data 拿到的数据。
            # 注意：本方法运行在 AppKit 主线程（_on_timer 回调），**绝不能**在这里
            # 调用 _get_high_score_news()/_get_jin10_important_news() —— 它们会回退到
            # Playwright 实时抓取，同步阻塞最长 15s，直接把菜单栏冻住并推迟图标绘制。
            timeline = None
            with self._menu_cache_lock:
                if self._menu_cache:
                    timeline = self._menu_cache.get('timeline')
            if not timeline:
                timeline = self._last_timeline_data

            if not timeline or not timeline.get('success'):
                return

            # ① 收集候选（未通知过、分数达标）
            candidates = []
            for news in timeline.get('list', []):
                news_type = news.get('type', '')
                if news_type not in ('high_score_news', 'jin10_news'):
                    continue

                score = news.get('score', 0) or 0
                if score < self.NOTIFY_MIN_SCORE:
                    continue

                title = news.get('title', '') or news.get('block_name', '')
                if not title:
                    continue

                news_id = f"{news_type}_{news.get('timestamp', 0)}_{title[:20]}"
                if news_id in self._notified_news_ids:
                    continue

                candidates.append({'id': news_id, 'score': score, 'title': title})

            if not candidates:
                return

            # ② 限流：距上次通知不足时间窗则本轮不发。候选留在池中（未标已通知），
            #    到点后一次性聚合发出——既不"攒着不发"，也不"逐条轰炸"。
            import time
            now = time.time()
            if now - self._last_notify_ts < self.NOTIFY_MIN_INTERVAL:
                return

            # ③ 相关性优先：持仓/自选/关注主题命中的排前面，同组按分数降序
            keywords = self._relevance_keywords()

            def _sort_key(item):
                lowered = item['title'].lower()
                hit = 1 if any(
                    k.lower() in lowered for k in keywords if k) else 0
                return (-hit, -item['score'])

            candidates.sort(key=_sort_key)

            # ④ 聚合发出：只弹一条；本轮**所有**候选都标记已通知，避免下轮重复
            for item in candidates:
                self._notified_news_ids.add(item['id'])
            if len(self._notified_news_ids) > 100:
                self._notified_news_ids = set(list(self._notified_news_ids)[-50:])

            top = candidates[0]
            if len(candidates) == 1:
                self._send_notification(
                    top['title'], f"重要新闻 · 评分: {top['score']:.2f}")
            else:
                self._send_notification(
                    f"📰 {len(candidates)} 条重要新闻",
                    top['title'][:60],
                    f"另有 {len(candidates) - 1} 条 · 点开菜单查看",
                )
            self._last_notify_ts = now

        except Exception as e:
            logger.error(f"[Tray] 检查通知失败: {e}")

    def _get_timeline_events(self, allow_local_fetch: bool = False) -> dict:
        """获取 24 小时时间线数据（带缓存）

        allow_local_fetch:
            - False（默认，**主线程必须用这个**）：只返回已有缓存，绝不触发本地实时抓取。
              本地抓取最终会回退到 `_fetch_jin10_via_playwright()`，同步 `asyncio.run`
              阻塞最长 15s，跑在主线程会直接冻结菜单栏。
            - True：允许本地抓取，仅限后台线程使用（如「一键总结」任务）。
        """
        import time
        now = time.time()
        
        # 缓存 30秒
        if self._last_timeline_data and (now - self._last_timeline_ts < 30):
            return self._last_timeline_data
        
        if not allow_local_fetch:
            # 主线程保护：宁可用旧数据/空数据，也不在这里阻塞抓取。
            return self._last_timeline_data or {"success": False, "stats": {}, "list": []}
        
        try:
            from datetime import datetime, timedelta
            from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
                _get_a_block_events,
                _get_us_events,
                _get_high_score_news,
                _get_jin10_important_news,
                select_timeline_events,
                TRAY_TIMELINE_LIMITS,
                format_change_percent,
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
            for event in select_timeline_events(all_events, TRAY_TIMELINE_LIMITS):
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
                    item['change'] = format_change_percent(event.get('change_percent', 0))
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

    def _wait_for_pid_exit(self, pid: int, timeout: float = 15.0) -> bool:
        """等待指定 PID 的进程真正退出。

        Returns:
            True 表示进程已退出；False 表示超时仍存活。
        """
        start = time_module.time()
        while time_module.time() - start < timeout:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            except PermissionError:
                # 进程仍存在（权限不足说明 PID 被占用）
                pass
            time_module.sleep(0.2)
        return False

    def _wait_for_naja_ready(self, timeout: float = 30.0) -> bool:
        """轮询 /api/health，等待新服务真正就绪。"""
        start = time_module.time()
        while time_module.time() - start < timeout:
            if self._check_naja_ready():
                return True
            time_module.sleep(0.5)
        return False

    def _call_on_main_thread(self, fn):
        """在 AppKit 主线程执行 fn；从后台线程调用时自动切回主线程。"""
        try:
            from PyObjCTools import AppHelper
            AppHelper.callAfter(fn)
        except Exception:
            # 拿不到 AppHelper（非 macOS / 异常）时退化为直接调用
            try:
                fn()
            except Exception as e:
                logger.error(f"主线程回调执行失败: {e}")

    def _quit_on_main_thread(self):
        """退出托盘。从后台线程调用时切回 AppKit 主线程，避免 UI 操作跨线程。"""
        import rumps
        self._call_on_main_thread(rumps.quit_application)

    # ── 操作状态位：让长任务"看得见" ──────────────────────────────────
    # 背景（2026-10-13 用户反馈）：点「系统 → 重启服务」后菜单立刻关闭，而重启
    # 最长要 45s（等旧进程退出 ≤15s + 等新服务就绪 ≤30s），期间菜单栏图标、
    # 菜单内容、通知**全无变化**；成功时更是完全静默（代码里只有
    # _notify_restart_failed 一条通知路径）。用户只能靠猜。
    #
    # 这里用菜单栏文字（app.title）承载状态——它是唯一「始终可见、不受勿扰
    # 模式影响、且与图标可共存」的通道（setStatusBarTitle→setTitle_ 与
    # setImage_ 互不冲突）。系统通知保留作为完成态提醒，但不再作为唯一反馈。

    def _set_app_title(self, text):
        """写菜单栏文字（传 None 清除）。仅主线程调用。"""
        if self._app is None:
            return
        try:
            self._app.title = text
        except Exception as e:
            logger.debug(f"设置菜单栏标题失败: {e}")

    def _apply_op_status(self):
        """把状态位渲染到菜单栏文字 + 菜单。**只能在主线程调用**。"""
        self._set_app_title(self._op_status["label"] if self._op_status else None)
        if self._app is None:
            return
        try:
            # 重建菜单，让状态行不再谎报「运行中」——重启期间旧服务确实已停。
            if self._naja_ready:
                self._build_menu()
            else:
                self._build_simple_menu()
        except Exception as e:
            logger.debug(f"状态位渲染菜单失败: {e}")

    def _begin_op(self, key: str, label: str) -> bool:
        """申请一个长任务状态位。返回 False = 已有长任务在进行（互斥拒绝）。

        互斥是必需的：重启期间再点一次重启会起第二个线程，两个线程同时 kill
        同一个 PID、同时 Popen 新进程 → 服务状态彻底错乱。
        """
        if self._op_status is not None and self._op_status.get("busy"):
            logger.info(f"拒绝操作 {key}：{self._op_status.get('key')} 正在进行中")
            return False
        import time
        self._op_status = {"key": key, "label": label,
                           "started": time.time(), "busy": True}
        self._call_on_main_thread(self._apply_op_status)
        return True

    def _update_op(self, label: str):
        """更新进行中长任务的文案（如「停止旧服务…」→「启动新服务…」）。"""
        if self._op_status is None:
            return
        self._op_status["label"] = label
        self._call_on_main_thread(self._apply_op_status)

    def _clear_op(self, key: str = None):
        """释放状态位，恢复菜单栏文字与菜单。

        传 key 时只清「确实是自己的」状态位——避免一个慢任务把另一个任务的
        状态误清掉（两者的完成时序本就无法保证）。
        """
        cur = self._op_status
        if cur is None:
            return
        if key is not None and cur.get("key") != key:
            return
        self._op_status = None
        self._call_on_main_thread(self._apply_op_status)

    def _flash_status(self, label: str, seconds: float = 2.0, key: str = "flash"):
        """短暂提示一个状态（如「已刷新」），到点自动清除。

        与长任务的区别：flash 不置 busy，可被后续 flash 覆盖，但**不会抢占**
        正在进行的长任务（否则会把「重启中…」冲掉，用户又失去进度）。
        """
        if self._op_status is not None and self._op_status.get("busy"):
            return
        import time
        import threading
        self._op_status = {"key": key, "label": label,
                           "started": time.time(), "busy": False}
        self._call_on_main_thread(self._apply_op_status)

        def _expire():
            # 只清「还是自己这个 flash」且「没被长任务顶掉」的
            cur = self._op_status
            if cur is not None and cur.get("key") == key and not cur.get("busy"):
                self._clear_op()

        threading.Timer(seconds, _expire).start()

    def _op_line(self, port) -> str:
        """状态行文案：有长任务进行时改为显示任务进度，空串表示走常态。

        为什么不能在有操作时继续写「运行中」：重启期间托盘自身**故意不重启**
        （避免图标空窗），菜单不会重建，那行会一直挂着旧状态——而此刻旧服务
        其实已经停了。用户点开菜单想确认，看到的反而是错的状态。
        """
        op = self._op_status
        if op is not None and op.get("busy"):
            return f"{op['label']} · 端口 {port}"
        return ""

    def _restart_tray(self):
        """重启 Naja 服务器（菜单栏文字实时显示进度；同一时刻只允许一个）

        整个流程在后台线程执行，避免阻塞菜单栏事件循环。
        """
        if not self._begin_op("restart", "🔄 正在重启…"):
            self._send_notification("⏳ 已有任务在进行", "请等待当前任务完成",
                                    "同一时刻只允许一个长任务")
            return
        import threading
        thread = threading.Thread(target=self._do_restart_tray, daemon=True)
        thread.start()

    def _do_restart_tray(self):
        """重启主流程 + 状态位兜底释放。

        finally 是必需的：若中途抛出未捕获异常（如写日志文件失败），状态位
        会永远停在「重启中…」，**后续所有长任务都会被互斥拒绝**——那比不显示
        状态更糟。所以无论成功、失败还是异常，都保证释放。
        """
        try:
            self._do_restart()
        finally:
            self._clear_op("restart")

    def _do_restart(self):
        logger.info("正在重启 Naja 服务...")
        self._update_op("🔄 停止旧服务…")

        env = os.environ.copy()
        env["LSUIElement"] = "1"
        # 告诉新服务：托盘由本进程继续持有，不要接管/重启托盘。
        # 这样整个服务重启期间菜单栏图标保持不变（旧方案会先杀托盘再起新托盘，
        # 造成约 3s 的图标空窗）。
        env["NAJA_KEEP_TRAY"] = "1"
        deva_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
        python_path = env.get("PYTHONPATH", "")
        if python_path:
            env["PYTHONPATH"] = f"{deva_root}:{python_path}"
        else:
            env["PYTHONPATH"] = deva_root

        # 1) 停止旧服务，并等待它真正退出。
        #    关键：旧服务优雅关闭需要数秒，期间 PID 文件仍是旧 PID。
        #    如果像以前那样只 sleep(1) 就启动新进程，新进程会被 __main__ 的
        #    is_running() 判定为“已在运行”而直接退出，导致服务整体停摆。
        pid = self._get_running_pid()
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                logger.info(f"已向旧 Naja 服务器发送停止信号 (PID: {pid})")
            except ProcessLookupError:
                logger.info(f"旧 Naja 服务器已不存在 (PID: {pid})")
                pid = None
            except Exception as e:
                logger.error(f"停止旧 Naja 服务器失败: {e}")
                pid = None

            if pid and not self._wait_for_pid_exit(pid, timeout=15.0):
                logger.warning(f"旧 Naja 服务器未在 15s 内退出，强制终止 (PID: {pid})")
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self._wait_for_pid_exit(pid, timeout=5.0)

            if pid:
                logger.info(f"旧 Naja 服务器已退出 (PID: {pid})")

        # 无论旧进程如何退出，都清掉可能残留的 PID 文件，避免新进程误判“已在运行”
        clear_pid()

        # 2) 启动新的 Naja 服务器
        self._update_op("🔄 启动新服务…")
        naja_cmd = [sys.executable, "-m", "deva.naja", "-s", "start"]
        naja_log_file = NAJA_DIR / "logs" / "naja_restart.log"
        try:
            from deva.naja.infra.log.colorful_logger import open_rotated_file
            with open_rotated_file(str(naja_log_file)) as f:
                subprocess.Popen(
                    naja_cmd,
                    env=env,
                    cwd=deva_root,
                    # 关键：托盘自身的 stdin 可能是继承来的坏 fd（lsof 显示 revoked）。
                    # 若不显式重定向，子进程会继承它，Python 解释器在
                    # init_sys_streams 阶段直接 "Fatal Python error: Bad file descriptor" 而崩。
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                    stdout=f,
                    stderr=subprocess.STDOUT
                )
            logger.info("已启动新的 Naja 服务器")
        except Exception as e:
            logger.error(f"启动新的 Naja 服务器失败: {e}")
            self._notify_restart_failed(f"启动失败: {e}")
            return

        # 3) 确认新服务真的起来了。未就绪时保留当前托盘，避免出现
        #    “旧服务已停、新服务未起、托盘又自杀”的全停局面。
        self._update_op("🔄 等待服务就绪…")
        if not self._wait_for_naja_ready(timeout=30.0):
            logger.error("新 Naja 服务器启动后 30s 内未就绪，保留当前托盘")
            self._notify_restart_failed(
                "新服务 30s 内未就绪，已保留托盘，详见 ~/.naja/logs/naja_restart.log"
            )
            return

        # 4) 新服务已就绪。托盘**不重启**：它在整个服务重启期间保持存活，
        #    菜单栏图标因此不会消失（旧方案「先杀旧托盘、再起新托盘」有约 3s 空窗）。
        #    只在主线程刷新一次菜单，让新服务的数据立刻生效。
        logger.info("新 Naja 服务器已就绪，托盘保持存活")
        # 成功态：原来这里**一句提示都没有**（只有失败才通知），用户根本
        # 不知道重启好没好。菜单栏文字也会由 _clear_op 恢复为常态。
        self._clear_op("restart")
        self._send_notification("✅ 重启完成", "Naja 服务已就绪",
                                f"端口 {_get_naja_port()}")
        self._call_on_main_thread(self._refresh_after_restart)

    def _refresh_after_restart(self):
        """服务重启完成后在主线程刷新托盘（本方法只在主线程被调用）。"""
        try:
            self._naja_ready = True
            self._start_background_preloader()  # 幂等：线程已在跑则直接返回
            self.update_data()
            logger.info("托盘菜单已刷新")
        except Exception as e:
            logger.error(f"重启后刷新托盘菜单失败: {e}")

    def _notify_restart_failed(self, message: str):
        """重启失败时提示用户"""
        try:
            import rumps
            rumps.notification(
                title="Naja 重启失败",
                subtitle="服务未启动",
                message=message
            )
        except Exception as e:
            logger.error(f"发送重启失败通知失败: {e}")

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
            # Popen（非阻塞）而非 run：run 会同步等 `open` 退出，虽然是毫秒级，
            # 但没必要在 AppKit 主线程上等任何子进程。
            subprocess.Popen(["open", str(log_dir)])
        except Exception as e:
            logger.error(f"打开日志目录失败: {e}")

    def _on_quit(self, sender):
        """退出托盘并停掉 Naja 服务。

        这里是**唯一有意保留的主线程阻塞**：SIGTERM 后忙等最多 10s，等优雅退出，
        超时再 SIGKILL。之所以不挪到后台线程——托盘进程一退，daemon 线程随之消失，
        就没人做"超时升级到 SIGKILL"这一步了，服务可能永远不退出。
        代价仅在用户主动点「退出」时发生（菜单本就即将消失），可接受。

        2026-10-13 补：先亮出「🚪 正在退出…」并**让 runloop 转一圈把标题画出来**，
        再执行阻塞等待——否则阻塞期间 AppKit 不重绘，用户在整个退出过程里看到的
        仍是「运行中」，又是一次无感知。
        """
        logger.info("托盘菜单触发退出")
        import threading
        import time
        self._op_status = {"key": "quit", "label": "🚪 正在退出…",
                           "started": time.time(), "busy": True}
        self._apply_op_status()
        # 用短延时定时器把真正的停止逻辑推后 0.4s：这 0.4s 内主线程空闲、runloop
        # 正常跑，菜单栏文字才真的画得出来；之后才进入阻塞等待。
        threading.Timer(0.4, self._call_on_main_thread_quit).start()

    def _call_on_main_thread_quit(self):
        """0.4s 后切回主线程执行真正的停止 + 退出（见 _on_quit 说明）。"""
        self._call_on_main_thread(self._stop_service_and_quit)

    def _stop_service_and_quit(self):
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
        """刷新托盘数据：后台拉一次最新数据，完成后重建菜单并给出可见反馈。

        原来只是同步调一次 _build_menu()（读内存缓存）——既没有可见反馈，
        也没真的去取新数据，用户点完完全无法判断"有没有用"。
        """
        logger.info("刷新托盘数据")
        import threading
        import time
        self._flash_status("🔄 刷新中…", 3.0, key="refresh")

        def work():
            data = _http_get("/api/tray/data", timeout=10.0)
            if data and data.get("success"):
                with self._menu_cache_lock:
                    self._menu_cache = {
                        'timeline': data.get('timeline', {}),
                        'status': data.get('health', {}),
                        'trading': data.get('trading', {}).get('is_trading', False),
                        'timestamp': time.time(),
                    }

            def apply():
                self._build_menu()
                self._flash_status(f"✅ 已刷新 {time.strftime('%H:%M:%S')}",
                                   2.0, key="refresh")

            self._call_on_main_thread(apply)

        threading.Thread(target=work, daemon=True).start()

    def _on_sync_from_server(self, sender):
        """从服务器同步数据（菜单栏文字显示进度；同一时刻只允许一个长任务）"""
        import threading
        import rumps

        logger.info("开始从服务器同步数据...")

        if not self._begin_op("sync", "☁️ 同步中…"):
            self._send_notification("⏳ 已有任务在进行", "请等待当前任务完成",
                                    "同一时刻只允许一个长任务")
            return

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
            finally:
                # 无论成功/失败/异常都释放状态位——卡住会让后续长任务全被互斥拒绝
                self._clear_op("sync")

        thread = threading.Thread(target=sync_task, daemon=True)
        thread.start()

    def _on_one_click_summary(self, sender):
        """一键总结：调用大模型总结时间线数据（带缓存）

        大模型调用可能十几秒（还含代理兜底重试），同样接入状态位——
        菜单栏会显示「🧠 总结中…」，用户不必盯着毫无变化的菜单栏猜。
        """
        import threading
        import rumps

        logger.info("开始一键总结...")

        if not self._begin_op("summary", "🧠 总结中…"):
            self._send_notification("⏳ 已有任务在进行", "请等待当前任务完成",
                                    "同一时刻只允许一个长任务")
            return

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
                # 获取时间线数据（本函数运行在后台线程，允许本地抓取补数据）
                timeline_data = self._get_timeline_events(allow_local_fetch=True)
                
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
                    
                    # 调用大模型（带代理兜底：启动后才失效的本地代理在此自愈）
                    from deva.llm.client import sync_gpt
                    try:
                        summary = sync_gpt(prompt)
                    except Exception:
                        # 启动时端口还活着、之后才死掉的本地代理会落到这里
                        # （启动期清洗当时判定它是"活代理"因而保留了它）。
                        # sanitize_proxy_env() 返回非空 = 确实剔掉了死代理，
                        # 环境已变 → 值得重试一次（AsyncOpenAI 每次新建都重读 env）。
                        from deva.naja.infra.runtime.daemon import sanitize_proxy_env
                        if not sanitize_proxy_env():
                            raise
                        logger.info("检测到已失效的本地代理，清除后重试一次")
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
                        'subtitle': self._summarize_error_hint(e),
                        'message': str(e)[:100] if len(str(e)) > 100 else str(e)
                    }
                }
        
        thread = threading.Thread(target=summary_task, daemon=True)
        thread.start()

    @staticmethod
    def _summarize_error_hint(exc):
        """把大模型调用异常翻译成一句**可操作**的中文提示。

        原来失败时只显示裸的 ``Connection error.``——用户完全不知道
        该去看哪里。而连接类错误绝大多数是代理/网络不可达（2026-10-13
        的「一键总结失效」正是被一个已失效的本地代理劫持），所以这里
        直接点明排查方向，让错误自证。
        """
        text = str(exc)
        if any(k in text for k in (
            "Connection error", "ConnectError", "APIConnectionError",
            "All connection attempts failed", "timed out", "Timeout",
        )):
            return "网络/代理不可达，请检查代理是否运行"
        if "401" in text or "Unauthorized" in text or "AuthenticationError" in text:
            return "API Key 无效或过期"
        if "402" in text or "Insufficient" in text or "quota" in text.lower():
            return "余额或额度不足"
        return "发生错误"

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

    def _show_summary_notification(self, summary, html_file=None, events=None):
        """总结完成：弹通知 + 打开 HTML 页面（**仅在主线程调用**）

        生成 HTML 属文件 IO，已挪到后台线程（见 _on_timer 的 _finish_summary）；
        这里只做 UI：通知 + 用 Popen（非阻塞）拉起页面。
        注意 `open` 用 Popen 而非 `run`——`run` 会同步等 `open` 退出。
        """
        import rumps
        import subprocess

        summary_display = summary[:100] + "..." if len(summary) > 100 else summary

        rumps.notification(
            title="✨ 市场总结完成",
            subtitle="已复制到剪贴板并发送到钉钉",
            message=summary_display
        )

        if html_file:
            try:
                subprocess.Popen(['open', str(html_file)])
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

    # 注：原 _get_system_status() / _get_system_status_cached() 已删除。
    # 两者都是「GET /api/health」，且都只在主线程被调用；健康数据现在随
    # /api/tray/data 一并进 _menu_cache['status']，由后台预加载线程负责刷新。
    # 留着它们只会诱导后来人再次把 HTTP 塞回主线程。

    def _check_naja_ready(self) -> bool:
        """检查 Naja 主进程是否已启动（HTTP 版，**仅限后台线程**调用）

        _wait_for_naja_ready() 在后台线程用它轮询，需要"API 真的能应答"这一
        强语义（端口 listen ≠ 应用已就绪）。主线程**必须**改用
        _check_naja_listening()。
        """
        health_data = _http_get("/api/health", timeout=2.0)
        return health_data is not None

    def _check_naja_listening(self) -> bool:
        """检查 Naja 端口是否已监听（**主线程安全**：纯 TCP 探测，0.3s 封顶）

        _on_timer 跑在 AppKit 主线程，原来在这里调 _check_naja_ready()
        （HTTP、2s 超时）——启动期每 5 秒就可能把菜单冻住 2 秒。
        改为端口探测：连得上即认为服务已起来；"数据是否真的可用"由后台
        预加载线程（10s 一轮 /api/tray/data）兜底。
        """
        import socket
        try:
            with socket.create_connection(("127.0.0.1", _get_naja_port()), timeout=0.3):
                return True
        except OSError:
            return False

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

        # ── 性能铁律：_build_menu 跑在 AppKit 主线程 ───────────────────────
        # （rumps 定时器回调 / 菜单点击 / 重启后刷新）
        # 本方法内**只允许读内存缓存**，绝不允许发 HTTP、绝不允许抓取。
        # 历史上这里踩过三个坑，全部是"同步堵塞主线程最长 5~15s"：
        #   ① 缓存未就绪时回退本地实时抓取 → Playwright 同步阻塞最长 15s；
        #   ② _get_system_status() → GET /api/health（5s 超时）——而它的返回值
        #      在菜单里**从未被使用**，是纯粹浪费的阻塞（已删除该取数）；
        #   ③ _is_trading_time() → GET /api/trading/status（5s 超时、**无缓存**）
        #      ——已删除，改用纯 datetime 的 _is_trading_time_local()。
        # 且 ②③ 原本还在 _menu_cache_lock **内**执行 → 持锁做 IO，连带把
        # 后台预加载线程也堵死在锁上（锁只应保护 dict 读写这几条毫秒级语句）。
        with self._menu_cache_lock:
            if self._menu_cache:
                self._timeline_events = self._menu_cache.get('timeline', {})
                trading_time = self._menu_cache.get('trading', False)
            else:
                self._timeline_events = self._last_timeline_data or {"success": False, "stats": {}, "list": []}
                # 缓存未就绪：本地纯计算兜底（零 IO）。服务端口径（含节假日）
                # 会在预加载线程拿到 /api/tray/data 后由缓存接管。
                trading_time = _is_trading_time_local()

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
            
            # ① 状态行——原来 3 行（标题/状态/端口）合并为 1 行
            # 有长任务进行时改显任务进度：重启期间旧服务确实已停、新服务未必
            # 就绪，此时再写「运行中」就是谎报状态，用户点开菜单确认反被误导。
            op_line = self._op_line(port)
            if op_line:
                self._app.menu[op_line] = None
            else:
                running = bool(self._get_running_pid())
                trading_label = "交易中" if trading_time else "休市"
                self._app.menu[f"📊 Naja {'运行中' if running else '已停止'} · {trading_label} · 端口 {port}"] = None
            self._app.menu["sep0"] = rumps.separator
            
            # ② 常用页面——只留高频页；补「关注管理」；低频运维页移入「系统」子菜单
            common_pages = rumps.MenuItem("📈 常用页面")
            common_pages.add(rumps.MenuItem("🔥 市场热点", callback=self._on_open_page("/market")))
            common_pages.add(rumps.MenuItem("⚡ 交易中心", callback=self._on_open_page("/awakening")))
            common_pages.add(rumps.MenuItem("🧠 认知系统", callback=self._on_open_page("/cognition")))
            common_pages.add(rumps.MenuItem("🎯 关注管理", callback=self._on_open_page("/focusadmin")))
            self._app.menu.add(common_pages)
            
            # （原「管理工具」4 项已并入菜单底部的「系统」子菜单）
            
            self._app.menu["sep1"] = rumps.separator
            
            # （「登录时自动启动」已移入「系统」子菜单）
            
            self._app.menu["sep1.5"] = rumps.separator
            
            # ③ 快捷动作（「从服务器同步」已移入「系统」子菜单）
            self._app.menu.add(rumps.MenuItem("🌐 打开 Web", callback=self._on_open_web))
            self._app.menu.add(rumps.MenuItem("📄 打开日志", callback=self._on_open_logs))
            self._app.menu.add(rumps.MenuItem("🔄 刷新", callback=self._on_refresh))
            self._app.menu["sep2"] = rumps.separator
            
            # --- 新闻流（一级直接可见；**按时间倒序**，不做按类型分组）---
            try:
                import time
                if self._timeline_events and self._timeline_events.get("success", False):
                    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
                        TRAY_MENU_MAX_EVENTS,
                    )

                    stats = self._timeline_events.get('stats', {})
                    total_count = sum(int(stats.get(k, 0) or 0) for k in
                                      ('cn_events', 'us_events', 'high_score_news', 'jin10_news'))

                    items = self._timeline_events.get('list', [])
                    shown = min(len(items), TRAY_MENU_MAX_EVENTS)

                    # 「24h 总量」与「上屏条数」是两个数（配额只放行 12 条），
                    # 原来只报总量会让标题看起来像 500 条要溢出——如实分开写。
                    flow_head = rumps.MenuItem(f"📰 今日新闻流 · 24h {total_count} 条 · 显示 {shown}")
                    flow_head.set_callback(self._on_open_page("/market"))
                    self._app.menu.add(flow_head)

                    # 一键总结——保留在一级菜单、紧跟标题，点开就能用
                    self._app.menu.add(rumps.MenuItem("✨ 一键总结当前时间线", callback=self._on_one_click_summary))

                    # **纯时间倒序**（原先按「新闻优先」分组，结果时间线被切成
                    # 「新闻段 + 板块段」两截，看着不像时间线）。
                    # 「新闻不被板块异动挤掉」这件事由取数侧的配额保证——
                    # select_timeline_events(TRAY_TIMELINE_LIMITS) 已经让
                    # 板块异动最多只占 3/12 个名额，呈现层再分组就是重复设防。
                    ordered = sorted(
                        items,
                        key=lambda e: -float(e.get('timestamp', 0) or 0),
                    )

                    today = time.strftime('%m-%d')
                    for event in ordered[:TRAY_MENU_MAX_EVENTS]:
                        try:
                            event_date = event.get('date', '')
                            event_time = event.get('time', '')
                            event_type = event.get('type', '')
                            title = event.get('title', '')
                            url = event.get('url', '')
                            change = event.get('change', '')
                            # 24h 内跨天时用 MM-DD 代替 HH:MM——省掉原来的「日期分隔」两行
                            stamp = event_time if event_date == today else event_date

                            if event_type == 'cn_event':
                                menu_text = f"{stamp} 🇨🇳 {change} {title}"
                                callback = self._on_open_page("/market")
                            elif event_type == 'us_event':
                                menu_text = f"{stamp} 🇺🇸 {change} {title}"
                                callback = self._on_open_page("/market")
                            elif event_type == 'high_score_news':
                                menu_text = f"{stamp} 📰 {title}"
                                callback = self._on_open_page("/cognition")
                            elif event_type == 'jin10_news':
                                menu_text = f"{stamp} 📌 {title}"

                                def make_callback(news_url):
                                    def callback(sender):
                                        if news_url:
                                            import webbrowser
                                            webbrowser.open(news_url)
                                    return callback

                                callback = make_callback(url) if url else None
                            else:
                                menu_text = f"{stamp} {title}"
                                callback = None

                            self._app.menu.add(rumps.MenuItem(menu_text, callback=callback))
                        except Exception as e:
                            logger.error(f"添加新闻流条目失败: {e}")

                    more_item = rumps.MenuItem(f"⏰ 查看全部时间线（{total_count} 条）")
                    more_item.set_callback(self._on_open_page("/market"))
                    self._app.menu.add(more_item)
                else:
                    self._app.menu.add(rumps.MenuItem("⏰ 暂无时间线数据"))
            except Exception as e:
                logger.error(f"构建新闻流菜单失败: {e}")
                self._app.menu.add(rumps.MenuItem("⚠️ 新闻流加载失败"))

            self._app.menu["sep3"] = rumps.separator

            # --- 系统：低频运维页 + 自启 + 同步 + 重启 + 退出，统一收进一个子菜单 ---
            system_menu = rumps.MenuItem("⚙️ 系统")
            system_menu.add(rumps.MenuItem("📜 日志流", callback=self._on_open_page("/logstream")))
            system_menu.add(rumps.MenuItem("⚙️ 系统状态", callback=self._on_open_page("/health")))
            system_menu.add(rumps.MenuItem("📁 数据源管理", callback=self._on_open_page("/dsadmin")))
            system_menu.add(rumps.MenuItem("📅 任务管理", callback=self._on_open_page("/taskadmin")))
            system_menu.add(rumps.MenuItem("📋 策略管理", callback=self._on_open_page("/strategyadmin")))
            system_menu.add(rumps.MenuItem("📊 信号管理", callback=self._on_open_page("/signaladmin")))
            try:
                autostart_item = rumps.MenuItem("🚀 登录时自动启动")
                autostart_item.state = 1 if is_login_item_enabled() else 0
                autostart_item.set_callback(self._on_toggle_autostart)
                system_menu.add(autostart_item)
            except Exception as e:
                logger.warning(f"添加登录启动项菜单失败: {e}")
            try:
                # 「启动时打开浏览器」开关：勾选状态直接从偏好文件读，改动只影响
                # **下一次** Naja 启动（服务与托盘是独立进程，本次窗口不会自动关）。
                open_browser_item = rumps.MenuItem("🌐 启动时打开浏览器")
                open_browser_item.state = 1 if get_pref("open_browser_on_start", True) else 0
                open_browser_item.set_callback(self._on_toggle_open_browser)
                system_menu.add(open_browser_item)
            except Exception as e:
                logger.warning(f"添加「启动时打开浏览器」菜单失败: {e}")
            system_menu.add(rumps.MenuItem("☁️ 从服务器同步", callback=self._on_sync_from_server))
            system_menu.add(rumps.MenuItem("🔄 重启服务", callback=self._on_reload))
            system_menu.add(rumps.MenuItem("🚪 退出", callback=self._on_quit))
            self._app.menu.add(system_menu)
            
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
                self._app.menu["📊 Naja（菜单更新失败）"] = None
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

            # 先启动后台预加载线程（异步拉 /api/tray/data），再注册定时器。
            # rumps 定时器在注册瞬间会立刻回调一次 _on_timer，若此时预加载尚未开始，
            # 菜单构建会命中空缓存分支（历史上这一步会触发 15s 的同步抓取）。
            self._start_background_preloader()

            # 注意：rumps.timer(interval)(func) 返回的是 func 本身，若再写 (self._app)
            # 就会在这里**立刻同步执行一次** _on_timer —— 而此时菜单缓存尚未就绪，
            # 主线程上的重活（HTTP/抓取）会一直阻塞到 save_tray_pid() 与 app.run() 之后，
            # 结果就是菜单栏图标迟迟不出现。这里只注册，让定时器在 run() 时自行启动。
            rumps.timer(interval=5)(self._on_timer)

            save_tray_pid()

            logger.info("托盘已启动（简化菜单）")
            self._app.run()
        except Exception as e:
            logger.error(f"启动托盘失败: {e}")
            clear_tray_pid()

    def _on_timer(self, _sender):
        import time
        import threading
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
            # 结果已就绪 → 立刻释放「🧠 总结中…」状态位（收尾仍在后台继续跑）
            self._clear_op("summary")
            
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
                logger.info(f"总结完成: {summary[:100]}...")

                # 收尾动作看似"轻"，其实全是同步阻塞调用：写文件、pbcopy、
                # 钉钉（构造 Dtalk + io_loop）、`open` 拉起浏览器。它们原来
                # 直接跑在这儿 —— 也就是 AppKit 主线程。整体丢到后台线程，
                # 只有"弹通知 + 打开页面"这两件 UI 事回主线程做。
                def _finish_summary(summary=summary, events=events):
                    summary_file = None
                    html_file = None
                    try:
                        summary_file = self._save_summary_to_file(summary)
                        self._copy_to_clipboard(summary)
                        self._send_to_dingtalk(summary)
                        html_file = self._generate_html_summary(summary, events)
                    except Exception as e:
                        logger.error(f"总结收尾失败: {e}")
                    self._call_on_main_thread(
                        lambda: self._show_summary_notification(summary, html_file, events)
                    )

                threading.Thread(target=_finish_summary, daemon=True).start()
        
        if not self._naja_ready:
            # 主线程安全：端口探测（0.3s 封顶），不再用 HTTP（原 2s 超时/每 5s）。
            if self._check_naja_listening():
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
        self._last_menu_build_ts = 0
        self._build_menu()

    def _on_toggle_autostart(self, sender):
        """切换登录启动项状态（**不在主线程执行 launchctl**）

        toggle_login_item() 内部是 subprocess.run(["launchctl", ...], timeout=5)
        + plist 写盘；放在菜单回调（AppKit 主线程）里会把菜单冻住最多 5 秒。
        改为后台线程执行，只有"改勾选状态 + 弹通知"回主线程。
        """
        import threading

        new_state = 1 - sender.state
        action = "启用" if new_state == 1 else "禁用"

        if not self._begin_op("autostart", "🚀 设置自启…"):
            self._send_notification("⏳ 已有任务在进行", "请等待当前任务完成",
                                    "同一时刻只允许一个长任务")
            return

        def work():
            try:
                success = toggle_login_item()
            except Exception as e:
                logger.error(f"切换登录启动项失败: {e}")
                success = False

            if success:
                logger.info(f"登录启动项已{action}")
            else:
                logger.error(f"登录启动项{action}失败")

            def apply():
                import rumps
                sender.state = new_state if success else 1 - new_state
                if success:
                    rumps.notification(
                        title="🚀 登录启动项",
                        subtitle=f"已{action}登录时自动启动",
                        message="重启电脑后生效" if new_state == 1 else "已取消自动启动",
                    )
                else:
                    # 原来失败**完全静默**（只写 logger.error）→ 用户以为勾上了，
                    # 下次开机才发现没生效。失败必须自证。
                    rumps.notification(
                        title="⚠️ 登录启动项设置失败",
                        subtitle=f"未能{action}登录时自动启动",
                        message="请检查系统设置，或查看托盘日志",
                    )
                # 释放状态位（会重建菜单，勾选状态由 is_login_item_enabled() 重读，
                # 不依赖已失效的旧 sender）
                self._clear_op("autostart")

            self._call_on_main_thread(apply)

        threading.Thread(target=work, daemon=True).start()

    def _on_toggle_open_browser(self, sender):
        """切换「启动时自动打开浏览器」（**不在主线程做文件 IO**）

        与「登录时自动启动」同款模式：后台线程落盘，主线程只改勾选 + 弹通知。

        生效范围：**下一次** Naja 启动。服务进程与托盘是两个独立进程，
        勾选只写偏好文件（``~/.naja/prefs.json``），由服务启动时读取——
        所以当前已经打开的浏览器窗口不会因此关掉。
        """
        import threading

        new_state = 1 - sender.state
        enabled = new_state == 1

        if not self._begin_op("open_browser", "🌐 保存设置…"):
            self._send_notification("⏳ 已有任务在进行", "请等待当前任务完成",
                                    "同一时刻只允许一个长任务")
            return

        def work():
            try:
                success = set_pref("open_browser_on_start", enabled)
            except Exception as e:
                logger.error(f"保存「启动时打开浏览器」设置失败: {e}")
                success = False

            if success:
                logger.info(f"「启动时打开浏览器」已{'开启' if enabled else '关闭'}")
            else:
                logger.error("「启动时打开浏览器」设置写入失败")

            def apply():
                import rumps
                sender.state = new_state if success else 1 - new_state
                if success:
                    rumps.notification(
                        title="🌐 启动时打开浏览器",
                        subtitle="已开启" if enabled else "已关闭",
                        message="下次启动 Naja 时生效",
                    )
                else:
                    # 失败必须自证——否则用户以为勾上了，下次启动才发现没生效。
                    rumps.notification(
                        title="⚠️ 设置保存失败",
                        subtitle="未能写入偏好文件",
                        message="请检查 ~/.naja 目录权限，或查看托盘日志",
                    )
                # 释放状态位（会重建菜单，勾选状态由 get_pref 重读，
                # 不依赖已失效的旧 sender）
                self._clear_op("open_browser")

            self._call_on_main_thread(apply)

        threading.Thread(target=work, daemon=True).start()


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
