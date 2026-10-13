#!/usr/bin/env python3
"""验证「托盘开关 → 服务启动不再自动打开浏览器」这条链路。

================================================================================
它解决什么问题
================================================================================
用户诉求：「托盘菜单里增加一个开关，勾选后不会再每次 naja 启动时都打开浏览器」。

追查后确认：打开浏览器的**不是 naja 自己的代码**，而是框架层
``deva/page_ui/server.py::PageServer.start()`` 里那句无条件的::

    os.system(f"open http://{self.host}:{self.port}/")

naja 启动时经由 ``application/web.py`` 的 ``NW("naja_webview", ...)`` 走到它，
而全仓 naja 只有这一处 ``NW(`` 调用。

这条链路的形状是「跨两个进程」：
    托盘勾选 → 写 ~/.naja/prefs.json → (重启) → 服务进程读 → 传给 PageServer
而本项目头号病理恰恰是「UI 写好了、链路没接」——所以这里必须守住**每一节**，
不能只测两端。

================================================================================
六段检查
================================================================================
  ① **PageServer 门控语义**（行为）：``open_browser=False`` 不 open；``True`` 才 open；
     且该参数是显式形参（不会漏进 ``tornado.Application`` 的 kwargs），默认 True。
  ② **偏好持久化**（行为）：缺省=开启；写后可读回；保留其它键；原子写无残留；坏文件回退默认。
  ③ **服务端决策**（行为·端到端）：``resolve_open_browser_on_start()`` 真读偏好文件。
  ④ **web.py 接线**（静态）：NW 调用确实把 open_browser 传下去，且不是写死的。
  ⑤ **托盘**（静态 + 行为）：菜单项存在、初值来自偏好、回调绑上、回落到 set_pref；
     回调真能写盘并翻转勾选；失败时勾选回滚且有可见提示。
  ⑥ **冷启动**：托盘模块可独立导入（保证新增的 prefs 顶层 import 不炸）。

================================================================================
用法
================================================================================

    cd <项目根>
    /Users/spark/.local/bin/python3 scripts/verify/verify_tray_browser_toggle.py
    /Users/spark/.local/bin/python3 scripts/verify/verify_tray_browser_toggle.py --strict

退出码：0 = PASS；--strict 下有违约则 1。

**只读约定**：只读源码与内存态；偏好全部指向临时文件，**绝不触碰** ~/.naja/prefs.json；
不起服务、不 open 任何东西（os.system 被 mock）。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import types
import unittest.mock as mock
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

_CHILD_ENV = {k: v for k, v in __import__("os").environ.items() if k != "PYTHONPATH"}

_SERVER_SRC = PROJECT_ROOT / "deva/page_ui/server.py"
_WEB_SRC = PROJECT_ROOT / "deva/naja/application/web.py"
_TRAY_SRC = PROJECT_ROOT / "deva/naja/infra/ui/menu_bar_tray.py"
_PREFS_SRC = PROJECT_ROOT / "deva/naja/infra/prefs.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _block(source: str, start_marker: str, end_marker: str) -> str:
    i = source.find(start_marker)
    if i < 0:
        return ""
    j = source.find(end_marker, i + len(start_marker))
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
    parser = argparse.ArgumentParser(description="验证托盘「启动时打开浏览器」开关链路")
    parser.add_argument("--strict", action="store_true", help="有违约则退出码 1")
    args = parser.parse_args()

    violations: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        if ok:
            print(f"  ✅ {name}" + (f"  [{detail}]" if detail else ""))
        else:
            violations.append(name)
            print(f"  ❌ {name}" + (f"  [{detail}]" if detail else ""))

    # ── ① PageServer 门控语义 ─────────────────────────────────────────
    print("=" * 68)
    print("① PageServer.start()：只有 open_browser 为真才拉起浏览器")
    print("=" * 68)
    try:
        from deva.page_ui import server as srv

        def _make(open_browser):
            obj = object.__new__(srv.PageServer)
            obj.application = types.SimpleNamespace(listen=lambda port: object())
            obj.port = 18080
            obj.host = "0.0.0.0"
            obj.open_browser = open_browser
            return obj

        with mock.patch.object(srv.os, "system") as sysm:
            _make(False).start()
            off_calls = list(sysm.call_args_list)
            sysm.reset_mock()
            _make(True).start()
            on_calls = list(sysm.call_args_list)

        check("open_browser=False → 不 open", not off_calls,
              f"意外调用 {[c.args for c in off_calls]}")
        check("open_browser=True → open 一次",
              len(on_calls) == 1 and "open http" in str(on_calls[0].args),
              f"{[c.args for c in on_calls]}")

        # 显式形参：若 open_browser 漏进 **kwargs，实例上不会有这个属性。
        s_off = srv.PageServer(name="g_off", host="127.0.0.1", port=18081,
                               start=False, open_browser=False)
        s_def = srv.PageServer(name="g_def", host="127.0.0.1", port=18082, start=False)
        check("open_browser 是显式形参（未漏进 tornado kwargs）",
              s_off.open_browser is False)
        check("默认值仍是 True（保持历史行为，不影响 admin 等调用方）",
              s_def.open_browser is True)
    except Exception as e:  # pragma: no cover - 环境异常
        check("PageServer 门控语义", False, f"{type(e).__name__}: {e}")

    # ── ② 偏好持久化 ──────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("② prefs：缺省=开启 / 可读回 / 保留其它键 / 原子写 / 坏文件回退")
    print("=" * 68)
    try:
        from deva.naja.infra import prefs

        tmpdir = Path(tempfile.mkdtemp(prefix="naja_prefs_"))
        pref_file = tmpdir / "prefs.json"

        check("prefs 模块存在", _PREFS_SRC.exists(), str(_PREFS_SRC))
        check("缺省文件时默认开启",
              prefs.get_pref("open_browser_on_start", path=pref_file) is True)
        check("set_pref 写盘成功",
              prefs.set_pref("open_browser_on_start", False, path=pref_file) is True)
        check("写后可读回 False",
              prefs.get_pref("open_browser_on_start", path=pref_file) is False)
        check("落盘内容是合法 JSON 且值正确",
              json.loads(pref_file.read_text(encoding="utf-8")).get(
                  "open_browser_on_start") is False)

        prefs.set_pref("some_other_key", "keep-me", path=pref_file)
        raw = json.loads(pref_file.read_text(encoding="utf-8"))
        check("写入新键不丢旧键",
              raw.get("open_browser_on_start") is False
              and raw.get("some_other_key") == "keep-me")
        check("无临时文件残留",
              not list(tmpdir.glob(".*tmp*")), str(list(tmpdir.iterdir())))

        pref_file.write_text("{ this is not json", encoding="utf-8")
        check("坏文件回退默认值（不抛异常）",
              prefs.get_pref("open_browser_on_start", path=pref_file) is True)
    except Exception as e:  # pragma: no cover
        check("偏好持久化", False, f"{type(e).__name__}: {e}")

    # ── ③ 服务端决策（端到端）──────────────────────────────────────────
    print()
    print("=" * 68)
    print("③ resolve_open_browser_on_start()：真读偏好文件")
    print("=" * 68)
    try:
        from deva.naja.application import web as nweb
        from deva.naja.infra import prefs

        real_file = prefs.PREFS_FILE
        tmpdir2 = Path(tempfile.mkdtemp(prefix="naja_prefs_e2e_"))
        try:
            prefs.PREFS_FILE = tmpdir2 / "prefs.json"   # 只在守卫进程内改
            check("缺省偏好 → 决策为 True",
                  nweb.resolve_open_browser_on_start() is True)
            prefs.set_pref("open_browser_on_start", False)   # 写入临时文件
            check("偏好关闭 → 决策为 False（端到端读到）",
                  nweb.resolve_open_browser_on_start() is False)
        finally:
            prefs.PREFS_FILE = real_file
    except Exception as e:  # pragma: no cover
        check("服务端决策", False, f"{type(e).__name__}: {e}")

    # ── ④ web.py 接线（静态）───────────────────────────────────────────
    print()
    print("=" * 68)
    print("④ application/web.py：把决策结果传给 NW / PageServer")
    print("=" * 68)
    web_src = _read(_WEB_SRC)
    web_code = _strip_comment_lines(web_src)
    check("定位到 web.py 源", bool(web_code), f"{len(web_code)} 字符")
    check("决策走 resolve_open_browser_on_start()（不写死）",
          "resolve_open_browser_on_start()" in web_code, "")
    check("NW(...) 传下 open_browser=",
          "open_browser=open_browser" in web_code, "")
    check("关闭时有可观测提示（日志/print，避免静默）",
          "跳过自动打开浏览器" in web_code, "")

    # ── ⑤ 托盘：菜单项 + 回调（静态 + 行为）────────────────────────────
    print()
    print("=" * 68)
    print("⑤ 托盘：菜单项 / 初值来自偏好 / 回调真写盘 / 失败可见")
    print("=" * 68)
    tray_src = _read(_TRAY_SRC)
    menu_blk = _strip_comment_lines(
        _block(tray_src, "def _build_menu(self):", "def _on_open_page(self, path):"))
    cb_blk = _strip_comment_lines(
        _block(tray_src, "def _on_toggle_open_browser(self, sender):", "\n_tray_instance"))

    check("系统子菜单含「🌐 启动时打开浏览器」项",
          "🌐 启动时打开浏览器" in menu_blk, "")
    check("菜单项初值来自 get_pref（不是写死）",
          'get_pref("open_browser_on_start"' in menu_blk, "")
    check("菜单项绑定了 self._on_toggle_open_browser",
          "self._on_toggle_open_browser" in menu_blk, "")
    check("定位到 _on_toggle_open_browser 方法块", bool(cb_blk), f"{len(cb_blk)} 字符")
    check("回调写入 set_pref(\"open_browser_on_start\", ...)",
          'set_pref("open_browser_on_start"' in cb_blk, "")
    check("回调走后台线程（不在主线程做文件 IO）",
          "threading.Thread(" in cb_blk, "")
    check("回调释放状态位（会重建菜单、重读偏好）",
          '_clear_op("open_browser")' in cb_blk, "")
    check("失败有可见提示（不能静默）",
          "设置保存失败" in cb_blk, "")

    # 行为：用一个假 rumps 隔离通知，验证回调真能写盘 ↔ 翻转勾选
    try:
        import rumps as _real_rumps  # noqa: F401
        have_rumps = True
    except Exception:
        have_rumps = False

    if have_rumps:
        fake_rumps = types.ModuleType("rumps")
        notes: list = []
        fake_rumps.notification = lambda **kw: notes.append(kw)
        saved = sys.modules.get("rumps")
        sys.modules["rumps"] = fake_rumps
        try:
            from deva.naja.infra.ui import menu_bar_tray as m

            tray = m.MenuBarTray()
            tray._initialized = True
            tray._app = None                     # 不构建菜单，只测回调逻辑
            tray._naja_ready = False
            tray._menu_cache = {}
            tray._call_on_main_thread = lambda fn: fn()

            captured: dict = {}
            real_set_pref = m.set_pref
            m.set_pref = lambda k, v: (captured.__setitem__(k, v), True)[1]

            def _wait(pred, timeout: float = 3.0) -> bool:
                end = time.time() + timeout
                while time.time() < end:
                    if pred():
                        return True
                    time.sleep(0.02)
                return bool(pred())

            try:
                # 注意：要等的是「回调的**最终效果**」（勾选翻转 + 状态位释放），
                # 不是「set_pref 被调用」——set_pref 发生在 apply() 之前，
                # 拿它当完成信号会读到中间态（本条用例最初就栽在这）。
                sender = types.SimpleNamespace(state=1)   # 当前=勾选
                tray._on_toggle_open_browser(sender)
                _wait(lambda: sender.state == 0 and tray._op_status is None)

                check("取消勾选 → 写入 False",
                      captured.get("open_browser_on_start") is False,
                      f"{captured}")
                check("勾选状态同步翻转（1→0）", sender.state == 0, f"{sender.state}")
                check("状态位已释放", tray._op_status is None, f"{tray._op_status}")
                check("成功时有通知", any("启动时打开浏览器" in str(n.get("title", ""))
                                          for n in notes), f"{notes}")

                # 失败分支：set_pref 返回 False → 勾选回滚到**原值** + 告警
                _wait(lambda: tray._op_status is None)   # 确保上一轮已彻底收尾
                notes.clear()
                m.set_pref = lambda k, v: False
                sender2 = types.SimpleNamespace(state=0)   # 原值=未勾选
                tray._on_toggle_open_browser(sender2)
                _wait(lambda: tray._op_status is None)
                check("写盘失败 → 勾选回滚到原值（0 保持 0）",
                      sender2.state == 0, f"{sender2.state}")
                check("写盘失败 → 有可见告警",
                      any("保存失败" in str(n.get("title", "")) for n in notes),
                      f"{notes}")
            finally:
                m.set_pref = real_set_pref
                _wait(lambda: tray._op_status is None)

            # 互斥：已有长任务时拒绝并提示
            notes.clear()
            tray._begin_op("restart", "🔄 重启中…")
            sender3 = types.SimpleNamespace(state=1)
            tray._on_toggle_open_browser(sender3)
            check("有长任务在进行时拒绝并提示",
                  sender3.state == 1 and tray._op_status.get("key") == "restart"
                  and any("已有任务在进行" in str(n.get("title", "")) for n in notes),
                  f"state={sender3.state} notes={notes}")
            tray._clear_op("restart")
        finally:
            if saved is not None:
                sys.modules["rumps"] = saved
            else:
                sys.modules.pop("rumps", None)
    else:
        print("  ⏭️ 跳过 ⑤ 行为用例：本环境无 rumps（静态检查已覆盖接线）")

    # ── ⑥ 冷启动 ──────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("⑥ 冷启动：托盘模块可独立导入（新增 prefs 顶层 import 不炸）")
    print("=" * 68)
    import subprocess

    cold = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r);"
         "from deva.naja.infra.ui import menu_bar_tray as m;"
         "assert hasattr(m.MenuBarTray, '_on_toggle_open_browser');"
         "from deva.naja.infra import prefs;"
         "assert prefs.DEFAULTS['open_browser_on_start'] is True;"
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
    print("✅ 全部通过：托盘开关 → 偏好文件 → 服务启动不再自动打开浏览器，链路完整")
    return 0


if __name__ == "__main__":
    sys.exit(main())
