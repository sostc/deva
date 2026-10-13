#!/usr/bin/env python3
"""验证「托盘长任务的状态反馈」—— 点了之后用户看得见。

================================================================================
它解决什么问题
================================================================================
用户反馈：「点击菜单里系统重启时，整个动画和显示不明显，状态无感知」。

追查后确认不是"动画不明显"，而是**四态全缺**：
``_on_reload → _restart_tray → _do_restart_tray`` 的实际耗时结构是

    等旧服务退出 ≤15s（_wait_for_pid_exit）
  + 起新进程（Popen -s start）
  + 等新服务就绪 ≤30s（_wait_for_naja_ready，每 0.5s 轮询）
  → 典型 8~15s，最坏 45s

而这十几秒里：菜单栏图标不变、菜单内容不变、**通知也没有**——代码里只有
``_notify_restart_failed`` 一条通知路径，**成功分支只写日志**。用户点完只能猜。

承载状态用的是菜单栏文字 ``app.title``（rumps ``setStatusBarTitle`` →
``setTitle_``，与 ``setImage_`` 互不冲突）：它是唯一「始终可见、不受系统勿扰
模式影响、且与图标可共存」的通道。原来全代码里 ``_app.title`` 一次都没被赋值。

================================================================================
六段检查
================================================================================
  ① **状态位机制**（功能）：占用 / 互斥 / 更新 / 释放 / 不误清别人的 / flash 不抢占 / flash 到期自动清
  ② **重启四态 + 保证释放**：四个阶段文案；``try/finally`` 释放（异常卡住会拒掉后续所有长任务）
  ③ **其他长任务接入**：同步 / 一键总结 / 登录自启 / 刷新
  ④ **状态行不谎报**：有操作进行时不再写「运行中」（此刻旧服务其实已停）
  ⑤ **退出先渲染再阻塞**：阻塞前先把状态画出去（阻塞期间 AppKit 不重绘）
  ⑥ **冷启动**：``menu_bar_tray`` 可独立导入

================================================================================
用法
================================================================================

    cd <项目根>
    /Users/spark/.local/bin/python3 scripts/verify/verify_tray_status.py
    /Users/spark/.local/bin/python3 scripts/verify/verify_tray_status.py --strict

退出码：0 = PASS；--strict 下有违约则 1。

**只读约定**：只读源码与内存态，不写落盘表、不起服务、不改菜单。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

_CHILD_ENV = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

_TRAY_SRC = PROJECT_ROOT / "deva/naja/infra/ui/menu_bar_tray.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _block(source: str, start_marker: str, end_marker: str) -> str:
    i = source.find(start_marker)
    if i < 0:
        return ""
    j = source.find(end_marker, i)
    if j < 0:
        return ""
    return source[i:j]


def _strip_comment_lines(code: str) -> str:
    """去掉整行注释——注释里提到被检查的符号不该算违约（本项目踩过）。"""
    return "\n".join(
        line for line in code.splitlines() if not line.lstrip().startswith("#")
    )


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


def main() -> int:
    parser = argparse.ArgumentParser(description="验证托盘长任务的状态反馈")
    parser.add_argument("--strict", action="store_true", help="有违约则退出码 1")
    args = parser.parse_args()

    violations: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        if ok:
            print(f"  ✅ {name}" + (f"  [{detail}]" if detail else ""))
        else:
            violations.append(name)
            print(f"  ❌ {name}" + (f"  [{detail}]" if detail else ""))

    tray_src = _read(_TRAY_SRC)

    # ── ① 状态位机制 ──────────────────────────────────────────────────
    print("=" * 68)
    print("① 状态位机制：占用 / 互斥 / 更新 / 释放 / flash")
    print("=" * 68)
    try:
        from deva.naja.infra.ui import menu_bar_tray as m

        tray = m.MenuBarTray()
        tray._app = _FakeApp()
        tray._menu_cache = {}
        tray._last_timeline_data = None
        tray._naja_ready = True
        tray._call_on_main_thread = lambda fn: fn()   # 测试进程无 runloop

        check("初始无状态位", tray._op_status is None and tray._op_line(8080) == "")

        ok = tray._begin_op("restart", "🔄 重启中…")
        check("占用成功且置 busy", ok is True and tray._op_status.get("busy") is True)
        check("状态写入菜单栏文字 app.title",
              tray._app.title == "🔄 重启中…", repr(tray._app.title))
        check("菜单状态行改为任务进度（含端口）",
              tray._op_line(8080) == "🔄 重启中… · 端口 8080", repr(tray._op_line(8080)))

        check("长任务互斥（第二个被拒绝）", tray._begin_op("sync", "☁️ 同步中…") is False)
        check("被拒绝时不覆盖进行中的任务",
              tray._op_status.get("key") == "restart"
              and tray._app.title == "🔄 重启中…")

        tray._update_op("🔄 停止旧服务…")
        check("阶段文案可更新", tray._app.title == "🔄 停止旧服务…", repr(tray._app.title))

        tray._clear_op("sync")
        check("其他 key 不能清掉自己的状态位",
              tray._op_status is not None and tray._op_status.get("key") == "restart")

        tray._flash_status("✅ 已刷新 12:00:00", 0.05)
        check("flash 不抢占进行中的长任务",
              tray._op_status.get("key") == "restart" and tray._app.title == "🔄 停止旧服务…")

        tray._clear_op("restart")
        check("释放后菜单栏恢复为只有图标",
              tray._op_status is None and tray._app.title is None
              and tray._op_line(8080) == "")

        tray._flash_status("✅ 已刷新 12:00:00", 0.1)
        check("无长任务时 flash 生效", tray._app.title == "✅ 已刷新 12:00:00")
        time.sleep(0.4)
        check("flash 到点自动清除",
              tray._op_status is None and tray._app.title is None)
    except Exception as e:  # pragma: no cover - 环境异常
        check("状态位机制", False, f"{type(e).__name__}: {e}")

    # ── ② 重启四态 + 保证释放 ────────────────────────────────────────
    print()
    print("=" * 68)
    print("② 重启服务：四态文案 + try/finally 保证释放")
    print("=" * 68)
    begin_blk = _strip_comment_lines(
        _block(tray_src, "def _restart_tray(self):", "def _do_restart_tray(self):"))
    guard_blk = _strip_comment_lines(
        _block(tray_src, "def _do_restart_tray(self):", "def _do_restart(self):"))
    body_blk = _strip_comment_lines(
        _block(tray_src, "def _do_restart(self):", "def _refresh_after_restart(self):"))

    check("定位到 _restart_tray / _do_restart_tray / _do_restart 三个块",
          all((begin_blk, guard_blk, body_blk)),
          f"{len(begin_blk)}/{len(guard_blk)}/{len(body_blk)} 字符")
    check("重启前先占用状态位（互斥）", '_begin_op("restart"' in begin_blk, "")
    check("互斥被拒时给用户可见提示", "_send_notification(" in begin_blk, "")

    for label in ("🔄 正在重启…", "🔄 停止旧服务…", "🔄 启动新服务…", "🔄 等待服务就绪…"):
        check(f"阶段文案存在: {label}", label in (begin_blk + body_blk), "")

    check("释放置于 try/finally（异常也不会卡住）",
          "try:" in guard_blk and "finally:" in guard_blk, "")
    check("finally 中释放 restart 状态位",
          '_clear_op("restart")' in guard_blk, "")

    check("成功分支有完成通知（原先静默）", "✅ 重启完成" in body_blk, "")
    check("失败通知仍然保留", "_notify_restart_failed" in body_blk, "")

    # ── ③ 其他长任务接入 ──────────────────────────────────────────────
    print()
    print("=" * 68)
    print("③ 其他长任务接入状态位")
    print("=" * 68)
    sync_blk = _strip_comment_lines(
        _block(tray_src, "def _on_sync_from_server(self, sender):",
               "def _on_one_click_summary(self, sender):"))
    sum_blk = _strip_comment_lines(
        _block(tray_src, "def _on_one_click_summary(self, sender):",
               "    @staticmethod\n    def _summarize_error_hint"))
    timer_blk = _strip_comment_lines(
        _block(tray_src, "def _on_timer(self, _sender):", "def stop(self):"))
    auto_blk = _strip_comment_lines(
        _block(tray_src, "def _on_toggle_autostart(self, sender):", "\n_tray_instance"))
    refresh_blk = _strip_comment_lines(
        _block(tray_src, "def _on_refresh(self, sender):",
               "def _on_sync_from_server(self, sender):"))

    check("服务器同步：占用状态位 + finally 释放",
          '_begin_op("sync"' in sync_blk and "finally:" in sync_blk
          and '_clear_op("sync")' in sync_blk, "")
    check("一键总结：占用状态位（大模型调用可能十几秒）",
          '_begin_op("summary"' in sum_blk, "")
    check("一键总结：结果就绪时释放", '_clear_op("summary")' in timer_blk, "")
    check("登录自启：占用状态位 + 释放",
          '_begin_op("autostart"' in auto_blk and '_clear_op("autostart")' in auto_blk, "")
    check("登录自启：失败有可见提示（原先完全静默）",
          "登录启动项设置失败" in auto_blk, "")
    check("刷新菜单：有可见反馈（原先纯静默）",
          "_flash_status(" in refresh_blk and "🔄 刷新中…" in refresh_blk, "")

    # ── ④ 状态行不谎报 ────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("④ 状态行不得谎报「运行中」（重启期间旧服务其实已停）")
    print("=" * 68)
    menu_blk = _strip_comment_lines(
        _block(tray_src, "def _build_menu(self):", "def _on_open_page(self, path):"))
    check("_build_menu 使用 _op_line(port)", "self._op_line(port)" in menu_blk, "")
    check("有操作时走 op 分支（而非直接写运行中）",
          "if op_line:" in menu_blk, "")

    try:
        from deva.naja.infra.ui import menu_bar_tray as m

        tray = m.MenuBarTray()
        tray._app = _FakeApp()
        tray._call_on_main_thread = lambda fn: fn()
        tray._naja_ready = True
        tray._menu_cache = {
            "timeline": {"success": True, "stats": {}, "list": []},
            "status": {"status": "ok"},
            "trading": False,
        }
        tray._begin_op("restart", "🔄 停止旧服务…")
        tray._build_menu()
        keys = [repr(k) for k in tray._app.menu.keys()]
        hit = [k for k in keys if "停止旧服务" in k]
        bad = [k for k in keys if "运行中" in k]
        check("重启期间菜单状态行显示任务进度", bool(hit), f"{hit}")
        check("重启期间菜单里不出现「运行中」", not bad, f"{bad}")
    except Exception as e:  # pragma: no cover
        check("状态行行为", False, f"{type(e).__name__}: {e}")

    # ── ⑤ 退出：先渲染再阻塞 ──────────────────────────────────────────
    print()
    print("=" * 68)
    print("⑤ 退出：先渲染状态，再进入阻塞等待")
    print("=" * 68)
    quit_blk = _strip_comment_lines(
        _block(tray_src, "def _on_quit(self, sender):",
               "    def _call_on_main_thread_quit"))
    check("定位到 _on_quit 方法块", bool(quit_blk), f"{len(quit_blk)} 字符")
    check("有退出中文案", "🚪 正在退出…" in quit_blk, "")
    check("阻塞前先渲染状态（_apply_op_status）", "_apply_op_status()" in quit_blk, "")
    check("用短延时定时器进入阻塞（让 runloop 有机会重绘）",
          "threading.Timer(" in quit_blk, "")
    check("有意保留的阻塞说明仍在",
          "唯一有意保留的主线程阻塞" in tray_src, "")

    # ── ⑥ 冷启动 ──────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("⑥ 冷启动：托盘模块可独立导入")
    print("=" * 68)
    import subprocess

    cold = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r);"
         "from deva.naja.infra.ui import menu_bar_tray as m;"
         "assert all(hasattr(m.MenuBarTray, n) for n in "
         "('_begin_op','_update_op','_clear_op','_flash_status','_op_line'));"
         "print('ok')" % str(PROJECT_ROOT)],
        capture_output=True, text=True, env=_CHILD_ENV, timeout=300,
    )
    out = (cold.stdout or cold.stderr or "").strip().splitlines()
    check("子进程冷启动导入成功",
          cold.returncode == 0 and "ok" in (cold.stdout or ""),
          out[-1] if out else "")

    # ── 汇总 ──────────────────────────────────────────────────────────
    print()
    print("=" * 68)
    if violations:
        print(f"❌ 违约 {len(violations)} 项: {violations}")
        return 1 if args.strict else 0
    print("✅ 全部通过：长任务状态可见、互斥可靠、状态行不谎报")
    return 0


if __name__ == "__main__":
    sys.exit(main())
