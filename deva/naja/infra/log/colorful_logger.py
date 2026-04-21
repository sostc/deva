"""Naja 统一彩色日志管理器

功能：
1. 控制台彩色输出（自动检测 TTY）
2. 日志级别颜色区分
3. 模块名前缀着色（不同模块不同颜色）
4. 内容类型智能着色（交易信号、错误、认知等）
5. 图形化边框支持

使用方式：
    from deva.naja.infra.log.colorful_logger import setup_colorful_logger, get_logger

    setup_colorful_logger()  # 在入口处调用一次
    logger = get_logger("naja.signal")
    logger.info("信号触发")
"""

import logging
import sys
import os
from typing import Optional, Dict


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


class ColorfulFormatter(logging.Formatter):
    """彩色日志格式化器 - 按模块着色"""

    def __init__(self, use_color: bool = None, show_timestamp: bool = True):
        super().__init__()
        if use_color is None:
            use_color = sys.stdout.isatty()
        self.use_color = use_color
        self.show_timestamp = show_timestamp

    def _get_module_color(self, module_name: str) -> str:
        for prefix, color in MODULE_COLORS.items():
            if module_name.startswith(prefix):
                return color
        return AnsiColors.WHITE

    def _get_level_color(self, levelname: str) -> str:
        return LEVEL_COLORS.get(levelname, AnsiColors.RESET)

    def format(self, record: logging.LogRecord) -> str:
        level_color = self._get_level_color(record.levelname)
        module_color = self._get_module_color(record.name)

        import datetime
        ts = datetime.datetime.fromtimestamp(record.created).strftime('%H:%M:%S')

        if self.use_color:
            if self.show_timestamp:
                return (
                    f"{AnsiColors.DIM}[{ts}]{AnsiColors.RESET} "
                    f"{level_color}[{record.levelname}]{AnsiColors.RESET} "
                    f"{module_color}[{record.name}]{AnsiColors.RESET} "
                    f"{record.getMessage()}"
                )
            else:
                return (
                    f"{level_color}[{record.levelname}]{AnsiColors.RESET} "
                    f"{module_color}[{record.name}]{AnsiColors.RESET} "
                    f"{record.getMessage()}"
                )
        else:
            if self.show_timestamp:
                return f"[{ts}] [{record.levelname}] [{record.name}] {record.getMessage()}"
            else:
                return f"[{record.levelname}] [{record.name}] {record.getMessage()}"


class PlainFormatter(logging.Formatter):
    """纯文本格式化器（用于文件日志或非 TTY 环境）"""

    def __init__(self, show_timestamp: bool = True):
        super().__init__()
        self.show_timestamp = show_timestamp

    def format(self, record: logging.LogRecord) -> str:
        import datetime
        ts = datetime.datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        if self.show_timestamp:
            return f"[{ts}] [{record.levelname}] [{record.name}] {record.getMessage()}"
        else:
            return f"[{record.levelname}] [{record.name}] {record.getMessage()}"


_colorful_logger_configured = False


def setup_colorful_logger(
    level: int = logging.INFO,
    force_color: bool = False,
):
    """
    设置全局彩色日志

    Args:
        level: 日志级别
        force_color: 强制启用颜色（即使非 TTY）
    """
    global _colorful_logger_configured

    use_color = sys.stdout.isatty() or force_color

    if use_color:
        formatter = ColorfulFormatter(use_color=True, show_timestamp=True)
    else:
        formatter = PlainFormatter(show_timestamp=True)

    def configure_logger(logger_name):
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.propagate = False
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    configure_logger('')
    configure_logger('deva')
    configure_logger('deva.utils')
    configure_logger('deva.utils.sqlitedict')
    configure_logger('deva.naja')
    configure_logger('dev')
    configure_logger('dev.naja')
    configure_logger('dev.utils')

    logging.getLogger('deva').propagate = False
    logging.getLogger('deva.utils').propagate = False
    logging.getLogger('deva.utils.sqlitedict').propagate = False

    _colorful_logger_configured = True


def get_logger(name: str = None) -> logging.Logger:
    """获取 logger 实例"""
    if not _colorful_logger_configured:
        setup_colorful_logger()
    if name:
        return logging.getLogger(name)
    return logging.getLogger('deva.naja')


def is_color_enabled() -> bool:
    """检查颜色是否启用"""
    return sys.stdout.isatty()


def print_banner(title: str, lines: list = None, width: int = 70, color: str = None):
    """打印带边框的横幅"""
    if color is None:
        color = AnsiColors.CYAN if is_color_enabled() else ''

    reset = AnsiColors.RESET if is_color_enabled() else ''
    bold = AnsiColors.BOLD if is_color_enabled() else ''

    border = '═' * (width - 2)

    print(f"{color}╔{border}╗{reset}")
    title_line = f"{bold}{title.center(width - 2)}{reset}"
    print(f"{color}║{reset}{title_line}{color}║{reset}")

    if lines:
        for line in lines:
            content = f" {line} ".ljust(width - 2)
            print(f"{color}║{reset} {content} {color}║{reset}")

    print(f"{color}╚{border}╝{reset}")


def print_section(title: str, color: str = None):
    """打印分隔标题"""
    if color is None:
        color = AnsiColors.MAGENTA if is_color_enabled() else ''

    reset = AnsiColors.RESET if is_color_enabled() else ''
    bold = AnsiColors.BOLD if is_color_enabled() else ''

    print(f"\n{color}{bold}{'─' * 60}{reset}")
    print(f"{color}{bold} {title}{reset}")
    print(f"{color}{bold}{'─' * 60}{reset}")


def log_exception(logger: logging.Logger, message: str, exc: Exception):
    """记录异常（带颜色）"""
    logger.error(f"{AnsiColors.RED}{message}: {exc}{AnsiColors.RESET}")


def log_success(logger: logging.Logger, message: str):
    """记录成功信息"""
    logger.info(f"{AnsiColors.GREEN}✅ {message}{AnsiColors.RESET}")


def log_warning(logger: logging.Logger, message: str):
    """记录警告信息"""
    logger.warning(f"{AnsiColors.YELLOW}⚠️ {message}{AnsiColors.RESET}")


def log_info(logger: logging.Logger, message: str):
    """记录普通信息"""
    logger.info(f"{AnsiColors.CYAN}ℹ️ {message}{AnsiColors.RESET}")
