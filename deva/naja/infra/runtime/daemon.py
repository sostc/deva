import os
import sys
import signal
import time
import re
import fcntl
from pathlib import Path
from typing import Optional, Callable
import logging

logger = logging.getLogger(__name__)

NAJA_DIR = Path.home() / ".naja"
PID_FILE = NAJA_DIR / "naja.pid"
TRAY_PID_FILE = NAJA_DIR / "naja_tray.pid"
PORT_FILE = NAJA_DIR / "naja.port"
LOG_FILE = NAJA_DIR / "logs" / "naja.log"


def _atomic_write_pid(pid_file: Path, pid: int) -> bool:
    """原子性地写入 PID 文件，避免竞态条件"""
    try:
        NAJA_DIR.mkdir(parents=True, exist_ok=True)
        temp_file = pid_file.with_suffix(f".tmp.{os.getpid()}")
        with open(temp_file, 'w') as f:
            f.write(str(pid))
            f.flush()
            os.fsync(f.fileno())
        os.rename(temp_file, pid_file)
        return True
    except Exception as e:
        logger.error(f"原子性写入 PID 文件失败: {e}")
        try:
            temp_file.unlink(missing_ok=True)
        except:
            pass
        return False


def _safe_read_pid(pid_file: Path) -> Optional[int]:
    """安全读取 PID 文件"""
    try:
        if not pid_file.exists():
            return None
        content = pid_file.read_text().strip()
        if not content:
            return None
        return int(content)
    except (ValueError, Exception) as e:
        logger.debug(f"读取 PID 文件失败: {e}")
        return None


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
    logs_dir = NAJA_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    _check_logs_dir_size(logs_dir, warn_mb=500)


def _check_logs_dir_size(logs_dir: Path, warn_mb: int = 500):
    """检查日志目录总大小，超过阈值时打印提示。"""
    try:
        total = 0
        for p in logs_dir.iterdir():
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
        total_mb = total / (1024 * 1024)
        if total_mb >= warn_mb:
            print(
                f"⚠ 日志目录 {logs_dir} 已占用 {total_mb:.0f}MB，"
                f"超过 {warn_mb}MB 阈值，建议清理旧文件",
                file=sys.stderr,
            )
    except Exception:
        pass


def save_pid(pid: Optional[int] = None) -> bool:
    """保存当前进程 PID，确保只有一个进程在运行
    
    Args:
        pid: 要保存的 PID，默认使用当前进程 PID
    
    Returns:
        是否保存成功
    """
    if pid is None:
        pid = os.getpid()
    
    existing_pid = get_running_pid()
    if existing_pid and existing_pid != pid:
        logger.warning(f"检测到其他 Naja 进程正在运行 (PID: {existing_pid})")
        return False
    
    return _atomic_write_pid(PID_FILE, pid)


def clear_pid() -> None:
    """清除 PID 文件"""
    try:
        PID_FILE.unlink(missing_ok=True)
        logger.debug("已清除 PID 文件")
    except Exception as e:
        logger.error(f"清除 PID 文件失败: {e}")


def save_tray_pid(pid: Optional[int] = None) -> bool:
    """保存托盘进程 PID
    
    Args:
        pid: 要保存的 PID，默认使用当前进程 PID
    
    Returns:
        是否保存成功
    """
    if pid is None:
        pid = os.getpid()
    
    existing_pid = get_running_tray_pid()
    if existing_pid and existing_pid != pid:
        logger.warning(f"检测到其他托盘进程正在运行 (PID: {existing_pid})")
        return False
    
    return _atomic_write_pid(TRAY_PID_FILE, pid)


def clear_tray_pid() -> None:
    """清除托盘 PID 文件"""
    try:
        TRAY_PID_FILE.unlink(missing_ok=True)
        logger.debug("已清除托盘 PID 文件")
    except Exception as e:
        logger.error(f"清除托盘 PID 文件失败: {e}")


def get_running_pid() -> Optional[int]:
    """获取正在运行的 Naja 主进程 PID"""
    pid = _safe_read_pid(PID_FILE)
    if pid is None:
        return None
    
    try:
        os.kill(pid, 0)
        return pid
    except (ProcessLookupError, PermissionError):
        PID_FILE.unlink(missing_ok=True)
        return None


def get_running_tray_pid() -> Optional[int]:
    """获取正在运行的托盘进程 PID"""
    pid = _safe_read_pid(TRAY_PID_FILE)
    if pid is None:
        return None
    
    try:
        os.kill(pid, 0)
        return pid
    except (ProcessLookupError, PermissionError):
        TRAY_PID_FILE.unlink(missing_ok=True)
        return None

def is_tray_running() -> bool:
    return get_running_tray_pid() is not None

def stop_tray(timeout: float = 5.0) -> bool:
    """停止托盘进程"""
    pid = get_running_tray_pid()
    if not pid:
        return True

    print(f"正在停止托盘 (PID: {pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print("✓ 托盘已停止")
        clear_tray_pid()
        return True

    start = time.time()
    while time.time() - start < timeout:
        try:
            os.kill(pid, 0)
            time.sleep(0.2)
        except ProcessLookupError:
            print("✓ 托盘已停止")
            clear_tray_pid()
            return True

    try:
        os.kill(pid, signal.SIGKILL)
        print("⚠ 托盘被强制终止")
        clear_tray_pid()
    except ProcessLookupError:
        pass

    return True

def is_running() -> bool:
    return get_running_pid() is not None


def stop_service(timeout: float = 10.0) -> bool:
    # 先停止托盘
    stop_tray()
    
    pid = get_running_pid()
    if not pid:
        print("✗ Naja 未在运行")
        return False

    print(f"正在停止 Naja (PID: {pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print("✗ 进程已不存在")
        clear_pid()
        return True

    start = time.time()
    while time.time() - start < timeout:
        try:
            os.kill(pid, 0)
            time.sleep(0.2)
        except ProcessLookupError:
            print("✓ Naja 已停止")
            clear_pid()
            return True

    try:
        os.kill(pid, signal.SIGKILL)
        print("⚠ Naja 被强制终止")
        clear_pid()
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
        clear_pid()
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
