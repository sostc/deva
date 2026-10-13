"""托盘长任务的状态反馈 —— 让"点了没反应"不再发生。

背景（2026-10-13，用户反馈）：点「系统 → 重启服务」后菜单立刻关闭，而重启
最长要 45s（等旧进程退出 ≤15s + 等新服务就绪 ≤30s），期间菜单栏图标、菜单
内容、通知**全无变化**；成功时更是完全静默——代码里只有 ``_notify_restart_failed``
一条通知路径，成功分支只写日志。

本文件钉死两件事：

  ① 状态位机制本身（``_begin_op`` / ``_update_op`` / ``_clear_op`` /
     ``_flash_status``）的正确性：占用、互斥、释放、不误清别人的状态。
  ② 各长任务确实接入了状态位，且**保证释放**（失败/异常路径也不例外——
     状态位卡住会让后续所有长任务被互斥拒绝，比不显示状态更糟）。
"""

import time

import pytest


# ── 工具 ─────────────────────────────────────────────────────────────────


class _FakeMenu(dict):
    def add(self, item):
        self[getattr(item, "title", str(item))] = item

    def clear(self):
        dict.clear(self)


class _FakeApp:
    def __init__(self):
        self.menu = _FakeMenu()
        self.icon = None
        self.title = None


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
    """去掉整行注释——注释里提到被检查的符号不该算违约。"""
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
    tray._naja_ready = True          # 走完整菜单，避免命中简化菜单
    # 测试进程里没有 AppKit runloop，callAfter 可能永不执行 → 同步化。
    tray._call_on_main_thread = lambda fn: fn()
    return m, tray


# ── ① 状态位机制 ─────────────────────────────────────────────────────────


def test_initial_status_is_none():
    m, tray = _tray_with_fake_app()
    assert tray._op_status is None
    assert tray._op_line(8080) == ""


def test_begin_op_marks_busy_and_sets_title():
    m, tray = _tray_with_fake_app()
    assert tray._begin_op("restart", "🔄 重启中…") is True

    assert tray._op_status["key"] == "restart"
    assert tray._op_status["busy"] is True
    assert tray._app.title == "🔄 重启中…", "状态必须写到菜单栏文字上（唯一始终可见的通道）"
    assert tray._op_line(8080) == "🔄 重启中… · 端口 8080"


def test_begin_op_is_mutually_exclusive():
    """长任务互斥：重启期间再点重启会起第二个线程同时 kill/Popen → 状态错乱。"""
    m, tray = _tray_with_fake_app()
    assert tray._begin_op("restart", "🔄 重启中…") is True
    assert tray._begin_op("sync", "☁️ 同步中…") is False, "第二个长任务必须被拒绝"
    # 被拒绝时**不得**覆盖正在进行的那个
    assert tray._op_status["key"] == "restart"
    assert tray._app.title == "🔄 重启中…"


def test_update_op_changes_label():
    m, tray = _tray_with_fake_app()
    tray._begin_op("restart", "🔄 正在重启…")
    tray._update_op("🔄 停止旧服务…")
    assert tray._app.title == "🔄 停止旧服务…"
    assert tray._op_line(8080) == "🔄 停止旧服务… · 端口 8080"


def test_clear_op_restores_normal_title():
    m, tray = _tray_with_fake_app()
    tray._begin_op("restart", "🔄 重启中…")
    tray._clear_op("restart")
    assert tray._op_status is None
    assert tray._app.title is None, "释放后菜单栏应恢复为只有图标"
    assert tray._op_line(8080) == ""


def test_clear_op_ignores_foreign_key():
    """别人（不同 key）的任务不能把自己的状态位清掉。"""
    m, tray = _tray_with_fake_app()
    tray._begin_op("restart", "🔄 重启中…")
    tray._clear_op("sync")
    assert tray._op_status is not None and tray._op_status["key"] == "restart"


def test_flash_does_not_preempt_busy_task():
    """flash（如「已刷新」）不得把「重启中…」冲掉——否则用户又失去进度。"""
    m, tray = _tray_with_fake_app()
    tray._begin_op("restart", "🔄 重启中…")
    tray._flash_status("✅ 已刷新 12:00:00", 0.05)
    assert tray._op_status["key"] == "restart"
    assert tray._app.title == "🔄 重启中…"


def test_flash_expires_automatically():
    m, tray = _tray_with_fake_app()
    tray._flash_status("✅ 已刷新 12:00:00", 0.1)
    assert tray._app.title == "✅ 已刷新 12:00:00"
    time.sleep(0.35)
    assert tray._op_status is None, "flash 到点必须自动清除"
    assert tray._app.title is None


# ── ② 各长任务接入 + 保证释放（静态） ────────────────────────────────────


def test_restart_has_four_states():
    src = _tray_src()
    begin = _strip_comment_lines(_block(src, "def _restart_tray(self):",
                                        "def _do_restart_tray(self):"))
    body = _strip_comment_lines(_block(src, "def _do_restart(self):",
                                       "def _refresh_after_restart(self):"))
    assert begin and body
    assert '_begin_op("restart"' in begin, "重启必须先占用状态位（互斥）"
    for label in ("🔄 正在重启…", "🔄 停止旧服务…", "🔄 启动新服务…", "🔄 等待服务就绪…"):
        assert label in begin + body, f"缺少重启阶段文案: {label}"


def test_restart_clears_status_even_on_failure():
    """状态位必须在 try/finally 里释放——异常时卡住会拒掉后续所有长任务。"""
    src = _tray_src()
    blk = _strip_comment_lines(_block(src, "def _do_restart_tray(self):",
                                      "def _do_restart(self):"))
    assert blk
    assert "try:" in blk and "finally:" in blk
    assert '_clear_op("restart")' in blk


def test_restart_success_has_notification():
    """成功分支原来一句提示都没有（只有失败才通知）→ 用户不知道好没好。"""
    src = _tray_src()
    blk = _block(src, "def _do_restart(self):", "def _refresh_after_restart(self):")
    assert "✅ 重启完成" in blk
    assert "_notify_restart_failed" in blk, "失败通知必须保留"


def test_sync_uses_status_and_clears():
    src = _tray_src()
    blk = _strip_comment_lines(_block(src, "def _on_sync_from_server(self, sender):",
                                      "def _on_one_click_summary(self, sender):"))
    assert blk
    assert '_begin_op("sync"' in blk
    assert "finally:" in blk, "同步也必须保证释放状态位"
    assert '_clear_op("sync")' in blk


def test_summary_uses_status_and_clears():
    src = _tray_src()
    begin = _strip_comment_lines(
        _block(src, "def _on_one_click_summary(self, sender):",
               "    @staticmethod\n    def _summarize_error_hint"))
    timer = _strip_comment_lines(_block(src, "def _on_timer(self, _sender):",
                                        "def stop(self):"))
    assert begin and timer
    assert '_begin_op("summary"' in begin, "大模型调用可能十几秒，必须进状态位"
    assert '_clear_op("summary")' in timer, "结果就绪时必须释放状态位"


def test_autostart_reports_failure():
    """原来失败**完全静默**（只写 logger.error）→ 用户以为勾上了。"""
    src = _tray_src()
    blk = _strip_comment_lines(_block(src, "def _on_toggle_autostart(self, sender):",
                                      "\n_tray_instance"))
    assert blk
    assert '_begin_op("autostart"' in blk
    assert '_clear_op("autostart")' in blk
    assert "登录启动项设置失败" in blk, "失败必须有可见提示"


def test_refresh_gives_visible_feedback():
    src = _tray_src()
    blk = _strip_comment_lines(_block(src, "def _on_refresh(self, sender):",
                                      "def _on_sync_from_server(self, sender):"))
    assert blk
    assert "_flash_status(" in blk, "刷新必须给可见反馈（原来纯静默）"
    assert "🔄 刷新中…" in blk


# ── ③ 状态行不得谎报「运行中」 ───────────────────────────────────────────


def test_status_line_does_not_claim_running_during_op():
    """重启期间托盘自身不重启（为了图标不空窗），菜单不会重建 → 若不改状态行，
    「Naja 运行中」会一直挂着，而此刻旧服务其实已停。"""
    src = _tray_src()
    menu = _strip_comment_lines(_block(src, "def _build_menu(self):",
                                       "def _on_open_page(self, path):"))
    assert menu
    assert "self._op_line(port)" in menu
    assert "if op_line:" in menu, "有操作进行时必须走 op 分支，而不是写「运行中」"

    # 行为断言（比扫文本可靠）：有操作时状态行给的是任务文案，且不含「运行中」
    m, tray = _tray_with_fake_app()
    assert tray._op_line(8080) == "", "无操作时返回空串，交给常态逻辑"
    tray._begin_op("restart", "🔄 停止旧服务…")
    line = tray._op_line(8080)
    assert "运行中" not in line
    assert "停止旧服务" in line and "8080" in line


# ── ④ 退出：先渲染状态再阻塞 ─────────────────────────────────────────────


def test_quit_renders_status_before_blocking():
    """退出会阻塞主线程最多 10s（SIGTERM 等待），而阻塞期间 AppKit 不重绘 ——
    所以必须先把状态画出去，再用短延时定时器进入阻塞。"""
    src = _tray_src()
    blk = _strip_comment_lines(_block(src, "def _on_quit(self, sender):",
                                      "    def _call_on_main_thread_quit"))
    assert blk
    assert "🚪 正在退出…" in blk
    assert "_apply_op_status()" in blk, "先渲染"
    assert "threading.Timer(" in blk, "再延迟进入阻塞，让 runloop 有机会重绘"


def test_quit_block_is_still_documented():
    """有意保留的主线程阻塞说明不能被删掉。"""
    src = _tray_src()
    blk = _block(src, "def _on_quit(self, sender):", "def _on_refresh(self, sender):")
    assert "唯一有意保留的主线程阻塞" in blk


# ── ⑤ 冷启动 ─────────────────────────────────────────────────────────────


def test_module_imports_standalone():
    pytest.importorskip("rumps")
    from deva.naja.infra.ui import menu_bar_tray

    for name in ("_begin_op", "_update_op", "_clear_op", "_flash_status", "_op_line"):
        assert hasattr(menu_bar_tray.MenuBarTray, name), name
