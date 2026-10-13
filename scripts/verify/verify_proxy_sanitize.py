#!/usr/bin/env python3
"""验证「启动期代理环境卫生」—— 失效的本地代理不得劫持大模型请求。

================================================================================
它解决什么问题
================================================================================

2026-10-13，托盘「一键总结」突然全部失败。日志里是：

    openai.APIConnectionError: Connection error.

排查（`~/.naja/logs/tray.log` 里的 httpx 堆栈）发现请求是**走代理**出去的，
而那个代理是 ``HTTP_PROXY=http://127.0.0.1:53631`` —— 一个随集成终端
会话生灭、当时**已无人监听**的沙箱代理。链条是：

  * 从带沙箱代理的终端执行 ``-s start`` → 当前环境含这个代理；
  * ``__main__`` 里 ``env = os.environ.copy()`` 把它复制给 Naja 与托盘子进程；
  * ``openai`` / ``httpx`` 默认 ``trust_env=True``，把它当成唯一出口；
  * 端口已死 → 所有大模型请求 ``All connection attempts failed``。

**代码本身毫无问题**，坏的是继承来的环境。

================================================================================
修法与守卫
================================================================================

``daemon.sanitize_proxy_env()``：剔除「回环地址 + 端口无人监听」的代理变量。
判据很窄 —— 只碰本机回环且确证端口不通的；用户真实的梯度代理
（Surge 6152 / Clash 7890 在监听）一律保留。

  ① **清洗行为**（离线纯函数）：死代理剔除；活代理保留；非回环不动；幂等；URL 解析
  ② **启动接入**：``main()``（所有启动路径唯一入口）与 ``start_tray.py`` 都调用清洗
  ③ **时序正确性**：清洗必须发生在 ``handle_service_command()``（其中才
     ``os.environ.copy()``）**之前**，否则清洗了个寂寞
  ④ **失败提示可自证**：连接类错误不再只显示裸的 ``Connection error.``
  ⑤ **本机环境体检**：当前进程若带着死代理，如实提示（属环境条件，不算违约）

================================================================================
用法
================================================================================

    cd <项目根>
    /Users/spark/.local/bin/python3 scripts/verify/verify_proxy_sanitize.py --strict

退出码：0 = PASS；--strict 下有违约则 1。

**只读约定**：只读源码与内存态，不写任何落盘表、不起服务。
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

_MAIN_SRC = PROJECT_ROOT / "deva/naja/__main__.py"
_TRAY_LAUNCHER_SRC = PROJECT_ROOT / "deva/naja/scripts/start_tray.py"
_TRAY_SRC = PROJECT_ROOT / "deva/naja/infra/ui/menu_bar_tray.py"
_DAEMON_SRC = PROJECT_ROOT / "deva/naja/infra/runtime/daemon.py"


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


def main() -> int:
    parser = argparse.ArgumentParser(description="验证启动期代理环境卫生")
    parser.add_argument("--strict", action="store_true", help="有违约则退出码 1")
    args = parser.parse_args()

    violations: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        if ok:
            print(f"  ✅ {name}" + (f"  [{detail}]" if detail else ""))
        else:
            violations.append(name)
            print(f"  ❌ {name}" + (f"  [{detail}]" if detail else ""))

    # ── ① 清洗行为（离线纯函数）─────────────────────────────────────────
    print("=" * 68)
    print("① 清洗行为：死代理剔除、活代理保留、非回环不动、幂等")
    print("=" * 68)
    from deva.naja.infra.runtime.daemon import _proxy_url_target, sanitize_proxy_env

    check("URL 解析：带 scheme / 省略 scheme / 无端口",
          _proxy_url_target("http://127.0.0.1:53631") == ("127.0.0.1", 53631)
          and _proxy_url_target("127.0.0.1:6152") == ("127.0.0.1", 6152)
          and _proxy_url_target("http://127.0.0.1") == ("127.0.0.1", None), "")

    dead = {"HTTP_PROXY": "http://127.0.0.1:53631", "https_proxy": "http://127.0.0.1:9"}
    removed = sanitize_proxy_env(dead)
    check("死代理（回环 + 端口无人监听）被剔除",
          set(removed) == {"HTTP_PROXY", "https_proxy"} and dead == {},
          f"removed={sorted(removed)}")

    # 起一个真监听端口模拟活代理
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    live_port = srv.getsockname()[1]
    try:
        alive = {"HTTP_PROXY": f"http://127.0.0.1:{live_port}"}
        check("活代理（Surge/Clash 在监听）保留不动",
              sanitize_proxy_env(alive) == {} and "HTTP_PROXY" in alive, "")
    finally:
        srv.close()

    remote = {"HTTPS_PROXY": "http://8.8.8.8:8080", "ALL_PROXY": "socks5://1.2.3.4:1080"}
    check("非回环代理一律尊重（不探测、不删）",
          sanitize_proxy_env(remote) == {} and len(remote) == 2, "")

    check("干净环境无副作用", sanitize_proxy_env({}) == {}, "")

    twice = {"HTTP_PROXY": "http://127.0.0.1:53631"}
    sanitize_proxy_env(twice)
    check("幂等：连跑两次结果一致", sanitize_proxy_env(twice) == {}, "")

    # ── ② 启动接入 ────────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("② 启动接入：所有启动路径的唯一入口都做了清洗")
    print("=" * 68)
    from deva.naja.infra import runtime as _runtime  # noqa: F401  确保可导入

    main_src = _read(_MAIN_SRC)
    check("daemon 公开导出 sanitize_proxy_env",
          "def sanitize_proxy_env(" in _read(_DAEMON_SRC), "")
    check("__main__ 从 daemon 导入 sanitize_proxy_env",
          "sanitize_proxy_env" in main_src.split("def handle_service_command")[0], "")

    main_body = _block(main_src, "def main():", "\nif __name__")
    check("main() 调用了 sanitize_proxy_env",
          "sanitize_proxy_env()" in main_body, "")

    launcher_src = _read(_TRAY_LAUNCHER_SRC)
    check("start_tray.py 调用了 sanitize_proxy_env（托盘进程不经过 __main__）",
          "sanitize_proxy_env()" in launcher_src, "")

    # ── ③ 时序正确性 ──────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("③ 时序：清洗必须早于 os.environ.copy()")
    print("=" * 68)
    # handle_service_command() 里才做 os.environ.copy()，而它由 main() 调用。
    # 因此 main() 函数体内 sanitize 必须出现在对 handle_service_command 的调用之前。
    i_sanitize = main_body.find("sanitize_proxy_env()")
    i_handle = main_body.find("handle_service_command()")
    check("main() 内：sanitize_proxy_env() 早于 handle_service_command()",
          i_sanitize >= 0 and i_handle >= 0 and i_sanitize < i_handle,
          f"sanitize@{i_sanitize} handle@{i_handle}")

    copy_at = main_src.find("env = os.environ.copy()")
    check("服务/托盘子进程确实基于 os.environ.copy()（意味着必须提前清洗）",
          copy_at > 0 and "handle_service_command" in main_src[:copy_at],
          f"copy@{copy_at}")

    # 托盘 launcher：清洗要在 start_tray() 之前
    i_l_sanitize = launcher_src.find("sanitize_proxy_env()")
    i_l_start = launcher_src.find("start_tray()")
    check("start_tray.py 内：清洗早于 start_tray()",
          i_l_sanitize >= 0 and i_l_start >= 0 and i_l_sanitize < i_l_start,
          f"sanitize@{i_l_sanitize} start@{i_l_start}")

    # ── ④ 失败提示可自证 ──────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("④ 失败提示：连接类错误给出可操作提示，而非裸的 Connection error.")
    print("=" * 68)
    tray_src = _read(_TRAY_SRC)
    check("_summarize_error_hint 已定义",
          "def _summarize_error_hint(" in tray_src, "")
    check("通知 subtitle 使用该提示",
          "self._summarize_error_hint(e)" in tray_src, "")
    check("「一键总结」带代理兜底重试（启动后才失效的代理在此自愈）",
          "sanitize_proxy_env" in tray_src and "清除后重试" in tray_src, "")
    try:
        from deva.naja.infra.ui.menu_bar_tray import MenuBarTray
        hint = MenuBarTray._summarize_error_hint(Exception("Connection error."))
        check("连接错误 → 提示指向网络/代理", "代理" in hint, f"hint={hint!r}")
        check("401 → 提示 API Key",
              "Key" in MenuBarTray._summarize_error_hint(Exception("401 Unauthorized")), "")
    except Exception as e:  # 环境缺 rumps/AppKit 时如实跳过
        print(f"  ⏭️  运行期提示检查跳过（{type(e).__name__}: {e}）")

    # ── ⑤ 本机环境体检 ────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("⑤ 本机环境体检（属环境条件，不计入违约）")
    print("=" * 68)
    suspect = {}
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                 "http_proxy", "https_proxy", "all_proxy"):
        raw = os.environ.get(name)
        if not raw:
            continue
        host, port = _proxy_url_target(raw)
        if host in ("127.0.0.1", "localhost", "::1") and port:
            try:
                with socket.create_connection((host, port), timeout=0.25):
                    pass
            except OSError:
                suspect[name] = raw
    if suspect:
        print(f"  ⚠️  当前进程带着失效的本地代理：{suspect}")
        print("     若在此终端启动 Naja，旧版本会把毒环境传给子进程；"
              "现在 sanitize_proxy_env() 会剔除它。")
    else:
        print("  ✅ 当前进程没有指向死端口的本地代理")

    # ── 汇总 ─────────────────────────────────────────────────────────────
    print()
    print("=" * 68)
    if violations:
        print(f"结果：{len(violations)} 项违约")
        for v in violations:
            print(f"  ❌ {v}")
        return 1 if args.strict else 0
    print("结果：全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
