"""验证脚本：托盘「重启服务」全流程（不依赖点菜单）。

背景
----
托盘菜单「🔄 重启服务」曾因竞态导致 Naja 整体停摆：
`_restart_tray()` 给旧服务发 SIGTERM 后只 sleep(1) 就拉起新进程，
而旧服务优雅关闭需要数秒，期间 PID 文件仍是旧 PID，新进程被
`deva/naja/__main__.py` 的 `is_running()` 判定为「已在运行」而直接退出；
托盘随后又 `quit_application()` 自杀 → 旧停、新不起、托盘没了。

本脚本直接调用修复后的 `MenuBarTray._do_restart_tray()`，把触碰
rumps 的两个方法打桩，断言：
  1. 服务换成了新 PID（旧服务确实被停掉并重启）
  2. /api/health 返回 200
  3. 没有走「启动失败」分支
  4. 托盘**保持存活**（不再调用退出）
  5. 已调度一次托盘菜单刷新
  6. 若重启前有托盘在跑，其 PID 不变（证明 NAJA_KEEP_TRAY 生效、托盘未被接管）

注意
----
必须在「干净环境」下运行。WorkBuddy 等宿主会通过 PYTHONPATH 注入
sitecustomize shim，其中 os.mkdir 的 broker 会把 EEXIST 抛成
PermissionError，导致 newspaper 导入失败。真实环境（launchd 启动）
没有这些变量，所以干净环境也更贴近生产。

用法
----
    cd <项目根>
    env -i HOME="$HOME" USER="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        /opt/homebrew/opt/python@3.13/bin/python3.13 \
        scripts/verify/verify_naja_restart.py

会重启一次正在运行的服务，约 10~60 秒。
退出码 0 = PASS，1 = FAIL。
"""
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from deva.naja.infra.runtime.daemon import get_running_pid, get_running_tray_pid  # noqa: E402
from deva.naja.infra.ui.menu_bar_tray import MenuBarTray  # noqa: E402


def health(timeout: float = 2.0):
    """探测本机 /api/health，绕开代理"""
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:8080/api/health", timeout=timeout) as r:
            return r.status
    except Exception:
        return None


def main() -> int:
    if not get_running_pid():
        print("✗ 服务未在运行，请先用 `python -m deva.naja -s start` 启动后再验证")
        return 1

    tray = object.__new__(MenuBarTray)  # 跳过 rumps 初始化，只要能调到方法即可

    quit_called = {"v": False}
    refresh_called = {"v": False}
    failed = {"msg": None}

    tray._quit_on_main_thread = lambda: quit_called.__setitem__("v", True)
    tray._notify_restart_failed = lambda msg: failed.__setitem__("msg", msg)
    # 只记录「已在主线程调度了刷新」，不真的执行（裸对象没有 _app / 缓存字段）
    tray._call_on_main_thread = lambda fn: refresh_called.__setitem__("v", True)

    old_pid = get_running_pid()
    old_tray = get_running_tray_pid()
    print(f"重启前   服务 PID={old_pid}  托盘 PID={old_tray}  health={health()}")

    t0 = time.time()
    tray._do_restart_tray()
    elapsed = time.time() - t0

    new_pid = get_running_pid()
    new_tray = get_running_tray_pid()
    new_health = health()
    print(f"重启后   服务 PID={new_pid}  托盘 PID={new_tray}  health={new_health}")
    print(f"耗时 {elapsed:.1f}s  托盘退出被调用={quit_called['v']}  "
          f"已调度刷新={refresh_called['v']}  失败通知={failed['msg']}")

    checks = {
        "旧服务已换新 PID": bool(new_pid) and new_pid != old_pid,
        "health 200": new_health == 200,
        "未走失败分支": failed["msg"] is None,
        "托盘保持存活（未退出）": not quit_called["v"],
        "已调度托盘菜单刷新": refresh_called["v"],
    }
    if old_tray:
        checks["托盘 PID 未变（keep_tray 生效）"] = new_tray == old_tray

    for name, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

    passed = all(checks.values())
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
