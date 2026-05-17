import os
import sys
import signal
import time
import re
from pathlib import Path
from typing import Optional, Callable
import logging

logger = logging.getLogger(__name__)

NAJA_DIR = Path.home() / ".naja"
PID_FILE = NAJA_DIR / "naja.pid"
PORT_FILE = NAJA_DIR / "naja.port"
LOG_FILE = NAJA_DIR / "logs" / "naja.log"


class AnsiColors:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    DIM = '\033[2m'


MODULE_COLORS = {
    'naja.register': AnsiColors.CYAN,
    'naja.bootstrap': AnsiColors.BOLD + AnsiColors.CYAN,
    'naja.lifecycle': AnsiColors.BOLD + AnsiColors.CYAN,
    'naja.signal': AnsiColors.GREEN,
    'naja.bandit': AnsiColors.MAGENTA,
    'naja.attention': AnsiColors.BLUE,
    'naja.cognition': AnsiColors.MAGENTA,
    'naja.radar': AnsiColors.CYAN,
    'naja.market_hotspot': AnsiColors.RED,
    'naja.strategy': AnsiColors.YELLOW,
    'naja.web': AnsiColors.GREEN,
    'naja.datasource': AnsiColors.CYAN,
    'naja.replay': AnsiColors.DIM + AnsiColors.WHITE,
    'naja.lab': AnsiColors.DIM + AnsiColors.WHITE,
    'naja.tune': AnsiColors.MAGENTA,
    'naja.infra': AnsiColors.WHITE,
    'naja.tasks': AnsiColors.CYAN,
    'deva.naja': AnsiColors.WHITE,
    'deva': AnsiColors.DIM + AnsiColors.WHITE,
}


LEVEL_COLORS = {
    'DEBUG': AnsiColors.DIM,
    'INFO': AnsiColors.GREEN,
    'WARNING': AnsiColors.YELLOW,
    'ERROR': AnsiColors.RED,
    'CRITICAL': AnsiColors.BOLD + AnsiColors.RED,
}


def _get_module_color(module_name: str) -> str:
    for prefix, color in MODULE_COLORS.items():
        if module_name.startswith(prefix):
            return color
    return AnsiColors.WHITE


def _get_level_color(levelname: str) -> str:
    return LEVEL_COLORS.get(levelname, AnsiColors.RESET)


def _colorize_log_line(line: str, use_color: bool = True) -> str:
    """给日志行添加颜色"""
    if not use_color:
        return line
    
    # 匹配日志格式: [2024-05-16 10:30:45] [INFO] [module.name] message
    match = re.match(r'^\[(.*?)\] \[(.*?)\] \[(.*?)\] (.*)$', line)
    if not match:
        return line
    
    ts, level, module, message = match.groups()
    level_color = _get_level_color(level)
    module_color = _get_module_color(module)
    
    return (
        f"{AnsiColors.DIM}[{ts}]{AnsiColors.RESET} "
        f"{level_color}[{level}]{AnsiColors.RESET} "
        f"{module_color}[{module}]{AnsiColors.RESET} "
        f"{message}"
    )


def follow_log(log_file: Path, level_filter: Optional[str] = None, lines: int = 50):
    """
    跟随日志文件，实时输出新内容
    
    Args:
        log_file: 日志文件路径
        level_filter: 日志级别过滤 (DEBUG/INFO/WARNING/ERROR/CRITICAL)，None 表示不过滤
        lines: 初始显示的行数
    """
    use_color = sys.stdout.isatty()
    
    if not log_file.exists():
        print(f"✗ 日志文件不存在: {log_file}")
        return
    
    print(f"📋 跟随日志: {log_file}")
    if level_filter:
        print(f"🔍 级别过滤: {level_filter}")
    print("─" * 60)
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            # 先读取最后几行
            f.seek(0, 2)
            file_size = f.tell()
            
            # 从后往前找换行符
            if file_size > 0:
                offset = min(file_size, 4096)
                f.seek(max(0, file_size - offset))
                content = f.read()
                lines_list = content.split('\n')
                
                # 显示最后 n 行
                for line in lines_list[-lines:]:
                    if line.strip():
                        _print_log_line(line, level_filter, use_color)
            
            # 跟随新内容
            f.seek(0, 2)
            print()
            print("📡 等待新日志... (Ctrl+C 退出)")
            print("─" * 60)
            
            while True:
                line = f.readline()
                if line:
                    _print_log_line(line.rstrip('\n'), level_filter, use_color)
                else:
                    time.sleep(0.1)
    
    except KeyboardInterrupt:
        print()
        print("👋 退出日志跟随")
    except Exception as e:
        print(f"✗ 读取日志失败: {e}")


def _print_log_line(line: str, level_filter: Optional[str], use_color: bool):
    """打印单行日志，带过滤"""
    if level_filter:
        # 检查是否包含该级别
        if f'[{level_filter}]' not in line:
            return
    
    colored_line = _colorize_log_line(line, use_color)
    print(colored_line)


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
