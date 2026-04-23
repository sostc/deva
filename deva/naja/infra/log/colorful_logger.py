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


class StartupProgress:
    """启动进度可视化工具

    使用方式：
        from deva.naja.infra.log.colorful_logger import StartupProgress

        progress = StartupProgress("🚀 Naja 管理平台启动中...")
        progress.start()

        with progress.section("📦 加载组件"):
            progress.item("stock_registry", True)
            progress.item("strategy_manager", True)
            progress.item("bandit", True)

        with progress.section("📡 启动雷达"):
            progress.item("GlobalMarketScanner", True)
            progress.item("NewsFetcher", True)

        progress.done("🎉 启动完成！")
    """

    def __init__(self, title: str = None, width: int = 60):
        self.width = width
        self.title = title
        self.use_color = is_color_enabled()
        self._section_stack = []
        self._current_items = []

    def _color(self, code: str) -> str:
        return code if self.use_color else ''

    def _reset(self) -> str:
        return AnsiColors.RESET if self.use_color else ''

    def _bold(self) -> str:
        return AnsiColors.BOLD if self.use_color else ''

    def start(self):
        """打印启动标题"""
        if self.title:
            print()
            print(self._color(AnsiColors.BOLD + AnsiColors.CYAN) + "=" * self.width + self._reset())
            print(self._color(AnsiColors.BOLD + AnsiColors.CYAN) + self.title.center(self.width) + self._reset())
            print(self._color(AnsiColors.BOLD + AnsiColors.CYAN) + "=" * self.width + self._reset())
        return self

    def section(self, name: str):
        """进入一个阶段，返回 context manager """
        return _SectionContext(self, name)

    def item(self, name: str, success: bool = True, details: str = None):
        """打印一个组件项"""
        if details:
            print(f"  {self._color(AnsiColors.GREEN)}✓{self._reset()} {name:<30} {self._color(AnsiColors.DIM)}{details}{self._reset()}")
        else:
            print(f"  {self._color(AnsiColors.GREEN)}✓{self._reset()} {name}")

    def warning(self, name: str, details: str = None):
        """打印警告项"""
        if details:
            print(f"  {self._color(AnsiColors.YELLOW)}⚠{self._reset()} {name:<30} {self._color(AnsiColors.DIM)}{details}{self._reset()}")
        else:
            print(f"  {self._color(AnsiColors.YELLOW)}⚠{self._reset()} {name}")

    def error(self, name: str, details: str = None):
        """打印错误项"""
        if details:
            print(f"  {self._color(AnsiColors.RED)}✗{self._reset()} {name:<30} {self._color(AnsiColors.DIM)}{details}{self._reset()}")
        else:
            print(f"  {self._color(AnsiColors.RED)}✗{self._reset()} {name}")

    def done(self, message: str = "启动完成"):
        """打印完成信息"""
        print()
        print(self._color(AnsiColors.GREEN + self._bold()) + f"✅ {message}" + self._reset())
        print()

    def tree(self, items: list, title: str = None):
        """打印树形结构

        Args:
            items: [(name, success, details), ...] 或 [(name, success), ...]
        """
        if title:
            print()
            print(self._color(AnsiColors.BOLD) + f"  {title}" + self._reset())

        for name, *rest in items:
            success = rest[0] if rest else True
            details = rest[1] if len(rest) > 1 else None

            icon = f"{self._color(AnsiColors.GREEN)}✓{self._reset()}" if success else f"{self._color(AnsiColors.YELLOW)}⚠{self._reset()}"
            detail_str = f" {self._color(AnsiColors.DIM)}({details}){self._reset()}" if details else ""

            print(f"  {icon} {name}{detail_str}")


class _SectionContext:
    """Section context manager for StartupProgress"""

    def __init__(self, progress: StartupProgress, name: str):
        self.progress = progress
        self.name = name

    def __enter__(self):
        print()
        print(self.progress._color(AnsiColors.BOLD + AnsiColors.CYAN) + f"  {self.name}" + self.progress._reset())
        return self.progress

    def __exit__(self, *args):
        pass


def print_tree_item(name: str, success: bool = True, details: str = None, indent: int = 2):
    """打印单个树形节点"""
    use_color = is_color_enabled()
    color = AnsiColors.GREEN if use_color else ''
    reset = AnsiColors.RESET if use_color else ''

    icon = f"{color}✓{reset}" if success else f"{AnsiColors.YELLOW if use_color else ''}⚠{reset}"
    detail_str = f" {AnsiColors.DIM if use_color else ''}({details}){reset}" if details else ""

    print(f"{' ' * indent}{icon} {name}{detail_str}")


def print_progress_bar(current: int, total: int, prefix: str = '', width: int = 30):
    """打印进度条

    Args:
        current: 当前进度
        total: 总数
        prefix: 前缀文字
        width: 进度条宽度
    """
    use_color = is_color_enabled()
    percent = current / total if total > 0 else 1.0
    filled = int(width * percent)
    bar = '█' * filled + '░' * (width - filled)

    color = AnsiColors.GREEN if use_color else ''
    reset = AnsiColors.RESET if use_color else ''

    print(f"\r{prefix} [{color}{bar}{reset}] {int(percent * 100)}%", end='', flush=True)

    if current >= total:
        print()


def print_spinner(message: str, done: bool = False):
    """打印旋转动画（单行）"""
    use_color = is_color_enabled()
    chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧']
    frame = chars[int(time.time() * 10) % len(chars)]

    if done:
        print(f"\r{AnsiColors.GREEN if use_color else ''}✓{AnsiColors.RESET if use_color else ''} {message}     ", flush=True)
    else:
        print(f"\r{AnsiColors.CYAN if use_color else ''}{frame}{AnsiColors.RESET if use_color else ''} {message}", end='', flush=True)


class StartupVisualizer:
    """启动可视化器 - 统一的启动日志输出

    功能：
    1. 分阶段 Banner 显示
    2. 组件树形列表 (✓/⚠/✗)
    3. 进度条动画
    4. 单行 Spinner

    使用方式：
        from deva.naja.infra.log.colorful_logger import StartupVisualizer

        sv = StartupVisualizer()

        # 阶段1：初始化
        sv.phase("🚀 启动系统引导流程")
        sv.item("stock_registry", "✓")
        sv.item("strategy_manager", "✓")
        sv.item("bandit", "✓")

        # 阶段2：加载数据
        sv.phase("📦 加载组件")
        sv.item("datasource_manager", "✓", "6 个datasource")
        sv.item("task_manager", "✓", "12 个task")
        sv.item("strategy_manager", "✓", "17 个strategy")

        # 阶段3：启动服务
        sv.phase("🌐 启动 Web 服务器")
        sv.item("http://localhost:8080", "→")

        # 完成
        sv.done()

    """

    def __init__(self, width: int = 60):
        self.width = width
        self.use_color = is_color_enabled()

    def _c(self, code: str) -> str:
        return code if self.use_color else ''

    def _r(self) -> str:
        return AnsiColors.RESET if self.use_color else ''

    def _b(self) -> str:
        return AnsiColors.BOLD if self.use_color else ''

    def banner(self, title: str, emoji: str = None):
        """打印大标题横幅

        Args:
            title: 标题文字
            emoji: 可选的 emoji 图标
        """
        print()
        title_text = f" {emoji} {title} " if emoji else f" {title} "
        separator = "═" * self.width
        print(self._c(AnsiColors.BOLD + AnsiColors.CYAN) + separator + self._r())
        print(self._c(AnsiColors.BOLD + AnsiColors.CYAN) + title_text.center(self.width) + self._r())
        print(self._c(AnsiColors.BOLD + AnsiColors.CYAN) + separator + self._r())
        print()
        return self

    def phase(self, title: str, emoji: str = None):
        """打印阶段标题

        Args:
            title: 阶段标题
            emoji: 可选的 emoji 图标
        """
        print()
        icon = f" {emoji}" if emoji else ""
        print(self._c(AnsiColors.BOLD + AnsiColors.CYAN) + f"  {icon} {title}" + self._r())
        print(self._c(AnsiColors.DIM) + "  " + "─" * 40 + self._r())
        return self

    def item(self, name: str, status: str = "✓", detail: str = None, color: str = None):
        """打印单个组件项

        Args:
            name: 组件名称
            status: 状态图标 (✓/⚠/✗/→/...)
            detail: 可选的详细信息
            color: 自定义颜色 (默认根据 status 自动选择)
        """
        if color is None:
            if status == "✓":
                color = AnsiColors.GREEN
            elif status in ("⚠", "✗"):
                color = AnsiColors.YELLOW if status == "⚠" else AnsiColors.RED
            elif status == "→":
                color = AnsiColors.CYAN
            else:
                color = AnsiColors.WHITE

        status_str = f"{self._c(color)}{status}{self._r()}"
        detail_str = f" {self._c(AnsiColors.DIM)}{detail}{self._r()}" if detail else ""
        name_str = f"{self._c(AnsiColors.WHITE)}{name}{self._r()}"

        print(f"  {status_str} {name_str}{detail_str}")
        return self

    def items(self, items: list, emoji: str = None):
        """批量打印组件列表

        Args:
            items: [(name, status, detail), ...] 或 [(name, status), ...]
            emoji: 可选的 emoji
        """
        for item in items:
            name = item[0]
            status = item[1] if len(item) > 1 else "✓"
            detail = item[2] if len(item) > 2 else None
            self.item(name, status, detail)
        return self

    def sub_item(self, name: str, status: str = "✓", detail: str = None):
        """打印子组件项（缩进更深）"""
        if detail:
            print(f"    {self._c(AnsiColors.DIM)}├─{self._r()} {self._c(AnsiColors.WHITE)}{name}{self._r()} {self._c(AnsiColors.DIM)}({detail}){self._r()}")
        else:
            print(f"    {self._c(AnsiColors.DIM)}├─{self._r()} {self._c(AnsiColors.WHITE)}{name}{self._r()}")
        return self

    def info(self, message: str, emoji: str = None):
        """打印信息行"""
        icon = f" {emoji}" if emoji else ""
        print(f"  {self._c(AnsiColors.CYAN)}ℹ{self._r()}{icon} {self._c(AnsiColors.WHITE)}{message}{self._r()}")
        return self

    def success(self, message: str, emoji: str = None):
        """打印成功信息"""
        icon = f" {emoji}" if emoji else ""
        print(f"  {self._c(AnsiColors.GREEN)}✓{self._r()}{icon} {self._c(AnsiColors.GREEN)}{message}{self._r()}")
        return self

    def warning(self, message: str, emoji: str = None):
        """打印警告信息"""
        icon = f" {emoji}" if emoji else ""
        print(f"  {self._c(AnsiColors.YELLOW)}⚠{self._r()}{icon} {self._c(AnsiColors.YELLOW)}{message}{self._r()}")
        return self

    def error(self, message: str, emoji: str = None):
        """打印错误信息"""
        icon = f" {emoji}" if emoji else ""
        print(f"  {self._c(AnsiColors.RED)}✗{self._r()}{icon} {self._c(AnsiColors.RED)}{message}{self._r()}")
        return self

    def progress(self, current: int, total: int, label: str = None):
        """打印进度条"""
        percent = current / total if total > 0 else 1.0
        width = 24
        filled = int(width * percent)
        bar = '█' * filled + '░' * (width - filled)
        label_str = f" {label}" if label else ""

        print(f"\r  {self._c(AnsiColors.CYAN)}[{self._c(AnsiColors.GREEN)}{bar}{self._c(AnsiColors.CYAN)}]{self._r()} {int(percent * 100):3d}%{label_str}  ", end='', flush=True)
        if current >= total:
            print()
        return self

    def spinner(self, message: str):
        """打印旋转动画（需后续调用 done()）"""
        chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧']
        frame = chars[int(time.time() * 10) % len(chars)]
        print(f"\r  {self._c(AnsiColors.CYAN)}{frame}{self._r()} {self._c(AnsiColors.WHITE)}{message}{self._r()}", end='', flush=True)
        return self

    def done(self, message: str = "启动完成", emoji: str = "🎉"):
        """打印完成信息"""
        print()
        print(self._c(AnsiColors.BOLD + AnsiColors.GREEN) + f"  {emoji} {message}" + self._r())
        print()
        return self

    def section(self, title: str):
        """返回一个阶段上下文管理器"""
        return _StartupSection(self, title)


class _StartupSection:
    """StartupVisualizer 阶段上下文管理器"""

    def __init__(self, viz: StartupVisualizer, title: str):
        self.viz = viz
        self.title = title

    def __enter__(self):
        self.viz.phase(self.title)
        return self.viz

    def __exit__(self, *args):
        pass


import time

