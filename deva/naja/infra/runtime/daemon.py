import os
import sys
import signal
import time
from pathlib import Path
from typing import Optional, Callable
import logging

logger = logging.getLogger(__name__)

NAJA_DIR = Path.home() / ".naja"
PID_FILE = NAJA_DIR / "naja.pid"
PORT_FILE = NAJA_DIR / "naja.port"
LOG_FILE = NAJA_DIR / "logs" / "naja.log"


def ensure_naja_dir():
    NAJA_DIR.mkdir(parents=True, exist_ok=True)
    (NAJA_DIR / "logs").mkdir(parents=True, exist_ok=True)


def get_running_pid() -> Optional[int]:
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        if pid <= 0:
            return None
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        PID_FILE.unlink(missing_ok=True)
        return None


def is_running() -> bool:
    return get_running_pid() is not None


def stop_service(timeout: float = 10.0) -> bool:
    pid = get_running_pid()
    if not pid:
        print("✗ Naja 未在运行")
        return False

    print(f"正在停止 Naja (PID: {pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print("✗ 进程已不存在")
        PID_FILE.unlink(missing_ok=True)
        return True

    start = time.time()
    while time.time() - start < timeout:
        try:
            os.kill(pid, 0)
            time.sleep(0.2)
        except ProcessLookupError:
            print("✓ Naja 已停止")
            PID_FILE.unlink(missing_ok=True)
            return True

    try:
        os.kill(pid, signal.SIGKILL)
        print("⚠ Naja 被强制终止")
        PID_FILE.unlink(missing_ok=True)
    except ProcessLookupError:
        pass

    return True


def reload_service() -> bool:
    pid = get_running_pid()
    if not pid:
        print("✗ Naja 未在运行，无法 reload")
        return False

    print(f"正在热重启 Naja (PID: {pid})...")
    try:
        os.kill(pid, signal.SIGUSR1)
        print("✓ 热重启信号已发送")
        return True
    except ProcessLookupError:
        print("✗ 进程已不存在")
        PID_FILE.unlink(missing_ok=True)
        return False


def restart_service():
    stop_service()
    time.sleep(1)


def get_status() -> dict:
    pid = get_running_pid()
    if pid:
        return {
            "running": True,
            "pid": pid,
            "pid_file": str(PID_FILE),
            "log_file": str(LOG_FILE)
        }
    return {
        "running": False,
        "pid_file": str(PID_FILE),
        "log_file": str(LOG_FILE)
    }


def setup_reload_handler(callback: Callable[[], None]):
    def handler(signum, frame):
        logging.info("收到 SIGUSR1 信号，开始热重启...")
        try:
            callback()
        except Exception as e:
            logging.error(f"热重启失败: {e}")
        finally:
            try:
                PID_FILE.unlink(missing_ok=True)
            except Exception:
                pass
            logging.info("进程退出")
            sys.exit(0)

    signal.signal(signal.SIGUSR1, handler)


def daemonize(launch_callback: Optional[Callable[[], None]] = None):
    pass
