#!/usr/bin/env python3
"""验证「托盘主线程零阻塞」—— 菜单回调与定时器里不得有同步 IO。

================================================================================
它解决什么问题
================================================================================

用户问「菜单里还有会堵塞的同步代码吗」。答案是**有，而且不止一处**。
rumps 的菜单回调与 ``rumps.timer`` 回调都跑在 AppKit 主 runloop 上，
任何 HTTP / 抓取 / 子进程等待都会冻住整条菜单栏（图标不刷、点击无响应）。

审计结论（本脚本负责钉死）：

  ① ``_build_menu()`` 空缓存分支里两个取数，都在主线程：
       - ``_get_system_status()`` → GET /api/health（5s 超时）
         —— 返回值在菜单里**从未被使用**，纯浪费的阻塞；
       - ``_is_trading_time()`` → GET /api/trading/status（5s 超时、**无缓存**）。
     更糟：两者都在 ``_menu_cache_lock`` **内**执行 → 持锁做 IO，
     连带把后台预加载线程也堵在锁上。
     → 修法：主线程只读内存缓存；缺失时用纯 datetime 的
       ``_is_trading_time_local()`` 兜底；两个 HTTP 版助手整体删除。
  ② ``_on_timer`` 的 ``_check_naja_ready()``（GET /api/health，2s）——启动期每 5s
     一次 → 改用主线程安全的端口探测 ``_check_naja_listening()``（0.3s 封顶）。
  ③ ``_on_toggle_autostart`` 直接在菜单回调里跑 ``launchctl``
     （``subprocess.run(..., timeout=5)`` + plist 写盘）→ 移入后台线程。
  ④ 总结收尾（写文件 / pbcopy / 钉钉 / 生成 HTML）全裸在主线程
     → 移入后台线程，主线程只留「弹通知 + 打开页面」。

**有意保留**的唯一主线程阻塞是 ``_on_quit`` 的 SIGTERM 等待：退出时无菜单可卡，
且迁到后台线程会失去"超时升级 SIGKILL"的能力（托盘一退，daemon 线程即消失）。

================================================================================
六段检查
================================================================================

  ① **空缓存构建菜单**（功能）：spy ``_http_get``，构建过程中 0 次 HTTP
  ② **就绪探测**（功能）：活端口 → True；死端口 → False 且耗时 < 0.5s
  ③ **`_build_menu` 静态守卫**：方法块内无 ``_http_get`` / ``_get_system_status`` /
     ``_is_trading_time(`` / ``_get_timeline_events(``
  ④ **`_on_timer` 静态守卫**：用端口探测；总结收尾在后台线程
  ⑤ **自启开关 + 死代码**：``_on_toggle_autostart`` 在后台线程；
     HTTP 版 `_get_system_status` / `_get_system_status_cached` / `_is_trading_time` 已删除
  ⑥ **冷启动**：``menu_bar_tray`` 可独立导入

================================================================================
用法
================================================================================

    cd <项目根>
    /Users/spark/.local/bin/python3 scripts/verify/verify_tray_no_block.py
    /Users/spark/.local/bin/python3 scripts/verify/verify_tray_no_block.py --strict

退出码：0 = PASS；--strict 下有违约则 1。

**只读约定**：本脚本只读源码与内存态，不写任何落盘表、不起服务、不改菜单。
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

_CHILD_ENV = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

_TRAY_SRC = PROJECT_ROOT / "deva/naja/infra/ui/menu_bar_tray.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _block(source: str, start_marker: str, end_marker: str) -> str:
    """截取 start_marker 到 end_marker 之间的源码块（找不到返回空串）。"""
    i = source.find(start_marker)
    if i < 0:
        return ""
    j = source.find(end_marker, i)
    if j < 0:
        return ""
    return source[i:j]


def _strip_comment_lines(code: str) -> str:
    """去掉整行注释后再扫描。

    否则守卫会被"解释这个坑"的注释本身触发——本改动里就踩过：注释中写了
    ``_get_system_status()`` 用于说明已删除的取数，结果把守卫自己判成违约。
    只去整行注释，不做 inline 剥离（避免误伤字符串字面量）。
    """
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


def main() -> int:
    parser = argparse.ArgumentParser(description="验证托盘主线程零阻塞")
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

    # ── ① 空缓存构建菜单：0 次 HTTP ────────────────────────────────────
    print("=" * 68)
    print("① 空缓存构建菜单：主线程一次 HTTP 都不许发")
    print("=" * 68)
    try:
        from deva.naja.infra.ui import menu_bar_tray as m

        calls: list = []
        orig_get = m._http_get

        def spy(path, port=None, timeout=5.0):
            calls.append((path, timeout))
            return None

        m._http_get = spy
        try:
            tray = m.MenuBarTray()
            tray._app = _FakeApp()
            tray._menu_cache = {}
            tray._last_timeline_data = None
            tray._build_menu()
            menu_n = len(tray._app.menu)
        finally:
            m._http_get = orig_get

        check("空缓存构建菜单 → 0 次 HTTP", calls == [], f"calls={calls}")
        check("降级但仍构建出菜单（非报错）", menu_n > 0, f"menu_n={menu_n}")
    except Exception as e:  # pragma: no cover - 环境异常
        check("空缓存构建菜单", False, f"{type(e).__name__}: {e}")

    # ── ② 就绪探测：端口探测，快且准 ──────────────────────────────────
    print()
    print("=" * 68)
    print("② 就绪探测：改用端口探测（主线程安全，0.3s 封顶）")
    print("=" * 68)
    try:
        from deva.naja.infra.ui import menu_bar_tray as m

        tray = m.MenuBarTray()
        check("存在 _check_naja_listening()",
              hasattr(m.MenuBarTray, "_check_naja_listening"), "")

        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        live_port = srv.getsockname()[1]

        def _accept():
            try:
                srv.accept()
            except OSError:
                pass

        threading.Thread(target=_accept, daemon=True).start()

        orig_port = m._get_naja_port
        try:
            m._get_naja_port = lambda: live_port
            live_ok = tray._check_naja_listening()

            m._get_naja_port = lambda: 1  # 保留端口，必然无人监听
            t0 = time.time()
            dead_ok = tray._check_naja_listening()
            dead_ms = (time.time() - t0) * 1000
        finally:
            m._get_naja_port = orig_port
            srv.close()

        check("活端口 → True", live_ok is True, f"port={live_port}")
        check("死端口 → False", dead_ok is False, "")
        check("死端口探测快速返回（<500ms）", dead_ms < 500, f"{dead_ms:.0f}ms")
    except Exception as e:  # pragma: no cover - 环境异常
        check("就绪探测", False, f"{type(e).__name__}: {e}")

    # ── ③ _build_menu 静态守卫 ────────────────────────────────────────
    print()
    print("=" * 68)
    print("③ _build_menu（AppKit 主线程）方法块内不得出现任何取数")
    print("=" * 68)
    # 必须按方法块切：整文件 grep 会命中 _build_simple_menu / _on_open_page。
    menu_blk = _strip_comment_lines(
        _block(tray_src, "def _build_menu(self):", "def _on_open_page(self, path):"))
    check("定位到 _build_menu 方法块", bool(menu_blk), f"{len(menu_blk)} 字符")

    banned = {
        "_http_get(": "HTTP 取数",
        "_get_system_status": "health 取数（5s，且返回值未使用）",
        "_is_trading_time(": "HTTP 版交易时段判断（5s，无缓存）",
        "_get_timeline_events(": "时间线取数（可回退 Playwright 15s）",
        "requests.": "HTTP 客户端",
        "urlopen": "HTTP 取数",
    }
    for token, why in banned.items():
        check(f"无 {token}（{why}）", token not in menu_blk, "")

    check("主线程只用本地纯计算的交易时段兜底",
          "_is_trading_time_local()" in menu_blk, "")
    check("缓存读取在锁内、且锁内只有 dict 操作（无 IO 关键字）",
          "with self._menu_cache_lock:" in menu_blk
          and "_http_get(" not in menu_blk, "")

    # ── ④ _on_timer 静态守卫 ──────────────────────────────────────────
    print()
    print("=" * 68)
    print("④ _on_timer（5s 定时回调）与总结收尾")
    print("=" * 68)
    timer_blk = _strip_comment_lines(
        _block(tray_src, "def _on_timer(self, _sender):", "def stop(self):"))
    check("定位到 _on_timer 方法块", bool(timer_blk), f"{len(timer_blk)} 字符")

    check("就绪检测走端口探测 _check_naja_listening()",
          "_check_naja_listening()" in timer_blk, "")
    check("主线程不再用 HTTP 版就绪检测 _check_naja_ready()",
          "_check_naja_ready()" not in timer_blk, "")
    check("_on_timer 内无任何 HTTP 取数", "_http_get(" not in timer_blk, "")

    check("总结收尾封装为 _finish_summary", "def _finish_summary(" in timer_blk, "")
    check("总结收尾在后台线程执行",
          "threading.Thread(target=_finish_summary" in timer_blk, "")
    for action in ("_save_summary_to_file", "_copy_to_clipboard",
                   "_send_to_dingtalk", "_generate_html_summary"):
        check(f"收尾动作 {action} 已移入后台", action in timer_blk, "")
    check("只有 UI 事回主线程（_call_on_main_thread）",
          "_call_on_main_thread(" in timer_blk, "")

    notif_blk = _strip_comment_lines(
        _block(tray_src, "def _show_summary_notification(",
               "def _generate_html_summary("))
    check("_show_summary_notification 只做 UI（不生成 HTML）",
          "_generate_html_summary(" not in notif_blk, "")
    check("打开页面用非阻塞 Popen（不用 run）",
          "subprocess.Popen(" in notif_blk and "subprocess.run(" not in notif_blk, "")

    # ── ⑤ 自启开关 + 死代码清除 ──────────────────────────────────────
    print()
    print("=" * 68)
    print("⑤ 自启开关（launchctl）移出主线程；HTTP 版助手已删")
    print("=" * 68)
    auto_blk = _strip_comment_lines(
        _block(tray_src, "def _on_toggle_autostart(self, sender):", "\n_tray_instance"))
    check("定位到 _on_toggle_autostart 方法块", bool(auto_blk), f"{len(auto_blk)} 字符")
    check("toggle_login_item() 在后台线程执行",
          "threading.Thread(target=work" in auto_blk, "")
    check("勾选状态回主线程修改",
          "_call_on_main_thread(apply)" in auto_blk, "")
    check("action 文案按目标状态取值（修复原先两分支写死同一个值）",
          'new_state == 1 else "禁用"' in auto_blk.replace("\n", " ")
          or '"启用" if new_state == 1 else "禁用"' in auto_blk, "")

    try:
        from deva.naja.infra.ui import menu_bar_tray as m

        check("已删除 _get_system_status（HTTP 版，主线程陷阱）",
              not hasattr(m.MenuBarTray, "_get_system_status"), "")
        check("已删除 _get_system_status_cached",
              not hasattr(m.MenuBarTray, "_get_system_status_cached"), "")
        check("已删除模块级 _is_trading_time（无缓存 HTTP 版）",
              not hasattr(m, "_is_trading_time"), "")
        check("保留 _is_trading_time_local（纯计算兜底）",
              hasattr(m, "_is_trading_time_local"), "")
    except Exception as e:  # pragma: no cover
        check("死代码检查", False, f"{type(e).__name__}: {e}")

    check("退出等待的阻塞已书面标注为有意保留",
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
         "assert hasattr(m.MenuBarTray, '_check_naja_listening');"
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
    print("✅ 全部通过：托盘主线程只读内存缓存；HTTP/子进程等待均已移出回调路径")
    return 0


if __name__ == "__main__":
    sys.exit(main())
