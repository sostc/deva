"""
Tuning Mode Logger Filter - 调参模式日志过滤器

功能：
1. 只显示与调参相关的关键日志
2. 屏蔽无关的调试日志
3. 高亮显示重要信息

使用方式：
在启动命令中添加 --tuning-mode 参数
"""

import logging
import sys
import re
from typing import Set, List, Optional


class TuningModeFilter(logging.Filter):
    """
    调参模式日志过滤器

    只允许通过的日志：
    1. SignalTuner 相关的日志
    2. AttentionTracker 相关的日志
    3. 交易信号 (BUY/SELL)
    4. 参数调整
    5. 认知中心相关的洞察
    6. 错误和警告
    7. 关键系统状态
    """

    ALLOWED_PATTERNS = [
        r'\[SignalTuner\]',
        r'\[AttentionTracker\]',
        r'\[Cognition\].*Insight',
        r'调参器',
        r'Signal Tuner',
        r'🚀.*BUY',
        r'💰.*SELL',
        r'🎯.*signal',
        r'信号',
        r'参数调整',
        r'调整:',
        r'阈值',
        r'threshold',
        r'胜率',
        r'收益',
        r'return',
        r'win_rate',
        r'ERROR',
        r'WARNING',
        r'⚠️',
        r'❌',
        r'✅',
        r'已启动',
        r'Started',
        r'已停止',
        r'Stopped',
        r'跟踪中',
        r'观察完成',
        r'反馈',
        r'feedback',
        r'盈利',
        r'亏损',
        r'profit',
        r'loss',
        r'市场状态监控报告',
        r'风险等级',
        r'波动率',
        r'执行次数',
        r'Bandit.*持仓',
        r'已处理.*\d+/\d+',
    ]

    BLOCKED_PATTERNS = [
        r'\[Lab-Debug\]',
        r'\[PyTorchProcessor\]',
        r'\[data_quality_gate\]',
        r'\[Center\].*数据质量',
        r'\[Center\].*噪音过滤',
        r'\[ReplayScheduler\]',
        r'\[Radar-News\]',
        r'\[TradingClock\]',
        r'\[Dictionary\]',
        r'\[DataSourceEntry\]',
        r'\[AttentionSystem\]',
        r'多值解析完成',
        r'题材列表',
        r'前\d+个题材',
        r'题材数=',
        r'个股数=',
        r'加载历史行情回放',
        r'启动 Web 服务器',
        r'Naja 管理平台',
        r'系统启动完成',
        r'性能监控已启动',
        r'DBStream',
        r'StorageMonitor',
        r'加载完成',
        r'运行状态恢复',
        r'自动调优器',
        r'初始化完成',
        r'初始化:',
        r'已注册',
        r'订阅',
        r'已激活',
        r'配置已加载',
        r'加载了 \d+ 个',
        r'历史信号',
        r'加载 1478 条',
        r'回放循环开始',
        r'回放表',
        r'使用自动调优模式',
        r'Unit started',
        r'_lab_debug_log',
        r'DEBUG:',
        r'DEBUG \(0\)',
        r'cache',
        r'cached',
        r'历史缓冲',
        r'噪音过滤',
        r'清洗',
        r'queue',
        r'Queue',
        r'pending',
        r'batch',
        r'PyTorch.*MPS',
        r'PyTorch.*设备',
        r'PyTorch.*模型',
        r'PyTorchEngine',
        r'设备: Apple',
        r'使用 Apple',
    ]

    def __init__(self, name: str = ''):
        super().__init__(name)
        self.allowed = [re.compile(p, re.IGNORECASE) for p in self.ALLOWED_PATTERNS]
        self.blocked = [re.compile(p, re.IGNORECASE) for p in self.BLOCKED_PATTERNS]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()

        for pattern in self.blocked:
            if pattern.search(message):
                return False

        for pattern in self.allowed:
            if pattern.search(message):
                return True

        if record.levelno >= logging.WARNING:
            return True

        return False


class TuningModeFormatter(logging.Formatter):
    """调参模式专用格式化器"""

    COLORS = {
        'reset': '\033[0m',
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'magenta': '\033[95m',
        'cyan': '\033[96m',
        'white': '\033[97m',
        'bold': '\033[1m',
    }

    def __init__(self, use_color: bool = True):
        super().__init__()
        self.use_color = use_color and sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()

        if 'BUY' in message or '买入' in message:
            color = self.COLORS['green']
            prefix = '🚀'
        elif 'SELL' in message or '卖出' in message:
            color = self.COLORS['red']
            prefix = '💰'
        elif 'ERROR' in message or '❌' in message:
            color = self.COLORS['red']
            prefix = '❌'
        elif 'WARNING' in message or '⚠️' in message:
            color = self.COLORS['yellow']
            prefix = '⚠️'
        elif 'SignalTuner' in message or '调参' in message:
            color = self.COLORS['cyan']
            prefix = '🎛️'
        elif 'AttentionTracker' in message or '跟踪' in message:
            color = self.COLORS['blue']
            prefix = '👁️'
        elif 'Insight' in message or '认知' in message:
            color = self.COLORS['magenta']
            prefix = '🧠'
        elif '调整' in message or 'threshold' in message.lower():
            color = self.COLORS['yellow']
            prefix = '⚙️'
        elif '胜率' in message or '收益' in message or 'return' in message.lower():
            color = self.COLORS['green']
            prefix = '📊'
        else:
            color = self.COLORS['reset']
            prefix = '  '

        if self.use_color:
            return f"{color}{prefix} {message}{self.COLORS['reset']}"
        else:
            return f"{prefix} {message}"


def setup_tuning_mode_logger(logger_name: str = 'dev.naja', level: int = logging.INFO):
    """
    设置调参模式日志

    Args:
        logger_name: logger 名称
        level: 日志级别
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.addFilter(TuningModeFilter())
    console_handler.setFormatter(TuningModeFormatter())

    logger.addHandler(console_handler)

    for logger_name in ['deva.naja', 'deva.naja.attention', 'deva.naja.bandit',
                        'deva.naja.cognition', 'deva.naja.radar', 'deva.naja.strategy',
                        'deva.naja.signal', 'deva.naja.replay', 'deva.naja.common',
                        'dev.naja', 'dev']:
        sub_logger = logging.getLogger(logger_name)
        sub_logger.setLevel(level)
        for handler in sub_logger.handlers[:]:
            if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout:
                continue
            sub_logger.removeHandler(handler)
        if not sub_logger.handlers:
            sub_logger.addHandler(console_handler)
        else:
            for h in sub_logger.handlers:
                if isinstance(h, logging.StreamHandler):
                    h.addFilter(TuningModeFilter())
                    h.setFormatter(TuningModeFormatter())

    logging.getLogger().addHandler(console_handler)

    return logger


def enable_tuning_mode():
    """启用调参模式"""
    import os
    os.environ['NAJA_TUNING_MODE'] = 'true'
    setup_tuning_mode_logger()


def is_tuning_mode() -> bool:
    """检查是否为调参模式"""
    import os
    return os.environ.get('NAJA_TUNING_MODE', 'false').lower() == 'true'


class TuningModeContext:
    """调参模式上下文管理器"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.original_level = None
        self.original_handlers = None

    def __enter__(self):
        if self.enabled:
            import os
            os.environ['NAJA_TUNING_MODE'] = 'true'
            logger = logging.getLogger('dev.naja')
            self.original_level = logger.level
            self.original_handlers = logger.handlers[:]

            setup_tuning_mode_logger()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.enabled:
            import os
            os.environ.pop('NAJA_TUNING_MODE', None)
            logger = logging.getLogger('dev.naja')
            logger.setLevel(self.original_level or logging.INFO)

            for handler in logger.handlers[:]:
                logger.removeHandler(handler)

            for handler in self.original_handlers or []:
                logger.addHandler(handler)


def print_tuning_banner():
    """打印调参模式横幅"""
    banner = """
╔═══════════════════════════════════════════════════════════════╗
║                    🎛️  NAJA TUNING MODE                       ║
║                                                               ║
║  日志已过滤，只显示关键信息:                                    ║
║  • SignalTuner 调参状态                                       ║
║  • AttentionTracker 跟踪状态                                  ║
║  • 交易信号 BUY/SELL                                         ║
║  • 参数调整                                                   ║
║  • 胜率/收益统计                                              ║
║  • 错误和警告                                                 ║
║                                                               ║
║  目标: 每天10只盈利股票                                        ║
╚═══════════════════════════════════════════════════════════════╝
"""
    print(banner)
