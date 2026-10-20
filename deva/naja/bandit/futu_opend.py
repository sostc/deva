"""Futu OpenD 守护：确保 11111 端口可达，不可达时把本机 OpenD 拉起来。

## 为什么需要这个模块

``FutuPortfolioSyncer.sync()`` 依赖 127.0.0.1:11111，而 OpenD 是**桌面 app**：
机器重启、用户主动退出、崩溃、系统休眠后被杀，都会让它消失。同步任务如果
只是「连不上就记一条失败」，那么账户镜像会**长期停在最后一次成功的那天**
（实测停在 6 天前），而页面上数字看着完全正常 —— 又是一次静默失效。

所以定时同步前必须先确认 OpenD 活着；死了就自己拉起来。

## 三条判据，缺一不可

1. **端口是唯一真相**：``open -a`` 返回 0 只代表 launchd 收下了请求，
   不代表进程起来了、更不代表登录成功。只认 TCP 11111 能不能连。
2. **端口通就绝不拉起**：OpenD 抢不到 11111 会退到别的端口或直接失败，
   在已运行的情况下再 ``open -a`` 只会把窗口抢到前台打扰用户。
3. **失败要冷却**：起不来通常是「需要人工登录 / 密码变了」，这类问题
   每 10 分钟重试一次只会连开一堆窗口。冷却期内只报告状态，不再拉起。

## 启动哪个

本机装了两份（共用 11111，不能同时运行）：

* ``/Applications/Futu_OpenD.app`` —— 界面版，用户日常 ``opend`` alias 用的就是它
* ``~/Applications/FutuOpenD/FutuOpenD.app`` —— 命令行版

优先界面版：它有登录态与「记住密码」，命令行版冷启动常常卡在登录、
端口通了也取不到数据。命令行版只作兜底（界面版不存在时才用）。
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORT = 11111

#: 按优先级排列的 app 路径；第一个存在的会被使用
APP_CANDIDATES: List[str] = [
    "/Applications/Futu_OpenD.app",
    os.path.expanduser("~/Applications/FutuOpenD/FutuOpenD.app"),
]

#: ``open -a`` 之后等端口就绪的上限（秒）。OpenD 冷启动 + 自动登录实测约 8~20s。
READY_TIMEOUT = float(os.environ.get("NAJA_OPEND_READY_TIMEOUT", "45") or 45)

#: 拉起失败后的冷却时间（秒）。冷却期内只报告，不再尝试拉起。
START_COOLDOWN = float(os.environ.get("NAJA_OPEND_START_COOLDOWN", "600") or 600)

#: 探活超时（秒）。本机回环，1 秒足够；失败也不该拖住调度线程。
PROBE_TIMEOUT = 1.0

_lock = threading.RLock()

# ── 进程内状态（UI / 守卫直接读）─────────────────────────────────────
_last_attempt_ts: float = 0.0
_last_error: str = ""
_last_started_app: str = ""
_last_ready_ts: float = 0.0
_attempt_count: int = 0


# ---------------------------------------------------------------- 探测


def probe(timeout: float = PROBE_TIMEOUT) -> bool:
    """TCP 连一下 11111，能连上就算活着。"""
    try:
        with socket.create_connection((HOST, PORT), timeout=timeout):
            return True
    except OSError:
        return False


def _opend_pids() -> List[int]:
    """列出 OpenD 主进程 PID（排除 CrashReporter 等附属进程）。

    只看 ``Contents/MacOS/`` 下的可执行文件：app 里还有 CrashReporter、
    Helper 之类，把它们算进来会让「进程在」永远为真，于是永远不去拉起。
    """
    try:
        out = subprocess.run(
            ["ps", "-A", "-o", "pid=,comm="],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []

    pids: List[int] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        pid_s, comm = parts
        if "Contents/MacOS/" not in comm:
            continue
        base = comm.rsplit("/", 1)[-1]
        if base in ("Futu_OpenD", "FutuOpenD"):
            try:
                pids.append(int(pid_s))
            except ValueError:
                continue
    return pids


def _pick_app() -> str:
    for path in APP_CANDIDATES:
        if os.path.isdir(path):
            return path
    return ""


def _start_app(app: str) -> str:
    """``open -a`` 启动 app。返回空串表示没报错（不代表起来了）。"""
    try:
        proc = subprocess.run(
            ["open", "-a", app],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return f"{type(e).__name__}: {e}"
    if proc.returncode != 0:
        return (proc.stderr or proc.stdout or f"open 返回 {proc.returncode}").strip()[:200]
    return ""


# ---------------------------------------------------------------- 主入口


def ensure_opend(auto_start: bool = True, timeout: Optional[float] = None) -> Dict[str, Any]:
    """确保 OpenD 可达；不可达且允许时拉起它。

    Returns:
        ``{
            "reachable": bool,        # 最终端口是否可达（唯一成功判据）
            "started": bool,          # 本次是否真的执行了 open -a
            "process_seen": bool,     # 拉起前是否已有 OpenD 进程
            "app": str,               # 使用的 app 路径（未拉起则为空）
            "waited": float,          # 等待端口就绪的秒数
            "skipped_reason": str,    # 因冷却 / 未安装而没拉起时的原因
            "error": str,             # 拉起或等待过程中的错误
        }``
    """
    global _last_attempt_ts, _last_error, _last_started_app, _last_ready_ts, _attempt_count

    timeout = READY_TIMEOUT if timeout is None else timeout
    result: Dict[str, Any] = {
        "reachable": False,
        "started": False,
        "process_seen": False,
        "app": "",
        "waited": 0.0,
        "skipped_reason": "",
        "error": "",
    }

    # 快路径：端口通 → 立刻返回，不做任何进程扫描（每 10 分钟一次，别浪费）
    if probe():
        result["reachable"] = True
        _last_ready_ts = time.time()
        return result

    with _lock:
        # 双检：拿锁期间别的线程可能已经拉起来了
        if probe():
            result["reachable"] = True
            _last_ready_ts = time.time()
            return result

        now = time.time()
        pids = _opend_pids()
        result["process_seen"] = bool(pids)

        if pids:
            # 进程在但端口不通：可能正在启动 / 正在登录。只等，不再 open。
            waited = 0.0
            deadline = now + timeout
            while time.time() < deadline:
                if probe():
                    result["reachable"] = True
                    _last_ready_ts = time.time()
                    break
                time.sleep(1.0)
                waited = time.time() - now
            result["waited"] = round(waited, 1)
            if not result["reachable"]:
                result["error"] = (
                    f"OpenD 进程存在（pid={pids[0]}）但 {HOST}:{PORT} 在 {timeout:.0f}s 内未就绪，"
                    "可能需要人工登录"
                )
                log.warning("[OpenD] %s", result["error"])
            return result

        if not auto_start:
            result["skipped_reason"] = "auto_start=False"
            return result

        app = _pick_app()
        if not app:
            result["error"] = "未找到 Futu_OpenD.app / FutuOpenD.app，无法自动启动"
            log.error("[OpenD] %s", result["error"])
            return result

        # 冷却：起不来大概率要人工干预，别每轮都开一次窗口
        since = now - _last_attempt_ts
        if _last_attempt_ts and since < START_COOLDOWN:
            result["skipped_reason"] = (
                f"冷却中（距上次拉起 {since:.0f}s < {START_COOLDOWN:.0f}s），上次错误：{_last_error or '无'}"
            )
            return result

        _last_attempt_ts = now
        _attempt_count += 1
        result["app"] = app
        _last_started_app = app

        err = _start_app(app)
        result["started"] = True
        if err:
            result["error"] = err
            _last_error = err
            log.error("[OpenD] 拉起失败（%s）: %s", app, err)
            return result

        log.warning(
            "[OpenD] %s:%d 不通且无进程，已执行 open -a %s，等待就绪…",
            HOST, PORT, os.path.basename(app),
        )
        t0 = time.time()
        while time.time() - t0 < timeout:
            if probe():
                result["reachable"] = True
                result["waited"] = round(time.time() - t0, 1)
                _last_ready_ts = time.time()
                _last_error = ""
                log.warning("[OpenD] 已就绪（等待 %.1fs）", result["waited"])
                return result
            time.sleep(1.0)

        result["waited"] = round(time.time() - t0, 1)
        result["error"] = (
            f"已拉起 {os.path.basename(app)}，但 {HOST}:{PORT} 在 {timeout:.0f}s 内仍未就绪"
            "（大概率卡在登录页，需要人工登录一次）"
        )
        _last_error = result["error"]
        log.error("[OpenD] %s", result["error"])
        return result


def status() -> Dict[str, Any]:
    """只读状态快照（不探测、不启动），给 UI / 守卫看。"""
    return {
        "reachable_last_known": bool(_last_ready_ts and (time.time() - _last_ready_ts) < 300),
        "last_ready_ts": _last_ready_ts,
        "last_attempt_ts": _last_attempt_ts,
        "last_started_app": _last_started_app,
        "attempt_count": _attempt_count,
        "last_error": _last_error,
        "cooldown": START_COOLDOWN,
        "ready_timeout": READY_TIMEOUT,
    }


def reset_for_test() -> None:
    """清空进程内状态（仅守卫使用）。"""
    global _last_attempt_ts, _last_error, _last_started_app, _last_ready_ts, _attempt_count
    with _lock:
        _last_attempt_ts = 0.0
        _last_error = ""
        _last_started_app = ""
        _last_ready_ts = 0.0
        _attempt_count = 0
