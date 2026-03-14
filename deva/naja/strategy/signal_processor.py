"""信号处理模块 (兼容导入)

此文件保留用于向后兼容，新代码请使用:
    from deva.naja.signal.processor import get_signal_type, get_signal_detail
"""

from ..signal.processor import (
    get_signal_type,
    get_signal_detail,
    generate_expanded_content,
    generate_signal_html,
    parse_strategy_result,
    SIGNAL_REGISTRY,
)
