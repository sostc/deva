"""托盘主线程零阻塞 —— AppKit 主线程上不得出现同步 IO。

背景（2026-10-13）：「一键总结」的代理问题修完后，回头审计**菜单回调里还剩
多少会在主线程同步阻塞的代码**。rumps 的菜单回调与定时器都跑在 AppKit 主
runloop 上，任何 HTTP / 抓取 / 子进程等待都会冻住整条菜单栏。

审计出的真实阻塞点（本文件负责钉死）：

  ① ``_build_menu()`` 空缓存分支里的两个取数：
     - ``_get_system_status()`` → GET /api/health（5s 超时）——它的返回值在菜单里
       **从未被使用**，是纯粹浪费的阻塞；
     - ``_is_trading_time()`` → GET /api/trading/status（5s 超时，**且无缓存**）。
     更糟的是两者都在 ``_menu_cache_lock`` **内**执行 → 持锁做 IO，连带把后台
     预加载线程也堵在锁上。修复后：主线程只读内存缓存，缺失时用纯 datetime 的
     ``_is_trading_time_local()`` 兜底；两个 HTTP 版助手整体删除。
  ② ``_on_timer`` 里 ``_check_naja_ready()``（GET /api/health，2s 超时）——启动期
     每 5 秒一次。修复后改用主线程安全的端口探测 ``_check_naja_listening()``。
  ③ ``_on_toggle_autostart`` 直接在菜单回调里跑 ``launchctl``
     （``subprocess.run(..., timeout=5)``，另加 plist 写盘）。
  ④ 总结收尾（写文件 / pbcopy / 钉钉 / ``open``）全部裸在主线程。

有意保留的唯一主线程阻塞是 ``_on_quit`` 的 SIGTERM 等待（退出时无菜单可卡，
且迁到后台线程会失去"超时升级 SIGKILL"的能力）。
"""

import time

import pytest


# ── 工具：无 GUI 环境下也能跑 _build_menu 的假 App/Menu ────────────────────


class _FakeMenu(dict):
    """只实现 _build_menu 用到的那几个 dict 方法。"""

    def add(self, item):
        self[getattr(item, "title", str(item))] = item

    def clear(self):
        dict.clear(self)


class _FakeApp:
    def __init__(self):
        self.menu = _FakeMenu()
        self.icon = None


def _tray_src() -> str:
    from pathlib import Path

    from deva.naja.infra.ui import menu_bar_tray as m

    return Path(m.__file__).read_text(encoding="utf-8")


def _block(source: str, start_marker: str, end_marker: str) -> str:
    i = source.find(start_marker)
    if i < 0:
        return ""
    j = source.find(end_marker, i)
    if j < 0:
        return ""
    return source[i:j]


def _strip_comment_lines(code: str) -> str:
    """去掉整行注释后再扫描。

    否则守卫会被"解释这个坑"的注释本身触发（本文件就踩过：注释里写了
    ``_get_system_status()`` 用于说明已删除的取数，结果把自己判违约）。
    只去整行注释，不做 inline 剥离——避免误伤字符串字面量。
    """
    return "\n".join(
        line for line in code.splitlines() if not line.lstrip().startswith("#")
    )


def _tray_with_fake_app():
    pytest.importorskip("rumps")
    from deva.naja.infra.ui import menu_bar_tray as m

    tray = m.MenuBarTray()
    tray._app = _FakeApp()
    tray._menu_cache = {}
    tray._last_timeline_data = None
    return m, tray


# ── ① 构建菜单：主线程绝不发 HTTP ────────────────────────────────────────


def test_build_menu_empty_cache_makes_no_http(monkeypatch):
    """缓存未就绪（服务未起/预加载失败）时构建菜单，**一次 HTTP 都不许发**。

    这正是真实卡顿场景：Naja 端口已 listen 但还没开始应答，缓存迟迟不填，
    于是每 30s 一次的定时刷新都在主线程各阻塞 5s+5s。
    """
    m, tray = _tray_with_fake_app()
    calls = []

    def spy(path, port=None, timeout=5.0):
        calls.append((path, timeout))
        return None

    monkeypatch.setattr(m, "_http_get", spy)
    tray._build_menu()

    assert calls == [], f"主线程构建菜单时发起了 HTTP: {calls}"
    assert len(tray._app.menu) > 0, "菜单应当照常构建（降级而非失败）"


def test_build_menu_with_cache_makes_no_http(monkeypatch):
    """缓存就绪时同样零 HTTP（只读内存）。"""
    m, tray = _tray_with_fake_app()
    tray._menu_cache = {
        "timeline": {"success": True, "stats": {}, "list": []},
        "status": {"status": "ok"},
        "trading": True,
    }
    calls = []
    monkeypatch.setattr(m, "_http_get",
                        lambda *a, **k: calls.append(a) or None)
    tray._build_menu()

    assert calls == []


def test_build_menu_block_has_no_blocking_fetch():
    """静态守卫：``_build_menu`` 方法块内不得出现任何取数调用。

    守卫必须**按方法块切**——整文件 grep 会命中 ``_on_open_page`` 等回调
    （它们合法地做别的事），也会命中 ``_build_simple_menu``（另一个方法）。
    """
    src = _tray_src()
    blk = _strip_comment_lines(
        _block(src, "def _build_menu(self):", "def _on_open_page(self, path):"))
    assert blk, "未定位到 _build_menu 方法块"

    for banned in ("_http_get(", "_get_system_status", "_is_trading_time(",
                   "requests.", "urlopen", "_get_timeline_events("):
        assert banned not in blk, f"_build_menu（主线程）出现阻塞取数: {banned}"


def test_http_versions_of_status_helpers_are_removed():
    """两个 HTTP 版助手整体删除，避免后来人再把 HTTP 塞回主线程。"""
    pytest.importorskip("rumps")
    from deva.naja.infra.ui import menu_bar_tray as m

    assert not hasattr(m.MenuBarTray, "_get_system_status")
    assert not hasattr(m.MenuBarTray, "_get_system_status_cached")
    assert not hasattr(m, "_is_trading_time"), "无缓存的 HTTP 版交易时段判断应已删除"


# ── ② 就绪探测：端口探测，主线程安全 ────────────────────────────────────


def test_check_naja_listening_true_for_live_port(monkeypatch):
    import socket
    import threading

    m, tray = _tray_with_fake_app()

    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def _accept():
        try:
            srv.accept()
        except OSError:
            pass  # 测试结束关掉 socket 时 accept 会被打断，属预期

    threading.Thread(target=_accept, daemon=True).start()
    monkeypatch.setattr(m, "_get_naja_port", lambda: port)
    try:
        assert tray._check_naja_listening() is True
    finally:
        srv.close()


def test_check_naja_listening_false_and_fast_for_dead_port(monkeypatch):
    """死端口必须**快速**返回 False（不能退化成超时等待）。"""
    m, tray = _tray_with_fake_app()
    monkeypatch.setattr(m, "_get_naja_port", lambda: 1)  # 保留端口，无人监听

    t0 = time.time()
    assert tray._check_naja_listening() is False
    assert time.time() - t0 < 0.5, "端口探测不应阻塞"


def test_on_timer_uses_port_probe_not_http():
    """静态守卫：_on_timer 的就绪检测走端口探测，且不出现任何 HTTP。"""
    src = _tray_src()
    blk = _strip_comment_lines(
        _block(src, "def _on_timer(self, _sender):", "def stop(self):"))
    assert blk, "未定位到 _on_timer 方法块"

    assert "_check_naja_listening()" in blk
    assert "_check_naja_ready()" not in blk, "主线程不得再用 HTTP 版就绪检测"
    assert "_http_get(" not in blk


# ── ③ 总结收尾：重活移出主线程 ──────────────────────────────────────────


def test_summary_finish_runs_in_background():
    """静态守卫：写文件 / pbcopy / 钉钉 / 生成 HTML 必须在后台线程。"""
    src = _tray_src()
    blk = _strip_comment_lines(
        _block(src, "def _on_timer(self, _sender):", "def stop(self):"))
    assert blk

    assert "def _finish_summary(" in blk
    assert "threading.Thread(target=_finish_summary" in blk
    # 收尾三件事必须在 _finish_summary 内被调用
    for action in ("_save_summary_to_file", "_copy_to_clipboard",
                   "_send_to_dingtalk", "_generate_html_summary"):
        assert action in blk
    # 只有 UI 事回主线程
    assert "_call_on_main_thread(" in blk
    assert "_show_summary_notification" in blk


def test_show_summary_notification_is_ui_only():
    """_show_summary_notification 只做 UI：通知 + 非阻塞拉起页面。"""
    src = _tray_src()
    blk = _strip_comment_lines(
        _block(src, "def _show_summary_notification(",
               "def _generate_html_summary("))
    assert blk
    assert "_generate_html_summary(" not in blk, "HTML 生成属 IO，应留在后台线程"
    assert "subprocess.Popen(" in blk, "打开页面应用 Popen（非阻塞）"
    assert "subprocess.run(" not in blk


# ── ④ 自启开关：launchctl 移出主线程 ────────────────────────────────────


def test_toggle_autostart_runs_in_background():
    src = _tray_src()
    blk = _block(src, "def _on_toggle_autostart(self, sender):", "\n_tray_instance")
    blk = _strip_comment_lines(blk)
    assert blk, "未定位到 _on_toggle_autostart 方法块"

    assert "toggle_login_item()" in blk
    assert "threading.Thread(target=work" in blk, "launchctl 必须在后台线程执行"
    assert "_call_on_main_thread(apply)" in blk, "勾选状态必须回主线程改"


def test_quit_block_is_the_only_documented_main_thread_wait():
    """_on_quit 的 SIGTERM 等待是有意保留的（退出时无菜单可卡），但必须写明。"""
    src = _tray_src()
    blk = _block(src, "def _on_quit(self, sender):", "def _on_refresh(self, sender):")
    assert blk
    assert "唯一有意保留的主线程阻塞" in blk, "有意保留的阻塞必须留下说明"


# ── ⑤ 冷启动：模块可独立导入 ────────────────────────────────────────────


def test_module_imports_standalone():
    pytest.importorskip("rumps")
    from deva.naja.infra.ui import menu_bar_tray

    assert hasattr(menu_bar_tray, "MenuBarTray")
    assert hasattr(menu_bar_tray.MenuBarTray, "_check_naja_listening")
